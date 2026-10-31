from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from app.database import (
    get_db, ConnectedEmailAccountModel, ProspectModel, 
    EmailThreadModel, EmailMessageModel, FollowUpLogModel,
    AutomationSettingsModel, ActivityLogModel, utc_now
)
from app.services.scheduler import AutomationEngine
from app.security import encrypt_credentials

router = APIRouter(prefix="/api/automation", tags=["Automation Engine"])

@router.get("/status")
def get_automation_status(db: Session = Depends(get_db)):
    active_accounts = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"])
    ).all()
    settings = db.query(AutomationSettingsModel).first()

    return {
        "scheduler_running": AutomationEngine.scheduler.running,
        "total_connected_accounts": len(active_accounts),
        "accounts": [
            {
                "id": a.id,
                "email_address": a.email_address,
                "provider_type": a.provider_type,
                "connection_status": a.connection_status,
                "auto_followup_enabled": a.auto_followup_enabled,
                "daily_sent_count": a.daily_sent_count,
                "daily_sending_limit": a.daily_sending_limit
            }
            for a in active_accounts
        ],
        "test_mode": settings.test_mode if settings else True,
        "auto_send_enabled": settings.auto_send_enabled if settings else False,
        "followup_delay_hours": settings.followup_delay_hours if settings else 72
    }

@router.post("/run-cycle")
def trigger_manual_automation_cycle(
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Manually triggers an automation cycle across all active mailboxes or an individual account.
    """
    if account_id and account_id != "ALL":
        target = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.id == account_id
        ).first()
        if not target:
            raise HTTPException(status_code=404, detail="Account not found")
        return AutomationEngine.run_cycle_for_account(target.id, db)

    # Run across all connected mailboxes
    active_accounts = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"])
    ).all()

    if not active_accounts:
        raise HTTPException(
            status_code=400, 
            detail="No active email accounts connected. Connect an account or seed demo accounts."
        )

    summaries = []
    for acc in active_accounts:
        try:
            res = AutomationEngine.run_cycle_for_account(acc.id, db)
            summaries.append(res)
        except Exception as e:
            summaries.append({
                "account_id": acc.id,
                "email_address": acc.email_address,
                "error": str(e)
            })

    return {"cycles": summaries, "total_processed_mailboxes": len(active_accounts)}

@router.post("/seed-demo")
def seed_demo_data(db: Session = Depends(get_db)):
    """
    Seeds the initial 6 Connected Mailboxes:
    - 4 Gmail / Google Workspace accounts
    - 2 Professional Domain Email accounts (SMTP/IMAP)
    Along with realistic cold outreach threads, replies, and follow-up states.
    """
    # 1. Ensure Global Automation Settings exist
    settings_model = db.query(AutomationSettingsModel).first()
    if not settings_model:
        settings_model = AutomationSettingsModel(
            followup_delay_hours=72,
            sending_window="09:00-17:00",
            timezone="America/New_York",
            maximum_followups=1,
            auto_send_enabled=False,
            test_mode=True
        )
        db.add(settings_model)
        db.commit()

    # 2. Define the 6 Initial Mailboxes
    mailboxes_spec = [
        {
            "email": "sarah.outreach@growthscale.io",
            "provider": "GMAIL",
            "auth": "OAUTH2",
            "creds": {"token": "mock_oauth_token_1", "refresh_token": "mock_refresh_1"},
            "limit": 50,
            "identifier": "google_sub_101"
        },
        {
            "email": "alex.sales@growthscale.io",
            "provider": "GMAIL",
            "auth": "OAUTH2",
            "creds": {"token": "mock_oauth_token_2", "refresh_token": "mock_refresh_2"},
            "limit": 50,
            "identifier": "google_sub_102"
        },
        {
            "email": "marcus.bdr@growthscale.io",
            "provider": "GMAIL",
            "auth": "OAUTH2",
            "creds": {"token": "mock_oauth_token_3", "refresh_token": "mock_refresh_3"},
            "limit": 40,
            "identifier": "google_sub_103"
        },
        {
            "email": "partnerships@growthscale.io",
            "provider": "GMAIL",
            "auth": "OAUTH2",
            "creds": {"token": "mock_oauth_token_4", "refresh_token": "mock_refresh_4"},
            "limit": 30,
            "identifier": "google_sub_104"
        },
        {
            "email": "david@acmeenterprises.com",
            "provider": "SMTP_IMAP",
            "auth": "PASSWORD",
            "creds": {
                "smtp_host": "smtp.acmeenterprises.com",
                "smtp_port": 465,
                "smtp_username": "david@acmeenterprises.com",
                "smtp_password": "app_password_david",
                "smtp_encryption": "SSL",
                "imap_host": "imap.acmeenterprises.com",
                "imap_port": 993,
                "imap_username": "david@acmeenterprises.com",
                "imap_password": "app_password_david",
                "imap_encryption": "SSL",
                "is_mock": True
            },
            "limit": 100,
            "identifier": "smtp.acmeenterprises.com"
        },
        {
            "email": "enterprise@cloudcraftsystems.com",
            "provider": "SMTP_IMAP",
            "auth": "PASSWORD",
            "creds": {
                "smtp_host": "mail.cloudcraftsystems.com",
                "smtp_port": 587,
                "smtp_username": "enterprise@cloudcraftsystems.com",
                "smtp_password": "app_password_cloudcraft",
                "smtp_encryption": "STARTTLS",
                "imap_host": "mail.cloudcraftsystems.com",
                "imap_port": 993,
                "imap_username": "enterprise@cloudcraftsystems.com",
                "imap_password": "app_password_cloudcraft",
                "imap_encryption": "SSL",
                "is_mock": True
            },
            "limit": 150,
            "identifier": "mail.cloudcraftsystems.com"
        }
    ]

    account_map = {}
    for spec in mailboxes_spec:
        acc = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.email_address == spec["email"]
        ).first()

        enc_creds = encrypt_credentials(spec["creds"])
        if not acc:
            acc = ConnectedEmailAccountModel(
                email_address=spec["email"],
                provider_type=spec["provider"],
                provider_account_identifier=spec["identifier"],
                authentication_type=spec["auth"],
                encrypted_credentials=enc_creds,
                encrypted_access_token="enc_sample_token",
                encrypted_refresh_token="enc_sample_refresh",
                connection_status="CONNECTED",
                auto_followup_enabled=True,
                daily_sending_limit=spec["limit"],
                daily_sent_count=0,
                last_sync_at=utc_now()
            )
            db.add(acc)
            db.flush()
        else:
            acc.provider_type = spec["provider"]
            acc.authentication_type = spec["auth"]
            acc.encrypted_credentials = enc_creds
            acc.connection_status = "CONNECTED"
            acc.auto_followup_enabled = True
            acc.last_sync_at = utc_now()
            db.flush()

        account_map[spec["email"]] = acc

    db.commit()

    now = utc_now()
    t_76h = now - timedelta(hours=76)
    t_24h = now - timedelta(hours=24)
    t_85h = now - timedelta(hours=85)
    t_92h = now - timedelta(hours=92)
    t_96h = now - timedelta(hours=96)

    # 3. Create realistic threads attached to their respective sending accounts
    sample_threads = [
        # Mailbox 1: sarah.outreach@growthscale.io
        {
            "account": account_map["sarah.outreach@growthscale.io"],
            "name": "Sarah Jenkins",
            "email": "sarah.jenkins@zenithproperty.io",
            "company": "Zenith Property Management",
            "subject": "Automating tenant response times for Zenith Property",
            "body": "Hi Sarah,\n\nI noticed Zenith Property manages hundreds of residential units. I believe there may be an opportunity to help your team automate lead management and improve tenant response times.\n\nWould you be open to a quick 10-minute conversation?\n\nBest regards,\nSarah",
            "thread_id": "sf_thread_g1_01",
            "msg_id": "sf_msg_g1_01",
            "sent_at": t_76h,
            "status": "DUE FOR FOLLOW-UP",
            "has_reply": False
        },
        {
            "account": account_map["sarah.outreach@growthscale.io"],
            "name": "Marcus Vance",
            "email": "marcus.v@apexlogistics.com",
            "company": "Apex Logistics Group",
            "subject": "Supply chain automation question for Apex",
            "body": "Hi Marcus,\n\nSaw Apex Logistics expanded into cross-docking recently. We help 3PL logistics brokers automate dispatch updates.\n\nWould you be open to a brief chat next Tuesday?\n\nBest,\nSarah",
            "thread_id": "sf_thread_g1_02",
            "msg_id": "sf_msg_g1_02",
            "sent_at": t_85h,
            "status": "RESPONDED",
            "has_reply": True,
            "reply_body": "Hey Sarah, thanks for reaching out. Yes, we are actually reviewing dispatch software this month. Could you send over a deck?"
        },
        # Mailbox 2: alex.sales@growthscale.io
        {
            "account": account_map["alex.sales@growthscale.io"],
            "name": "Dr. Emily Watson",
            "email": "e.watson@horizonhealth.org",
            "company": "Horizon Health Clinic",
            "subject": "Patient booking follow-up workflow for Horizon",
            "body": "Hi Dr. Watson,\n\nI noticed Horizon Health clinic recently expanded your telehealth practice. Are you currently automating patient reminders?\n\nBest,\nAlex",
            "thread_id": "sf_thread_g2_01",
            "msg_id": "sf_msg_g2_01",
            "sent_at": t_76h,
            "status": "DUE FOR FOLLOW-UP",
            "has_reply": False
        },
        {
            "account": account_map["alex.sales@growthscale.io"],
            "name": "Liam Scott",
            "email": "liam@bluecoastventures.com",
            "company": "Blue Coast Ventures",
            "subject": "Quick intro - portfolio workflow automation",
            "body": "Hi Liam,\n\nHope your week is going well. We help VC operations automate founder reporting updates.\n\nBest,\nAlex",
            "thread_id": "sf_thread_g2_02",
            "msg_id": "sf_msg_g2_02",
            "sent_at": t_24h,
            "status": "PENDING",
            "has_reply": False
        },
        # Mailbox 3: marcus.bdr@growthscale.io
        {
            "account": account_map["marcus.bdr@growthscale.io"],
            "name": "Invalid Recipient",
            "email": "nonexistent.user999@badhostdomain.org",
            "company": "Obsolete Corp",
            "subject": "Partnership inquiry",
            "body": "Hi team,\n\nReaching out regarding a potential collaboration.",
            "thread_id": "sf_thread_g3_01",
            "msg_id": "sf_msg_g3_01",
            "sent_at": t_92h,
            "status": "BOUNCED",
            "has_reply": False,
            "is_bounce": True
        },
        # Mailbox 4: partnerships@growthscale.io
        {
            "account": account_map["partnerships@growthscale.io"],
            "name": "Elena Rostova",
            "email": "elena.r@innovatetech.io",
            "company": "InnovateTech Global",
            "subject": "Integration partnership with InnovateTech",
            "body": "Hi Elena,\n\nLoved your recent release on automated webhooks. Would love to explore a tech partnership.\n\nBest,\nPartnerships Team",
            "thread_id": "sf_thread_g4_01",
            "msg_id": "sf_msg_g4_01",
            "sent_at": t_96h,
            "status": "FOLLOW-UP SENT",
            "has_reply": False,
            "followup_already_sent": True
        },
        # Mailbox 5 (Professional Domain SMTP/IMAP): david@acmeenterprises.com
        {
            "account": account_map["david@acmeenterprises.com"],
            "name": "Rachel Adams",
            "email": "rachel@peakmanufacturing.com",
            "company": "Peak Manufacturing Inc",
            "subject": "ERP integration inquiry for Peak Manufacturing",
            "body": "Hi Rachel,\n\nI noticed Peak Manufacturing upgraded plant operations in Chicago. We provide custom ERP sync connectors.\n\nWould you be open to connecting?\n\nBest regards,\nDavid",
            "thread_id": "sf_thread_p1_01",
            "msg_id": "sf_msg_p1_01",
            "sent_at": t_76h,
            "status": "DUE FOR FOLLOW-UP",
            "has_reply": False
        },
        {
            "account": account_map["david@acmeenterprises.com"],
            "name": "Oliver Zhang",
            "email": "oliver@vertexholdings.com",
            "company": "Vertex Holdings",
            "subject": "Acquisition sourcing workflow",
            "body": "Hi Oliver,\n\nReaching out to see if Vertex Holdings is reviewing pipeline automation tools this quarter.\n\nBest,\nDavid",
            "thread_id": "sf_thread_p1_02",
            "msg_id": "sf_msg_p1_02",
            "sent_at": t_85h,
            "status": "RESPONDED",
            "has_reply": True,
            "reply_body": "David, sounds interesting. Let's schedule a call on Thursday at 2 PM."
        },
        # Mailbox 6 (Professional Domain SMTP/IMAP): enterprise@cloudcraftsystems.com
        {
            "account": account_map["enterprise@cloudcraftsystems.com"],
            "name": "Thomas Thorne",
            "email": "t.thorne@cyberfortress.net",
            "company": "CyberFortress Security",
            "subject": "Cloud compliance automation for CyberFortress",
            "body": "Hi Thomas,\n\nI noticed CyberFortress manages SOC2 and ISO compliance audits. Would love to show you how CloudCraft automates evidence collection.\n\nBest,\nEnterprise Solutions",
            "thread_id": "sf_thread_p2_01",
            "msg_id": "sf_msg_p2_01",
            "sent_at": t_76h,
            "status": "DUE FOR FOLLOW-UP",
            "has_reply": False
        },
        {
            "account": account_map["enterprise@cloudcraftsystems.com"],
            "name": "Gary Mitchell",
            "email": "gary.m@legacyoptout.com",
            "company": "Legacy Systems",
            "subject": "Infrastructure modernizing query",
            "body": "Hi Gary, reaching out regarding legacy migration.",
            "thread_id": "sf_thread_p2_02",
            "msg_id": "sf_msg_p2_02",
            "sent_at": t_92h,
            "status": "UNSUBSCRIBED",
            "has_reply": True,
            "reply_body": "Please remove me from your list and do not contact me again."
        }
    ]

    for item in sample_threads:
        acc = item["account"]
        existing_th = db.query(EmailThreadModel).filter(
            EmailThreadModel.gmail_thread_id == item["thread_id"]
        ).first()

        if not existing_th:
            # 1. Prospect
            prospect = ProspectModel(
                user_id=acc.user_id,
                sending_account_id=acc.id,
                name=item["name"],
                email=item["email"],
                company=item["company"],
                status=item["status"]
            )
            db.add(prospect)
            db.flush()

            # 2. Thread
            thread = EmailThreadModel(
                user_id=acc.user_id,
                sending_account_id=acc.id,
                email_provider=acc.provider_type,
                prospect_id=prospect.id,
                recipient_address=item["email"],
                gmail_thread_id=item["thread_id"],
                gmail_original_message_id=item["msg_id"],
                original_message_id=item["msg_id"],
                original_subject=item["subject"],
                original_body=item["body"],
                original_sent_at=item["sent_at"],
                next_followup_at=item["sent_at"] + timedelta(hours=72),
                followup_count=1 if item.get("followup_already_sent") else 0,
                status=item["status"],
                replied_at=now - timedelta(hours=2) if item.get("has_reply") else None
            )
            db.add(thread)
            db.flush()

            # 3. Outbound Initial Message
            msg = EmailMessageModel(
                sending_account_id=acc.id,
                thread_record_id=thread.id,
                gmail_message_id=item["msg_id"],
                sender=acc.email_address,
                recipient=item["email"],
                subject=item["subject"],
                body=item["body"],
                message_type="OUTBOUND_INITIAL",
                sent_at=item["sent_at"]
            )
            db.add(msg)

            # Inbound Reply or Bounce
            if item.get("has_reply"):
                reply_type = "UNSUBSCRIBED" if item.get("status") == "UNSUBSCRIBED" else "INBOUND_REPLY"
                rep = EmailMessageModel(
                    sending_account_id=acc.id,
                    thread_record_id=thread.id,
                    gmail_message_id=f"rep_{item['msg_id']}",
                    sender=item["email"],
                    recipient=acc.email_address,
                    subject=f"Re: {item['subject']}",
                    body=item.get("reply_body", "Yes, let's connect."),
                    message_type=reply_type,
                    sent_at=now - timedelta(hours=2)
                )
                db.add(rep)

            if item.get("is_bounce"):
                bnc = EmailMessageModel(
                    sending_account_id=acc.id,
                    thread_record_id=thread.id,
                    gmail_message_id=f"bounce_{item['msg_id']}",
                    sender="mailer-daemon@googlemail.com",
                    recipient=acc.email_address,
                    subject="Delivery Status Notification (Failure)",
                    body="550 5.1.1 The email account that you tried to reach does not exist.",
                    message_type="INBOUND_BOUNCE",
                    sent_at=now - timedelta(hours=70)
                )
                db.add(bnc)

            if item.get("followup_already_sent"):
                fup = FollowUpLogModel(
                    sending_account_id=acc.id,
                    email_thread_id=thread.id,
                    generated_content="Hi Elena, just following up on my previous note. Would love to explore this.",
                    gmail_message_id=f"fup_{item['msg_id']}",
                    sent_at=now - timedelta(hours=12),
                    status="SENT"
                )
                db.add(fup)

    db.commit()

    return {
        "message": "Successfully seeded initial 6 connected mailboxes (4 Gmail + 2 Professional SMTP/IMAP) and realistic outreach conversations.",
        "connected_mailboxes_count": len(account_map),
        "mailboxes": list(account_map.keys())
    }
