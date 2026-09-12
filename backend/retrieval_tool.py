import logging
from typing import Optional, List

from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from backend.config import settings
from backend.data_vector_collections import RBAC_MAPPING, get_role_filter
from backend.query_router import QueryRouter

logger = logging.getLogger(__name__)


class RetrievalTool:
    def __init__(self, query_router: QueryRouter):
        self.query_router = query_router
        self.embeddings = HuggingFaceEmbeddings(model_name=settings.embed_model_id)
        self.qdrant_client: Optional[QdrantClient] = None
        
        # Authorized collections per role
        self.role_collections = {
            "employee":    ["general"],
            "finance":     ["general", "finance"],
            "engineering": ["general", "engineering"],
            "marketing":   ["general", "marketing"],
            "c_level":     ["general", "finance", "engineering", "marketing"],
        }

    def get_qdrant_client(self) -> QdrantClient:
        if self.qdrant_client is None:
            candidate_kwargs = {"path": settings.qdrant_path}

            qdrant_url = (settings.qdrant_url or "").strip()
            qdrant_api_key = (settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else "").strip()

            if qdrant_url:
                remote_kwargs = {"url": qdrant_url}
                if qdrant_api_key:
                    remote_kwargs["api_key"] = qdrant_api_key
                try:
                    remote_client = QdrantClient(**remote_kwargs)
                    remote_client.get_collections()
                    self.qdrant_client = remote_client
                    return self.qdrant_client
                except Exception as exc:
                    logger.warning("[Retrieval] Remote Qdrant at '%s' is unavailable; falling back to local path '%s': %s", qdrant_url, settings.qdrant_path, exc)

            self.qdrant_client = QdrantClient(**candidate_kwargs)
        return self.qdrant_client

    def get_vectorstore(self, collection_name: str) -> QdrantVectorStore:
        return QdrantVectorStore(
            client=self.get_qdrant_client(),
            collection_name=collection_name,
            embedding=self.embeddings,
        )

    def close(self):
        if self.qdrant_client is not None:
            self.qdrant_client.close()
            self.qdrant_client = None

    def search_collection(self, query: str, collection: str, user_role: str, k: int = 4) -> list:
        try:
            vs = self.get_vectorstore(collection)
            rbac_filter = get_role_filter(user_role)
            return vs.similarity_search(query, k=k, filter=rbac_filter)
        except Exception as e:
            logger.warning(f"[Retrieval] Failed to search collection '{collection}': {e}")
            return []

    def format_chunks(self, docs: list) -> str:
        if not docs:
            return "No relevant documents found."

        parts = []
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            source = meta.get("source_document", "Unknown")
            page = meta.get("page_number", "?")
            section = meta.get("section_title", "")
            collection = meta.get("collection", "")

            header = f"[{i}] Source: {source}, Page {page}"
            if section:
                header += f" | Section: {section}"
            if collection:
                header += f" | Collection: {collection}"

            parts.append(f"{header}\n{doc.page_content}")

        return "\n\n---\n\n".join(parts)

    def retrieve(self, query: str, user_role: str, force_route: str = None) -> str:
        # 1. Classify query with Semantic Router
        route_name = force_route if force_route else self.query_router.get_semantic_route(query)
        logger.info(f"[Retrieval] Query routed to '{route_name}' | Role: '{user_role}'")

        # 2. Check RBAC access for the route
        access = self.query_router.check_route_access(route_name, user_role)
        if not access["allowed"]:
            logger.warning(f"[Retrieval] Access denied: role='{user_role}' route='{route_name}'")
            return access["message"]

        # 3. Determine which collection(s) to search
        allowed_collections = self.role_collections.get(user_role, ["general"])

        if route_name == "cross_department":
            target_collections = allowed_collections
        elif route_name in RBAC_MAPPING:
            if route_name in allowed_collections:
                target_collections = [route_name]
            else:
                target_collections = ["general"]
        else:
            target_collections = ["general"]

        # 4. Retrieve from each target collection and combine
        all_docs = []
        for collection in target_collections:
            docs = self.search_collection(query, collection, user_role, k=3)
            all_docs.extend(docs)

        logger.info(f"[Retrieval] Retrieved {len(all_docs)} chunks from {target_collections}")

        # 5. Format and return
        return self.format_chunks(all_docs)

    def get_as_tool(self):
        @tool
        def retrieve_finbot_chunks(query: str, user_role: str, computed_route: str = "cross_department") -> str:
            """
            Retrieves relevant document chunks from Qdrant for the given query and user role.
            """
            return self.retrieve(query, user_role, force_route=computed_route)
        return retrieve_finbot_chunks
