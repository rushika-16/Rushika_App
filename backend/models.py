from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    application_id: str

    name: str
    mobile: str
    email: str

    dob: Optional[str] = None
    employment_type: Optional[str] = None
    monthly_income: Optional[float] = None
    credit_score: Optional[int] = None

    card_type: Optional[str] = None
    credit_limit: Optional[float] = None

    status: str = "in_progress"

    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievalLog(SQLModel, table=True):
    __tablename__ = "retrieval_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: str
    query: str
    retrieved_chunks: str
    similarity_scores: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DecisionLog(SQLModel, table=True):
    __tablename__ = "decision_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: str
    input_snapshot: str
    decision_output: str
    risk_score: float = 0.0
    card_type: str = "N/A"
    status: str
    explanation_text: str = ""
    system_prompt_version: str
    rag_prompt_version: str
    guardrail_version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)