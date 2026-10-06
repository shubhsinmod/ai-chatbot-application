# Sigmoss Chatbot Application Documentation

The Sigmoss Chatbot is a full-stack Retrieval-Augmented Generation (RAG) application. It acts as an intelligent, conversational assistant capable of answering user queries strictly based on the company's internal knowledge base (PDFs, Markdown profiles, and web crawls) without hallucinating.

---

## 1. System Architecture

The application is split into two independent services:

### Backend (FastAPI + Python)
- **Framework:** FastAPI (served via Uvicorn on port `8000`)
- **LLM Integration:** OpenAI Python SDK (configured to connect to Groq's high-speed inference API).
- **Embeddings:** `FastEmbed` (BAAI/bge-small-en-v1.5) for converting text into semantic vectors.
- **Vector Database:** `ChromaDB` (Local persistent storage).
- **Core Responsibilities:**
  - Exposes REST endpoints for the chatbot and the admin dashboard.
  - Handles uploading and parsing of PDFs (`PyPDF2`), HTML/Web crawling (`BeautifulSoup`), and text/markdown files.
  - Executes the RAG pipeline (vector search + prompt augmentation + LLM generation).

### Frontend (React + Vite)
- **Framework:** React 18, bootstrapped with Vite (served on port `5173`).
- **Styling:** Vanilla CSS (`App.css`, `index.css`) with responsive design.
- **Features:** 
  - Real-time chat interface mimicking modern messaging apps.
  - Interactive quick-reply buttons.
  - Markdown rendering for assistant responses (`react-markdown`).
  - Local browser storage (`localStorage`) to persist chat history across reloads.
  - Proxy configuration to route `/api/*` calls securely to the backend without CORS issues.

---

## 2. Directory Structure

```text
sigmoss-chatbot/
├── .env                # Environment variables and secrets
├── app/
│   ├── main.py         # FastAPI application, route definitions, models
│   ├── rag.py          # RAG engine (embedding, ChromaDB, OpenAI client)
│   └── profile.md      # Seed knowledge base (quick facts, support hours)
├── data/               # Persistent storage (auto-generated)
│   └── chroma/         # ChromaDB vector store files
├── frontend/
│   ├── index.html      # React entry HTML
│   ├── package.json    # Frontend dependencies
│   ├── vite.config.js  # Vite config (contains backend proxy rules)
│   └── src/
│       ├── App.jsx     # Main React Chatbot component
│       ├── App.css     # Local component styling
│       └── main.jsx    # React DOM rendering
├── static/
│   ├── widget.js       # Vanilla JS embeddable floating chat widget
│   └── demo.html       # HTML file demonstrating the widget
└── requirements.txt    # Python backend dependencies
```

---

## 3. Environment Configuration (`.env`)

The backend relies on the `.env` file for API keys and operational parameters:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Authentication key (currently set to the Groq API key). |
| `OPENAI_MODEL` | The specific model to use (e.g., `openai/gpt-oss-120b`). |
| `OPENAI_BASE_URL` | Overrides the default OpenAI endpoint (e.g., `https://api.groq.com/openai/v1`). |
| `COMPANY_NAME` | Used dynamically in the LLM System Prompt. |
| `ADMIN_TOKEN` | Secret token used to authenticate uploads to the `/api/admin` endpoints. |
| `SEED_URLS` | Comma-separated URLs the system will scrape on first boot. |
| `RATE_LIMIT_PER_MIN`| Limits the number of questions a single IP can ask per minute (DDOS protection). |

---

## 4. How the RAG Engine Works

When a user submits a question, the application executes the following sequence:

1. **Vectorization:** The user's question (e.g., "What are your products?") is passed to `FastEmbed` which converts it into a mathematical array (vector).
2. **Search:** The system queries `ChromaDB` for the top 6 text chunks in the database whose vectors most closely align mathematically with the question's vector.
3. **Prompt Assembly:** The system builds a massive hidden string (prompt). It starts with a strict instruction block (`SYSTEM`), appends the 6 factual text chunks retrieved from ChromaDB, adds the recent chat history, and finally appends the user's question.
4. **Generation:** This combined prompt is sent to the LLM (Groq). Because the prompt contains the company's facts and strict instructions to *only* use those facts, the LLM generates a highly accurate, customized response.

---

## 5. API Endpoints

### Chat API
- **`POST /api/chat`**
  - **Payload:** `{ "question": "string", "history": [ {"role": "user", "content": "..."} ] }`
  - **Response:** `{ "answer": "Markdown string...", "sources": [{"name": "...", "url": "..."}] }`
  - **Behavior:** Processes the question through the RAG engine. Protected by rate limiting. Will return `502 Bad Gateway` gracefully if the LLM provider experiences an outage.

### Admin APIs
*(Requires `x-admin-token` matching `ADMIN_TOKEN` in headers)*
- **`GET /api/admin/sources`**: Returns a list of all ingested documents and their chunk counts.
- **`POST /api/admin/upload`**: Accepts raw text or `multipart/form-data` file uploads (PDF, TXT, MD). Parses the file and ingests it into ChromaDB.
- **`DELETE /api/admin/sources/{doc_id}`**: Removes a specific document and its associated vectors from the database.
- **`POST /api/admin/crawl`**: Triggers a background web crawler to scrape and ingest a specific URL.

---

## 6. Running the Application

Both servers must be running simultaneously for the application to function.

**1. Start the Backend:**
```powershell
cd d:\Shubham\chatbot\sigmoss-chatbot\sigmoss-chatbot
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**2. Start the Frontend:**
Open a new terminal window:
```powershell
cd d:\Shubham\chatbot\sigmoss-chatbot\sigmoss-chatbot\frontend
cmd.exe /c npm run dev
```

**Accessing the UI:**
Navigate to `http://localhost:5173` in any modern web browser to interact with the chatbot.
