from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.database import (
    get_db, ConnectedEmailAccountModel, EmailThreadModel, 
    FollowUpLogModel, ActivityLogModel, utc_now
)
from app.security import encrypt_credentials, decrypt_credentials
from app.services.providers.factory import get_email_provider

router = APIRouter(prefix="/api/accounts", tags=["Email Accounts Management"])

class ConnectSmtpImapPayload(BaseModel):
    email_address: str
    smtp_host: str
    smtp_port: int = 465
    smtp_username: str
    smtp_password: str
    smtp_encryption: str = "SSL" # SSL, STARTTLS, NONE
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    imap_encryption: str = "SSL" # SSL, STARTTLS, NONE
    daily_sending_limit: int = Field(50, ge=1, le=2000)

class UpdateLimitsPayload(BaseModel):
    daily_sending_limit: int = Field(..., ge=1, le=5000)

class ToggleAutomationPayload(BaseModel):
    enabled: Optional[bool] = None

@router.get("")
def list_accounts(db: Session = Depends(get_db)):
    """
    Returns all connected mailboxes (Gmail + SMTP/IMAP) with account-level metrics,
    connection health, and automation statuses.
    """
    accounts = db.query(ConnectedEmailAccountModel).all()
    results = []

    for acc in accounts:
        # Calculate account-level statistics
        total_tracked = db.query(EmailThreadModel).filter(
            EmailThreadModel.sending_account_id == acc.id
        ).count()

        pending_followups = db.query(EmailThreadModel).filter(
            EmailThreadModel.sending_account_id == acc.id,
            EmailThreadModel.status.in_(["PENDING", "DUE FOR FOLLOW-UP"])
        ).count()

        followups_sent = db.query(FollowUpLogModel).filter(
            FollowUpLogModel.sending_account_id == acc.id,
            FollowUpLogModel.status == "SENT"
        ).count()

        replies_received = db.query(EmailThreadModel).filter(
            EmailThreadModel.sending_account_id == acc.id,
            EmailThreadModel.status == "RESPONDED"
        ).count()

        bounced_emails = db.query(EmailThreadModel).filter(
            EmailThreadModel.sending_account_id == acc.id,
            EmailThreadModel.status == "BOUNCED"
        ).count()

        results.append({
            "id": acc.id,
            "email_address": acc.email_address,
            "gmail_address": acc.email_address, # Backwards compatibility
            "provider_type": acc.provider_type,
            "provider_account_identifier": acc.provider_account_identifier,
            "authentication_type": acc.authentication_type,
            "connection_status": acc.connection_status,
            "status": acc.status, # Backwards compatibility
            "is_active": acc.connection_status in ["CONNECTED", "ACTIVE"],
            "auto_followup_enabled": acc.auto_followup_enabled,
            "daily_sending_limit": acc.daily_sending_limit,
            "daily_sent_count": acc.daily_sent_count,
            "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "stats": {
                "total_tracked": total_tracked,
                "pending_followups": pending_followups,
                "followups_sent": followups_sent,
                "replies_received": replies_received,
                "bounced_emails": bounced_emails
            }
        })

    return results

@router.post("/smtp-imap")
def connect_smtp_imap_account(payload: ConnectSmtpImapPayload, db: Session = Depends(get_db)):
    """
    Connects a professional domain email account using SMTP and IMAP.
    Tests connection, encrypts credentials, and adds to connected_email_accounts.
    """
    email_clean = payload.email_address.strip().lower()

    # Check if this email is already registered
    existing = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.email_address == email_clean
    ).first()

    creds_dict = {
        "smtp_host": payload.smtp_host.strip(),
        "smtp_port": payload.smtp_port,
        "smtp_username": payload.smtp_username.strip(),
        "smtp_password": payload.smtp_password,
        "smtp_encryption": payload.smtp_encryption.upper(),
        "imap_host": payload.imap_host.strip(),
        "imap_port": payload.imap_port,
        "imap_username": payload.imap_username.strip(),
        "imap_password": payload.imap_password,
        "imap_encryption": payload.imap_encryption.upper(),
    }
    encrypted_creds = encrypt_credentials(creds_dict)

    if existing:
        account = existing
        account.provider_type = "SMTP_IMAP"
        account.authentication_type = "PASSWORD"
        account.provider_account_identifier = payload.smtp_host.strip()
        account.encrypted_credentials = encrypted_creds
        account.daily_sending_limit = payload.daily_sending_limit
        account.connection_status = "CONNECTED"
        account.auto_followup_enabled = True
    else:
        account = ConnectedEmailAccountModel(
            email_address=email_clean,
            provider_type="SMTP_IMAP",
            provider_account_identifier=payload.smtp_host.strip(),
            authentication_type="PASSWORD",
            encrypted_credentials=encrypted_creds,
            daily_sending_limit=payload.daily_sending_limit,
            connection_status="CONNECTED",
            auto_followup_enabled=True
        )
        db.add(account)

    db.commit()
    db.refresh(account)

    # Test connection health
    provider = get_email_provider(account)
    healthy, msg = provider.test_connection()
    if not healthy:
        account.connection_status = "ERROR"
        db.commit()

    log = ActivityLogModel(
        user_id=account.user_id,
        action="ACCOUNT_CONNECTED",
        description=f"Connected Professional SMTP/IMAP account {account.email_address} (Host: {payload.smtp_host}). Status: {account.connection_status}"
    )
    db.add(log)
    db.commit()

    return {
        "message": f"Account {account.email_address} connected successfully.",
        "account_id": account.id,
        "status": account.connection_status,
        "test_result": msg
    }

@router.post("/{account_id}/test")
def test_account_connection(account_id: str, db: Session = Depends(get_db)):
    """Tests credentials and connectivity for an individual email account."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    provider = get_email_provider(account)
    healthy, msg = provider.test_connection()
    db.commit()

    return {
        "account_id": account.id,
        "email_address": account.email_address,
        "provider_type": account.provider_type,
        "healthy": healthy,
        "connection_status": account.connection_status,
        "message": msg
    }

@router.post("/{account_id}/toggle-automation")
def toggle_account_automation(
    account_id: str, 
    payload: Optional[ToggleAutomationPayload] = None, 
    db: Session = Depends(get_db)
):
    """Enables or disables automated follow-up processing for an individual account."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload and payload.enabled is not None:
        account.auto_followup_enabled = payload.enabled
    else:
        account.auto_followup_enabled = not account.auto_followup_enabled

    db.commit()

    log = ActivityLogModel(
        user_id=account.user_id,
        action="ACCOUNT_AUTOMATION_TOGGLED",
        description=f"Automation for mailbox {account.email_address} set to {'ENABLED' if account.auto_followup_enabled else 'PAUSED'}."
    )
    db.add(log)
    db.commit()

    return {
        "account_id": account.id,
        "email_address": account.email_address,
        "auto_followup_enabled": account.auto_followup_enabled
    }

@router.put("/{account_id}/limits")
def update_account_limits(account_id: str, payload: UpdateLimitsPayload, db: Session = Depends(get_db)):
    """Updates the daily sending limit for an individual account."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.daily_sending_limit = payload.daily_sending_limit
    db.commit()

    return {
        "account_id": account.id,
        "email_address": account.email_address,
        "daily_sending_limit": account.daily_sending_limit
    }

@router.post("/{account_id}/disconnect")
def disconnect_account(account_id: str, db: Session = Depends(get_db)):
    """Disconnects an individual mailbox, isolating it without affecting other accounts."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.connection_status = "DISCONNECTED"
    account.auto_followup_enabled = False
    db.commit()

    log = ActivityLogModel(
        user_id=account.user_id,
        action="ACCOUNT_DISCONNECTED",
        description=f"Mailbox {account.email_address} disconnected. Other connected mailboxes remain active."
    )
    db.add(log)
    db.commit()

    return {
        "message": f"Account {account.email_address} disconnected.",
        "connection_status": "DISCONNECTED"
    }

@router.get("/{account_id}/deliverability")
def get_account_deliverability(account_id: str, db: Session = Depends(get_db)):
    """
    Runs deliverability health checks (SPF, DKIM, DMARC, MX) for an account's domain.
    Section 8 Deliverability & Domain Health verification.
    """
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from app.services.deliverability import DeliverabilityService
    report = DeliverabilityService.check_domain_health(account.email_address)
    report["account_id"] = account.id
    report["email_address"] = account.email_address
    report["provider_type"] = account.provider_type
    return report

@router.delete("/{account_id}")
def delete_account(account_id: str, db: Session = Depends(get_db)):
    """Deletes an email account record."""
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.id == account_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    email_addr = account.email_address
    db.delete(account)
    db.commit()

    return {"message": f"Account {email_addr} deleted successfully."}
