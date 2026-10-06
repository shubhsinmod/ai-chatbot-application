import io, os, re, uuid
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

import chromadb
import httpx
from openai import OpenAI
from bs4 import BeautifulSoup
from fastembed import TextEmbedding
from pypdf import PdfReader

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
TOP_K = int(os.getenv("TOP_K", "6"))
COMPANY = os.getenv("COMPANY_NAME", "Sigmoss Systems Pvt. Ltd.")
CHUNK, OVERLAP = 900, 150

_embedder = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=os.getenv("FASTEMBED_CACHE_PATH") or None)
_col = chromadb.PersistentClient(path=str(DATA_DIR / "chroma")).get_or_create_collection(
    "knowledge_base", metadata={"hnsw:space": "cosine"})
_llm = None

SYSTEM = f"""You are the friendly virtual assistant on the website of {COMPANY}.
Answer visitors' questions using ONLY the numbered context passages provided.
- Be concise, clear, and structure your answer well using markdown (bullet points, bold text, etc.) unless plain text is requested.
- If the user asks about our products, services, or features, make sure to list ALL of them comprehensively if multiple are mentioned in the context, rather than just highlighting one.
- If the answer is not in the context, say you don't have that information and suggest using the Contact section or "Schedule a Demo" on the website. Never invent prices, phone numbers, emails, customers or features.
- If asked something unrelated to {COMPANY}, politely say you can only help with questions about the company, its products and services.
- Never mention "context" or "passages". Do NOT include inline citations, reference numbers (like "[1]"), or source names in your answer UNLESS the user explicitly asks you where the information came from."""


def _client():
    global _llm
    if _llm is None:
        _llm = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL") or None)
    return _llm


def _embed(texts):
    return [v.tolist() for v in _embedder.embed(texts)]


def _chunks(text):
    text = " ".join(text.split())
    start = 0
    while start < len(text):
        end = min(start + CHUNK, len(text))
        if end < len(text):
            cut = text.rfind(". ", start + CHUNK // 2, end)
            end = cut + 1 if cut != -1 else end
        piece = text[start:end].strip()
        if piece:
            yield piece
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)


def add_text(name: str, source: str, kind: str, pages: list[tuple[int, str]]) -> dict:
    """Index text. Re-indexing the same source replaces the old version."""
    _col.delete(where={"source": source})
    doc_id = uuid.uuid4().hex[:12]
    ids, docs, metas = [], [], []
    for page, text in pages:
        for piece in _chunks(text):
            ids.append(f"{doc_id}:{len(ids)}")
            docs.append(piece)
            metas.append({"doc_id": doc_id, "name": name, "source": source, "kind": kind, "page": page})
    if not docs:
        raise ValueError("No extractable text found (scanned PDF?).")
    for i in range(0, len(docs), 64):
        _col.add(ids=ids[i:i+64], documents=docs[i:i+64], metadatas=metas[i:i+64],
                 embeddings=_embed(docs[i:i+64]))
    return {"doc_id": doc_id, "name": name, "kind": kind, "chunks": len(docs)}


def ingest_file(data: bytes, filename: str) -> dict:
    low = filename.lower()
    if low.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        pages = [(i, p.extract_text() or "") for i, p in enumerate(reader.pages, 1)]
    elif low.endswith((".txt", ".md")):
        pages = [(0, data.decode("utf-8", errors="ignore"))]
    else:
        raise ValueError("Supported files: PDF, TXT, MD.")
    return add_text(filename, f"file:{filename}", "file", pages)


_NOISE = re.compile(r"lorem ipsum|type your keyword", re.I)


def _html_to_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "iframe", "svg", "form"]):
        t.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        s = el.get_text(" ", strip=True)
        if len(s) > 2 and not _NOISE.search(s) and (not lines or lines[-1] != s):
            lines.append(s)
    return title, "\n".join(lines), soup


def crawl(start_url: str, max_pages: int = 30) -> list[dict]:
    host = urlparse(start_url).netloc
    queue, seen, out = [start_url], set(), []
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "KnowledgeBot/1.0"}) as http:
        while queue and len(seen) < max_pages:
            url = urldefrag(queue.pop(0))[0]
            if url in seen:
                continue
            seen.add(url)
            try:
                r = http.get(url)
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                    continue
                title, text, soup = _html_to_text(r.text)
                if text:
                    out.append(add_text(title or url, url, "web", [(0, text)]))
                for a in soup.find_all("a", href=True):
                    nxt = urldefrag(urljoin(url, a["href"]))[0]
                    p = urlparse(nxt)
                    if p.netloc == host and p.scheme in ("http", "https") and nxt not in seen \
                            and not re.search(r"\.(jpg|jpeg|png|gif|svg|zip|css|js|pdf)$", p.path, re.I):
                        queue.append(nxt)
            except Exception as e:  # keep crawling on individual failures
                print("crawl error", url, e)
    return out


def list_sources():
    got = _col.get(include=["metadatas"])
    out = {}
    for m in got["metadatas"]:
        d = out.setdefault(m["doc_id"], {"doc_id": m["doc_id"], "name": m["name"], "source": m["source"],
                                         "kind": m["kind"], "chunks": 0})
        d["chunks"] += 1
    return sorted(out.values(), key=lambda d: (d["kind"], d["name"].lower()))


def delete_source(doc_id: str):
    _col.delete(where={"doc_id": doc_id})


def count() -> int:
    return _col.count()


def ask(question: str, history: list[dict] | None = None) -> dict:
    res = _col.query(query_embeddings=_embed([question]), n_results=TOP_K, include=["documents", "metadatas"])
    hits = list(zip(res["documents"][0], res["metadatas"][0])) if res and res.get("documents") and res.get("metadatas") else []
    context = "\n\n".join(f"[{i}] [Source Type: {m['kind'].upper()}, Source Name: {m['name']}]\n{d}" for i, (d, m) in enumerate(hits, 1)) or "(empty)"
    clean = [{"role": h["role"], "content": str(h["content"])[:1500]} for h in (history or [])[-6:]
             if h.get("role") in ("user", "assistant")]
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    messages = [{"role": "system", "content": SYSTEM}, *clean, {"role": "user", "content": f"Context:\n{context}\n\nVisitor question: {question}"}]
    msg = _client().chat.completions.create(model=MODEL, max_tokens=700, messages=messages)
    
    if not msg or not msg.choices or not msg.choices[0].message or not msg.choices[0].message.content:
        answer = "I'm sorry, I couldn't generate a response at this time. Please try asking in a different way."
    else:
        answer = msg.choices[0].message.content.strip()
    seen, sources = set(), []
    for _, m in hits[:3]:
        if m["name"] not in seen:
            seen.add(m["name"])
            sources.append({"name": m["name"], "url": m["source"] if m["kind"] == "web" else None})
    return {"answer": answer, "sources": sources}
