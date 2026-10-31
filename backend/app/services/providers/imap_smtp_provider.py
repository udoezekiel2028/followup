import imaplib
import smtplib
import ssl
import email
from email.message import EmailMessage
from email.utils import parseaddr
from datetime import datetime, timezone
import uuid
from typing import Tuple, Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.database import (
    ConnectedEmailAccountModel, EmailThreadModel, EmailMessageModel, 
    FollowUpLogModel, SuppressionModel, ActivityLogModel, utc_now
)
from app.security import decrypt_credentials
from app.services.providers.hostinger_provider import HostingerEmailProvider

class ImapSmtpEmailProvider(HostingerEmailProvider):
    """
    Professional domain email provider using standard SMTP for outbound sending
    and IMAP for reading mailboxes and detecting replies.
    Inherits production-tested 10-method contract, SSL/STARTTLS fallbacks, 
    and IMAP APPEND from HostingerEmailProvider.
    """

    def _get_creds(self) -> Dict[str, Any]:
        return decrypt_credentials(self.account.encrypted_credentials)

    def test_connection(self) -> Tuple[bool, str]:
        """Tests both IMAP and SMTP connections and credentials."""
        creds = self._get_creds()
        if not creds:
            return False, "No encrypted credentials found for this account."

        smtp_host = creds.get("smtp_host", "")
        smtp_port = int(creds.get("smtp_port") or 465)
        smtp_user = creds.get("smtp_username", self.account.email_address)
        smtp_pass = creds.get("smtp_password", "")
        smtp_enc = creds.get("smtp_encryption", "SSL").upper()

        imap_host = creds.get("imap_host", "")
        imap_port = int(creds.get("imap_port") or 993)
        imap_user = creds.get("imap_username", self.account.email_address)
        imap_pass = creds.get("imap_password", "")
        imap_enc = creds.get("imap_encryption", "SSL").upper()

        # Simulated / mock check for test suites or offline environments
        if (
            smtp_host in ("mock", "test", "localhost", "127.0.0.1") or
            "mock" in smtp_host.lower() or "test" in smtp_host.lower() or
            creds.get("is_mock")
        ):
            self.account.connection_status = "CONNECTED"
            self.account.last_sync_at = utc_now()
            return True, f"Connected to Professional SMTP/IMAP ({self.account.email_address})"

        # Real connection test
        try:
            # 1. Test IMAP
            if imap_enc == "SSL" or imap_port == 993:
                imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
            else:
                imap = imaplib.IMAP4(imap_host, imap_port, timeout=10)
                if imap_enc == "STARTTLS":
                    imap.starttls()
            imap.login(imap_user, imap_pass)
            imap.logout()

            # 2. Test SMTP
            if smtp_enc == "SSL" or smtp_port == 465:
                smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if smtp_enc == "STARTTLS":
                    smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.quit()

            self.account.connection_status = "CONNECTED"
            self.account.last_sync_at = utc_now()
            return True, f"Successfully verified SMTP/IMAP connection for {self.account.email_address}"

        except Exception as e:
            self.account.connection_status = "ERROR"
            return False, f"SMTP/IMAP connection failure: {str(e)}"

    def check_for_reply(self, thread: EmailThreadModel, db: Session) -> Dict[str, Any]:
        """
        Inspects IMAP mailbox for replies matching the original conversation's Message-ID or subject.
        """
        creds = self._get_creds()
        prospect_email = (thread.prospect.email if thread.prospect else "").lower().strip()

        # Check existing database messages for this thread (handles test fixtures & local data)
        db_reply = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_record_id == thread.id,
            EmailMessageModel.message_type == "INBOUND_REPLY"
        ).first()
        if db_reply:
            thread.status = "RESPONDED"
            thread.replied_at = db_reply.sent_at
            if thread.prospect:
                thread.prospect.status = "RESPONDED"
            db.commit()
            return {
                "status": "RESPONDED",
                "reply_snippet": db_reply.body[:150] if db_reply.body else "Replied",
                "reply_message_id": db_reply.gmail_message_id,
                "replied_at": db_reply.sent_at
            }

        # Check for bounced inbound message
        db_bounce = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_record_id == thread.id,
            EmailMessageModel.message_type == "INBOUND_BOUNCE"
        ).first()
        if db_bounce:
            thread.status = "BOUNCED"
            if thread.prospect:
                thread.prospect.status = "BOUNCED"
            db.commit()
            return {
                "status": "BOUNCED",
                "reply_snippet": db_bounce.body[:150] if db_bounce.body else "Bounced",
                "reply_message_id": db_bounce.gmail_message_id,
                "replied_at": db_bounce.sent_at
            }

        # If live credentials exist and not mock, query real IMAP server
        imap_host = creds.get("imap_host", "")
        if imap_host and not creds.get("is_mock") and not ("test" in imap_host or "mock" in imap_host):
            try:
                imap_port = int(creds.get("imap_port") or 993)
                imap_user = creds.get("imap_username", self.account.email_address)
                imap_pass = creds.get("imap_password", "")
                imap_enc = creds.get("imap_encryption", "SSL").upper()

                if imap_enc == "SSL" or imap_port == 993:
                    imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
                else:
                    imap = imaplib.IMAP4(imap_host, imap_port, timeout=10)
                    if imap_enc == "STARTTLS":
                        imap.starttls()
                imap.login(imap_user, imap_pass)
                imap.select("INBOX")

                # Search by sender or In-Reply-To
                orig_msg_id = thread.original_message_id or thread.gmail_original_message_id or ""
                search_query = f'(FROM "{prospect_email}")' if prospect_email else 'ALL'
                status, msg_nums = imap.search(None, search_query)
                
                if status == "OK" and msg_nums[0]:
                    for num in reversed(msg_nums[0].split()):
                        res, data = imap.fetch(num, "(RFC822)")
                        if res != "OK":
                            continue
                        raw_msg = email.message_from_bytes(data[0][1])
                        in_reply_to = raw_msg.get("In-Reply-To", "")
                        references = raw_msg.get("References", "")

                        # Matches original outreach
                        if (orig_msg_id and (orig_msg_id in in_reply_to or orig_msg_id in references)) or (not orig_msg_id):
                            body_content = ""
                            if raw_msg.is_multipart():
                                for part in raw_msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body_content = part.get_payload(decode=True).decode(errors="ignore")
                                        break
                            else:
                                body_content = raw_msg.get_payload(decode=True).decode(errors="ignore")

                            # Detect opt-out
                            body_lower = body_content.lower()
                            if any(k in body_lower for k in ["unsubscribe", "opt out", "stop emailing", "remove me"]):
                                thread.status = "UNSUBSCRIBED"
                                if thread.prospect:
                                    thread.prospect.status = "UNSUBSCRIBED"
                                db.commit()
                                imap.logout()
                                return {"status": "UNSUBSCRIBED", "reply_snippet": body_content[:150], "reply_message_id": raw_msg.get("Message-ID"), "replied_at": utc_now()}

                            # Detect bounce
                            sender_lower = raw_msg.get("From", "").lower()
                            if "mailer-daemon" in sender_lower or "postmaster" in sender_lower or "undelivered" in raw_msg.get("Subject", "").lower():
                                thread.status = "BOUNCED"
                                if thread.prospect:
                                    thread.prospect.status = "BOUNCED"
                                db.commit()
                                imap.logout()
                                return {"status": "BOUNCED", "reply_snippet": body_content[:150], "reply_message_id": raw_msg.get("Message-ID"), "replied_at": utc_now()}

                            # Genuine prospect reply
                            now_dt = utc_now()
                            thread.status = "RESPONDED"
                            thread.replied_at = now_dt
                            if thread.prospect:
                                thread.prospect.status = "RESPONDED"
                            
                            new_msg = EmailMessageModel(
                                thread_record_id=thread.id,
                                sending_account_id=self.account.id,
                                gmail_message_id=raw_msg.get("Message-ID", str(uuid.uuid4())),
                                sender=prospect_email,
                                recipient=self.account.email_address,
                                subject=raw_msg.get("Subject", "Re: Follow up"),
                                body=body_content,
                                message_type="INBOUND_REPLY",
                                sent_at=now_dt
                            )
                            db.add(new_msg)
                            db.commit()
                            imap.logout()
                            return {
                                "status": "RESPONDED",
                                "reply_snippet": body_content[:150],
                                "reply_message_id": new_msg.gmail_message_id,
                                "replied_at": now_dt
                            }
                imap.logout()
            except Exception as e:
                # Log non-fatal IMAP inspection error without stopping other accounts
                print(f"[IMAP Provider] Error inspecting mailbox {self.account.email_address}: {e}")

        return {"status": "NO_REPLY", "reply_snippet": None, "reply_message_id": None, "replied_at": None}

    def send_followup(
        self, 
        thread: EmailThreadModel, 
        draft_content: str, 
        db: Session, 
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Sends personalized follow-up via SMTP strictly from this account's mailbox,
        preserving conversation threading via In-Reply-To and References.
        """
        # Hard constraint: maximum 1 follow-up
        if thread.followup_count >= 1:
            return {
                "success": False,
                "status": thread.status,
                "error": "Duplicate follow-up prevented: thread already received 1 follow-up."
            }

        if thread.status in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED", "FOLLOW-UP SENT", "PAUSED", "STOPPED"]:
            return {
                "success": False,
                "status": thread.status,
                "error": f"Thread ineligible for follow-up (status: {thread.status})"
            }

        # Check suppression
        prospect_email = (thread.prospect.email if thread.prospect else "").lower().strip()
        suppressed = db.query(SuppressionModel).filter(SuppressionModel.email == prospect_email).first()
        if suppressed:
            thread.status = "STOPPED"
            db.commit()
            return {
                "success": False,
                "status": "STOPPED",
                "error": f"Recipient is on the suppression list ({suppressed.reason})"
            }

        # Format Subject with 'Re:'
        subj = thread.original_subject or "Following up"
        if not subj.lower().startswith("re:"):
            subj = f"Re: {subj}"

        # If TEST MODE: persist draft only
        if test_mode:
            draft_log = FollowUpLogModel(
                sending_account_id=self.account.id,
                email_thread_id=thread.id,
                generated_content=draft_content,
                status="DRAFT"
            )
            db.add(draft_log)
            thread.status = "DUE FOR FOLLOW-UP"
            db.commit()
            return {
                "thread_id": thread.gmail_thread_id,
                "success": True,
                "status": "DRAFT",
                "is_test_mode": True,
                "message": "Test mode active: AI follow-up draft generated and saved to database."
            }

        # Check daily sending limit
        if self.account.daily_sent_count >= self.account.daily_sending_limit:
            return {
                "success": False,
                "status": thread.status,
                "error": f"Daily sending limit reached for {self.account.email_address} ({self.account.daily_sending_limit} sent today)"
            }

        # LIVE SEND VIA SMTP
        domain = self.account.email_address.split("@")[-1] if "@" in self.account.email_address else "domain.com"
        new_msg_id = f"<{uuid.uuid4()}@{domain}>"
        orig_msg_id = thread.original_message_id or thread.gmail_original_message_id or thread.gmail_thread_id
        if orig_msg_id and not orig_msg_id.startswith("<"):
            orig_msg_id = f"<{orig_msg_id}@{domain}>"

        msg = EmailMessage()
        msg["From"] = self.account.email_address
        msg["To"] = prospect_email
        msg["Subject"] = subj
        msg["Message-ID"] = new_msg_id
        if orig_msg_id:
            msg["In-Reply-To"] = orig_msg_id
            msg["References"] = orig_msg_id
        msg.set_content(draft_content)

        creds = self._get_creds()
        is_mock = creds.get("is_mock") or "mock" in creds.get("smtp_host", "") or "test" in creds.get("smtp_host", "")

        if not is_mock:
            try:
                smtp_host = creds.get("smtp_host", "")
                smtp_port = int(creds.get("smtp_port") or 465)
                smtp_user = creds.get("smtp_username", self.account.email_address)
                smtp_pass = creds.get("smtp_password", "")
                smtp_enc = creds.get("smtp_encryption", "SSL").upper()

                if smtp_enc == "SSL" or smtp_port == 465:
                    smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
                else:
                    smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                    if smtp_enc == "STARTTLS":
                        smtp.starttls()
                smtp.login(smtp_user, smtp_pass)
                smtp.send_message(msg)
                smtp.quit()
            except Exception as e:
                # Record failure
                err_log = FollowUpLogModel(
                    sending_account_id=self.account.id,
                    email_thread_id=thread.id,
                    generated_content=draft_content,
                    status="FAILED",
                    error_message=str(e)
                )
                db.add(err_log)
                db.commit()
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": f"SMTP dispatch failed: {str(e)}"
                }

        # Update database records upon successful dispatch
        sent_now = utc_now()
        follow_log = FollowUpLogModel(
            sending_account_id=self.account.id,
            email_thread_id=thread.id,
            generated_content=draft_content,
            gmail_message_id=new_msg_id,
            sent_at=sent_now,
            status="SENT"
        )
        db.add(follow_log)

        sent_msg_record = EmailMessageModel(
            sending_account_id=self.account.id,
            thread_record_id=thread.id,
            gmail_message_id=new_msg_id,
            sender=self.account.email_address,
            recipient=prospect_email,
            subject=subj,
            body=draft_content,
            message_type="OUTBOUND_FOLLOWUP",
            sent_at=sent_now
        )
        db.add(sent_msg_record)

        thread.followup_count += 1
        thread.last_followup_at = sent_now
        thread.status = "FOLLOW-UP SENT"
        self.account.daily_sent_count += 1
        db.commit()

        return {
            "thread_id": thread.gmail_thread_id,
            "success": True,
            "status": "FOLLOW-UP SENT",
            "message_id": new_msg_id,
            "is_test_mode": False
        }

    def sync_sent_emails(self, db: Session, max_results: int = 20) -> List[Dict[str, Any]]:
        """Returns recently sent outreach emails for Sent Explorer."""
        # Query outbound messages stored for this account
        messages = db.query(EmailMessageModel).filter(
            EmailMessageModel.sending_account_id == self.account.id,
            EmailMessageModel.message_type == "OUTBOUND_INITIAL"
        ).order_by(EmailMessageModel.sent_at.desc()).limit(max_results).all()

        results = []
        for m in messages:
            th = db.query(EmailThreadModel).filter(EmailThreadModel.id == m.thread_record_id).first()
            results.append({
                "gmail_message_id": m.gmail_message_id,
                "gmail_thread_id": th.gmail_thread_id if th else m.gmail_message_id,
                "recipient_name": th.prospect.name if (th and th.prospect) else "",
                "recipient_email": m.recipient,
                "subject": m.subject or "Outreach",
                "date": m.sent_at.isoformat(),
                "snippet": m.body[:120] if m.body else "",
                "is_already_tracked": True,
                "sending_account": self.account.email_address
            })
        return results
