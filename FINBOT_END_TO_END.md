# Ebratul FinBot: Website Overview and End-to-End Workflow

## 1. Ebratul FinBot কী কাজ করে?

Ebratul FinBot হলো Ebratul Technologies-এর internal AI assistant। এটি company-এর internal documents থেকে employee-এর প্রশ্নের উত্তর দেয়।

প্রধান উদ্দেশ্য:

- Company policy, finance, engineering এবং marketing document search করা
- User-এর role অনুযায়ী document access নিয়ন্ত্রণ করা
- Retrieved document-এর ভিত্তিতে AI answer তৈরি করা
- Answer-এর সাথে source document এবং page citation দেখানো
- Unauthorized department-এর sensitive information block করা
- Off-topic, harmful এবং কিছু sensitive input আটকানো
- Chat session এবং chat history রাখা
- Admin-কে user ও document manage করার সুবিধা দেওয়া

এটি সাধারণ public chatbot নয়। Ebratul FinBot-এর উত্তর internal knowledge base এবং authenticated user-এর permission-এর ওপর নির্ভর করে।

---

## 2. Technology Stack

### Backend

- Python
- FastAPI
- LangChain / LangGraph
- Groq LLM
- Hugging Face sentence-transformer embeddings
- Qdrant vector database
- SQLite checkpoint database
- JWT-based authentication

### Frontend

- Next.js
- React
- React Markdown
- CSS Modules

### Main Ports

| Service | URL |
|---|---|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| Health check | `http://localhost:8000/health` |

---

## 3. High-Level Architecture

```text
User
  |
  v
Next.js Frontend
  |
  | JWT Authorization Header
  v
FastAPI Backend
  |
  +--> Authentication
  |
  +--> Input Guardrails
  |
  +--> Semantic Query Router
  |
  +--> RBAC Permission Check
  |
  +--> Qdrant Retrieval
  |
  +--> Groq LLM
  |
  +--> Output Guardrails
  |
  v
Answer + Citations + Metadata
```

---

## 4. Application Start হলে কী হয়?

### Backend startup

Backend চালু হলে:

1. `.env` file থেকে configuration load হয়।
2. Groq API key এবং model name load হয়।
3. Embedding model memory-তে load হয়।
4. Semantic router initialize হয়।
5. Qdrant client local path অথবা configured remote URL-এর জন্য প্রস্তুত হয়।
6. SQLite checkpoint database initialize হয়।
7. FastAPI routes available হয়।

Embedding model load হওয়ার কারণে প্রথম startup কিছুটা সময় নিতে পারে।

### Frontend startup

Next.js frontend চালু হলে:

1. Login page serve হয়।
2. `AuthContext` localStorage-এর JWT token check করে।
3. Valid token থাকলে user `/chat` page-এ যায়।
4. Token না থাকলে user login page-এ থাকে।

---

## 5. Login Flow

Frontend login form থেকে username এবং password backend-এ যায়।

```text
POST /api/auth/login
```

Backend:

1. UserStore-এ username খোঁজে।
2. Password hash verify করে।
3. User role এবং admin status দেখে।
4. একটি signed JWT token তৈরি করে।
5. Token এবং user information frontend-এ ফেরত দেয়।

Frontend:

1. JWT token `localStorage`-এ `finbot_token` নামে save করে।
2. User information React auth context-এ রাখে।
3. User-কে `/chat` page-এ পাঠায়।

প্রতিটি authenticated request-এ frontend পাঠায়:

```http
Authorization: Bearer <jwt-token>
```

### Demo users

| Username | Password | Role | Access |
|---|---|---|---|
| `admin` | `admin123` | C-Level Admin | সব collection |
| `alice` | `demo123` | Employee | general |
| `bob` | `demo123` | Finance | general, finance |
| `carol` | `demo123` | Engineering | general, engineering |
| `dave` | `demo123` | Marketing | general, marketing |
| `eve` | `demo123` | C-Level | সব collection |

বর্তমান demo implementation-এ user store in-memory। তাই admin panel থেকে তৈরি user backend restart-এর পরে স্থায়ীভাবে থাকবে না। Production-এর জন্য database দরকার।

---

## 6. Chat Query End-to-End Flow

User chat input-এ প্রশ্ন লিখে Send চাপলে frontend call করে:

```http
POST /api/agent
```

Request body:

```json
{
  "query": "What is the company leave policy?",
  "session_id": "unique-session-id"
}
```

Backend JWT থেকে user role নেয়। Request body থেকে role নেয় না। এটি গুরুত্বপূর্ণ, কারণ user নিজের role fake করে অন্য department-এর data access করতে পারে না।

### Step 1: Rate limit

প্রতিটি session-এর query count check হয়। Default limit:

```text
20 queries per session
```

Limit শেষ হলে request blocked response দেয়।

### Step 2: Input guardrails

Input guardrail query check করে:

- Query off-topic কি না
- Harmful request কি না
- Sensitive personal information আছে কি না
- PII যেমন email, card বা account-related information আছে কি না

অস্বাভাবিক বা prohibited query হলে LLM-এ না পাঠিয়ে block করা হয়।

### Step 3: Semantic routing

Query semantic router দিয়ে একটি route পায়:

- `general`
- `finance`
- `engineering`
- `marketing`
- `cross_department`

উদাহরণ:

```text
"What is the revenue growth?"
       |
       v
finance
```

```text
"Show the system architecture."
       |
       v
engineering
```

### Step 4: RBAC permission check

User role-এর সাথে route compare হয়।

| Role | Allowed collections |
|---|---|
| Employee | general |
| Finance | general, finance |
| Engineering | general, engineering |
| Marketing | general, marketing |
| C-Level | general, finance, engineering, marketing |

Finance user engineering query করলে access denied হতে পারে। C-Level user সব collection access করতে পারে।

### Step 5: Qdrant vector retrieval

Internal documents আগে ingest করে ছোট ছোট chunks-এ ভাগ করা হয়।

প্রতিটি chunk-এর সাথে metadata থাকে:

- Source document
- Page number
- Collection
- Section
- Access roles
- Chunk type

User query embedding-এ convert হয়। তারপর Qdrant semantic similarity search করে সবচেয়ে relevant chunks বের করে।

Retrieval-এর সময় role filter প্রয়োগ হয়:

```text
query
  |
  +--> vector similarity
  |
  +--> metadata.access_roles filter
  |
  v
authorized document chunks
```

অর্থাৎ শুধু LLM prompt-এ permission বলা হয় না; vector retrieval layer-এই unauthorized document filter করা হয়।

### Step 6: Groq LLM answer generation

Retrieved chunks এবং user question Groq model-এ পাঠানো হয়।

LLM system instruction অনুযায়ী:

- শুধু internal retrieved information ব্যবহার করে
- নিজের training knowledge দিয়ে অনুমান না করে
- Source এবং page citation দেয়
- Access denied হলে সেটা জানায়
- Unsupported information বানিয়ে বলে না

### Step 7: Output guardrails

LLM response পাওয়ার পরে output guardrail check করে:

- Answer retrieved context-এর সাথে grounded কি না
- Citation আছে কি না
- Sensitive figure বা information unauthorizedভাবে leak করেছে কি না
- Cross-role data leak হয়েছে কি না

Problem পাওয়া গেলে answer warning বা blocked status সহ ফেরত যায়।

### Step 8: Frontend response rendering

Backend response-এ সাধারণত থাকে:

```json
{
  "answer": "Generated answer",
  "citations": [],
  "route": "finance",
  "user_role": "finance",
  "accessible_collections": ["general", "finance"],
  "guardrail_warning": null,
  "blocked": false,
  "message": "Success"
}
```

Frontend:

1. User message immediately screen-এ দেখায়।
2. Typing indicator দেখায়।
3. Assistant answer Markdown হিসেবে render করে।
4. Route badge দেখায়।
5. Citation এবং warning দেখায়।
6. Session history refresh করে।

---

## 7. Groq unavailable হলে কী হয়?

যদি Groq key invalid হয়, model unavailable হয়, network সমস্যা হয়, অথবা provider error দেয়, backend পুরো chat fail না করে retrieval fallback ব্যবহার করে।

Fallback flow:

```text
Groq request failed
       |
       v
Qdrant retrieved chunks
       |
       v
document-based fallback answer
```

তখন answer-এর শুরুতে এমন message দেখা যেতে পারে:

```text
I couldn’t reach the live Groq model, but the available internal documents suggest the following:
```

এটি indicates করে যে app-এর authentication এবং retrieval কাজ করেছে, কিন্তু live model response পাওয়া যায়নি।

`.env` পরিবর্তন করার পরে backend restart করতে হবে, কারণ configuration startup-এর সময় memory-তে load হয়।

---

## 8. Document ingestion কীভাবে কাজ করে?

Department-wise data folder ব্যবহার করা হয়:

```text
backend/data/
├── general/
├── finance/
├── engineering/
└── marketing/
```

Ingestion process:

1. Folder scan করা হয়।
2. PDF, DOCX, DOC, Markdown এবং TXT file load করা হয়।
3. Docling document parse করে।
4. Hierarchical chunker document ভাগ করে।
5. RBAC metadata যোগ করা হয়।
6. Hugging Face embedding তৈরি হয়।
7. Chunk Qdrant collection-এ save হয়।

Collection mapping:

```text
general      -> all roles
finance      -> finance, c_level
engineering  -> engineering, c_level
marketing    -> marketing, c_level
```

Local vector data সাধারণত configured `QDRANT_PATH` directory-তে থাকে।

---

## 9. Collection button কী কাজ করে?

Navbar-এ user-এর accessible collection buttons থাকে, যেমন:

- general
- finance
- engineering
- marketing

এই button static label নয়। Click করলে:

1. Chat page-এ route হয়।
2. URL-এ collection query parameter যোগ হয়।
3. Chat input automatically scoped question দিয়ে fill হয়।
4. User Send চাপলে ওই collection সম্পর্কিত question backend-এ যায়।

উদাহরণ:

```text
finance button click
       |
       v
/chat?collection=finance
       |
       v
"What information is available in the finance documents?"
```

Actual permission backend-এই validate হয়। তাই frontend button manually manipulate করলেও unauthorized access পাওয়া যায় না।

---

## 10. Chat history এবং session

প্রতিটি chat-এর একটি `session_id` থাকে।

Session-এর মাধ্যমে:

- একই conversation-এর messages আলাদা রাখা হয়
- Sidebar-এ previous session দেখানো হয়
- পুরনো session select করলে history load হয়
- প্রথম message থেকে session title তৈরি হয়

Relevant endpoints:

```http
GET /api/chat/sessions
GET /api/chat/sessions/{session_id}
```

বর্তমানে LangGraph checkpoint এবং SQLite ব্যবহার করা হচ্ছে।

---

## 11. Admin Panel

Admin user `/admin` page access করতে পারে।

Admin features:

- সব user list করা
- নতুন user create করা
- User delete করা
- User role update করা
- Role list দেখা
- Document list দেখা
- Document upload করা
- Document delete করা
- Evaluation dataset দেখা
- RAG evaluation run করা
- Latest evaluation result দেখা

প্রতিটি admin API endpoint backend-এ `_require_admin()` check করে। শুধু frontend button hide করলেই security নিশ্চিত হয় না; backend authorization-ও আছে।

---

## 12. Important API endpoints

### Authentication

```http
GET  /health
POST /api/auth/login
GET  /api/auth/me
```

### Agent এবং chat

```http
POST /api/agent
GET  /api/chat/sessions
GET  /api/chat/sessions/{session_id}
```

### Admin users

```http
GET    /api/admin/users
POST   /api/admin/users
DELETE /api/admin/users/{user_id}
PUT    /api/admin/users/{user_id}/role
GET    /api/admin/roles
```

### Admin documents

```http
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

---

## 13. Local run instructions

### Backend

```bash
cd /data/project
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Development reload mode:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd /data/project/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

### Basic verification

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"healthy"}
```

---

## 14. Current limitations and production recommendations

বর্তমান projectটি demo/assignment-friendly implementation। Production-এর আগে নিচের বিষয়গুলো improve করা উচিত:

1. In-memory UserStore-এর পরিবর্তে PostgreSQL database ব্যবহার করা।
2. Password-এর জন্য SHA-256-এর পরিবর্তে bcrypt বা Argon2 ব্যবহার করা।
3. Hardcoded JWT secret environment variable-এ রাখা।
4. JWT token localStorage-এর পরিবর্তে secure httpOnly cookie বিবেচনা করা।
5. Admin-created user permanent database-এ save করা।
6. File upload-এর content type, size এবং filename আরও strictভাবে validate করা।
7. Backend error response-এ internal exception details expose না করা।
8. Qdrant production deployment-এ authenticated remote instance ব্যবহার করা।
9. HTTPS এবং secure CORS configuration ব্যবহার করা।
10. Chat messages-এর জন্য PostgreSQL persistence যোগ করা।
11. Structured logging এবং monitoring যোগ করা।
12. Groq failure-এর জন্য retry, timeout এবং provider status monitoring যোগ করা।

---

## 15. One-line summary

Ebratul FinBot হলো একটি authenticated, role-aware, document-grounded internal AI assistant যেখানে user query প্রথমে guardrail ও routing-এর মধ্য দিয়ে যায়, তারপর RBAC-filtered Qdrant retrieval হয়, retrieved context Groq model-এ পাঠানো হয়, এবং output citation ও security guardrail pass করার পরে frontend-এ দেখানো হয়।
