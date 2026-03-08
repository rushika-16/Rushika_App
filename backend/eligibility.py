from datetime import date, datetime


def calculate_age(dob: str) -> int:
    """
    Calculate age from date of birth (YYYY-MM-DD) with safety check
    """
    # Safety Check: if dob is missing or not a string, return 0 to prevent crash
    if not dob or not isinstance(dob, str):
        return 0
        
    try:
        birth_date = date.fromisoformat(dob)
    except ValueError:
        try:
            birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return 0

    today = date.today()

    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )

def evaluate_eligibility(
    dob: str,
    employment_type: str,
    monthly_income: float,
    credit_score: int,
):
    """
    Main underwriting decision engine
    """

    # ==========================
    # 1. AGE CALCULATION
    # ==========================
    age = calculate_age(dob)

    # ==========================
    # 2. HARD REJECTION FILTERS
    # ==========================

    ineligible_profession_message = (
        "Thank you for sharing your details. At the moment, our credit card program is available only for "
        "salaried and self-employed individuals. We truly appreciate your interest and hope to serve you in the future."
    )

    if age <= 18 or age >= 60:
        return {
            "status": "rejected",
            "reason": "Applicant age must be above 18 and below 60 years.",
            "decision_explanation": "Applicant age must be above 18 and below 60 years."
        }

    normalized_employment = (employment_type or "").strip().lower()

    if normalized_employment not in ["salaried", "self-employed"]:
        return {
            "status": "rejected",
            "reason": ineligible_profession_message,
            "decision_explanation": ineligible_profession_message,
        }

    if credit_score < 600:
        return {
            "status": "rejected",
            "reason": "Minimum credit score requirement is 600.",
            "decision_explanation": "Minimum credit score requirement is 600."
        }

    if monthly_income < 2000:
        return {
            "status": "rejected",
            "reason": "Income below minimum requirement.",
            "decision_explanation": "Income below minimum requirement."
        }

    # ==========================
    # 3. TIER BY CREDIT SCORE
    # ==========================

    if 600 <= credit_score <= 699:
        tier_by_score = "Standard"
    elif 700 <= credit_score <= 799:
        tier_by_score = "Premium"
    else:
        tier_by_score = "Elite"

    # ==========================
    # 4. TIER BY INCOME
    # ==========================

    if monthly_income >= 10000:
        tier_by_income = "Elite"
    elif monthly_income >= 5000:
        tier_by_income = "Premium"
    else:
        tier_by_income = "Standard"

    # ==========================
    # 5. CONSERVATIVE FINAL TIER
    # (Take lower of the two)
    # ==========================

    tier_order = ["Standard", "Premium", "Elite"]

    final_tier = tier_order[
        min(
            tier_order.index(tier_by_score),
            tier_order.index(tier_by_income),
        )
    ]

    # ==========================
    # 6. CREDIT LIMIT LOGIC
    # ==========================

    if final_tier == "Elite":
        credit_limit = monthly_income * 2
    elif final_tier == "Premium":
        credit_limit = monthly_income * 1
    else:
        credit_limit = monthly_income * 0.5

    # ==========================
    # 7. RISK SCORE MODEL (Sprint 2)
    # ==========================

    risk_score = (credit_score * 0.7) + (monthly_income * 0.3)

    # ==========================
    # 8. FINAL DECISION RESPONSE
    # ==========================

    return {
        "status": "eligible",
        "card_type": final_tier,
        "credit_limit": round(credit_limit, 2),
        "risk_score": round(risk_score, 2),
        "decision_explanation": (
            f"Applicant qualifies for {final_tier} card based on "
            f"credit score {credit_score} and monthly income {monthly_income}."
        ),
    }