import pytest
import uuid
from app.services.mailer_service import MailerService
from app.database import EmailThreadModel, ProspectModel, SessionLocal
from datetime import datetime, timezone

def test_prevent_duplicate_followup_if_already_sent():
    db = SessionLocal()
    try:
        uid = str(uuid.uuid4())[:8]
        p = ProspectModel(email=f"dup_{uid}@test.com")
        db.add(p)
        db.flush()

        thread = EmailThreadModel(
            prospect_id=p.id,
            gmail_thread_id=f"thread_dup_check_{uid}",
            status="FOLLOW-UP SENT",
            followup_count=1,
            original_sent_at=datetime.now(timezone.utc)
        )
        db.add(thread)
        db.commit()

        res = MailerService.execute_follow_up_for_thread(thread, db)
        assert res["success"] is False
        assert "terminal status" in res["message"] or "limit" in res["message"]
    finally:
        db.close()

def test_prevent_followup_if_prospect_responded():
    db = SessionLocal()
    try:
        uid = str(uuid.uuid4())[:8]
        p = ProspectModel(email=f"responded_{uid}@test.com")
        db.add(p)
        db.flush()

        thread = EmailThreadModel(
            prospect_id=p.id,
            gmail_thread_id=f"thread_responded_check_{uid}",
            status="RESPONDED",
            followup_count=0,
            original_sent_at=datetime.now(timezone.utc)
        )
        db.add(thread)
        db.commit()

        res = MailerService.execute_follow_up_for_thread(thread, db)
        assert res["success"] is False
        assert "terminal status" in res["message"]
    finally:
        db.close()
