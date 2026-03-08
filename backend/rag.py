import json
import importlib
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from sqlmodel import Session

from backend.database import engine
from backend.eligibility import calculate_age
from backend.guardrails import (
    enforce_non_promissory_language,
    is_advisory_query,
    is_unsafe_input,
)
from backend.models import RetrievalLog

FALLBACK_MESSAGE = "Information not available in approved credit policy."
TOP_K = 3
LOW_CONFIDENCE_THRESHOLD = 0.2

_POLICY_CHUNKS: List[str] = []
_POLICY_VECTORS: List[Dict[str, float]] = []
_CHROMA_COLLECTION = None


def _load_policy_text() -> str:
    policy_dir = Path(__file__).resolve().parent / "policies"
    if not policy_dir.exists():
        return ""

    policy_texts = []
    for file_path in sorted(policy_dir.glob("*.txt")):
        policy_texts.append(file_path.read_text(encoding="utf-8"))
    return "\n\n".join(policy_texts)


def _chunk_text(text: str, chunk_size: int = 60, overlap: int = 15) -> List[str]:
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap)
    return chunks


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _embed(text: str) -> Dict[str, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}

    counts: Dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0

    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return counts

    return {token: value / norm for token, value in counts.items()}


def _cosine_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    if len(left) > len(right):
        left, right = right, left

    return sum(value * right.get(token, 0.0) for token, value in left.items())


def _init_vector_store() -> None:
    global _POLICY_CHUNKS, _POLICY_VECTORS, _CHROMA_COLLECTION
    if _POLICY_CHUNKS:
        return

    policy_text = _load_policy_text()
    _POLICY_CHUNKS = _chunk_text(policy_text)
    _POLICY_VECTORS = [_embed(chunk) for chunk in _POLICY_CHUNKS]

    try:
        chromadb = importlib.import_module("chromadb")
        client = chromadb.PersistentClient(path=str(Path(__file__).resolve().parent / ".chroma"))
        _CHROMA_COLLECTION = client.get_or_create_collection(name="credit_policy_chunks")

        existing_count = _CHROMA_COLLECTION.count()
        if existing_count == 0 and _POLICY_CHUNKS:
            ids = [f"chunk_{index}" for index in range(len(_POLICY_CHUNKS))]
            _CHROMA_COLLECTION.add(ids=ids, documents=_POLICY_CHUNKS)
    except Exception:
        _CHROMA_COLLECTION = None


def _retrieve_top_k(query: str, k: int = TOP_K) -> Tuple[List[str], List[float]]:
    _init_vector_store()

    if _CHROMA_COLLECTION is not None:
        result = _CHROMA_COLLECTION.query(
            query_texts=[query],
            n_results=min(k, max(1, len(_POLICY_CHUNKS))),
            include=["documents", "distances"],
        )
        docs = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]
        scores = [round(1.0 / (1.0 + distance), 4) for distance in distances]
        return docs, scores

    query_vector = _embed(query)
    scored = []
    for chunk, vector in zip(_POLICY_CHUNKS, _POLICY_VECTORS):
        score = _cosine_similarity(query_vector, vector)
        scored.append((chunk, round(float(score), 4)))

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:k]
    return [item[0] for item in top], [item[1] for item in top]


def _log_retrieval(application_id: str, query: str, chunks: List[str], scores: List[float]) -> None:
    with Session(engine) as session:
        session.add(
            RetrievalLog(
                application_id=str(application_id),
                query=query,
                retrieved_chunks=json.dumps(chunks),
                similarity_scores=json.dumps(scores),
                timestamp=datetime.utcnow(),
            )
        )
        session.commit()


def retrieve_policy_context(query: str, application_id: int) -> dict:
    retrieved_chunks, similarity_scores = _retrieve_top_k(query=query, k=TOP_K)

    max_score = max(similarity_scores) if similarity_scores else 0.0
    if max_score < LOW_CONFIDENCE_THRESHOLD:
        retrieved_chunks = [FALLBACK_MESSAGE]
        similarity_scores = [0.0]

    _log_retrieval(str(application_id), query, retrieved_chunks, similarity_scores)

    return {
        "retrieved_chunks": retrieved_chunks,
        "similarity_scores": similarity_scores,
    }


def _generate_ai_narrative(query: str, retrieved_chunks: List[str]) -> str:
    if not retrieved_chunks or retrieved_chunks[0] == FALLBACK_MESSAGE:
        return FALLBACK_MESSAGE

    context = "\n\n".join(retrieved_chunks)
    prompt = (
        "You are a compliance-safe credit policy explainer. "
        "Answer only from the provided policy context. "
        "If the answer is not present in context, say exactly: "
        f"'{FALLBACK_MESSAGE}'.\n\n"
        f"Policy Context:\n{context}\n\n"
        f"Question: {query}\n"
        "Provide a concise, transparent explanation."
    )

    try:
        import ollama

        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]
    except Exception:
        return (
            "Based on approved policy: "
            + " ".join(retrieved_chunks[:2])
        )


def build_structured_explanation(application, decision_output: dict, user_query: str = "") -> dict:
    query = user_query or "Explain this pre-qualification decision based on policy criteria."

    if is_unsafe_input(query):
        blocked = "This system cannot assist with that request."
        blocked = enforce_non_promissory_language(blocked)
        return {
            "explanation_text": blocked,
            "retrieved_chunks": [],
            "similarity_scores": [],
            "guardrail_blocked": True,
        }

    if is_advisory_query(query):
        advisory = (
            "This system provides pre-qualification based on submitted data and does not provide financial advice."
        )
        advisory = enforce_non_promissory_language(advisory)
        return {
            "explanation_text": advisory,
            "retrieved_chunks": [],
            "similarity_scores": [],
            "guardrail_blocked": True,
        }

    retrieval = retrieve_policy_context(query=query, application_id=application.application_id)
    retrieved_chunks = retrieval["retrieved_chunks"]

    status = decision_output.get("status", application.status)
    age = calculate_age(application.dob) if application.dob else 0
    card_type = decision_output.get("card_type") or application.card_type or "N/A"
    risk_score = decision_output.get("risk_score", 0)

    deterministic_summary = (
        "SECTION 1 - Deterministic Summary\n"
        f"- Applicant age: {age}\n"
        f"- Monthly income: {application.monthly_income}\n"
        f"- Credit score: {application.credit_score}\n"
        f"- Employment type: {application.employment_type}\n"
        f"- Assigned card tier: {card_type}\n"
        f"- Risk score: {risk_score}\n"
    )

    ai_narrative = _generate_ai_narrative(query=query, retrieved_chunks=retrieved_chunks)

    if status == "rejected":
        rejection_reason = decision_output.get("reason") or decision_output.get("decision_explanation") or "Eligibility criteria not met."
        improvement = "Improve eligibility by increasing documented income stability, maintaining on-time repayments, and improving credit score through legitimate means."
        ai_narrative = (
            f"Rejection reason: {rejection_reason}\n"
            f"Compliant improvement suggestion: {improvement}"
        )

    full_text = (
        f"{deterministic_summary}\n"
        "SECTION 2 - AI Narrative\n"
        f"{ai_narrative}\n\n"
        "This system does not provide financial advisory services."
    )

    full_text = enforce_non_promissory_language(full_text)

    return {
        "explanation_text": full_text,
        "retrieved_chunks": retrieval["retrieved_chunks"],
        "similarity_scores": retrieval["similarity_scores"],
        "guardrail_blocked": False,
    }
