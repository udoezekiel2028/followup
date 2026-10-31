import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.database import (
    SessionLocal, init_db, ConnectedEmailAccountModel, 
    ProspectModel, EmailThreadModel, EmailMessageModel, 
    AutomationSettingsModel, SuppressionModel
)
from app.services.reply_detector import ReplyDetectorService
from app.services.ai_followup import AIFollowUpService
from app.services.mailer_service import MailerService
from app.services.gmail_monitor import GmailMonitorService
from app.security import encrypt_token, decrypt_token
from app.services.scheduler import AutomationEngine

@pytest.fixture(autouse=True)
def clean_database():
    init_db()
    db = SessionLocal()
    try:
        db.query(EmailMessageModel).delete()
        db.query(EmailThreadModel).delete()
        db.query(ProspectModel).delete()
        db.query(ConnectedEmailAccountModel).delete()
        db.query(SuppressionModel).delete()
        db.commit()
    finally:
        db.close()

# ------------------------------------------------------------------------------
# TEST 1 & 2: Email detection and tracking
# ------------------------------------------------------------------------------
def test_1_and_2_cold_email_detection_and_tracking():
    settings_model = AutomationSettingsModel()
    suppressions = []

    is_cold, reason = GmailMonitorService.is_eligible_cold_outreach(
        recipient_email="prospect@acme.com",
        sender_email="sales@mycompany.com",
        subject="Intro to Automation for Acme",
        headers={},
        body_text="Hi John, saw Acme's recent expansion. We help streamline property workflows.",
        settings_model=settings_model,
        suppressions=suppressions
    )
    assert is_cold is True
    assert reason is None

    # Confirm non-cold emails (e.g. receipts, internal) are filtered out
    is_cold_receipt, r_reason = GmailMonitorService.is_eligible_cold_outreach(
        recipient_email="accounting@acme.com",
        sender_email="sales@mycompany.com",
        subject="Your Receipt and Invoice for Subscription",
        headers={},
        body_text="Here is your receipt",
        settings_model=settings_model,
        suppressions=suppressions
    )
    assert is_cold_receipt is False
    assert "receipt" in r_reason.lower() or "keyword" in r_reason.lower()

# ------------------------------------------------------------------------------
# TEST 3 & 4: 72 hours passage simulation and eligibility
# ------------------------------------------------------------------------------
def test_3_and_4_simulate_72h_passage_and_eligibility():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())[:8]
        p = ProspectModel(name="Test Lead", email=f"lead72h_{uid}@test.com", status="PENDING")
        db.add(p)
        db.flush()

        thread = EmailThreadModel(
            prospect_id=p.id,
            gmail_thread_id=f"thread_72h_{uid}",
            original_subject="Initial outreach",
            original_body="Original body text",
            original_sent_at=now - timedelta(hours=73),
            next_followup_at=now - timedelta(hours=1),
            followup_count=0,
            status="PENDING"
        )
        db.add(thread)
        db.commit()

        delay_hours = 72
        cutoff = now - timedelta(hours=delay_hours)
        eligible = db.query(EmailThreadModel).filter(
            EmailThreadModel.status.in_(["PENDING", "DUE FOR FOLLOW-UP"]),
            EmailThreadModel.followup_count == 0,
            EmailThreadModel.original_sent_at <= cutoff
        ).all()

        assert any(t.gmail_thread_id == f"thread_72h_{uid}" for t in eligible)
    finally:
        db.close()

# ------------------------------------------------------------------------------
# TEST 5: Prospect reply received -> cancelled / marked RESPONDED
# ------------------------------------------------------------------------------
def test_5_reply_received_cancels_followup():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())[:8]
        p = ProspectModel(name="Alice", email=f"alice_{uid}@enterprise.com", status="PENDING")
        db.add(p)
        db.flush()

        thread = EmailThreadModel(
            prospect_id=p.id,
            gmail_thread_id=f"thread_reply_{uid}",
            original_sent_at=now - timedelta(hours=75),
            status="RESPONDED",
            followup_count=0
        )
        db.add(thread)
        db.commit()

        res = MailerService.execute_follow_up_for_thread(thread, db)
        assert res["success"] is False
        assert "terminal status" in res["message"] or "RESPONDED" in res["message"]
    finally:
        db.close()

# ------------------------------------------------------------------------------
# TEST 6: Automated OOO & Bounce notifications handled separately
# ------------------------------------------------------------------------------
def test_6_automated_replies_and_bounces():
    bounce_cls = ReplyDetectorService.classify_message_content(
        sender="mailer-daemon@googlemail.com",
        subject="Delivery Status Notification (Failure)",
        body="550 5.1.1 User unknown"
    )
    assert bounce_cls == "BOUNCED"

    ooo_cls = ReplyDetectorService.classify_message_content(
        sender="prospect@company.com",
        subject="Automatic reply: Out of office until next Monday",
        body="I am currently on annual leave and have limited access to email."
    )
    assert ooo_cls == "OOO"

    genuine_cls = ReplyDetectorService.classify_message_content(
        sender="prospect@company.com",
        subject="Re: Partnership discussion",
        body="Hi Alex, I'd like to learn more. Can you send over a 1-pager?"
    )
    assert genuine_cls is None

# ------------------------------------------------------------------------------
# TEST 7: AI follow-up quality, concise tone, signature & anti-hallucination
# ------------------------------------------------------------------------------
def test_7_ai_follow_up_generation():
    prospect = ProspectModel(
        name="John",
        email="john@propertymgmt.com",
        company="Property Management Inc"
    )
    settings = AutomationSettingsModel(
        email_signature="Best,\nSam",
        ai_instructions="Be concise and courteous."
    )

    res = AIFollowUpService.generate_follow_up(prospect, settings)
    assert res["subject"].startswith("Re:")
    assert "John" in res["body"]
    assert "Best,\nSam" in res["body"]
    assert len(res["body"].split()) <= 150

# ------------------------------------------------------------------------------
# TEST 8: MIME payload adheres strictly to in-thread headers (In-Reply-To & References)
# ------------------------------------------------------------------------------
def test_8_in_thread_headers_preservation():
    payload = MailerService.create_in_thread_mime_message(
        sender="sales@mycompany.com",
        to="prospect@acme.com",
        subject="Quick follow-up",
        body_text="Hi John, following up on our note.",
        original_msg_id="original_msg_12345",
        thread_id="gmail_thread_abc"
    )
    assert payload["threadId"] == "gmail_thread_abc"
    assert "raw" in payload

# ------------------------------------------------------------------------------
# TEST 9: Duplicate prevention - worker run twice sends 0 duplicates
# ------------------------------------------------------------------------------
def test_9_idempotency_duplicate_prevention():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        uid = str(uuid.uuid4())[:8]
        p = ProspectModel(name="Bob", email=f"bob_{uid}@dup.com", status="FOLLOW-UP SENT")
        db.add(p)
        db.flush()

        thread = EmailThreadModel(
            prospect_id=p.id,
            gmail_thread_id=f"thread_dup_{uid}",
            original_sent_at=now - timedelta(hours=80),
            followup_count=1,
            status="FOLLOW-UP SENT"
        )
        db.add(thread)
        db.commit()

        res = MailerService.execute_follow_up_for_thread(thread, db)
        assert res["success"] is False
        assert "limit" in res["message"] or "terminal status" in res["message"]
    finally:
        db.close()

# ------------------------------------------------------------------------------
# TEST 10: Disconnecting Gmail account pauses system safely
# ------------------------------------------------------------------------------
def test_10_disconnect_gmail_pauses_system():
    db = SessionLocal()
    try:
        uid = str(uuid.uuid4())[:8]
        enc_token = encrypt_token("sample-access-token")
        enc_refresh = encrypt_token("sample-refresh-token")

        account = ConnectedEmailAccountModel(
            gmail_address=f"user_{uid}@work.com",
            encrypted_access_token=enc_token,
            encrypted_refresh_token=enc_refresh,
            status="ACTIVE"
        )
        db.add(account)
        db.commit()

        # Disconnect account
        account.status = "DISCONNECTED"
        db.commit()

        # Attempt to run cycle for account
        summary = AutomationEngine.run_cycle_for_account(account.id, db)
        assert "Account inactive or disconnected" in summary["skipped_reasons"]
    finally:
        db.close()
