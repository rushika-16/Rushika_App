import re
import os
import logging
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from backend.database import create_db_and_tables, get_session
from backend.models import Application 
from backend.service import (
    find_existing_application,
    create_application,
    get_credit_score_by_ssn,
    submit_details,
)
from backend.eligibility import evaluate_eligibility
from backend.rag import build_structured_explanation

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("credit_card_ai.backend")

app = FastAPI()


class SSNLookupRequest(BaseModel):
    ssn: str

INVALID_NAME_PHRASES = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "whats up",
    "what s up",
    "hi dear",
    "hey dear",
    "hello dear",
    "hi whats up",
    "hi what s up",
}

NAME_DISALLOWED_TOKENS = {
    "hi", "hello", "hey", "yo", "sup", "whats", "what", "up",
    "dear", "bro", "buddy", "dude", "sir", "madam",
    "you", "your", "me", "my", "mine", "i", "am", "im", "got",
    "test", "random", "name", "guest", "none", "okay", "ok",
}

NAME_PREFIX_PATTERN = re.compile(r"^(my name is|i am|i'm|this is)\s+", re.IGNORECASE)


def normalize_name_candidate(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    text = NAME_PREFIX_PATTERN.sub("", text).strip()
    return text


def validate_human_name(value: str) -> bool:
    normalized_value = normalize_name_candidate(value)
    normalized = re.sub(r"[^a-zA-Z ]", " ", normalized_value.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return False

    if normalized in INVALID_NAME_PHRASES:
        return False

    tokens = normalized.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False

    if any(len(token) < 2 for token in tokens):
        return False

    if any(token in NAME_DISALLOWED_TOKENS for token in tokens):
        return False

    if not re.fullmatch(r"[A-Za-z ]{2,}", normalized_value):
        return False

    return True

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.get("/")
def read_root():
    return {"message": "Credit Card AI Backend Running"}


@app.get("/healthz")
def healthz(session: Session = Depends(get_session)):
    try:
        session.exec(select(1)).one()
        return {"status": "ok", "database": "ok"}
    except Exception:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Service unavailable")

@app.post("/start")
def start_application(
    name: str = "Guest", 
    mobile: str = "000", 
    email: str = "none@test.com", 
    session: Session = Depends(get_session)
):
    cleaned_name = normalize_name_candidate(name)

    if not validate_human_name(cleaned_name):
        raise HTTPException(
            status_code=400,
            detail="Please enter a proper full name (first and last name) using alphabets only.",
        )

    # 1. Check if user already exists
    existing_app = find_existing_application(session, mobile, email)

    if existing_app:
        return {
            "message": "Resuming existing application",
            "application_id": existing_app.application_id,
            "status": existing_app.status,
        }

    # 2. If not, create a new one
    new_app = create_application(session, cleaned_name, mobile, email)

    return {
        "message": "New application started successfully",
        "application_id": new_app.application_id,
        "status": new_app.status,
    }


@app.post("/lookup-credit-score")
def lookup_credit_score(payload: SSNLookupRequest):
    normalized_ssn = re.sub(r"\D", "", (payload.ssn or "").strip())
    if not re.fullmatch(r"\d{9}", normalized_ssn):
        raise HTTPException(
            status_code=400,
            detail="Please provide SSN in XXX-XX-XXXX format or as 9 digits.",
        )

    lookup_result = get_credit_score_by_ssn(normalized_ssn)
    logger.info(
        "SSN lookup response: ssn=%s score=%s record_found=%s",
        lookup_result["ssn_masked"],
        lookup_result["credit_score"],
        lookup_result["record_found"],
    )
    return lookup_result

@app.post("/submit-details")
def submit_application_details(
    application_id: str,
    dob: str,
    employment_type: str,
    monthly_income: float,
    credit_score: int,
    ssn_masked: str = "",
    session: Session = Depends(get_session),
):
    return submit_details(
        session,
        application_id,
        dob,
        employment_type,
        monthly_income,
        credit_score,
        ssn_masked=ssn_masked,
    )

@app.get("/application/{application_id}")
def get_application(application_id: str, session: Session = Depends(get_session)):
    statement = select(Application).where(Application.application_id == application_id)
    app_data = session.exec(statement).first()

    if not app_data:
        raise HTTPException(status_code=404, detail="Application not found")

    return app_data


@app.post("/explain-decision")
def explain_decision(
    application_id: str,
    user_query: str = "",
    session: Session = Depends(get_session),
):
    statement = select(Application).where(Application.application_id == application_id)
    app_data = session.exec(statement).first()

    if not app_data:
        raise HTTPException(status_code=404, detail="Application not found")

    if not all([
        app_data.dob,
        app_data.employment_type,
        app_data.monthly_income is not None,
        app_data.credit_score is not None,
    ]):
        raise HTTPException(status_code=400, detail="Application details are incomplete")

    decision_output = evaluate_eligibility(
        dob=app_data.dob,
        employment_type=app_data.employment_type,
        monthly_income=app_data.monthly_income,
        credit_score=app_data.credit_score,
    )

    return build_structured_explanation(
        application=app_data,
        decision_output=decision_output,
        user_query=user_query,
    )

# Use 'backend.application' to point to the correct folder
from backend.application import router as application_router
app.include_router(application_router)

