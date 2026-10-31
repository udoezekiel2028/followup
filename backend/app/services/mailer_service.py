import base64
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database import (
    ConnectedEmailAccountModel, ProspectModel, EmailThreadModel, 
    EmailMessageModel, FollowUpLogModel, SuppressionModel, 
    AutomationSettingsModel, ActivityLogModel, utc_now
)
from app.services.oauth_service import GoogleOAuthService
from app.services.ai_followup import AIFollowUpService
from app.services.reply_detector import ReplyDetectorService

class MailerService:
    @staticmethod
    def create_in_thread_mime_message(
        sender: str,
        to: str,
        subject: str,
        body_text: str,
        original_msg_id: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Builds RFC 5322 compliant email configured strictly to reply inside an existing Gmail thread.
        Sets In-Reply-To and References headers.
        """
        message = MIMEText(body_text, 'plain', 'utf-8')
        message['to'] = to
        message['from'] = sender
        
        # Ensure subject starts with Re:
        clean_subj = subject
        if not clean_subj.lower().startswith('re:'):
            clean_subj = f"Re: {clean_subj}"
        message['subject'] = clean_subj

        if original_msg_id:
            # Format message-id for In-Reply-To and References
            rfc_msg_id = original_msg_id if original_msg_id.startswith('<') else f"<{original_msg_id}@mail.gmail.com>"
            message['In-Reply-To'] = rfc_msg_id
            message['References'] = rfc_msg_id

        raw_bytes = message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode('utf-8')

        payload: Dict[str, Any] = {'raw': raw_b64}
        if thread_id:
            payload['threadId'] = thread_id

        return payload

    @classmethod
    def execute_follow_up_for_thread(
        cls, 
        thread: EmailThreadModel, 
        db: Session,
        force_live_send: bool = False,
        manual_override_body: Optional[str] = None,
        manual_override_subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes follow-up logic for an email thread with multi-account support:
        1. Pre-flight check: status, suppression, follow-up count.
        2. Resolves exact sending account (strictly from original sending mailbox).
        3. If SMTP/IMAP account, delegates to ImapSmtpEmailProvider.
        4. Pre-send race condition verification: recheck thread for replies immediately before dispatch.
        5. Generates AI content.
        6. If TEST MODE: saves draft in database/follow_up_logs with sending_account_id.
        7. If LIVE SEND: checks daily sending limits, sends via Gmail API, validates returned threadId.
        """
        # Resolve original sending account
        account = thread.sending_account
        if not account and thread.sending_account_id:
            account = db.query(ConnectedEmailAccountModel).filter(
                ConnectedEmailAccountModel.id == thread.sending_account_id
            ).first()
        if not account:
            account = db.query(ConnectedEmailAccountModel).first()

        settings_model = db.query(AutomationSettingsModel).first()
        prospect = thread.prospect
        prospect_email = (prospect.email if prospect else "").lower().strip()

        result = {
            "thread_id": thread.gmail_thread_id,
            "success": False,
            "status": thread.status,
            "is_test_mode": True,
            "message": ""
        }

        # 1. Terminal status check
        if thread.status in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED", "STOPPED", "FOLLOW-UP SENT"]:
            result["message"] = f"Thread is in terminal status: {thread.status}. Follow-up aborted."
            return result

        # 2. Maximum follow-ups check (default 1)
        max_followups = settings_model.maximum_followups if settings_model else 1
        if thread.followup_count >= max_followups:
            result["message"] = f"Maximum follow-up limit ({max_followups}) already reached. Aborted."
            return result

        # 3. Suppression check
        is_suppressed = db.query(SuppressionModel).filter(
            (SuppressionModel.email == prospect_email) |
            (SuppressionModel.email == prospect_email.split('@')[-1])
        ).first()

        if is_suppressed:
            thread.status = "UNSUBSCRIBED"
            if prospect:
                prospect.status = "UNSUBSCRIBED"
            db.commit()
            result["message"] = f"Recipient is on suppression list ({is_suppressed.reason}). Aborted."
            return result

        # Determine Test Mode vs Live
        is_test_mode = True
        if force_live_send:
            is_test_mode = False
        elif settings_model:
            is_test_mode = settings_model.test_mode or (not settings_model.auto_send_enabled)

        # 4. Generate AI Follow-Up Content (or use manual overrides)
        if manual_override_body:
            subject = manual_override_subject or f"Re: {thread.original_subject}"
            body = manual_override_body
        else:
            ai_data = AIFollowUpService.generate_follow_up(prospect, settings_model)
            subject = ai_data["subject"]
            body = ai_data["body"]

        # Delegate to SMTP/IMAP provider if this is a professional domain email account
        if account and account.provider_type == "SMTP_IMAP":
            from app.services.providers.imap_smtp_provider import ImapSmtpEmailProvider
            provider = ImapSmtpEmailProvider(account)
            return provider.send_followup(thread, body, db, test_mode=is_test_mode)

        # 5. PRE-SEND RACE GUARD: Recheck for reply immediately before sending
        if account and account.status in ["ACTIVE", "CONNECTED"]:
            recheck = ReplyDetectorService.inspect_thread(thread, db)
            if recheck.get("has_replied") or thread.status in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED"]:
                result["message"] = f"Pre-send check detected status changed to {thread.status}. Follow-up aborted."
                result["status"] = thread.status
                return result

        result["is_test_mode"] = is_test_mode

        # Create Follow-Up Log
        follow_up_log = FollowUpLogModel(
            sending_account_id=account.id if account else None,
            email_thread_id=thread.id,
            generated_content=body,
            status="DRAFT" if is_test_mode else "PENDING"
        )
        db.add(follow_up_log)
        db.flush()

        # 6. Test Mode: Save Draft Only
        if is_test_mode:
            thread.status = "DUE FOR FOLLOW-UP"
            thread.last_followup_at = utc_now()
            follow_up_log.status = "DRAFT"
            db.commit()

            act = ActivityLogModel(
                user_id=thread.user_id,
                action="FOLLOW_UP_DRAFTED",
                description=f"[TEST MODE] AI Follow-up draft created for {prospect_email} in thread {thread.gmail_thread_id} from {account.email_address if account else 'default'}. Not dispatched."
            )
            db.add(act)
            db.commit()

            result["success"] = True
            result["status"] = "DUE FOR FOLLOW-UP"
            result["draft_id"] = follow_up_log.id
            result["message"] = "Test mode active: Generated follow-up draft without live sending."
            return result

        # 7. Live Sending Mode via Gmail API
        if not account or account.status not in ["ACTIVE", "CONNECTED"]:
            result["message"] = "No active Gmail account connected for live sending."
            return result

        # Check account daily sending quota
        if account.daily_sent_count >= account.daily_sending_limit:
            result["message"] = f"Daily sending limit reached for {account.email_address} ({account.daily_sending_limit} sent today). Follow-up queued."
            return result

        try:
            service = GoogleOAuthService.get_gmail_service(account, db)

            mime_payload = cls.create_in_thread_mime_message(
                sender=account.email_address,
                to=prospect_email,
                subject=subject,
                body_text=body,
                original_msg_id=thread.gmail_original_message_id,
                thread_id=thread.gmail_thread_id
            )

            sent_res = service.users().messages().send(
                userId='me',
                body=mime_payload
            ).execute()

            returned_thread_id = sent_res.get('threadId')
            new_msg_id = sent_res.get('id')

            # CRITICAL VERIFICATION: Ensure Gmail attached to expected thread
            if returned_thread_id != thread.gmail_thread_id:
                follow_up_log.status = "FAILED"
                follow_up_log.error_message = f"Thread mismatch: Expected {thread.gmail_thread_id}, received {returned_thread_id}"
                db.commit()
                result["message"] = "Gmail failed to attach follow-up to original thread. Aborted."
                return result

            now_utc = utc_now()

            # Update records
            follow_up_log.status = "SENT"
            follow_up_log.sent_at = now_utc
            follow_up_log.gmail_message_id = new_msg_id

            thread.status = "FOLLOW-UP SENT"
            thread.followup_count += 1
            thread.last_followup_at = now_utc
            account.daily_sent_count += 1

            if prospect:
                prospect.status = "FOLLOW-UP SENT"

            # Record message
            out_msg = EmailMessageModel(
                sending_account_id=account.id,
                thread_record_id=thread.id,
                gmail_message_id=new_msg_id,
                sender=account.email_address,
                recipient=prospect_email,
                subject=subject,
                body=body,
                message_type="OUTBOUND_FOLLOWUP",
                sent_at=now_utc
            )
            db.add(out_msg)
            db.commit()

            act = ActivityLogModel(
                user_id=thread.user_id,
                action="FOLLOW_UP_SENT",
                description=f"Follow-up dispatched from {account.email_address} in thread {thread.gmail_thread_id} to {prospect_email}"
            )
            db.add(act)
            db.commit()

            result["success"] = True
            result["status"] = "FOLLOW-UP SENT"
            result["gmail_message_id"] = new_msg_id
            result["message"] = f"Follow-up successfully sent to {prospect_email} in thread."
            return result

        except Exception as e:
            follow_up_log.status = "FAILED"
            follow_up_log.error_message = str(e)
            thread.status = "FAILED"
            db.commit()

            act = ActivityLogModel(
                user_id=thread.user_id,
                action="FOLLOW_UP_FAILED",
                description=f"Follow-up failed from {account.email_address} for {prospect_email}: {str(e)}"
            )
            db.add(act)
            db.commit()

            result["message"] = f"Live send failed: {str(e)}"
            return result
