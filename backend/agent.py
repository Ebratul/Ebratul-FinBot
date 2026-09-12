import logging
import re
import sqlite3

from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_groq import ChatGroq
from langchain.agents import create_agent

from backend.config import settings
from backend.input_guardrails import InputGuardrails
from backend.output_guardrails import OutputGuardrails
from backend.query_router import QueryRouter
from backend.retrieval_tool import RetrievalTool
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _extract_citations(tool_messages: list) -> list:
    """
    Parses citation metadata from the formatted chunk headers produced by
    RetrievalTool.format_chunks(), e.g.:
        [1] Source: report.pdf, Page 4 | Section: Revenue | Collection: finance
    Returns a list of dicts: {source, page, section, collection}
    """
    import re
    citations = []
    seen = set()
    pattern = re.compile(
        r"\[\d+\]\s+Source:\s+(?P<source>[^,]+),\s+Page\s+(?P<page>[^|\n]+)"
        r"(?:\s*\|\s+Section:\s+(?P<section>[^|\n]+))?"
        r"(?:\s*\|\s+Collection:\s+(?P<collection>[^|\n]+))?",
        re.IGNORECASE,
    )
    for msg in tool_messages:
        content = getattr(msg, "content", "")
        for m in pattern.finditer(content):
            key = (m.group("source").strip(), m.group("page").strip())
            if key not in seen:
                seen.add(key)
                citations.append({
                    "source": m.group("source").strip(),
                    "page": m.group("page").strip(),
                    "section": (m.group("section") or "").strip(),
                    "collection": (m.group("collection") or "").strip(),
                })
    return citations

class FinBotAgent:
    def __init__(self):
        self.db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(self.db_conn)
        self.checkpointer.setup()
        
        self.db_conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db_conn.commit()

        self.config = settings
        self.query_router = QueryRouter()
        self.input_guardrails = InputGuardrails()
        self.output_guardrails = OutputGuardrails()
        self.retrieval_tool_instance = RetrievalTool(self.query_router)
        
        self.llm = ChatGroq(
            api_key=self.config.groq_api_key.get_secret_value(),
            model=self.config.groq_model_name,
            temperature=0,
        )
        
        self.tools = [self.retrieval_tool_instance.get_as_tool()]
        
        self.system_message = """You are Ebratul FinBot, an internal AI assistant for Ebratul Technologies.
You answer employee questions accurately using ONLY information from the company's internal documents.

Rules:
- Use the retrieve_finbot_chunks tool to fetch relevant information before answering.
- ALWAYS cite the source document and page number at the very bottom of your final answer using a markdown blockquote (e.g. "> Source: report.pdf, Page 4").
- Do NOT speculate, hallucinate, or use your own training knowledge.
- If the tool returns an access denied message, politely inform the user they don't have access.
- If no relevant information is found, say so clearly.
- You must exactly pass the provided user_role and computed_route values into the retrieval tool."""

    def _build_fallback_answer(self, query: str, user_role: str, route: str) -> tuple[str, list, list, str]:
        """Fallback response used when the configured LLM provider is unavailable."""
        retrieved_text = self.retrieval_tool_instance.retrieve(query, user_role, force_route=route)
        if "No relevant documents found." in retrieved_text or "Access denied" in retrieved_text:
            answer = "I couldn’t find relevant internal documentation for that question, or your role does not have access to the requested information."
            return answer, [], [], retrieved_text

        blocks = [part.strip() for part in retrieved_text.split("\n\n---\n\n") if part.strip()]
        summary_parts = []
        citations = []
        for block in blocks[:2]:
            header, _, body = block.partition("\n")
            summary_parts.append(body.strip())
            match = re.search(r"Source:\s*(.+?),\s*Page\s*(.+?)(?:\s*\|\s*Section:\s*(.+?))?(?:\s*\|\s*Collection:\s*(.+?))?$", header)
            if match:
                citations.append({
                    "source": match.group(1).strip(),
                    "page": match.group(2).strip(),
                    "section": (match.group(3) or "").strip(),
                    "collection": (match.group(4) or "").strip(),
                })

        if summary_parts:
            answer = "I couldn’t reach the live Groq model, but the available internal documents suggest the following:\n\n" + "\n\n".join(summary_parts[:2])
        else:
            answer = "I couldn’t reach the live Groq model, but the retrieval layer did return relevant internal documents for this request."

        return answer, citations, summary_parts, retrieved_text

    def ask_finbot(self, query: str, user_role: str, session_id: str, bypass_guardrails: bool = False, user_id: str = None) -> dict:
        """
        Full FinBot query pipeline with input and output guardrails.
        """
        # ── Step 1: Rate Limiting ──────────────────────────────────────────────────
        if not bypass_guardrails:
            rate_ok, rate_msg = self.input_guardrails.check_rate_limit(session_id)
            if not rate_ok:
                logger.warning(f"[Agent] Rate limit hit for session '{session_id}'")
                return {
                    "answer": rate_msg,
                    "route": None,
                    "guardrail_warning": None,
                    "blocked": True,
                    "accessible_collections": self.retrieval_tool_instance.role_collections.get(user_role, ["general"]),
                    "user_role": user_role,
                    "message": "Rate limit exceeded."
                }

            # ── Step 1.5: Early Input Guardrails (Semantic Routing) ────────────────────
            route_result = self.input_guardrails.run_semantic_guardrail(query)
            if route_result and route_result.name in ["off_topic", "potentially_harmful"]:
                # Use a higher threshold of 0.78 for the Qwen model to prevent false positives
                if route_result.similarity_score > 0.78:
                    logger.warning(f"[Agent] Early block ({route_result.name}) for session '{session_id}' with score {route_result.similarity_score}")
                    return {
                        "answer": "❌ I cannot help with that request.",
                        "route": route_result.name,
                        "guardrail_warning": None,
                        "blocked": True,
                        "accessible_collections": self.retrieval_tool_instance.role_collections.get(user_role, ["general"]),
                        "user_role": user_role,
                        "message": f"Query blocked by input guardrail: {route_result.name}"
                    }

        # ── Step 2: Get semantic route for metadata ────────────────────────────────
        route = self.query_router.get_semantic_route(query)
        logger.info(f"[Agent] Session={session_id} | Role={user_role} | Route={route}")

        try:
            agent_graph = create_agent(
                model=self.llm,
                tools=self.tools,
                system_prompt=self.system_message,
                middleware=self.input_guardrails.get_input_middlewares(),
                checkpointer=self.checkpointer
            )

            # Inject user_role and route into the query so the tool receives it
            augmented_query = f"{query}\n\n[user_role: {user_role}]\n[computed_route: {route}]"

            result = agent_graph.invoke(
                {"messages": [HumanMessage(content=augmented_query)]},
                config={"configurable": {"thread_id": session_id}}
            )

            # Extract the raw answer
            raw_answer = result["messages"][-1].content
            
            # ── Step 4: Extract chunks for output guardrail grounding check ───────────
            retrieved_chunks = []
            tool_messages = []
            for msg in result.get("messages", []):
                if isinstance(msg, ToolMessage) and msg.name == "retrieve_finbot_chunks":
                    retrieved_chunks.append(msg.content)
                    tool_messages.append(msg)

            # ── Step 4b: Extract structured citations from retrieved chunks ────────────
            citations = _extract_citations(tool_messages)

            # ── Step 5: Output Guardrails ─────────────────────────────────────────────
            if not bypass_guardrails:
                final_answer = self.output_guardrails.run_output_guardrails(
                    response=raw_answer,
                    user_role=user_role,
                    retrieved_chunks=retrieved_chunks,
                )
            else:
                final_answer = raw_answer

            # ── Step 6: Extract warnings and blocked status ───────────────────────────
            blocked = final_answer.startswith("🔒")
            guardrail_warning = None

            for marker in ["⚠️ **Source Warning:**", "⚠️ **Grounding Warning:**"]:
                if marker in final_answer:
                    idx = final_answer.index(marker)
                    guardrail_warning = final_answer[idx:].strip()
                    final_answer = final_answer[:idx].strip()
                    break

            if user_id:
                title = query[:30] + '...' if len(query) > 30 else query
                self.db_conn.execute(
                    "INSERT OR IGNORE INTO user_sessions (session_id, user_id, title) VALUES (?, ?, ?)",
                    (session_id, user_id, title)
                )
                self.db_conn.commit()

            return {
                "answer": final_answer,
                "citations": citations,
                "retrieved_chunks": retrieved_chunks,
                "route": route,
                "guardrail_warning": guardrail_warning,
                "blocked": blocked,
                "user_role": user_role,
                "accessible_collections": self.retrieval_tool_instance.role_collections.get(user_role, ["general"]),
                "message": "Success" if not blocked else "Response blocked by output guardrail."
            }

        except Exception as e:
            logger.warning(f"[Agent] LLM execution failed for session '{session_id}', using retrieval fallback: {e}")
            fallback_answer, fallback_citations, _, _ = self._build_fallback_answer(query, user_role, route)
            if user_id:
                title = query[:30] + '...' if len(query) > 30 else query
                self.db_conn.execute(
                    "INSERT OR IGNORE INTO user_sessions (session_id, user_id, title) VALUES (?, ?, ?)",
                    (session_id, user_id, title)
                )
                self.db_conn.commit()
            return {
                "answer": fallback_answer,
                "citations": fallback_citations,
                "retrieved_chunks": [],
                "route": route,
                "guardrail_warning": None,
                "blocked": False,
                "user_role": user_role,
                "accessible_collections": self.retrieval_tool_instance.role_collections.get(user_role, ["general"]),
                "message": "Success (LLM unavailable; retrieval fallback used)."
            }

    def get_user_sessions(self, user_id: str) -> list:
        cursor = self.db_conn.cursor()
        cursor.execute(
            "SELECT session_id, title, created_at FROM user_sessions WHERE user_id = ? ORDER BY created_at DESC", 
            (user_id,)
        )
        return [{"id": row[0], "title": row[1], "created_at": row[2]} for row in cursor.fetchall()]

    def get_session_history(self, session_id: str) -> list:
        agent_graph = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_message,
            middleware=self.input_guardrails.get_input_middlewares(),
            checkpointer=self.checkpointer
        )
        
        try:
            state = agent_graph.get_state({"configurable": {"thread_id": session_id}})
            messages = state.values.get("messages", [])
        except Exception:
            return []
            
        history = []
        import re
        current_route = None
        for msg in messages:
            if isinstance(msg, HumanMessage):
                route_match = re.search(r'\[computed_route: (.*?)\]', msg.content)
                if route_match:
                    current_route = route_match.group(1)
                content = re.sub(r'\n\n\[user_role: .*?\]\n\[computed_route: .*?\]$', '', msg.content)
                # Fallback for old histories before we added computed_route
                content = re.sub(r'\n\n\[user_role: .*?\]$', '', content)
                history.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage) and msg.content:
                history.append({"role": "assistant", "content": msg.content, "route": current_route})
        
        return history

    def close(self):
        self.retrieval_tool_instance.close()
        if hasattr(self, "db_conn") and self.db_conn:
            self.db_conn.close()

# For backward compatibility if needed, but we'll move to use the class
_global_agent = None

def ask_finbot(query: str, user_role: str, session_id: str, bypass_guardrails: bool = False, user_id: str = None) -> dict:
    global _global_agent
    if _global_agent is None:
        _global_agent = FinBotAgent()
    return _global_agent.ask_finbot(query, user_role, session_id, bypass_guardrails, user_id)

def close_qdrant_client():
    global _global_agent
    if _global_agent:
        _global_agent.close()
