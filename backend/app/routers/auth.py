from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, ConnectedEmailAccountModel, ActivityLogModel
from app.services.oauth_service import GoogleOAuthService
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication & Accounts"])

@router.get("/google/url")
def get_google_auth_url(state: str = Query(None)):
    """Generates the Google OAuth 2.0 authorization URL."""
    res = GoogleOAuthService.get_authorization_url(state=state)
    return res

@router.get("/google/callback")
def google_oauth_callback(
    code: str = Query(None), 
    error: str = Query(None), 
    state: str = Query(None),
    db: Session = Depends(get_db)
):
    """Handles the OAuth callback from Google."""
    if error:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/settings?error={error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        account = GoogleOAuthService.exchange_code_for_tokens(code=code, db=db)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?connected=true&email={account.gmail_address}"
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/settings?error={str(e)}"
        )

@router.get("/accounts")
def get_connected_accounts(db: Session = Depends(get_db)):
    """Returns all connected Gmail/Google Workspace accounts with encryption status."""
    accounts = db.query(ConnectedEmailAccountModel).all()
    return [
        {
            "id": a.id,
            "gmail_address": a.gmail_address,
            "connected_at": a.connected_at.isoformat(),
            "status": a.status,
            "is_active": (a.status == "ACTIVE")
        }
        for a in accounts
    ]

@router.post("/accounts/{account_id}/disconnect")
def disconnect_account(account_id: str, db: Session = Depends(get_db)):
    """Deactivates a connected email account and pauses automation safely."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.status = "DISCONNECTED"
    db.commit()

    act = ActivityLogModel(
        user_id=account.user_id,
        action="ACCOUNT_DISCONNECTED",
        description=f"Gmail account {account.gmail_address} disconnected. Automation safely paused."
    )
    db.add(act)
    db.commit()

    return {"message": f"Account {account.gmail_address} disconnected successfully. Automation paused."}
