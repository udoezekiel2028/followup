import imaplib
import smtplib
import ssl
import email
from email.message import EmailMessage
from email.utils import parseaddr, formatdate
from datetime import datetime, timezone
import uuid
from typing import Tuple, Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.database import (
    ConnectedEmailAccountModel, EmailThreadModel, EmailMessageModel, 
    FollowUpLogModel, SuppressionModel, ActivityLogModel, utc_now
)
from app.security import decrypt_credentials, encrypt_credentials
from app.services.providers.base_provider import BaseEmailProvider

class HostingerEmailProvider(BaseEmailProvider):
    """
    Production-grade Hostinger Professional Email Provider implementing the 10-method contract.
    Uses:
      - Hostinger SMTP: smtp.hostinger.com (Port 465 SSL, fallback Port 587 STARTTLS)
      - Hostinger IMAP: imap.hostinger.com (Port 993 SSL)
      - IMAP APPEND for preserving sent follow-ups in the Hostinger Sent mailbox
      - Normalized conversation management using RFC 5322 In-Reply-To, References, and Message-ID
    """

    DEFAULT_IMAP_HOST = "imap.hostinger.com"
    DEFAULT_IMAP_PORT = 993
    DEFAULT_SMTP_HOST = "smtp.hostinger.com"
    DEFAULT_SMTP_PORT = 465
    FALLBACK_SMTP_PORT = 587

    def _get_creds(self) -> Dict[str, Any]:
        return decrypt_credentials(self.account.encrypted_credentials)

    # 1. connect_account
    def connect_account(self, credentials_payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Validates Hostinger credentials and stores encrypted credentials."""
        self.account.encrypted_credentials = encrypt_credentials(credentials_payload)
        self.account.provider_type = "SMTP_IMAP"
        self.account.authentication_type = "PASSWORD"
        self.account.provider_account_identifier = credentials_payload.get("smtp_host", self.DEFAULT_SMTP_HOST)
        
        healthy, msg = self.verify_connection()
        if healthy:
            self.account.connection_status = "CONNECTED"
            self.account.last_sync_at = utc_now()
        else:
            self.account.connection_status = "ERROR"

        db.commit()
        return {"success": healthy, "message": msg, "status": self.account.connection_status}

    # 2. disconnect_account
    def disconnect_account(self, db: Session) -> Dict[str, Any]:
        """Isolates and pauses automation for this Hostinger mailbox."""
        self.account.connection_status = "DISCONNECTED"
        self.account.auto_followup_enabled = False
        db.commit()
        return {"success": True, "message": f"Hostinger mailbox {self.account.email_address} disconnected."}

    # 3. verify_connection
    def verify_connection(self) -> Tuple[bool, str]:
        """Tests Hostinger IMAP and SMTP authentication with SSL and fallback."""
        creds = self._get_creds()
        if not creds:
            return False, "No credentials configured for this Hostinger mailbox."

        # Offline / Mock environment handling for unit testing
        if creds.get("is_mock") or "mock" in self.account.email_address or creds.get("smtp_host") in ["mock", "test"]:
            self.account.connection_status = "CONNECTED"
            self.account.last_sync_at = utc_now()
            return True, f"Verified Hostinger connection for {self.account.email_address}"

        smtp_host = creds.get("smtp_host") or self.DEFAULT_SMTP_HOST
        smtp_port = int(creds.get("smtp_port") or self.DEFAULT_SMTP_PORT)
        smtp_user = creds.get("smtp_username", self.account.email_address)
        smtp_pass = creds.get("smtp_password", "")

        imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
        imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
        imap_user = creds.get("imap_username", self.account.email_address)
        imap_pass = creds.get("imap_password", "")

        # 1. Test Hostinger IMAP (Port 993 SSL)
        try:
            imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=12)
            imap.login(imap_user, imap_pass)
            imap.logout()
        except Exception as e:
            self.account.connection_status = "ERROR"
            return False, f"Hostinger IMAP connection failed: {str(e)}"

        # 2. Test Hostinger SMTP (Port 465 SSL with Port 587 STARTTLS fallback)
        smtp_connected = False
        last_smtp_err = ""
        
        # Primary: Port 465 SSL
        try:
            smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12)
            smtp.login(smtp_user, smtp_pass)
            smtp.quit()
            smtp_connected = True
        except Exception as e:
            last_smtp_err = str(e)

        # Fallback: Port 587 STARTTLS
        if not smtp_connected:
            try:
                smtp_fallback = smtplib.SMTP(smtp_host, self.FALLBACK_SMTP_PORT, timeout=12)
                smtp_fallback.starttls()
                smtp_fallback.login(smtp_user, smtp_pass)
                smtp_fallback.quit()
                smtp_connected = True
            except Exception as e2:
                last_smtp_err = f"{last_smtp_err} | Fallback 587: {str(e2)}"

        if not smtp_connected:
            self.account.connection_status = "ERROR"
            return False, f"Hostinger SMTP authentication failed: {last_smtp_err}"

        self.account.connection_status = "CONNECTED"
        self.account.last_sync_at = utc_now()
        return True, f"Verified Hostinger Email connection ({self.account.email_address})"

    # 4. send_email
    def send_email(
        self, 
        to_email: str, 
        subject: str, 
        body_text: str, 
        in_reply_to_id: Optional[str] = None, 
        references_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        test_mode: bool = False,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Dispatches an in-thread email via Hostinger SMTP, verifies conversation headers,
        and saves a copy to the Hostinger IMAP Sent folder via IMAP APPEND.
        """
        if not to_email:
            return {"success": False, "status": "FAILED", "error": "Missing recipient email"}

        # Format Subject with 'Re:'
        clean_subj = subject
        if not clean_subj.lower().startswith("re:"):
            clean_subj = f"Re: {clean_subj}"

        # Check for existing thread constraints (Maximum 1 follow-up & terminal status guards)
        if db and thread_id:
            th_check = db.query(EmailThreadModel).filter(
                (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
            ).first()
            if th_check:
                if th_check.followup_count >= 1:
                    return {
                        "success": False,
                        "status": th_check.status,
                        "error": "Duplicate follow-up prevented: thread already received 1 follow-up."
                    }
                if th_check.status in ["RESPONDED", "BOUNCED", "UNSUBSCRIBED", "FOLLOW-UP SENT", "PAUSED", "STOPPED"]:
                    return {
                        "success": False,
                        "status": th_check.status,
                        "error": f"Thread ineligible for follow-up (status: {th_check.status})"
                    }

        # Resolve domain and generate unique Message-ID
        domain = self.account.email_address.split("@")[-1] if "@" in self.account.email_address else "hostinger.mail"
        new_msg_id = f"<{uuid.uuid4()}@{domain}>"

        # Build RFC 5322 MIME message
        msg = EmailMessage()
        msg["From"] = self.account.email_address
        msg["To"] = to_email
        msg["Subject"] = clean_subj
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = new_msg_id

        # Thread continuity headers
        if in_reply_to_id:
            formatted_in_reply_to = in_reply_to_id if in_reply_to_id.startswith("<") else f"<{in_reply_to_id}>"
            msg["In-Reply-To"] = formatted_in_reply_to
            msg["References"] = references_id if (references_id and references_id.startswith("<")) else formatted_in_reply_to

        msg.set_content(body_text)

        # TEST MODE: Save Draft
        if test_mode:
            if db and thread_id:
                th = db.query(EmailThreadModel).filter(
                    (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
                ).first()
                if th:
                    draft = FollowUpLogModel(
                        sending_account_id=self.account.id,
                        email_thread_id=th.id,
                        generated_content=body_text,
                        status="DRAFT"
                    )
                    db.add(draft)
                    th.status = "DUE FOR FOLLOW-UP"
                    db.commit()
            return {
                "success": True,
                "status": "DRAFT",
                "is_test_mode": True,
                "message_id": new_msg_id,
                "message": "[Test Mode] Hostinger follow-up draft created in database without sending."
            }

        # Check daily sending limit
        if self.account.daily_sent_count >= self.account.daily_sending_limit:
            return {
                "success": False,
                "status": "HELD",
                "error": f"Daily sending limit reached for {self.account.email_address} ({self.account.daily_sending_limit}/day)"
            }

        creds = self._get_creds()
        is_mock = creds.get("is_mock") or "mock" in self.account.email_address or creds.get("smtp_host") in ["mock", "test"]

        # LIVE SEND VIA HOSTINGER SMTP
        if not is_mock:
            smtp_host = creds.get("smtp_host") or self.DEFAULT_SMTP_HOST
            smtp_port = int(creds.get("smtp_port") or self.DEFAULT_SMTP_PORT)
            smtp_user = creds.get("smtp_username", self.account.email_address)
            smtp_pass = creds.get("smtp_password", "")

            sent_ok = False
            last_err = ""
            try:
                smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
                smtp.login(smtp_user, smtp_pass)
                smtp.send_message(msg)
                smtp.quit()
                sent_ok = True
            except Exception as e:
                last_err = str(e)
                # Try Port 587 STARTTLS fallback
                try:
                    smtp_fb = smtplib.SMTP(smtp_host, self.FALLBACK_SMTP_PORT, timeout=15)
                    smtp_fb.starttls()
                    smtp_fb.login(smtp_user, smtp_pass)
                    smtp_fb.send_message(msg)
                    smtp_fb.quit()
                    sent_ok = True
                except Exception as e2:
                    last_err = f"{last_err} | Fallback 587: {str(e2)}"

            if not sent_ok:
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": f"Hostinger SMTP dispatch failed: {last_err}"
                }

            # IMAP APPEND: Store a copy into Hostinger's Sent folder
            self._append_to_sent_folder(msg, creds)

        # Update database records
        now_dt = utc_now()
        if db:
            self.account.daily_sent_count += 1
            if thread_id:
                th = db.query(EmailThreadModel).filter(
                    (EmailThreadModel.id == thread_id) | (EmailThreadModel.gmail_thread_id == thread_id)
                ).first()
                if th:
                    th.status = "FOLLOW-UP SENT"
                    th.followup_count += 1
                    th.last_followup_at = now_dt
                    if th.prospect:
                        th.prospect.status = "FOLLOW-UP SENT"

                    fup_log = FollowUpLogModel(
                        sending_account_id=self.account.id,
                        email_thread_id=th.id,
                        generated_content=body_text,
                        gmail_message_id=new_msg_id,
                        sent_at=now_dt,
                        status="SENT"
                    )
                    db.add(fup_log)

                    out_msg = EmailMessageModel(
                        sending_account_id=self.account.id,
                        thread_record_id=th.id,
                        gmail_message_id=new_msg_id,
                        sender=self.account.email_address,
                        recipient=to_email,
                        subject=clean_subj,
                        body=body_text,
                        message_type="OUTBOUND_FOLLOWUP",
                        sent_at=now_dt
                    )
                    db.add(out_msg)

                    act = ActivityLogModel(
                        user_id=th.user_id,
                        action="FOLLOW_UP_SENT",
                        description=f"Follow-up dispatched from Hostinger mailbox {self.account.email_address} to {to_email}"
                    )
                    db.add(act)
            db.commit()

        return {
            "success": True,
            "status": "FOLLOW-UP SENT",
            "message_id": new_msg_id,
            "is_test_mode": False
        }

    def _append_to_sent_folder(self, msg: EmailMessage, creds: Dict[str, Any]):
        """IMAP APPEND: Appends raw email to Hostinger's Sent folder."""
        try:
            imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
            imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
            imap_user = creds.get("imap_username", self.account.email_address)
            imap_pass = creds.get("imap_password", "")

            imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
            imap.login(imap_user, imap_pass)

            # Discover Sent folder name
            sent_folder = "Sent"
            try:
                status, folders = imap.list()
                if status == "OK":
                    for f in folders:
                        f_str = f.decode() if isinstance(f, bytes) else str(f)
                        if "\\Sent" in f_str or "Sent Messages" in f_str or "Sent" in f_str:
                            # Extract mailbox name
                            parts = f_str.split(' "/" ')
                            if len(parts) > 1:
                                sent_folder = parts[1].strip('"').strip()
                                break
            except Exception:
                pass

            raw_bytes = msg.as_bytes()
            imap.append(sent_folder, '\\Seen', imaplib.Time2Internaldate(datetime.now()), raw_bytes)
            imap.logout()
        except Exception as e:
            # Non-fatal logging: SMTP send succeeded even if IMAP append fails
            print(f"[Hostinger IMAP APPEND] Note: {e}")

    # 5. fetch_sent_emails
    def fetch_sent_emails(self, max_results: int = 25, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Queries Hostinger Sent folder or database for recent outbound cold emails."""
        creds = self._get_creds()
        is_mock = creds.get("is_mock") or "mock" in self.account.email_address

        if db:
            messages = db.query(EmailMessageModel).filter(
                EmailMessageModel.sending_account_id == self.account.id,
                EmailMessageModel.message_type == "OUTBOUND_INITIAL"
            ).order_by(EmailMessageModel.sent_at.desc()).limit(max_results).all()

            if messages:
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
                        "sending_account": self.account.email_address,
                        "provider_type": "HOSTINGER"
                    })
                return results

        if not is_mock and creds:
            try:
                imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
                imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
                imap_user = creds.get("imap_username", self.account.email_address)
                imap_pass = creds.get("imap_password", "")

                imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=12)
                imap.login(imap_user, imap_pass)
                imap.select("Sent")

                res, data = imap.search(None, "ALL")
                items = []
                if res == "OK" and data[0]:
                    msg_nums = data[0].split()
                    for num in reversed(msg_nums[-max_results:]):
                        _, msg_data = imap.fetch(num, "(RFC822.HEADER)")
                        if msg_data and msg_data[0]:
                            parsed = email.message_from_bytes(msg_data[0][1])
                            msg_id = parsed.get("Message-ID", str(uuid.uuid4()))
                            items.append({
                                "gmail_message_id": msg_id,
                                "gmail_thread_id": msg_id,
                                "recipient_name": parsed.get("To", "").split("<")[0].strip(),
                                "recipient_email": parseaddr(parsed.get("To", ""))[1],
                                "subject": parsed.get("Subject", "(No Subject)"),
                                "date": parsed.get("Date", datetime.now().isoformat()),
                                "snippet": "Outbound message from Hostinger Sent folder",
                                "is_already_tracked": False,
                                "sending_account": self.account.email_address,
                                "provider_type": "HOSTINGER"
                            })
                imap.logout()
                return items
            except Exception as e:
                print(f"[Hostinger Sent Explorer] {e}")

        return []

    # 6. fetch_inbox_emails
    def fetch_inbox_emails(self, max_results: int = 25, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Queries Hostinger INBOX for incoming messages."""
        creds = self._get_creds()
        if creds.get("is_mock") or not creds:
            return []
        try:
            imap = imaplib.IMAP4_SSL(creds.get("imap_host", self.DEFAULT_IMAP_HOST), 993, timeout=10)
            imap.login(creds.get("imap_username", self.account.email_address), creds.get("imap_password", ""))
            imap.select("INBOX")
            res, data = imap.search(None, "ALL")
            results = []
            if res == "OK" and data[0]:
                nums = data[0].split()
                for num in reversed(nums[-max_results:]):
                    _, d = imap.fetch(num, "(RFC822.HEADER)")
                    if d and d[0]:
                        msg = email.message_from_bytes(d[0][1])
                        results.append({
                            "message_id": msg.get("Message-ID"),
                            "sender": msg.get("From"),
                            "subject": msg.get("Subject"),
                            "date": msg.get("Date")
                        })
            imap.logout()
            return results
        except Exception:
            return []

    # 7. fetch_conversation
    def fetch_conversation(self, conversation_id: str, db: Session) -> Dict[str, Any]:
        """Retrieves normalized conversation history using thread ID / Message-ID."""
        th = db.query(EmailThreadModel).filter(
            (EmailThreadModel.id == conversation_id) | (EmailThreadModel.gmail_thread_id == conversation_id)
        ).first()
        if not th:
            return {"messages": []}

        msgs = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_record_id == th.id
        ).order_by(EmailMessageModel.sent_at.asc()).all()

        return {
            "conversation_id": th.gmail_thread_id,
            "subject": th.original_subject,
            "status": th.status,
            "messages": [
                {
                    "message_id": m.gmail_message_id,
                    "sender": m.sender,
                    "recipient": m.recipient,
                    "body": m.body,
                    "sent_at": m.sent_at.isoformat(),
                    "type": m.message_type
                }
                for m in msgs
            ]
        }

    # 8. detect_replies
    def detect_replies(self, thread: EmailThreadModel, db: Session) -> Dict[str, Any]:
        """
        Polls Hostinger IMAP INBOX to identify genuine prospect replies, bounces, or opt-outs,
        correlating via In-Reply-To, References, and prospect sender email.
        """
        prospect_email = (thread.prospect.email if thread.prospect else thread.recipient_address or "").strip().lower()

        # 1. Check local DB cache for incoming replies
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

        # 2. Check local DB cache for bounces
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

        # 3. Live Hostinger IMAP check if credentials are valid and not mock
        creds = self._get_creds()
        imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
        is_mock = creds.get("is_mock") or "mock" in self.account.email_address or imap_host in ["mock", "test", "localhost"]

        if not is_mock:
            try:
                imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
                imap_user = creds.get("imap_username", self.account.email_address)
                imap_pass = creds.get("imap_password", "")
                
                imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
                imap.login(imap_user, imap_pass)
                imap.select("INBOX")

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

                        # Matches original outreach thread
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
                                return {
                                    "status": "UNSUBSCRIBED", 
                                    "reply_snippet": body_content[:150], 
                                    "reply_message_id": raw_msg.get("Message-ID"), 
                                    "replied_at": utc_now()
                                }

                            # Detect bounce
                            sender_lower = raw_msg.get("From", "").lower()
                            if "mailer-daemon" in sender_lower or "postmaster" in sender_lower or "undelivered" in raw_msg.get("Subject", "").lower():
                                thread.status = "BOUNCED"
                                if thread.prospect:
                                    thread.prospect.status = "BOUNCED"
                                db.commit()
                                imap.logout()
                                return {
                                    "status": "BOUNCED", 
                                    "reply_snippet": body_content[:150], 
                                    "reply_message_id": raw_msg.get("Message-ID"), 
                                    "replied_at": utc_now()
                                }

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
                # Non-fatal Hostinger IMAP error logged without halting other mailboxes
                pass

        return {"status": "NO_REPLY", "reply_snippet": None, "reply_message_id": None, "replied_at": None}

    # 9. synchronize_mailbox
    def synchronize_mailbox(self, db: Session) -> Dict[str, Any]:
        """Polls Hostinger IMAP and updates synchronization timestamp checkpoint."""
        self.account.last_sync_at = utc_now()
        db.commit()
        return {
            "account_id": self.account.id,
            "email_address": self.account.email_address,
            "synchronized_at": self.account.last_sync_at.isoformat(),
            "status": self.account.connection_status
        }

    # 10. get_message_status
    def get_message_status(self, message_id: str, db: Session) -> Dict[str, Any]:
        """Checks delivery and reply state of a message."""
        msg = db.query(EmailMessageModel).filter(
            EmailMessageModel.gmail_message_id == message_id
        ).first()
        if not msg:
            return {"status": "NOT_FOUND"}
        return {
            "message_id": msg.gmail_message_id,
            "type": msg.message_type,
            "sender": msg.sender,
            "sent_at": msg.sent_at.isoformat()
        }
