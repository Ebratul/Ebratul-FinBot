import json
import logging
import os
import re
from typing import List, Dict, Any, Optional

from datasets import Dataset
from ragas import evaluate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    faithfulness,
    context_precision,
    context_recall,
)

from backend.agent import FinBotAgent
from backend.config import settings

logger = logging.getLogger(__name__)


def _parse_chunk_texts(formatted_chunks_str: str) -> List[str]:
    """
    Parse individual chunk texts from the formatted string produced by
    RetrievalTool.format_chunks(). Splits on '---' separators and strips headers.
    """
    if not formatted_chunks_str or formatted_chunks_str.startswith("No relevant"):
        return []

    chunks = []
    # Split on the separator between chunks
    parts = re.split(r"\n\n---\n\n", formatted_chunks_str)
    for part in parts:
        # Remove the header line "[N] Source: ..., Page ... | Section: ... | Collection: ..."
        lines = part.strip().splitlines()
        # Skip lines that look like headers (start with "[N]")
        content_lines = [l for l in lines if not re.match(r"^\[\d+\]", l)]
        text = "\n".join(content_lines).strip()
        if text:
            chunks.append(text)
    return chunks


class FinBotEvaluator:
    def __init__(self):
        self.agent = FinBotAgent()

        # Initialize RAGAs Critic LLM (Groq) and Embeddings (BGE) — same as notebook
        llm_model = os.getenv("EVAL_LLM_MODEL", "llama-3.3-70b-versatile")
        embed_model = os.getenv("EVAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

        critic_llm = ChatGroq(
            model=llm_model,
            temperature=0,
            max_tokens=1024,
            api_key=settings.groq_api_key.get_secret_value()
        )
        critic_embeddings = HuggingFaceEmbeddings(model_name=embed_model)

        self.ragas_llm = LangchainLLMWrapper(critic_llm)
        self.ragas_emb = LangchainEmbeddingsWrapper(critic_embeddings)

        self.metrics = [
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
        ]
        for metric in self.metrics:
            metric.llm = self.ragas_llm
            metric.embeddings = self.ragas_emb

    def load_dataset(self) -> List[Dict[str, str]]:
        dataset_path = os.path.join(os.path.dirname(__file__), "evaluation", "ragas_dataset.json")
        if not os.path.exists(dataset_path):
            logger.error(f"Evaluation dataset not found at {dataset_path}")
            return []
        with open(dataset_path, "r") as f:
            return json.load(f)

    def run_ablation_study(self, sample_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Runs two evaluation passes:
          - baseline: guardrails bypassed (no input/output filtering)
          - final:    full secure pipeline (guardrails ON)
        Returns metric scores for both, plus the dataset used.
        """
        raw_dataset = self.load_dataset()
        if not raw_dataset:
            raise ValueError("Evaluation dataset is empty or missing.")
        if sample_size:
            raw_dataset = raw_dataset[:sample_size]

        logger.info(f"[Evaluator] Starting ablation study on {len(raw_dataset)} questions")

        baseline_results = self._evaluate_pipeline(raw_dataset, bypass_guardrails=True)
        final_results = self._evaluate_pipeline(raw_dataset, bypass_guardrails=False)

        return {
            "baseline": baseline_results,
            "final": final_results,
            "dataset": raw_dataset,
            "sample_size": len(raw_dataset),
        }

    def _evaluate_pipeline(
        self, raw_dataset: List[Dict[str, str]], bypass_guardrails: bool
    ) -> List[Dict[str, Any]]:
        """
        Runs the FinBot RAG pipeline for each question and collects
        (question, answer, contexts, ground_truth). Then evaluates with RAGAs.
        """
        label = "BASELINE (guardrails OFF)" if bypass_guardrails else "FINAL (guardrails ON)"
        logger.info(f"[Evaluator] Running pipeline — {label}")

        rows = []
        for i, item in enumerate(raw_dataset):
            question = item["question"]
            ground_truth = item["ground_truth"]

            try:
                response = self.agent.ask_finbot(
                    query=question,
                    user_role="c_level",
                    session_id=f"eval_{i}",
                    bypass_guardrails=bypass_guardrails,
                )

                answer = response.get("answer", "")

                # Extract context texts from the raw tool message strings
                raw_chunks_list = response.get("retrieved_chunks", [])
                contexts = []
                for chunk_str in raw_chunks_list:
                    parsed = _parse_chunk_texts(chunk_str)
                    contexts.extend(parsed)

                if not contexts:
                    contexts = ["No context retrieved."]

                rows.append({
                    "question": question,
                    "answer": answer,
                    "contexts": contexts,
                    "ground_truth": ground_truth,
                })
                logger.info(f"[Evaluator] Q{i+1}/{len(raw_dataset)} done ({len(contexts)} chunks)")

            except Exception as e:
                logger.error(f"[Evaluator] Failed on Q{i+1}: {e}")
                rows.append({
                    "question": question,
                    "answer": "Error generating answer.",
                    "contexts": ["Error retrieving context."],
                    "ground_truth": ground_truth,
                })

        # Build HuggingFace Dataset and run RAGAs
        dataset = Dataset.from_list(rows)
        logger.info(f"[Evaluator] Running RAGAs metrics for {label}...")

        eval_result = evaluate(
            dataset,
            metrics=self.metrics,
            llm=self.ragas_llm,
            embeddings=self.ragas_emb,
        )

        df = eval_result.to_pandas()
        # Sanitize NaN/inf values that break JSON serialization
        import math
        records = []
        for row in df.to_dict(orient="records"):
            clean = {}
            for k, v in row.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    clean[k] = None
                else:
                    clean[k] = v
            records.append(clean)

        logger.info(f"[Evaluator] {label} complete.")
        return records


_evaluator = None


def get_evaluator() -> FinBotEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = FinBotEvaluator()
    return _evaluator
