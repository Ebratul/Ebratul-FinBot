# Ebratul FinBot

> A secure internal AI assistant for Ebratul Technologies that answers questions from authorized company documents.

Ebratul FinBot is a role-aware Retrieval-Augmented Generation (RAG) application. It combines FastAPI, Next.js, Groq, Hugging Face embeddings, and Qdrant to provide grounded answers while enforcing access control during document retrieval.

## What it does

- Answers questions about internal company documents
- Supports general, finance, engineering, and marketing knowledge
- Uses role-based access control (RBAC) at the vector retrieval layer
- Returns source document and page citations
- Blocks off-topic, harmful, and unauthorized requests
- Maintains chat sessions and history
- Provides an admin panel for users, documents, and evaluations
- Uses a retrieval fallback when the live Groq model is unavailable

## Architecture

```text
User
  |
  v
Next.js Frontend
  |
  | JWT Authorization
  v
FastAPI Backend
  |
  +--> Authentication
  +--> Input Guardrails
  +--> Semantic Query Routing
  +--> RBAC Permission Check
  +--> Qdrant Vector Retrieval
  +--> Groq LLM Generation
  +--> Output Guardrails
  |
  v
Grounded Answer + Citations
```

## End-to-end query flow

1. The user signs in through the Next.js frontend.
2. The FastAPI backend verifies the credentials and returns a JWT.
3. The frontend stores the token and sends it with authenticated requests.
4. The user submits a question to `POST /api/agent`.
5. Input guardrails check rate limits, off-topic requests, harmful requests, and sensitive data.
6. The semantic router classifies the question as `general`, `finance`, `engineering`, `marketing`, or `cross_department`.
7. The backend derives the user role from the JWT, not from the request body.
8. Qdrant searches only the collections allowed for that role.
9. Retrieved document chunks are sent to the Groq model with grounding and citation instructions.
10. Output guardrails check grounding, citations, and cross-role leakage.
11. The frontend renders the answer, route, warnings, citations, and session updates.

## Role access

| Role | Accessible collections |
|---|---|
| Employee | `general` |
| Finance | `general`, `finance` |
| Engineering | `general`, `engineering` |
| Marketing | `general`, `marketing` |
| C-Level | `general`, `finance`, `engineering`, `marketing` |

The access rule is enforced in Qdrant metadata filters. Hiding a button in the frontend is not the security boundary.

## Demo accounts

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | C-Level Admin |
| `alice` | `demo123` | Employee |
| `bob` | `demo123` | Finance |
| `carol` | `demo123` | Engineering |
| `dave` | `demo123` | Marketing |
| `eve` | `demo123` | C-Level |

These accounts are seeded in the current demo user store. User data is in memory, so production deployments should replace it with a persistent database.

## Technology stack

### Backend

- Python
- FastAPI
- LangChain and LangGraph
- Groq LLM
- Hugging Face sentence-transformer embeddings
- Qdrant vector store
- SQLite checkpoint storage
- JWT authentication

### Frontend

- Next.js
- React
- React Markdown
- CSS Modules

## Project structure

```text
.
├── backend/
│   ├── main.py                    # FastAPI routes
│   ├── agent.py                   # RAG and LLM orchestration
│   ├── config.py                  # Environment configuration
│   ├── user_store.py              # Demo authentication and roles
│   ├── query_router.py            # Semantic routing
│   ├── input_guardrails.py        # Input validation and blocking
│   ├── output_guardrails.py       # Grounding and leakage checks
│   ├── retrieval_tool.py          # RBAC-filtered Qdrant search
│   └── data_vector_collections.py # Document ingestion and metadata
├── frontend/
│   └── src/
│       ├── app/                   # Login, chat, and admin pages
│       ├── components/            # Navbar and shared UI
│       ├── context/               # Authentication context
│       └── lib/api.js             # Backend API client
├── qdrant_storage/                # Local vector data
├── checkpoints.sqlite             # Local chat/checkpoint data
├── FINBOT_END_TO_END.md           # Detailed workflow documentation
└── pyproject.toml
```

## Requirements

- Python 3.10+
- Node.js and npm
- A valid Groq API key
- Hugging Face access for embedding model downloads
- Local disk space for Qdrant data and embedding models

## Environment configuration

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Important settings:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL_NAME=openai/gpt-oss-20b
EMBED_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
QDRANT_PATH=/tmp/my_lang_vs
SESSION_MAX_QUERIES=20
```

Never commit real API keys or tokens to source control.

## Installation

### Backend

```bash
cd /data/project
pip install uv
uv sync
```

### Frontend

```bash
cd /data/project/frontend
npm install
```

## Run locally

Start the backend:

```bash
cd /data/project
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

For development reload:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Start the frontend in another terminal:

```bash
cd /data/project/frontend
npm run dev
```

Open the application:

```text
http://localhost:3000
```

The backend API is available at:

```text
http://localhost:8000
```

The API root returns service information. For interactive API documentation, open:

```text
http://localhost:8000/docs
```

## Vercel deployment

Deploy the Next.js frontend to Vercel separately from the FastAPI backend. The
frontend's `vercel.json` keeps Vercel focused on the Next.js application,
avoiding the backend's heavyweight machine-learning dependencies and Vercel's
500 MB serverless function limit.

In the Vercel project settings, set:

```text
Root Directory: frontend
Framework Preset: Next.js
```

Add the deployed backend URL as an environment variable:

```env
NEXT_PUBLIC_API_URL=https://your-backend-domain.example.com
```

Deploy the FastAPI service on a Python-friendly host (for example, Railway,
Render, or Fly.io) and configure its CORS origins for the Vercel frontend
domain. Do not deploy the full RAG backend as a Vercel Python function because
embedding, document-processing, and vector-search dependencies exceed the
serverless bundle limit.

## Health check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"healthy"}
```

## Document ingestion

Documents are organized by collection:

```text
backend/data/
├── general/
├── finance/
├── engineering/
└── marketing/
```

The ingestion pipeline:

1. Loads PDF, DOCX, DOC, Markdown, and TXT files.
2. Parses documents with Docling.
3. Creates hierarchical chunks.
4. Adds source, page, section, collection, and access-role metadata.
5. Generates embeddings.
6. Stores chunks in the appropriate Qdrant collection.

Run ingestion with:

```bash
cd /data/project
.venv/bin/python -m backend.data_vector_collections
```

## Main API endpoints

### Authentication

```http
GET  /health
POST /api/auth/login
GET  /api/auth/me
```

### Chat

```http
POST /api/agent
GET  /api/chat/sessions
GET  /api/chat/sessions/{session_id}
```

### Admin

```http
GET    /api/admin/users
POST   /api/admin/users
DELETE /api/admin/users/{user_id}
PUT    /api/admin/users/{user_id}/role
GET    /api/admin/roles
GET    /api/admin/documents
POST   /api/admin/documents/upload
DELETE /api/admin/documents/{collection}/{filename}
```

### Evaluation

```http
GET  /api/evaluation/dataset
POST /api/evaluation/run
GET  /api/evaluation/results
```

## Frontend features

- Login and logout
- Role-aware navigation
- Interactive collection buttons
- New chat creation
- Previous session selection
- Markdown and table rendering
- Typing indicator
- Citations and guardrail warnings
- Admin user management
- Admin document management
- RAG evaluation controls

## Groq fallback behavior

If the Groq API request fails because of an invalid key, unavailable model, timeout, or network issue, the backend returns a retrieval-based fallback answer instead of crashing:

```text
I couldn’t reach the live Groq model, but the available internal documents suggest the following:
```

After changing `.env`, restart the backend so the new configuration is loaded.

## Validation commands

```bash
cd /data/project/frontend
npm run lint
npm run build
```

## Production recommendations

The current project is suitable for a local demo and assignment environment. Before production:

1. Replace the in-memory user store with PostgreSQL.
2. Use Argon2 or bcrypt instead of plain SHA-256 password hashing.
3. Move the JWT secret into an environment variable.
4. Consider secure httpOnly cookies for authentication.
5. Persist users, chat sessions, and messages in a database.
6. Add strict upload size, file type, and filename validation.
7. Avoid returning internal exception details in API responses.
8. Use an authenticated remote Qdrant deployment.
9. Configure HTTPS and restricted CORS origins.
10. Add structured logging, monitoring, retries, and timeouts.

## Detailed documentation

For the complete Bengali/English end-to-end explanation, see:

[FINBOT_END_TO_END.md](./FINBOT_END_TO_END.md)
# Ebratul-FinBot
