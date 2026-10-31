from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from app.database import (
    get_db, EmailThreadModel, FollowUpLogModel, 
    AutomationSettingsModel, ActivityLogModel, ConnectedEmailAccountModel, utc_now
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Calculates metrics adhering to Section 8 & Section E (Multi-Account Support).
    Supports filtering by specific account_id or providing combined metrics across all mailboxes.
    """
    threads_query = db.query(EmailThreadModel)
    if account_id:
        threads_query = threads_query.filter(EmailThreadModel.sending_account_id == account_id)

    all_threads = threads_query.all()
    total_tracked = len(all_threads)

    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    counts = {
        "PENDING": 0,
        "DUE FOR FOLLOW-UP": 0,
        "FOLLOW-UP SENT": 0,
        "RESPONDED": 0,
        "BOUNCED": 0,
        "UNSUBSCRIBED": 0,
        "FAILED": 0,
        "PAUSED": 0,
        "STOPPED": 0
    }

    followups_due_today = 0
    for t in all_threads:
        st = t.status
        counts[st] = counts.get(st, 0) + 1

        if t.status in ["PENDING", "DUE FOR FOLLOW-UP"]:
            if t.next_followup_at:
                nf = t.next_followup_at.replace(tzinfo=timezone.utc) if t.next_followup_at.tzinfo is None else t.next_followup_at
                if nf <= today_end:
                    followups_due_today += 1

    awaiting_followup = counts.get("PENDING", 0) + counts.get("DUE FOR FOLLOW-UP", 0)
    followups_sent = counts.get("FOLLOW-UP SENT", 0)
    responded = counts.get("RESPONDED", 0)
    bounced = counts.get("BOUNCED", 0)

    # Response rate: percentage of follow-ups that yielded replies
    followup_response_rate = round((responded / (followups_sent + responded) * 100), 1) if (followups_sent + responded) > 0 else 0.0
    overall_response_rate = round((responded / total_tracked * 100), 1) if total_tracked > 0 else 0.0

    settings = db.query(AutomationSettingsModel).first()
    test_mode_active = settings.test_mode if settings else True
    auto_send_active = settings.auto_send_enabled if settings else False

    # Account-level summary breakdown across all connected mailboxes
    all_accounts = db.query(ConnectedEmailAccountModel).all()
    accounts_summary = []
    for acc in all_accounts:
        acc_threads = db.query(EmailThreadModel).filter(EmailThreadModel.sending_account_id == acc.id).all()
        acc_sent = sum(1 for t in acc_threads if t.status == "FOLLOW-UP SENT")
        acc_resp = sum(1 for t in acc_threads if t.status == "RESPONDED")
        acc_bounced = sum(1 for t in acc_threads if t.status == "BOUNCED")
        acc_pending = sum(1 for t in acc_threads if t.status in ["PENDING", "DUE FOR FOLLOW-UP"])

        accounts_summary.append({
            "account_id": acc.id,
            "email_address": acc.email_address,
            "provider_type": acc.provider_type,
            "connection_status": acc.connection_status,
            "auto_followup_enabled": acc.auto_followup_enabled,
            "daily_sending_limit": acc.daily_sending_limit,
            "daily_sent_count": acc.daily_sent_count,
            "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
            "total_tracked": len(acc_threads),
            "pending_followups": acc_pending,
            "followups_sent": acc_sent,
            "replies_received": acc_resp,
            "bounced_emails": acc_bounced
        })

    recent_logs = db.query(ActivityLogModel).order_by(
        ActivityLogModel.created_at.desc()
    ).limit(10).all()

    return {
        "filter_account_id": account_id,
        "total_tracked": total_tracked,
        "awaiting_followup": awaiting_followup,
        "followups_due_today": followups_due_today,
        "followups_sent": followups_sent,
        "responded": responded,
        "bounced": bounced,
        "followup_response_rate": followup_response_rate,
        "overall_response_rate": overall_response_rate,
        "test_mode_active": test_mode_active,
        "auto_send_active": auto_send_active,
        "status_counts": counts,
        "accounts_summary": accounts_summary,
        "total_connected_accounts": len(all_accounts),
        "recent_activity": [
            {
                "id": log.id,
                "event_type": log.action,
                "message": log.description,
                "created_at": log.created_at.isoformat()
            }
            for log in recent_logs
        ]
    }
