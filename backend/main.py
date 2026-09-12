import os
import shutil
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from backend.agent import FinBotAgent
from backend.user_store import user_store, create_token, verify_token, ROLE_COLLECTIONS
from backend.data_vector_collections import (
    load_document, enrich_langchain_doc, add_to_vectorstore, RBAC_MAPPING,
)
from backend.evaluator_service import get_evaluator

logger = logging.getLogger(__name__)

app = FastAPI(title="Ebratul FinBot API", description="Internal AI assistant for Ebratul Technologies")

# ── CORS for NextJS frontend ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate the agent singleton
agent = FinBotAgent()

# Data directory for documents
DATA_DIR = Path(__file__).parent / "data"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _get_current_user(authorization: Optional[str] = Header(None)):
    """Extract and verify user from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def _require_admin(payload: dict):
    """Raise 403 if user is not admin."""
    if not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


# ── REQUEST / RESPONSE MODELS ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user: dict

class AgentRequest(BaseModel):
    query: str = Field(..., example="What is the company leave policy?")
    session_id: str = Field(..., example="user-123-session")

class AgentResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    route: Optional[str] = None
    user_role: str
    accessible_collections: List[str]
    guardrail_warning: Optional[str] = None
    blocked: bool
    message: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str

class UpdateRoleRequest(BaseModel):
    role: str

class DocumentInfo(BaseModel):
    filename: str
    collection: str
    size_bytes: int


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate a user and return a JWT token."""
    user = user_store.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(user)
    return {"token": token, "user": user.to_dict()}


@app.get("/api/auth/me")
async def get_current_user_info(authorization: Optional[str] = Header(None)):
    """Get the current authenticated user's info."""
    payload = _get_current_user(authorization)
    user = user_store.get_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT / CHAT ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/agent", response_model=AgentResponse)
async def call_agent(request: AgentRequest, authorization: Optional[str] = Header(None)):
    """
    Main chat endpoint. User role is derived from the JWT token, not from the request body.
    """
    payload = _get_current_user(authorization)
    user_role = payload["role"]

    try:
        result = agent.ask_finbot(
            query=request.query,
            user_role=user_role,
            session_id=request.session_id,
            user_id=payload["sub"]
        )
        return result
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/sessions")
async def get_chat_sessions(authorization: Optional[str] = Header(None)):
    payload = _get_current_user(authorization)
    try:
        sessions = agent.get_user_sessions(payload["sub"])
        return sessions
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sessions")

@app.get("/api/chat/sessions/{session_id}")
async def get_chat_session_history(session_id: str, authorization: Optional[str] = Header(None)):
    _get_current_user(authorization)
    try:
        history = agent.get_session_history(session_id)
        return history
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/users")
async def list_users(authorization: Optional[str] = Header(None)):
    """List all users (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)
    return user_store.get_all()


@app.post("/api/admin/users")
async def create_user(req: CreateUserRequest, authorization: Optional[str] = Header(None)):
    """Create a new user (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    if req.role not in ROLE_COLLECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {list(ROLE_COLLECTIONS.keys())}")

    user = user_store.create_user(req.username, req.password, req.role, req.display_name)
    if not user:
        raise HTTPException(status_code=409, detail="Username already exists")
    return user.to_dict()


@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Delete a user (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    if payload["sub"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if not user_store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@app.put("/api/admin/users/{user_id}/role")
async def update_user_role(user_id: str, req: UpdateRoleRequest, authorization: Optional[str] = Header(None)):
    """Update a user's role (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    if req.role not in ROLE_COLLECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {list(ROLE_COLLECTIONS.keys())}")

    user = user_store.update_role(user_id, req.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


@app.get("/api/admin/roles")
async def list_roles(authorization: Optional[str] = Header(None)):
    """List all available roles and their collection access."""
    payload = _get_current_user(authorization)
    _require_admin(payload)
    return ROLE_COLLECTIONS


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — DOCUMENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/documents")
async def list_documents(authorization: Optional[str] = Header(None)):
    """List all indexed documents, grouped by collection."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    documents = []
    for collection_name in RBAC_MAPPING.keys():
        collection_dir = DATA_DIR / collection_name
        if collection_dir.exists():
            for f in collection_dir.rglob("*"):
                if f.is_file() and f.suffix.lower() in [".pdf", ".docx", ".doc", ".md", ".txt"]:
                    documents.append({
                        "filename": f.name,
                        "collection": collection_name,
                        "size_bytes": f.stat().st_size,
                    })
    return documents


@app.post("/api/admin/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form(...),
    authorization: Optional[str] = Header(None),
):
    """Upload a new document into a collection and index it."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    if collection not in RBAC_MAPPING:
        raise HTTPException(status_code=400, detail=f"Invalid collection. Must be one of: {list(RBAC_MAPPING.keys())}")

    allowed_extensions = {".pdf", ".docx", ".doc", ".md", ".txt"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_extensions}")

    # Save file to data directory
    collection_dir = DATA_DIR / collection
    collection_dir.mkdir(parents=True, exist_ok=True)
    file_path = collection_dir / file.filename

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Index the document
    try:
        roles = RBAC_MAPPING[collection]
        dl_docs = load_document(str(file_path))
        enriched_docs = []
        for chunk in dl_docs:
            lc_doc = enrich_langchain_doc(
                lc_doc=chunk,
                source=str(file_path),
                collection=collection,
                access_roles=roles,
            )
            enriched_docs.append(lc_doc)

        add_to_vectorstore(enriched_docs, collection_name=collection)

        return {
            "message": f"Document '{file.filename}' uploaded and indexed into '{collection}'",
            "chunks_indexed": len(enriched_docs),
        }
    except Exception as e:
        # Clean up the file if indexing fails
        if file_path.exists():
            file_path.unlink()
        logger.error(f"Document indexing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@app.delete("/api/admin/documents/{collection}/{filename}")
async def delete_document(collection: str, filename: str, authorization: Optional[str] = Header(None)):
    """Remove a document from the collection folder."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    file_path = DATA_DIR / collection / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    file_path.unlink()
    return {"message": f"Document '{filename}' removed from '{collection}'. Re-index to update the vector store."}


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — RAGAS EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

# In-memory storage for latest evaluation results
latest_eval_results = {}

@app.get("/api/evaluation/dataset")
async def get_evaluation_dataset(authorization: Optional[str] = Header(None)):
    """Fetch the ground-truth dataset (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)
    
    evaluator = get_evaluator()
    return evaluator.load_dataset()

@app.post("/api/evaluation/run")
async def run_evaluation(sample_size: Optional[int] = None, authorization: Optional[str] = Header(None)):
    """Run the RAGAs ablation study (admin only). Long-running — runs sync in executor."""
    import asyncio
    from functools import partial

    payload = _get_current_user(authorization)
    _require_admin(payload)

    global latest_eval_results
    evaluator = get_evaluator()

    try:
        loop = asyncio.get_event_loop()
        fn = partial(evaluator.run_ablation_study, sample_size=sample_size)
        results = await loop.run_in_executor(None, fn)
        latest_eval_results = results
        return results
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

@app.get("/api/evaluation/results")
async def get_latest_results(authorization: Optional[str] = Header(None)):
    """Get the most recent evaluation results (admin only)."""
    payload = _get_current_user(authorization)
    _require_admin(payload)

    return latest_eval_results


# ── SHUTDOWN ──────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
def shutdown_event():
    agent.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
