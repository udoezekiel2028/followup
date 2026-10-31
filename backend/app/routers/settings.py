from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.database import (
    get_db, AutomationSettingsModel, ConnectedEmailAccountModel, 
    SuppressionModel, ActivityLogModel
)

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class SettingsUpdatePayload(BaseModel):
    followup_delay_hours: Optional[int] = Field(None, ge=1, le=720)
    sending_window: Optional[str] = None
    timezone: Optional[str] = None
    maximum_followups: Optional[int] = Field(None, ge=1, le=5)
    auto_send_enabled: Optional[bool] = None
    test_mode: Optional[bool] = None
    ai_model: Optional[str] = None
    ai_instructions: Optional[str] = None
    email_signature: Optional[str] = None
    excluded_domains: Optional[List[str]] = None
    excluded_emails: Optional[List[str]] = None

@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """Retrieves current SmartFollow AI automation configuration."""
    settings = db.query(AutomationSettingsModel).first()
    if not settings:
        settings = AutomationSettingsModel(
            followup_delay_hours=72,
            sending_window="09:00-17:00",
            timezone="America/New_York",
            maximum_followups=1,
            auto_send_enabled=False,
            test_mode=True
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    account = db.query(ConnectedEmailAccountModel).first()

    return {
        "id": settings.id,
        "followup_delay_hours": settings.followup_delay_hours,
        "sending_window": settings.sending_window,
        "timezone": settings.timezone,
        "maximum_followups": settings.maximum_followups,
        "auto_send_enabled": settings.auto_send_enabled,
        "test_mode": settings.test_mode,
        "ai_model": settings.ai_model,
        "ai_instructions": settings.ai_instructions,
        "email_signature": settings.email_signature,
        "excluded_domains": settings.excluded_domains or [],
        "excluded_emails": settings.excluded_emails or [],
        "connected_account": {
            "id": account.id,
            "gmail_address": account.gmail_address,
            "status": account.status,
            "connected_at": account.connected_at.isoformat()
        } if account else None
    }

@router.put("")
def update_settings(payload: SettingsUpdatePayload, db: Session = Depends(get_db)):
    """Updates automation settings, safety toggles, and AI prompt configuration."""
    settings = db.query(AutomationSettingsModel).first()
    if not settings:
        settings = AutomationSettingsModel()
        db.add(settings)

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, val)

    db.commit()
    db.refresh(settings)

    act = ActivityLogModel(
        user_id=settings.user_id,
        action="SETTINGS_UPDATED",
        description="SmartFollow AI configuration updated by user."
    )
    db.add(act)
    db.commit()

    return {"message": "Settings updated successfully"}

@router.get("/suppression")
def get_suppression_list(db: Session = Depends(get_db)):
    items = db.query(SuppressionModel).order_by(SuppressionModel.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "email": s.email,
            "reason": s.reason,
            "created_at": s.created_at.isoformat()
        }
        for s in items
    ]

@router.post("/suppression")
def add_suppression(payload: Dict[str, str], db: Session = Depends(get_db)):
    email_val = payload.get("email", "").strip().lower()
    reason_val = payload.get("reason", "DO_NOT_CONTACT").upper()

    if not email_val:
        raise HTTPException(status_code=400, detail="Missing email")

    existing = db.query(SuppressionModel).filter(SuppressionModel.email == email_val).first()
    if existing:
        return {"id": existing.id, "email": existing.email, "reason": existing.reason}

    new_item = SuppressionModel(email=email_val, reason=reason_val)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"id": new_item.id, "email": new_item.email, "reason": new_item.reason}

@router.delete("/suppression/{id}")
def remove_suppression(id: str, db: Session = Depends(get_db)):
    item = db.query(SuppressionModel).filter(SuppressionModel.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Suppression entry not found")
    db.delete(item)
    db.commit()
    return {"message": "Suppression entry removed"}
