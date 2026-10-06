import os, threading, time, secrets
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import rag  # noqa: E402

BASE = Path(__file__).resolve().parent
STATIC = BASE.parent / "static"
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
RATE = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "30"))
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]


def _seed():
    try:
        rag.add_text("Company profile", "profile", "file", [(0, (BASE / "profile.md").read_text())])
        for url in filter(None, (u.strip() for u in os.getenv("SEED_URLS", "").split(","))):
            rag.crawl(url, MAX_PAGES)
    except Exception as e:
        print("seed error:", e)


@asynccontextmanager
async def lifespan(_):
    if rag.count() == 0:  # first start: build the knowledge base in the background
        threading.Thread(target=_seed, daemon=True).start()
    yield


app = FastAPI(title="Website Chatbot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, deque] = defaultdict(deque)


def _limit(request: Request):
    ip = (request.headers.get("x-forwarded-for") or request.client.host).split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        raise HTTPException(429, "Too many messages. Please wait a minute and try again.")
    q.append(now)


def admin(x_admin_token: str = Header(default="")):
    token = os.getenv("ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(403, "Admin is disabled: set ADMIN_TOKEN on the server.")
    if not secrets.compare_digest(x_admin_token, token):
        raise HTTPException(401, "Wrong admin token.")


class Turn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] | None = None


class CrawlIn(BaseModel):
    url: str
    max_pages: int = 30


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", dependencies=[Depends(_limit)])
def chat(body: ChatIn):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "Chatbot is not configured yet.")
    try:
        return rag.ask(body.question, [t.model_dump() for t in body.history or []])
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(502, "The assistant is unavailable right now. Please try again shortly.")


@app.get("/api/admin/sources", dependencies=[Depends(admin)])
def sources():
    return rag.list_sources()


@app.post("/api/admin/upload", dependencies=[Depends(admin)])
def upload(files: list[UploadFile] = File(...)):
    done, errors = [], []
    for f in files:
        try:
            data = f.file.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("File is too large.")
            done.append(rag.ingest_file(data, f.filename))
        except Exception as e:
            errors.append({"name": f.filename, "error": str(e)})
    return {"added": done, "errors": errors}


@app.post("/api/admin/crawl", dependencies=[Depends(admin)])
def crawl(body: CrawlIn):
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")
    pages = rag.crawl(body.url, min(body.max_pages, 100))
    return {"pages": len(pages)}


@app.delete("/api/admin/sources/{doc_id}", dependencies=[Depends(admin)])
def delete(doc_id: str):
    rag.delete_source(doc_id)
    return {"deleted": doc_id}


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/")
def demo():
    return FileResponse(STATIC / "demo.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
