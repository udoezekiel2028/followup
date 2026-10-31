import pytest
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.database import (
    SessionLocal, init_db, ConnectedEmailAccountModel, 
    ProspectModel, EmailThreadModel, EmailMessageModel, 
    AutomationSettingsModel, utc_now
)
from app.security import encrypt_credentials
from app.services.providers.hostinger_provider import HostingerEmailProvider
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    db = SessionLocal()
    try:
        db.query(EmailMessageModel).delete()
        db.query(EmailThreadModel).delete()
        db.query(ProspectModel).delete()
        db.query(ConnectedEmailAccountModel).delete()
        db.commit()
    finally:
        db.close()

def test_find_sent_folder_discovery():
    mock_imap = MagicMock()
    
    # 1. Hostinger Dovecot with dot delimiter and \Sent flag
    mock_imap.list.return_value = ("OK", [
        b'(\\HasNoChildren) "." "INBOX"',
        b'(\\HasNoChildren \\Sent) "." "INBOX.Sent"',
        b'(\\HasNoChildren \\Trash) "." "INBOX.Trash"',
    ])
    mock_imap.select.return_value = ("OK", [b"10"])
    sent = HostingerEmailProvider.find_sent_folder(mock_imap)
    assert sent == "INBOX.Sent"

    # 2. Hostinger Dovecot with slash delimiter and \Sent flag
    mock_imap.list.return_value = ("OK", [
        b'(\\HasNoChildren \\Sent) "/" "INBOX/Sent"',
    ])
    sent = HostingerEmailProvider.find_sent_folder(mock_imap)
    assert sent == "INBOX/Sent"

    # 3. Standard Sent folder
    mock_imap.list.return_value = ("OK", [
        b'(\\HasNoChildren) "/" "Sent"',
    ])
    sent = HostingerEmailProvider.find_sent_folder(mock_imap)
    assert sent == "Sent"

def test_hostinger_synchronize_mailbox_ingestion():
    db = SessionLocal()
    try:
        account = ConnectedEmailAccountModel(
            email_address="sales@myhostingerdomain.com",
            provider_type="HOSTINGER",
            provider_account_identifier="smtp.hostinger.com",
            authentication_type="PASSWORD",
            encrypted_credentials=encrypt_credentials({
                "smtp_host": "smtp.hostinger.com",
                "smtp_port": 465,
                "imap_host": "imap.hostinger.com",
                "imap_port": 993,
                "imap_username": "sales@myhostingerdomain.com",
                "imap_password": "secure_password",
                "is_mock": False
            }),
            connection_status="CONNECTED",
            auto_followup_enabled=True,
            daily_sending_limit=100
        )
        db.add(account)
        db.commit()

        provider = HostingerEmailProvider(account)

        # Mock IMAP session returning 2 outbound messages:
        # Message 1: Genuine cold outreach to a lead
        # Message 2: Self-sent email (should be skipped)
        raw_cold_email = (
            b"Message-ID: <test-cold-123@myhostingerdomain.com>\r\n"
            b"From: sales@myhostingerdomain.com\r\n"
            b"To: Jane Doe <jane@acmecorp.com>\r\n"
            b"Subject: Quick question regarding growth strategy\r\n"
            b"Date: Mon, 20 Oct 2026 10:00:00 +0000\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hi Jane, I came across Acme Corp and loved your recent launch. Would you be open to a quick 10-minute chat?"
        )

        raw_self_email = (
            b"Message-ID: <test-self-999@myhostingerdomain.com>\r\n"
            b"From: sales@myhostingerdomain.com\r\n"
            b"To: sales@myhostingerdomain.com\r\n"
            b"Subject: Note to self\r\n"
            b"Date: Tue, 21 Oct 2026 10:00:00 +0000\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Remember to buy groceries."
        )

        mock_imap_instance = MagicMock()
        mock_imap_instance.list.return_value = ("OK", [b'(\\HasNoChildren \\Sent) "." "INBOX.Sent"'])
        mock_imap_instance.select.return_value = ("OK", [b"2"])
        mock_imap_instance.search.side_effect = [
            ("OK", [b"1 2"]),  # Sent folder search
            ("OK", [b""]),     # INBOX reply search
        ]
        mock_imap_instance.fetch.side_effect = [
            ("OK", [(b"2", raw_self_email)]),
            ("OK", [(b"1", raw_cold_email)]),
        ]

        with patch("imaplib.IMAP4_SSL", return_value=mock_imap_instance):
            result = provider.synchronize_mailbox(db)

        assert result["identified_cold_emails"] == 1
        assert result["scanned"] == 2

        # Verify DB records
        thread = db.query(EmailThreadModel).filter(
            EmailThreadModel.recipient_address == "jane@acmecorp.com"
        ).first()
        assert thread is not None
        assert thread.sending_account_id == account.id
        assert thread.original_subject == "Quick question regarding growth strategy"
        assert thread.status == "DUE FOR FOLLOW-UP"  # Sent in past (> 72 hours)
        assert thread.prospect is not None
        assert thread.prospect.name == "Jane Doe" or thread.prospect.name == "Jane"
        assert thread.prospect.company == "Acmecorp"

        # Verify EmailMessageModel
        msg = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_record_id == thread.id
        ).first()
        assert msg is not None
        assert msg.message_type == "OUTBOUND_INITIAL"
        assert "Hi Jane" in msg.body

    finally:
        db.close()

def test_sync_sent_and_sync_now_endpoints():
    response = client.post("/api/automation/sync-sent")
    assert response.status_code == 200
    data = response.json()
    assert "identified_cold_emails" in data
    assert "message" in data

    response_now = client.post("/api/automation/sync-now")
    assert response_now.status_code == 200
    data_now = response_now.json()
    assert "identified_cold_emails" in data_now
