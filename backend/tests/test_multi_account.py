import pytest
import uuid
import threading
from datetime import datetime, timezone, timedelta
from app.database import (
    SessionLocal, init_db, ConnectedEmailAccountModel, 
    ProspectModel, EmailThreadModel, EmailMessageModel, 
    AutomationSettingsModel, FollowUpLogModel, utc_now
)
from app.security import encrypt_credentials, decrypt_credentials
from app.services.providers.factory import get_email_provider
from app.services.scheduler import AutomationEngine
from app.services.mailer_service import MailerService

@pytest.fixture(autouse=True)
def clean_database():
    init_db()
    db = SessionLocal()
    try:
        db.query(FollowUpLogModel).delete()
        db.query(EmailMessageModel).delete()
        db.query(EmailThreadModel).delete()
        db.query(ProspectModel).delete()
        db.query(ConnectedEmailAccountModel).delete()
        db.commit()
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 1 & 2: Connect 4 Gmail + 2 Professional SMTP/IMAP Accounts (6 Total)
# ------------------------------------------------------------------------------
def test_1_and_2_connect_six_distinct_mailboxes():
    db = SessionLocal()
    try:
        # 4 Gmail Accounts
        gmail_addresses = [
            "sarah.outreach@growthscale.io",
            "alex.sales@growthscale.io",
            "marcus.bdr@growthscale.io",
            "partnerships@growthscale.io"
        ]
        created_gmail = []
        for g_email in gmail_addresses:
            acc = ConnectedEmailAccountModel(
                email_address=g_email,
                provider_type="GMAIL",
                provider_account_identifier=f"google_id_{g_email.split('@')[0]}",
                authentication_type="OAUTH2",
                encrypted_credentials=encrypt_credentials({"token": f"token_{g_email}", "refresh_token": "refresh"}),
                connection_status="CONNECTED",
                auto_followup_enabled=True,
                daily_sending_limit=50
            )
            db.add(acc)
            created_gmail.append(acc)

        # 2 Professional Domain SMTP/IMAP Accounts
        prof_accounts = [
            {
                "email": "david@acmeenterprises.com",
                "host": "smtp.acmeenterprises.com"
            },
            {
                "email": "enterprise@cloudcraftsystems.com",
                "host": "mail.cloudcraftsystems.com"
            }
        ]
        created_prof = []
        for p in prof_accounts:
            acc = ConnectedEmailAccountModel(
                email_address=p["email"],
                provider_type="SMTP_IMAP",
                provider_account_identifier=p["host"],
                authentication_type="PASSWORD",
                encrypted_credentials=encrypt_credentials({
                    "smtp_host": p["host"],
                    "smtp_port": 465,
                    "smtp_username": p["email"],
                    "smtp_password": "secret_app_pw",
                    "imap_host": p["host"],
                    "imap_port": 993,
                    "imap_username": p["email"],
                    "imap_password": "secret_app_pw",
                    "is_mock": True
                }),
                connection_status="CONNECTED",
                auto_followup_enabled=True,
                daily_sending_limit=100
            )
            db.add(acc)
            created_prof.append(acc)

        db.commit()

        # Verify all 6 accounts exist in DB with unique IDs
        all_accounts = db.query(ConnectedEmailAccountModel).all()
        assert len(all_accounts) == 6
        assert len(set(a.id for a in all_accounts)) == 6
        assert len(set(a.email_address for a in all_accounts)) == 6

        # Verify provider factory instantiates correct classes
        for a in all_accounts:
            provider = get_email_provider(a)
            healthy, msg = provider.test_connection()
            assert healthy is True
            if a.provider_type == "GMAIL":
                assert provider.__class__.__name__ == "GmailEmailProvider"
            else:
                assert provider.__class__.__name__ == "ImapSmtpEmailProvider"
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 3: Track emails sent across all 6 accounts
# ------------------------------------------------------------------------------
def test_3_track_emails_across_all_six_accounts():
    db = SessionLocal()
    try:
        now = utc_now()
        # Create 6 accounts
        accounts = []
        for i in range(1, 7):
            provider = "GMAIL" if i <= 4 else "SMTP_IMAP"
            acc = ConnectedEmailAccountModel(
                email_address=f"sender{i}@company{i}.com",
                provider_type=provider,
                encrypted_credentials=encrypt_credentials({"is_mock": True}),
                connection_status="CONNECTED"
            )
            db.add(acc)
            accounts.append(acc)
        db.commit()

        # Track 1 email conversation in each of the 6 accounts
        tracked_threads = []
        for acc in accounts:
            prospect = ProspectModel(
                name=f"Lead for {acc.email_address}",
                email=f"lead_for_{acc.id[:6]}@target.com",
                sending_account_id=acc.id,
                status="PENDING"
            )
            db.add(prospect)
            db.flush()

            thread = EmailThreadModel(
                sending_account_id=acc.id,
                email_provider=acc.provider_type,
                prospect_id=prospect.id,
                recipient_address=prospect.email,
                gmail_thread_id=f"thread_id_{acc.id}",
                original_message_id=f"msg_{acc.id}",
                original_subject=f"Outreach from {acc.email_address}",
                original_body="Hello, inquiring about lead automation.",
                original_sent_at=now - timedelta(hours=75),
                next_followup_at=now - timedelta(hours=3),
                status="PENDING",
                followup_count=0
            )
            db.add(thread)
            tracked_threads.append(thread)
        db.commit()

        assert len(tracked_threads) == 6
        for t in tracked_threads:
            assert t.sending_account_id is not None
            assert t.sending_account.email_address is not None
            assert t.status == "PENDING"
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 4 & 5: Independent reply detection & cross-account isolation
# A reply in Gmail account 1 must NOT affect conversations in Gmail account 2
# ------------------------------------------------------------------------------
def test_4_and_5_reply_isolation_between_accounts():
    db = SessionLocal()
    try:
        now = utc_now()

        # Account 1 & Account 2
        acc1 = ConnectedEmailAccountModel(
            email_address="account1@company.com",
            provider_type="GMAIL",
            encrypted_credentials=encrypt_credentials({"is_mock": True}),
            connection_status="CONNECTED"
        )
        acc2 = ConnectedEmailAccountModel(
            email_address="account2@company.com",
            provider_type="GMAIL",
            encrypted_credentials=encrypt_credentials({"is_mock": True}),
            connection_status="CONNECTED"
        )
        db.add_all([acc1, acc2])
        db.commit()

        # Thread in Account 1
        p1 = ProspectModel(email="lead1@client.com", sending_account_id=acc1.id)
        db.add(p1)
        db.flush()
        th1 = EmailThreadModel(
            sending_account_id=acc1.id,
            prospect_id=p1.id,
            recipient_address=p1.email,
            gmail_thread_id="thread_acc1_lead1",
            original_sent_at=now - timedelta(hours=75),
            status="PENDING"
        )
        db.add(th1)

        # Thread in Account 2 with same client domain
        p2 = ProspectModel(email="lead2@client.com", sending_account_id=acc2.id)
        db.add(p2)
        db.flush()
        th2 = EmailThreadModel(
            sending_account_id=acc2.id,
            prospect_id=p2.id,
            recipient_address=p2.email,
            gmail_thread_id="thread_acc2_lead2",
            original_sent_at=now - timedelta(hours=75),
            status="PENDING"
        )
        db.add(th2)
        db.commit()

        # Inbound reply is received ONLY in Account 1's conversation
        reply_msg1 = EmailMessageModel(
            sending_account_id=acc1.id,
            thread_record_id=th1.id,
            gmail_message_id="reply_msg_101",
            sender="lead1@client.com",
            recipient=acc1.email_address,
            subject="Re: Inquiry",
            body="Thanks for reaching out! Let's talk.",
            message_type="INBOUND_REPLY",
            sent_at=now - timedelta(hours=10)
        )
        db.add(reply_msg1)
        db.commit()

        # Detect replies in both accounts
        provider1 = get_email_provider(acc1)
        res1 = provider1.check_for_reply(th1, db)

        provider2 = get_email_provider(acc2)
        res2 = provider2.check_for_reply(th2, db)

        # Assert Account 1 marked as RESPONDED
        assert res1["status"] == "RESPONDED"
        assert th1.status == "RESPONDED"
        assert th1.replied_at is not None

        # Assert Account 2 remains completely UNTOUCHED and PENDING!
        assert res2["status"] == "NO_REPLY"
        assert th2.status == "PENDING"
        assert th2.replied_at is None
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 6, 7 & 8: Follow-ups generated strictly from original sending account
# and remain inside the original conversation thread
# ------------------------------------------------------------------------------
def test_6_7_and_8_followup_affinity_and_thread_continuity():
    db = SessionLocal()
    try:
        now = utc_now()
        # Setup SMTP/IMAP Professional Account
        prof_acc = ConnectedEmailAccountModel(
            email_address="david@acmeenterprises.com",
            provider_type="SMTP_IMAP",
            encrypted_credentials=encrypt_credentials({
                "smtp_host": "smtp.acmeenterprises.com",
                "smtp_port": 465,
                "is_mock": True
            }),
            connection_status="CONNECTED",
            auto_followup_enabled=True,
            daily_sending_limit=50,
            daily_sent_count=0
        )
        db.add(prof_acc)
        db.commit()

        prospect = ProspectModel(
            name="Rachel Adams",
            email="rachel@peakmanufacturing.com",
            sending_account_id=prof_acc.id,
            status="PENDING"
        )
        db.add(prospect)
        db.flush()

        orig_msg_id = "<msg_12345@acmeenterprises.com>"
        thread = EmailThreadModel(
            sending_account_id=prof_acc.id,
            email_provider="SMTP_IMAP",
            prospect_id=prospect.id,
            recipient_address=prospect.email,
            gmail_thread_id="prof_thread_101",
            original_message_id=orig_msg_id,
            original_subject="ERP integration inquiry",
            original_body="Initial outreach text...",
            original_sent_at=now - timedelta(hours=76),
            status="PENDING",
            followup_count=0
        )
        db.add(thread)
        db.commit()

        # Dispatch follow-up
        provider = get_email_provider(prof_acc)
        res = provider.send_followup(
            thread=thread,
            draft_content="Hi Rachel, just following up on our ERP conversation.",
            db=db,
            test_mode=False
        )

        assert res["success"] is True
        assert res["status"] == "FOLLOW-UP SENT"
        assert thread.status == "FOLLOW-UP SENT"
        assert thread.followup_count == 1
        assert prof_acc.daily_sent_count == 1

        # Verify sent email message was stored with exact sending mailbox affinity
        sent_msg = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_record_id == thread.id,
            EmailMessageModel.message_type == "OUTBOUND_FOLLOWUP"
        ).first()

        assert sent_msg is not None
        assert sent_msg.sender == prof_acc.email_address
        assert sent_msg.recipient == prospect.email
        assert sent_msg.sending_account_id == prof_acc.id

        # Verify second follow-up is hard blocked (Max 1 Follow-Up rule)
        res_duplicate = provider.send_followup(
            thread=thread,
            draft_content="Another follow-up",
            db=db,
            test_mode=False
        )
        assert res_duplicate["success"] is False
        assert "Duplicate follow-up prevented" in res_duplicate["error"]
        assert thread.followup_count == 1
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 9: Error isolation
# Disconnect one account and verify the other five continue working uninterrupted
# ------------------------------------------------------------------------------
def test_9_error_isolation_single_account_failure():
    db = SessionLocal()
    try:
        now = utc_now()
        # Create 6 accounts: Account 1 is broken/disconnected, Accounts 2-6 are healthy
        accounts = []
        for i in range(1, 7):
            acc = ConnectedEmailAccountModel(
                email_address=f"mailbox{i}@domain.com",
                provider_type="GMAIL" if i <= 4 else "SMTP_IMAP",
                encrypted_credentials=encrypt_credentials({"is_mock": True}),
                connection_status="CONNECTED" if i > 1 else "DISCONNECTED",
                auto_followup_enabled=(i > 1),
                daily_sending_limit=50
            )
            db.add(acc)
            accounts.append(acc)
        db.commit()

        # Add an eligible pending thread to Account 2
        acc2 = accounts[1]
        p2 = ProspectModel(email="lead@success.com", sending_account_id=acc2.id)
        db.add(p2)
        db.flush()
        th2 = EmailThreadModel(
            sending_account_id=acc2.id,
            email_provider=acc2.provider_type,
            prospect_id=p2.id,
            recipient_address=p2.email,
            gmail_thread_id="th_acc2",
            original_subject="Followup Test",
            original_body="Body text",
            original_sent_at=now - timedelta(hours=76),
            status="PENDING",
            followup_count=0
        )
        db.add(th2)
        db.commit()

        # Run scheduler cycle
        AutomationEngine.run_hourly_job()

        # Verify Account 1 remained disconnected without crashing the engine
        acc1 = db.query(ConnectedEmailAccountModel).filter(ConnectedEmailAccountModel.id == accounts[0].id).first()
        assert acc1.connection_status == "DISCONNECTED"

        # Verify Account 2 processed successfully
        db.refresh(th2)
        assert th2.status in ["DUE FOR FOLLOW-UP", "FOLLOW-UP SENT"]
    finally:
        db.close()

# ------------------------------------------------------------------------------
# ACCEPTANCE TEST 10: Concurrency & duplicate prevention across background workers
# ------------------------------------------------------------------------------
def test_10_concurrent_duplicate_prevention():
    db = SessionLocal()
    try:
        now = utc_now()
        acc = ConnectedEmailAccountModel(
            email_address="busy.worker@domain.com",
            provider_type="SMTP_IMAP",
            encrypted_credentials=encrypt_credentials({"is_mock": True}),
            connection_status="CONNECTED",
            auto_followup_enabled=True,
            daily_sending_limit=50
        )
        db.add(acc)
        db.commit()

        prospect = ProspectModel(email="concurrency@test.com", sending_account_id=acc.id)
        db.add(prospect)
        db.flush()

        thread = EmailThreadModel(
            sending_account_id=acc.id,
            email_provider="SMTP_IMAP",
            prospect_id=prospect.id,
            recipient_address=prospect.email,
            gmail_thread_id="concurrent_thread_1",
            original_subject="Urgent follow-up",
            original_body="Initial cold pitch",
            original_sent_at=now - timedelta(hours=80),
            status="PENDING",
            followup_count=0
        )
        db.add(thread)
        db.commit()

        # Simulate two concurrent threads executing simultaneously for the same account
        results = []
        def worker_task():
            db_worker = SessionLocal()
            try:
                res = AutomationEngine.run_cycle_for_account(acc.id, db_worker)
                results.append(res)
            finally:
                db_worker.close()

        t1 = threading.Thread(target=worker_task)
        t2 = threading.Thread(target=worker_task)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # One worker acquired lock, the other safely received busy notification
        assert len(results) == 2
        statuses = [r.get("status") for r in results]
        assert "busy" in statuses or any(r.get("followups_drafted", 0) > 0 for r in results)

        # Thread must have received at most 1 follow-up action, never duplicated
        db.refresh(thread)
        assert thread.followup_count <= 1
    finally:
        db.close()
