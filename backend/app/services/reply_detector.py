from email.utils import parseaddr, parsedate_to_datetime
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session
from app.database import (
    ConnectedEmailAccountModel, ProspectModel, EmailThreadModel, 
    EmailMessageModel, SuppressionModel, ActivityLogModel, utc_now
)
from app.services.oauth_service import GoogleOAuthService
from app.services.gmail_monitor import GmailMonitorService

class ReplyDetectorService:
    BOUNCE_INDICATORS = [
        "delivery status notification (failure)",
        "undelivered mail returned to sender",
        "550 5.1.1",
        "user unknown",
        "mailbox not found",
        "mailbox unavailable",
        "address not found",
        "host or domain name not found",
        "message blocked",
        "rejected your message",
        "permanent failure"
    ]

    UNSUBSCRIBE_INDICATORS = [
        "unsubscribe",
        "remove me",
        "please remove",
        "do not contact",
        "stop emailing",
        "not interested",
        "opt out",
        "take me off",
        "leave me alone"
    ]

    OOO_INDICATORS = [
        "out of office",
        "automatic reply",
        "auto-reply",
        "away from my email",
        "away from my desk",
        "annual leave",
        "maternity leave",
        "paternity leave",
        "out of the office",
        "on vacation",
        "limited access to email"
    ]

    @classmethod
    def classify_message_content(cls, sender: str, subject: str, body: str) -> Optional[str]:
        """
        Classifies incoming message content into:
        'BOUNCED', 'UNSUBSCRIBED', 'OOO', or None (genuine message).
        """
        sender_lower = (sender or "").lower()
        subject_lower = (subject or "").lower()
        body_lower = (body or "").lower()
        combined = f"{sender_lower} {subject_lower} {body_lower}"

        # 1. Check Bounce / Mailer-Daemon
        if "mailer-daemon" in sender_lower or "postmaster" in sender_lower:
            return "BOUNCED"
        for phrase in cls.BOUNCE_INDICATORS:
            if phrase in combined:
                return "BOUNCED"

        # 2. Check Opt-Out / Unsubscribe
        for phrase in cls.UNSUBSCRIBE_INDICATORS:
            if phrase in combined:
                return "UNSUBSCRIBED"

        # 3. Check Out-of-Office (OOO)
        for phrase in cls.OOO_INDICATORS:
            if phrase in subject_lower or phrase in body_lower[:300]:
                return "OOO"

        return None

    # Backward-compatible alias for bounce/optout check
    check_for_bounce_or_optout = classify_message_content

    @classmethod
    def inspect_thread(cls, thread: EmailThreadModel, db: Session) -> Dict[str, Any]:
        """
        Inspects the conversation thread strictly within the original sending mailbox.
        Distinguishes genuine prospect replies from bounces, OOO, and user's own sent emails.
        Delegates to ImapSmtpEmailProvider if the thread belongs to an SMTP/IMAP account.
        """
        # Resolve original sending account
        account = thread.sending_account
        if not account and thread.sending_account_id:
            account = db.query(ConnectedEmailAccountModel).filter(
                ConnectedEmailAccountModel.id == thread.sending_account_id
            ).first()
        if not account:
            account = db.query(ConnectedEmailAccountModel).first()

        result = {
            "thread_id": thread.gmail_thread_id,
            "has_replied": False,
            "status_updated": False,
            "new_status": thread.status,
            "reply_snippet": None
        }

        # Terminal statuses
        if thread.status in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED", "STOPPED"]:
            return result

        if not account or account.status not in ["ACTIVE", "CONNECTED"]:
            return result

        # Delegate to SMTP/IMAP provider if this is a professional domain account
        if account.provider_type == "SMTP_IMAP":
            from app.services.providers.imap_smtp_provider import ImapSmtpEmailProvider
            provider = ImapSmtpEmailProvider(account)
            rep_res = provider.check_for_reply(thread, db)
            if rep_res.get("status") in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED"]:
                result["has_replied"] = (rep_res.get("status") == "RESPONDED")
                result["status_updated"] = True
                result["new_status"] = rep_res.get("status")
                result["reply_snippet"] = rep_res.get("reply_snippet")
            return result

        # GMAIL INSPECTION
        try:
            service = GoogleOAuthService.get_gmail_service(account, db)
            thread_data = service.users().threads().get(
                userId='me',
                id=thread.gmail_thread_id,
                format='full'
            ).execute()

            messages = thread_data.get('messages', [])
            prospect = thread.prospect
            prospect_email = (prospect.email if prospect else "").lower().strip()
            my_gmail = (account.email_address or account.gmail_address or "").lower().strip()
            original_sent_at = thread.original_sent_at

            for msg in messages:
                msg_id = msg['id']
                payload = msg.get('payload', {})
                raw_headers = payload.get('headers', [])
                headers_dict = {h['name']: h['value'] for h in raw_headers}

                from_header = headers_dict.get('From', '')
                to_header = headers_dict.get('To', '')
                date_header = headers_dict.get('Date', '')
                subject_header = headers_dict.get('Subject', '')

                _, sender_clean = GmailMonitorService.clean_email(from_header)
                _, recipient_clean = GmailMonitorService.clean_email(to_header)

                try:
                    msg_sent_at = parsedate_to_datetime(date_header).astimezone(timezone.utc)
                except Exception:
                    internal_ms = int(msg.get('internalDate', 0))
                    msg_sent_at = datetime.fromtimestamp(internal_ms / 1000.0, tz=timezone.utc) if internal_ms else utc_now()

                text_body, html_body = GmailMonitorService.extract_body_from_payload(payload)
                body_content = text_body or msg.get('snippet', '')

                # 1. Strictly exclude messages sent by my connected Gmail account
                if sender_clean == my_gmail:
                    continue

                # 2. Only examine messages timestamped AFTER initial outreach
                if msg_sent_at <= original_sent_at:
                    continue

                # 3. Classify incoming message
                classification = cls.classify_message_content(sender_clean, subject_header, body_content)

                if classification == "BOUNCED":
                    thread.status = "BOUNCED"
                    if prospect:
                        prospect.status = "BOUNCED"
                    # Add to suppression list
                    suppression = SuppressionModel(
                        user_id=thread.user_id,
                        email=prospect_email,
                        reason="BOUNCED"
                    )
                    db.merge(suppression)
                    db.commit()

                    result["new_status"] = "BOUNCED"
                    result["status_updated"] = True
                    result["reply_snippet"] = body_content[:150]

                    act = ActivityLogModel(
                        user_id=thread.user_id,
                        action="EMAIL_BOUNCED",
                        description=f"Outreach bounced for {prospect_email} in mailbox {account.email_address}. Suppressed."
                    )
                    db.add(act)
                    db.commit()
                    return result

                elif classification == "UNSUBSCRIBED":
                    thread.status = "UNSUBSCRIBED"
                    if prospect:
                        prospect.status = "UNSUBSCRIBED"
                    suppression = SuppressionModel(
                        user_id=thread.user_id,
                        email=prospect_email,
                        reason="UNSUBSCRIBED"
                    )
                    db.merge(suppression)
                    db.commit()

                    result["new_status"] = "UNSUBSCRIBED"
                    result["status_updated"] = True
                    result["reply_snippet"] = body_content[:150]

                    act = ActivityLogModel(
                        user_id=thread.user_id,
                        action="PROSPECT_UNSUBSCRIBED",
                        description=f"Prospect {prospect_email} opted out in mailbox {account.email_address}. Suppressed."
                    )
                    db.add(act)
                    db.commit()
                    return result

                elif classification == "OOO":
                    # Mark OOO inbound message without stopping future follow-up
                    existing = db.query(EmailMessageModel).filter(
                        EmailMessageModel.gmail_message_id == msg_id
                    ).first()
                    if not existing:
                        ooo_msg = EmailMessageModel(
                            sending_account_id=account.id,
                            thread_record_id=thread.id,
                            gmail_message_id=msg_id,
                            sender=sender_clean,
                            recipient=recipient_clean,
                            subject=subject_header,
                            body=body_content,
                            message_type="INBOUND_OOO",
                            sent_at=msg_sent_at
                        )
                        db.add(ooo_msg)
                        db.commit()
                    continue

                # 4. Genuine Prospect Reply Detected
                now_utc = utc_now()
                thread.status = "RESPONDED"
                thread.replied_at = msg_sent_at
                if prospect:
                    prospect.status = "RESPONDED"

                # Record message
                existing = db.query(EmailMessageModel).filter(
                    EmailMessageModel.gmail_message_id == msg_id
                ).first()
                if not existing:
                    reply_msg = EmailMessageModel(
                        sending_account_id=account.id,
                        thread_record_id=thread.id,
                        gmail_message_id=msg_id,
                        sender=sender_clean,
                        recipient=recipient_clean,
                        subject=subject_header,
                        body=body_content,
                        message_type="INBOUND_REPLY",
                        sent_at=msg_sent_at
                    )
                    db.add(reply_msg)

                # Remove AUTO_FOLLOWUP label from Gmail thread since prospect replied
                try:
                    from app.services.label_manager import GmailLabelManager
                    GmailLabelManager.remove_auto_followup_label(service, thread.gmail_thread_id)
                except Exception:
                    pass

                db.commit()

                act = ActivityLogModel(
                    user_id=thread.user_id,
                    action="REPLY_RECEIVED",
                    description=f"Genuine reply detected from {prospect_email} in mailbox {account.email_address}. Follow-ups halted."
                )
                db.add(act)
                db.commit()

                result["has_replied"] = True
                result["status_updated"] = True
                result["new_status"] = "RESPONDED"
                result["reply_snippet"] = body_content[:150]
                return result

        except Exception as e:
            # Safe non-fatal error handling
            print(f"Error inspecting thread {thread.gmail_thread_id} in mailbox {account.email_address}: {e}")

        return result
