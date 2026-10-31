from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database import (
    get_db, ConnectedEmailAccountModel, ProspectModel, 
    EmailThreadModel, EmailMessageModel, FollowUpLogModel, 
    AutomationSettingsModel, ActivityLogModel, utc_now
)
from app.services.gmail_monitor import GmailMonitorService
from app.services.mailer_service import MailerService
from app.services.reply_detector import ReplyDetectorService
from app.services.ai_followup import AIFollowUpService
from app.services.label_manager import GmailLabelManager
from app.services.oauth_service import GoogleOAuthService
from app.services.providers.factory import get_email_provider

router = APIRouter(prefix="/api/email-management", tags=["Email Management"])

@router.get("/threads")
def list_tracked_threads(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    sort_by: str = Query("original_sent_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists tracked cold email conversations with search, account filter, status filter, and pagination."""
    query = db.query(EmailThreadModel)

    if account_id and account_id != "ALL":
        query = query.filter(EmailThreadModel.sending_account_id == account_id)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.join(ProspectModel, EmailThreadModel.prospect_id == ProspectModel.id, isouter=True).filter(
            or_(
                EmailThreadModel.original_subject.ilike(search_term),
                EmailThreadModel.original_body.ilike(search_term),
                ProspectModel.email.ilike(search_term),
                ProspectModel.name.ilike(search_term),
                ProspectModel.company.ilike(search_term)
            )
        )

    if status and status.upper() != "ALL":
        query = query.filter(EmailThreadModel.status == status.upper())

    sort_col = getattr(EmailThreadModel, sort_by, EmailThreadModel.original_sent_at)
    if sort_order.lower() == "asc":
        query = query.order_by(asc(sort_col))
    else:
        query = query.order_by(desc(sort_col))

    total = query.count()
    threads = query.offset((page - 1) * page_size).limit(page_size).all()

    now = utc_now()
    results = []
    for t in threads:
        sent_at = t.original_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        days_elapsed = max(0, (now - sent_at).days)

        # Time remaining until next follow-up
        time_remaining_str = "Eligible Now"
        if t.next_followup_at and t.status in ["PENDING"]:
            next_f = t.next_followup_at.replace(tzinfo=timezone.utc) if t.next_followup_at.tzinfo is None else t.next_followup_at
            if next_f > now:
                diff = next_f - now
                hours_rem = int(diff.total_seconds() // 3600)
                time_remaining_str = f"{hours_rem}h remaining"

        p = t.prospect
        acc = t.sending_account
        sending_account_email = acc.email_address if acc else "Default Mailbox"

        results.append({
            "id": t.id,
            "sending_account_id": t.sending_account_id,
            "sending_account_email": sending_account_email,
            "email_provider": t.email_provider or (acc.provider_type if acc else "GMAIL"),
            "prospect_id": t.prospect_id,
            "prospect_name": p.name if p else None,
            "prospect_email": p.email if p else "Unknown",
            "prospect_company": p.company if p else None,
            "gmail_thread_id": t.gmail_thread_id,
            "original_subject": t.original_subject,
            "original_body": t.original_body,
            "original_sent_at": t.original_sent_at.isoformat(),
            "next_followup_at": t.next_followup_at.isoformat() if t.next_followup_at else None,
            "time_remaining": time_remaining_str,
            "followup_count": t.followup_count,
            "last_followup_at": t.last_followup_at.isoformat() if t.last_followup_at else None,
            "status": t.status,
            "replied_at": t.replied_at.isoformat() if t.replied_at else None,
            "days_elapsed": days_elapsed
        })

    return {
        "items": results,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size)
    }

@router.get("/threads/{thread_id}/detail")
def get_thread_detail(thread_id: str, db: Session = Depends(get_db)):
    """Retrieves full conversation history and latest follow-up draft."""
    thread = db.query(EmailThreadModel).filter(
        (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
    ).first()

    if not thread:
        raise HTTPException(status_code=404, detail="Tracked thread not found")

    messages = db.query(EmailMessageModel).filter(
        EmailMessageModel.thread_record_id == thread.id
    ).order_by(EmailMessageModel.sent_at.asc()).all()

    draft = db.query(FollowUpLogModel).filter(
        FollowUpLogModel.email_thread_id == thread.id
    ).order_by(FollowUpLogModel.sent_at.desc()).first()

    p = thread.prospect
    acc = thread.sending_account

    return {
        "thread": {
            "id": thread.id,
            "sending_account_id": thread.sending_account_id,
            "sending_account_email": acc.email_address if acc else None,
            "email_provider": thread.email_provider or (acc.provider_type if acc else "GMAIL"),
            "gmail_thread_id": thread.gmail_thread_id,
            "original_subject": thread.original_subject,
            "original_body": thread.original_body,
            "original_sent_at": thread.original_sent_at.isoformat(),
            "status": thread.status,
            "followup_count": thread.followup_count,
            "replied_at": thread.replied_at.isoformat() if thread.replied_at else None
        },
        "prospect": {
            "id": p.id if p else None,
            "name": p.name if p else None,
            "email": p.email if p else "Unknown",
            "company": p.company if p else None
        },
        "messages": [
            {
                "id": m.id,
                "sending_account_id": m.sending_account_id,
                "gmail_message_id": m.gmail_message_id,
                "sender": m.sender,
                "recipient": m.recipient,
                "subject": m.subject,
                "body": m.body,
                "message_type": m.message_type,
                "sent_at": m.sent_at.isoformat()
            }
            for m in messages
        ],
        "draft": {
            "id": draft.id,
            "generated_content": draft.generated_content,
            "status": draft.status,
            "error_message": draft.error_message
        } if draft else None
    }

@router.get("/sent-explorer")
def list_sent_emails_to_track(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Browse recent Sent emails from a specific or all active mailboxes to manually click 'TRACK THIS EMAIL'."""
    if account_id and account_id != "ALL":
        accounts = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.id == account_id,
            ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"])
        ).all()
    else:
        accounts = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"])
        ).all()

    if not accounts:
        return []

    results = []
    for acc in accounts:
        try:
            provider = get_email_provider(acc)
            items = provider.sync_sent_emails(db, max_results=15)
            for it in items:
                it["sending_account_id"] = acc.id
                it["sending_account_email"] = acc.email_address
                it["provider_type"] = acc.provider_type
            results.extend(items)
        except Exception as e:
            print(f"Sent explorer error for {acc.email_address}: {e}")

    return results

@router.post("/track-sent")
def track_sent_email_manually(payload: Dict[str, str], db: Session = Depends(get_db)):
    """Method A: Manual Tracking - Begins monitoring conversation and tags AUTO_FOLLOWUP."""
    thread_id = payload.get("gmail_thread_id")
    if not thread_id:
        raise HTTPException(status_code=400, detail="Missing gmail_thread_id")

    account_id = payload.get("account_id")
    if account_id:
        account = db.query(ConnectedEmailAccountModel).filter(ConnectedEmailAccountModel.id == account_id).first()
    else:
        account = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"])
        ).first()

    if not account or account.connection_status not in ["CONNECTED", "ACTIVE"]:
        raise HTTPException(status_code=400, detail="No active email account connected")

    tracked = GmailMonitorService.track_conversation(account, thread_id, db, manual=True)
    if not tracked:
        raise HTTPException(status_code=400, detail="Could not track thread from mailbox")

    # Ensure sending_account_id is attached
    tracked.sending_account_id = account.id
    tracked.email_provider = account.provider_type
    db.commit()

    return {"message": f"Email is now tracked under {account.email_address}", "thread_id": tracked.id}

@router.post("/threads/{thread_id}/pause")
def pause_thread_automation(thread_id: str, db: Session = Depends(get_db)):
    """Pauses follow-up automation for this conversation."""
    thread = db.query(EmailThreadModel).filter(
        (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.status = "PAUSED"
    db.commit()

    act = ActivityLogModel(
        user_id=thread.user_id,
        action="AUTOMATION_PAUSED",
        description=f"Automation paused for thread {thread.gmail_thread_id}"
    )
    db.add(act)
    db.commit()
    return {"message": "Automation paused for this thread."}

@router.post("/threads/{thread_id}/resume")
def resume_thread_automation(thread_id: str, db: Session = Depends(get_db)):
    """Resumes follow-up automation for this conversation."""
    thread = db.query(EmailThreadModel).filter(
        (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.status = "PENDING"
    db.commit()

    act = ActivityLogModel(
        user_id=thread.user_id,
        action="AUTOMATION_RESUMED",
        description=f"Automation resumed for thread {thread.gmail_thread_id}"
    )
    db.add(act)
    db.commit()
    return {"message": "Automation resumed for this thread."}

@router.post("/threads/{thread_id}/stop")
def stop_thread_tracking(thread_id: str, db: Session = Depends(get_db)):
    """Stops tracking and removes AUTO_FOLLOWUP label in Gmail."""
    thread = db.query(EmailThreadModel).filter(
        (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.status = "STOPPED"
    db.commit()

    account = thread.sending_account
    if account and account.connection_status in ["CONNECTED", "ACTIVE"] and account.provider_type == "GMAIL":
        try:
            service = GoogleOAuthService.get_gmail_service(account, db)
            GmailLabelManager.remove_label_from_thread(service, thread.gmail_thread_id)
        except Exception:
            pass

    act = ActivityLogModel(
        user_id=thread.user_id,
        action="TRACKING_STOPPED",
        description=f"Tracking stopped for thread {thread.gmail_thread_id}."
    )
    db.add(act)
    db.commit()
    return {"message": "Tracking stopped for this thread."}

@router.post("/threads/{thread_id}/send-now")
def send_now_manual(thread_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Manually dispatch follow-up immediately into thread (with operator confirmation)."""
    thread = db.query(EmailThreadModel).filter(
        (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    body_override = payload.get("body")
    subject_override = payload.get("subject")
    force_live = payload.get("force_live_send", True)

    res = MailerService.execute_follow_up_for_thread(
        thread=thread,
        db=db,
        force_live_send=force_live,
        manual_override_body=body_override,
        manual_override_subject=subject_override
    )
    return res
