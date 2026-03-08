import json
import re
import time
import uuid
from sqlmodel import select
from backend.models import Application, DecisionLog
from backend.eligibility import evaluate_eligibility
from backend.prompt_versions import (
    SYSTEM_PROMPT_VERSION,
    RAG_PROMPT_VERSION,
    GUARDRAIL_VERSION,
)


def _log_decision(session, application: Application, input_snapshot: dict, decision_output: dict):
    session.add(
        DecisionLog(
            application_id=application.application_id,
            input_snapshot=json.dumps(input_snapshot),
            decision_output=json.dumps(decision_output),
            risk_score=float(decision_output.get("risk_score", 0.0) or 0.0),
            card_type=decision_output.get("card_type", "N/A") or "N/A",
            status=decision_output.get("status", application.status),
            explanation_text=decision_output.get("decision_explanation") or decision_output.get("reason", ""),
            system_prompt_version=SYSTEM_PROMPT_VERSION,
            rag_prompt_version=RAG_PROMPT_VERSION,
            guardrail_version=GUARDRAIL_VERSION,
        )
    )


def find_existing_application(session, mobile: str, email: str):
    statement = select(Application).where(
        Application.mobile == mobile,
        Application.email == email,
        Application.status != "completed"
    )
    result = session.exec(statement).first()
    return result


def create_application(session, name: str, mobile: str, email: str):
    application_id = str(uuid.uuid4())

    new_application = Application(
        application_id=application_id,
        name=name,
        mobile=mobile,
        email=email,
        status="in_progress"
    )

    session.add(new_application)
    session.commit()
    session.refresh(new_application)

    return new_application


def submit_details(session, application_id: str, dob: str, employment_type: str,
                   monthly_income: float, credit_score: int, ssn_masked: str = ""):

    statement = select(Application).where(Application.application_id == application_id)
    application = session.exec(statement).first()

    if not application:
        return {"status": "error", "message": "Application not found"}

    input_snapshot = {
        "application_id": application_id,
        "dob": dob,
        "employment_type": employment_type,
        "monthly_income": monthly_income,
        "credit_score": credit_score,
        "ssn_masked": sanitize_masked_ssn(ssn_masked),
    }

    application.dob = dob
    application.employment_type = employment_type
    application.monthly_income = monthly_income
    application.credit_score = credit_score

    result = evaluate_eligibility(dob, employment_type, monthly_income, credit_score)

    if result["status"] == "rejected":
        application.status = "rejected"
        _log_decision(session, application, input_snapshot, result)
        session.commit()
        return result

    application.card_type = result["card_type"]
    application.credit_limit = result["credit_limit"]
    application.status = "eligible"

    _log_decision(session, application, input_snapshot, result)
    session.commit()
    session.refresh(application)

    return result


SSN_TO_CREDIT_SCORE = {
    "123456789": 850,
    "987654321": 825,
    "111223333": 810,
    "222334444": 780,
    "555667777": 745,
    "999001111": 590,
    "888776666": 550,
    "444556666": 520,
    "333221111": 680,
    "000123456": 350,
}


def normalize_ssn(ssn: str) -> str:
    return re.sub(r"\D", "", (ssn or "").strip())


def mask_ssn(ssn: str) -> str:
    normalized_ssn = normalize_ssn(ssn)
    if len(normalized_ssn) != 9:
        return "***-**-***"
    return f"***-**-{normalized_ssn[-3:]}"


def sanitize_masked_ssn(value: str) -> str:
    text = (value or "").strip()
    if re.fullmatch(r"\*{3}-\*{2}-\d{3}", text):
        return text
    return mask_ssn(text)


def get_credit_score_by_ssn(ssn: str) -> dict:
    normalized_ssn = normalize_ssn(ssn)
    time.sleep(1.0)

    record_found = normalized_ssn in SSN_TO_CREDIT_SCORE
    credit_score = SSN_TO_CREDIT_SCORE.get(normalized_ssn, 600)

    return {
        "ssn_masked": mask_ssn(normalized_ssn),
        "credit_score": credit_score,
        "record_found": record_found,
        "message": "Record Found" if record_found else "No Record Found. Using fallback score 600.",
    }