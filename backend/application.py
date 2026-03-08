from fastapi import APIRouter
from pydantic import BaseModel
import uuid
from datetime import datetime

router = APIRouter()

class ApplicationRequest(BaseModel):
    name: str
    email: str
    card_type: str
    credit_limit: float

@router.post("/confirm-application")
def confirm_application(data: ApplicationRequest):
    
    application_id = str(uuid.uuid4())[:8]

    response = {
        "application_id": application_id,
        "status": "approved",
        "card_type": data.card_type,
        "credit_limit": data.credit_limit,
        "message": "Your card has been successfully approved!"
    }

    return response