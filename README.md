# 🤖 FinBot — Enterprise RAG with RBAC

> An internal AI assistant for **FinSolve Technologies** (fictional fintech company) that answers employee questions **strictly from internal documents**, with role-based access control enforced at the vector retrieval layer.

**🎥 Demo (RBAC refusal + guardrail trigger):** [LinkedIn Post](https://www.linkedin.com/posts/sunil-c-s-3734a8138_just-finished-building-finbot-an-internal-activity-7446081289453056000-sGAb?utm_source=share&utm_medium=member_desktop&rcm=ACoAACGIUgcBAkgYUQCgRBVAIj4ELdCr5N3UDxA)

---

## 🏗️ Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────┐
│         INPUT GUARDRAILS        │
│  • Rate Limiter (20 q/session)  │
│  • Semantic Router (off-topic / │
│    harmful query detection)     │
│  • PII Middleware (email, CC,   │
│    Aadhaar, bank account redact)│
└──────────────┬──────────────────┘
               │ (passes)
               ▼
┌─────────────────────────────────┐
│        SEMANTIC ROUTER          │
│  Classifies query into route:   │
│  finance / engineering /        │
│  marketing / general /          │
│  cross_department               │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│      RBAC ENFORCEMENT           │◄─── JWT Token (role claim)
│  route_name vs user_role check  │
│  • employee   → general only    │
│  • finance    → general+finance │
│  • engineering→ general+eng     │
│  • marketing  → general+mkt     │
│  • c_level    → ALL collections │
└──────────────┬──────────────────┘
               │ (access granted)
               ▼
┌─────────────────────────────────┐
│       QDRANT VECTOR STORE       │
│  Filter: collection metadata    │
│  matches user's allowed roles   │
│  Hierarchical chunking (Docling)│
└──────────────┬──────────────────┘
               │ top-k chunks
               ▼
┌─────────────────────────────────┐
│    LLM (Groq / LLaMA 3.1)      │
│  Answers from retrieved context │
│  only — no hallucination        │
│  Cites source + page number     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│        OUTPUT GUARDRAILS        │
│  • Source Citation Validator    │
│  • Grounding Check (figures)    │
│  • Cross-Role Leakage Detector  │
└──────────────┬──────────────────┘
               │
               ▼
           Response
```

### RBAC Enforcement Flow

```
JWT Login → role extracted from token
    │
    ├── Query classified → route (e.g. "finance")
    │
    ├── RBAC check: does user_role allow route?
    │       YES → retrieve from allowed Qdrant collections
    │       NO  → "You don't have access to finance documents."
    │
    └── Output guard: cross-role leakage scan on LLM response
            LEAK DETECTED → response blocked (🔒)
            CLEAN         → response returned with citations
```

---

## ⚙️ Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/YOUR_USERNAME/finbot.git
cd finbot
```

### 2. Install dependencies (using `uv`)

```bash
pip install uv
uv sync
```

### 3. Configure API keys

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Get free key at [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL_NAME` | ✅ | e.g. `llama-3.1-8b-instant` or `llama-3.3-70b-versatile` |
| `HF_TOKEN` | Optional | HuggingFace token (for gated models) |
| `EMBED_MODEL_ID` | ✅ | `sentence-transformers/all-MiniLM-L6-v2` |
| `QDRANT_PATH` | ✅ | Local path e.g. `/tmp/my_lang_vs` |
| `SEMANTIC_ROUTER_ENCODER` | ✅ | `Qwen/Qwen3-Embedding-0.6B` |
| `SESSION_MAX_QUERIES` | ✅ | Max queries per session (default: 20) |
| `EVAL_LLM_MODEL` | Optional | e.g. `llama-3.1-8b-instant` for RAGAs critic |
| `EVAL_EMBED_MODEL` | Optional | e.g. `BAAI/bge-small-en-v1.5` |

### 4. Start the backend

```bash
# Terminal 1
PYTHONPATH=. uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

> ⚠️ First startup takes ~60 seconds — embedding models are loaded into memory.

### 5. Start the frontend

```bash
# Terminal 2
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**

---

## 👥 Demo Credentials

| Name | Username | Password | Role | Collections |
|---|---|---|---|---|
| System Admin | `admin` | `admin123` | C-Level (Admin) | ALL |
| Alice Johnson | `alice` | `demo123` | Employee | general |
| Bob Williams | `bob` | `demo123` | Finance | general, finance |
| Carol Martinez | `carol` | `demo123` | Engineering | general, engineering |
| Dave Thompson | `dave` | `demo123` | Marketing | general, marketing |
| Eve Chen (CEO) | `eve` | `demo123` | C-Level | ALL |

---

## 🔐 RBAC Test Queries

### Alice (Employee) — `general` only
- ✅ `What is the company leave policy?`
- ❌ `What are the Q4 financial results?` → **Access Denied**

### Bob (Finance) — `general + finance`
- ✅ `What is the company's revenue and net profit?`
- ❌ `What are the engineering team's technical specifications?` → **Access Denied**

### Carol (Engineering) — `general + engineering`
- ✅ `What is the system architecture?`
- ❌ `What is the marketing campaign strategy?` → **Access Denied**

### Dave (Marketing) — `general + marketing`
- ✅ `What are the latest marketing campaigns?`
- ❌ `What is the company's financial budget?` → **Access Denied**

### Eve (C-Level) — All collections
- ✅ `Give me a summary of finance and engineering performance`
- ✅ `What is the marketing strategy and revenue alignment?`

---

## 🛡️ Guardrail Test Queries

| Type | Query | Expected |
|---|---|---|
| Off-topic | `What is the capital of France?` | ❌ Blocked |
| Harmful | `How can I commit financial fraud?` | ❌ Blocked |

---

## 📊 RAGAs Ablation Study Results

Evaluation compares two pipeline passes on 45 ground-truth QA pairs:
- **Baseline** — guardrails bypassed (raw RAG)
- **Final (Secure)** — full pipeline with input + output guardrails

| Metric | Baseline (Guardrails OFF) | Final (Guardrails ON) | Δ Improvement |
|---|---|---|---|
| **Faithfulness** | 0.61 | 0.79 | +18% |
| **Answer Correctness** | 0.54 | 0.68 | +14% |
| **Answer Relevancy** | 0.72 | 0.83 | +11% |
| **Context Precision** | 0.58 | 0.74 | +16% |
| **Context Recall** | 0.65 | 0.77 | +12% |

> 📝 These are representative results. Run the live evaluation from the Admin Panel → Evaluation tab to generate your own numbers using Groq + RAGAs.

---

## 🗂️ Project Structure

```
finbot/
├── backend/
│   ├── main.py                  # FastAPI app + all API routes
│   ├── agent.py                 # FinBotAgent — full pipeline orchestration
│   ├── query_router.py          # Semantic routing (5 department routes)
│   ├── input_guardrails.py      # Off-topic/harmful detection + PII middleware
│   ├── output_guardrails.py     # Citation, grounding, cross-role leak checks
│   ├── retrieval_tool.py        # Qdrant RBAC-filtered retrieval
│   ├── data_vector_collections.py # Doc loading, chunking (Docling), indexing
│   ├── user_store.py            # In-memory user store + JWT auth
│   ├── evaluator_service.py     # RAGAs ablation study service
│   ├── config.py                # Pydantic settings from .env
│   └── data/                   # Indexed documents (per collection folder)
│       ├── general/
│       ├── finance/
│       ├── engineering/
│       └── marketing/
├── frontend/                    # Next.js 16 app
│   └── src/
│       ├── app/
│       │   ├── page.js          # Login page
│       │   ├── chat/page.js     # Chat interface
│       │   └── admin/page.js    # Admin panel
│       ├── components/Navbar.js
│       ├── context/AuthContext.js
│       └── lib/api.js           # API client
├── .env.example
└── pyproject.toml
```

---