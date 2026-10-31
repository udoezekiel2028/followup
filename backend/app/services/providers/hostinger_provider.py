import imaplib
import smtplib
import ssl
import email
import email.header
import re
from email.message import EmailMessage
from email.utils import parseaddr, formatdate, parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import uuid
from typing import Tuple, Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.database import (
    ConnectedEmailAccountModel, EmailThreadModel, EmailMessageModel, 
    FollowUpLogModel, SuppressionModel, ActivityLogModel, ProspectModel,
    AutomationSettingsModel, utc_now
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

    @classmethod
    def find_sent_folder(cls, imap: imaplib.IMAP4_SSL) -> str:
        """
        Dynamically discovers the Sent mailbox folder name on Dovecot/Hostinger/cPanel.
        Handles RFC 6154 flags (\\Sent), dot/slash delimiters, and candidate fallbacks.
        """
        try:
            status, folders = imap.list()
            if status == "OK" and folders:
                # 1. Look for folder with \Sent attribute flag
                for f in folders:
                    if not f:
                        continue
                    f_str = f.decode("utf-8", errors="ignore") if isinstance(f, bytes) else str(f)
                    if r"\sent" in f_str.lower():
                        match = re.search(r'\((.*?)\)\s+(?:"(.*?)"|(\S+))\s+(?:"(.*?)"|(\S+))$', f_str)
                        if match:
                            folder_name = match.group(4) or match.group(5)
                            if folder_name:
                                folder_clean = folder_name.strip('"')
                                try:
                                    res, _ = imap.select(f'"{folder_clean}"', readonly=True)
                                    if res == "OK":
                                        return folder_clean
                                    res, _ = imap.select(folder_clean, readonly=True)
                                    if res == "OK":
                                        return folder_clean
                                except Exception:
                                    pass

                # 2. Look for folder with 'sent' in its name
                for f in folders:
                    if not f:
                        continue
                    f_str = f.decode("utf-8", errors="ignore") if isinstance(f, bytes) else str(f)
                    if "sent" in f_str.lower():
                        match = re.search(r'\((.*?)\)\s+(?:"(.*?)"|(\S+))\s+(?:"(.*?)"|(\S+))$', f_str)
                        if match:
                            folder_name = match.group(4) or match.group(5)
                            if folder_name:
                                folder_clean = folder_name.strip('"')
                                try:
                                    res, _ = imap.select(f'"{folder_clean}"', readonly=True)
                                    if res == "OK":
                                        return folder_clean
                                    res, _ = imap.select(folder_clean, readonly=True)
                                    if res == "OK":
                                        return folder_clean
                                except Exception:
                                    pass
        except Exception as e:
            print(f"[Hostinger find_sent_folder imap.list error] {e}")

        # 3. Known candidate folder names on Hostinger/Dovecot/cPanel
        candidates = [
            "INBOX.Sent",
            "INBOX/Sent",
            "Sent",
            "Sent Messages",
            "Sent Items",
            "INBOX.Sent Items",
            "INBOX/Sent Items",
            "INBOX.Sent Messages",
            "INBOX/Sent Messages",
        ]
        for c in candidates:
            try:
                res, _ = imap.select(f'"{c}"', readonly=True)
                if res == "OK":
                    return c
                res, _ = imap.select(c, readonly=True)
                if res == "OK":
                    return c
            except Exception:
                continue

        return "INBOX.Sent"

    @staticmethod
    def _decode_mime_header(val: Optional[str]) -> str:
        if not val:
            return ""
        try:
            decoded_parts = email.header.decode_header(val)
            res = []
            for content, enc in decoded_parts:
                if isinstance(content, bytes):
                    res.append(content.decode(enc or "utf-8", errors="ignore"))
                else:
                    res.append(str(content))
            return "".join(res).strip()
        except Exception:
            return str(val)

    @staticmethod
    def _extract_body_from_msg(parsed: email.message.Message) -> str:
        body_text = ""
        try:
            if parsed.is_multipart():
                for part in parsed.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition:
                        continue
                    if content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="ignore")
                            break
                    elif content_type == "text/html" and not body_text:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            html_raw = payload.decode(charset, errors="ignore")
                            body_text = re.sub(r'<[^>]+>', ' ', html_raw)
            else:
                payload = parsed.get_payload(decode=True)
                if payload:
                    charset = parsed.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="ignore")
        except Exception:
            pass
        return body_text.strip()

    def _append_to_sent_folder(self, msg: EmailMessage, creds: Dict[str, Any]):
        """IMAP APPEND: Appends raw email to Hostinger's Sent folder."""
        try:
            imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
            imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
            imap_user = creds.get("imap_username", self.account.email_address)
            imap_pass = creds.get("imap_password", "")

            imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10)
            imap.login(imap_user, imap_pass)
            sent_folder = self.find_sent_folder(imap)

            raw_bytes = msg.as_bytes()
            imap.append(f'"{sent_folder}"' if ' ' in sent_folder else sent_folder, '\\Seen', imaplib.Time2Internaldate(datetime.now()), raw_bytes)
            imap.logout()
        except Exception as e:
            # Non-fatal logging: SMTP send succeeded even if IMAP append fails
            print(f"[Hostinger IMAP APPEND] Note: {e}")

    # 5. fetch_sent_emails
    def fetch_sent_emails(self, max_results: int = 25, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """
        Queries Hostinger Sent folder in real-time to discover real sent outbound emails.
        Correlates with database to indicate which conversations are currently tracked.
        """
        creds = self._get_creds()
        is_mock = creds.get("is_mock") or "mock" in self.account.email_address or creds.get("smtp_host") in ["mock", "test", "localhost"]

        # Tracked message IDs in DB for correlation
        tracked_ids = set()
        if db:
            tracked = db.query(EmailThreadModel.gmail_thread_id, EmailThreadModel.original_message_id).filter(
                EmailThreadModel.sending_account_id == self.account.id
            ).all()
            for th_id, orig_id in tracked:
                if th_id: tracked_ids.add(th_id)
                if orig_id: tracked_ids.add(orig_id)

        items = []

        # 1. Real-time live IMAP query to Hostinger Sent mailbox
        if not is_mock and creds:
            try:
                imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
                imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
                imap_user = creds.get("imap_username", self.account.email_address)
                imap_pass = creds.get("imap_password", "")

                imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=12)
                imap.login(imap_user, imap_pass)

                sent_folder = self.find_sent_folder(imap)
                imap.select(f'"{sent_folder}"' if ' ' in sent_folder else sent_folder, readonly=True)

                res, data = imap.search(None, "ALL")
                if res == "OK" and data[0]:
                    msg_nums = data[0].split()
                    for num in reversed(msg_nums[-max_results:]):
                        _, msg_data = imap.fetch(num, "(RFC822)")
                        if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                            parsed = email.message_from_bytes(msg_data[0][1])
                            msg_id = (parsed.get("Message-ID") or "").strip() or f"<{uuid.uuid4()}@{self.account.email_address.split('@')[-1]}>"
                            
                            to_raw = parsed.get("To", "")
                            clean_name, clean_to = parseaddr(to_raw)
                            clean_name = self._decode_mime_header(clean_name)
                            subject = self._decode_mime_header(parsed.get("Subject", "(No Subject)"))
                            body_text = self._extract_body_from_msg(parsed)

                            items.append({
                                "gmail_message_id": msg_id,
                                "gmail_thread_id": msg_id,
                                "recipient_name": clean_name or clean_to,
                                "recipient_email": clean_to,
                                "subject": subject,
                                "date": parsed.get("Date", datetime.now().isoformat()),
                                "snippet": body_text[:120].strip() if body_text else "Outbound message from Hostinger Sent folder",
                                "is_already_tracked": msg_id in tracked_ids,
                                "sending_account": self.account.email_address,
                                "provider_type": "HOSTINGER"
                            })
                imap.logout()
                if items:
                    return items
            except Exception as e:
                print(f"[Hostinger Sent Explorer Live Query] {e}")

        # Fallback to local DB records if offline/mock or no IMAP messages
        if db:
            messages = db.query(EmailMessageModel).filter(
                EmailMessageModel.sending_account_id == self.account.id,
                EmailMessageModel.message_type == "OUTBOUND_INITIAL"
            ).order_by(EmailMessageModel.sent_at.desc()).limit(max_results).all()

            for m in messages:
                th = db.query(EmailThreadModel).filter(EmailThreadModel.id == m.thread_record_id).first()
                items.append({
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

        return items

    def sync_sent_emails(self, db: Session, max_results: int = 30) -> List[Dict[str, Any]]:
        """
        Synchronizes Sent mailbox into database, ingesting newly found cold emails,
        then returns recent sent items for Sent Explorer.
        """
        self.synchronize_mailbox(db)
        return self.fetch_sent_emails(max_results=max_results, db=db)

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
        """
        Automatic Ingestion Engine for Hostinger / Professional IMAP:
        1. Connects to Hostinger IMAP.
        2. Discovers and scans Sent mailbox for outbound cold emails.
        3. Parses RFC 822 messages, applies cold email eligibility rules.
        4. Ingests eligible emails into ProspectModel, EmailThreadModel, and EmailMessageModel.
        5. Polls INBOX for incoming replies, bounces, and opt-outs.
        6. Updates last_sync_at checkpoint.
        """
        creds = self._get_creds()
        imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
        is_mock = creds.get("is_mock") or "mock" in self.account.email_address or imap_host in ["mock", "test", "localhost"]

        identified_cold_emails = 0
        scanned_count = 0
        error_msg = None

        if not is_mock and creds:
            try:
                imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
                imap_user = creds.get("imap_username", self.account.email_address)
                imap_pass = creds.get("imap_password", "")

                imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
                imap.login(imap_user, imap_pass)

                # 1. SCAN SENT MAILBOX
                sent_folder = self.find_sent_folder(imap)
                imap.select(f'"{sent_folder}"' if ' ' in sent_folder else sent_folder, readonly=True)

                settings_model = db.query(AutomationSettingsModel).first()
                delay_hours = settings_model.followup_delay_hours if settings_model else 72
                suppression_emails = {s.email.lower() for s in db.query(SuppressionModel).all()}

                res, data = imap.search(None, "ALL")
                if res == "OK" and data[0]:
                    msg_nums = data[0].split()
                    scanned_count = len(msg_nums)
                    # Scan most recent 50 messages
                    for num in reversed(msg_nums[-50:]):
                        _, msg_data = imap.fetch(num, "(RFC822)")
                        if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                            continue

                        raw_msg = email.message_from_bytes(msg_data[0][1])
                        msg_id = (raw_msg.get("Message-ID") or "").strip()
                        if not msg_id:
                            msg_id = f"<{uuid.uuid4()}@{self.account.email_address.split('@')[-1]}>"

                        to_header = raw_msg.get("To", "")
                        clean_name, clean_to = parseaddr(to_header)
                        clean_name = self._decode_mime_header(clean_name)
                        clean_to = clean_to.strip().lower()

                        # Eligibility validations
                        if not clean_to or "@" not in clean_to:
                            continue
                        if clean_to == self.account.email_address.lower():
                            continue

                        # Domain exclusions
                        recipient_domain = clean_to.split("@")[-1]
                        sender_domain = self.account.email_address.split("@")[-1].lower()
                        if recipient_domain == sender_domain:
                            continue

                        # Automated mailbox exclusions
                        user_prefix = clean_to.split("@")[0].lower()
                        if any(k in user_prefix for k in ["noreply", "no-reply", "mailer-daemon", "postmaster", "notifications", "support", "billing", "bounce", "alert"]):
                            continue

                        if clean_to in suppression_emails or recipient_domain in suppression_emails:
                            continue

                        # Parse Subject & Body
                        subject = self._decode_mime_header(raw_msg.get("Subject", "(No Subject)"))
                        body_text = self._extract_body_from_msg(raw_msg)

                        # Check non-cold keywords
                        subj_lower = subject.lower()
                        if any(kw in subj_lower for kw in ["invoice", "receipt", "verification", "password reset", "order confirmation", "statement"]):
                            continue

                        # Parse Date
                        date_str = raw_msg.get("Date", "")
                        sent_dt = utc_now()
                        if date_str:
                            try:
                                parsed_dt = parsedate_to_datetime(date_str)
                                if parsed_dt.tzinfo is None:
                                    sent_dt = parsed_dt.replace(tzinfo=timezone.utc)
                                else:
                                    sent_dt = parsed_dt.astimezone(timezone.utc)
                            except Exception:
                                sent_dt = utc_now()

                        # Check if already tracked
                        existing_thread = db.query(EmailThreadModel).filter(
                            (EmailThreadModel.gmail_thread_id == msg_id) |
                            (EmailThreadModel.original_message_id == msg_id) |
                            (EmailThreadModel.gmail_original_message_id == msg_id) |
                            (
                                (EmailThreadModel.sending_account_id == self.account.id) &
                                (EmailThreadModel.recipient_address == clean_to) &
                                (EmailThreadModel.original_subject == subject)
                            )
                        ).first()

                        if existing_thread:
                            if not existing_thread.sending_account_id:
                                existing_thread.sending_account_id = self.account.id
                                db.commit()
                            continue

                        # Derive Prospect info
                        if not clean_name or "@" in clean_name:
                            salutation = re.search(r'(?:hi|hello|hey|dear)\s+([A-Z][a-z]+)', body_text, re.IGNORECASE)
                            if salutation:
                                clean_name = salutation.group(1).capitalize()
                            else:
                                clean_name = clean_to.split("@")[0].replace(".", " ").title()

                        company = recipient_domain.split(".")[0].capitalize() if recipient_domain else "Company"

                        prospect = db.query(ProspectModel).filter(ProspectModel.email == clean_to).first()
                        if not prospect:
                            prospect = ProspectModel(
                                user_id=self.account.user_id,
                                email=clean_to,
                                name=clean_name,
                                company=company,
                                status="PENDING"
                            )
                            db.add(prospect)
                            db.flush()

                        # Follow-up timing & thread creation
                        next_followup = sent_dt + timedelta(hours=delay_hours)
                        initial_status = "DUE FOR FOLLOW-UP" if next_followup <= utc_now() else "PENDING"

                        new_thread = EmailThreadModel(
                            id=str(uuid.uuid4()),
                            user_id=self.account.user_id,
                            sending_account_id=self.account.id,
                            prospect_id=prospect.id,
                            email_provider="HOSTINGER",
                            gmail_thread_id=msg_id,
                            original_message_id=msg_id,
                            gmail_original_message_id=msg_id,
                            recipient_address=clean_to,
                            original_subject=subject,
                            original_body=body_text[:3000] if body_text else "(Hostinger Outbound Email)",
                            original_sent_at=sent_dt,
                            next_followup_at=next_followup,
                            followup_count=0,
                            status=initial_status
                        )
                        db.add(new_thread)
                        db.flush()

                        new_msg = EmailMessageModel(
                            thread_record_id=new_thread.id,
                            sending_account_id=self.account.id,
                            gmail_message_id=msg_id,
                            sender=self.account.email_address,
                            recipient=clean_to,
                            subject=subject,
                            body=body_text[:3000] if body_text else "",
                            message_type="OUTBOUND_INITIAL",
                            sent_at=sent_dt
                        )
                        db.add(new_msg)

                        act = ActivityLogModel(
                            user_id=self.account.user_id,
                            action="AUTO_EMAIL_TRACKED",
                            description=f"Auto-tracked Hostinger outbound email to {clean_to} (Subject: '{subject}')"
                        )
                        db.add(act)
                        identified_cold_emails += 1
                        db.commit()

                # 2. POLL INBOX FOR REPLIES ON ACTIVE THREADS
                active_threads = db.query(EmailThreadModel).filter(
                    EmailThreadModel.sending_account_id == self.account.id,
                    EmailThreadModel.status.in_(["PENDING", "DUE FOR FOLLOW-UP", "FOLLOW-UP SENT"])
                ).all()

                for th in active_threads:
                    try:
                        self.detect_replies(th, db)
                    except Exception:
                        pass

                imap.logout()
            except Exception as e:
                error_msg = str(e)
                print(f"[Hostinger Mailbox Synchronization Error] {e}")

        self.account.last_sync_at = utc_now()
        db.commit()

        return {
            "account_id": self.account.id,
            "email_address": self.account.email_address,
            "synchronized_at": self.account.last_sync_at.isoformat(),
            "status": self.account.connection_status,
            "identified_cold_emails": identified_cold_emails,
            "scanned": scanned_count,
            "error": error_msg
        }

    def track_sent_message(self, message_id_or_thread_id: str, db: Session, manual: bool = True) -> Optional[EmailThreadModel]:
        """
        Manually tracks an email found in Hostinger Sent mailbox via Sent Explorer.
        """
        existing = db.query(EmailThreadModel).filter(
            (EmailThreadModel.gmail_thread_id == message_id_or_thread_id) |
            (EmailThreadModel.original_message_id == message_id_or_thread_id)
        ).first()
        if existing:
            return existing

        creds = self._get_creds()
        if not creds:
            return None

        imap_host = creds.get("imap_host") or self.DEFAULT_IMAP_HOST
        imap_port = int(creds.get("imap_port") or self.DEFAULT_IMAP_PORT)
        imap_user = creds.get("imap_username", self.account.email_address)
        imap_pass = creds.get("imap_password", "")

        try:
            imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=12)
            imap.login(imap_user, imap_pass)
            sent_folder = self.find_sent_folder(imap)
            imap.select(f'"{sent_folder}"' if ' ' in sent_folder else sent_folder, readonly=True)

            res, data = imap.search(None, f'(HEADER Message-ID "{message_id_or_thread_id}")')
            if res != "OK" or not data[0]:
                res, data = imap.search(None, "ALL")

            found_msg = None
            if res == "OK" and data[0]:
                for num in reversed(data[0].split()[-30:]):
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                        parsed = email.message_from_bytes(msg_data[0][1])
                        curr_id = parsed.get("Message-ID", "")
                        if message_id_or_thread_id in curr_id or message_id_or_thread_id == curr_id:
                            found_msg = parsed
                            break
                        if not found_msg:
                            found_msg = parsed

            imap.logout()

            if not found_msg:
                return None

            clean_name, clean_to = parseaddr(found_msg.get("To", ""))
            clean_name = self._decode_mime_header(clean_name)
            clean_to = clean_to.strip().lower()
            subject = self._decode_mime_header(found_msg.get("Subject", "(No Subject)"))
            body_text = self._extract_body_from_msg(found_msg)

            recipient_domain = clean_to.split("@")[-1]
            company = recipient_domain.split(".")[0].capitalize() if recipient_domain else "Company"

            prospect = db.query(ProspectModel).filter(ProspectModel.email == clean_to).first()
            if not prospect:
                prospect = ProspectModel(
                    user_id=self.account.user_id,
                    email=clean_to,
                    name=clean_name or clean_to.split("@")[0].title(),
                    company=company,
                    status="PENDING"
                )
                db.add(prospect)
                db.flush()

            settings_model = db.query(AutomationSettingsModel).first()
            delay_hours = settings_model.followup_delay_hours if settings_model else 72
            sent_dt = utc_now()
            date_str = found_msg.get("Date", "")
            if date_str:
                try:
                    pdt = parsedate_to_datetime(date_str)
                    sent_dt = pdt.replace(tzinfo=timezone.utc) if pdt.tzinfo is None else pdt.astimezone(timezone.utc)
                except Exception:
                    pass

            next_fup = sent_dt + timedelta(hours=delay_hours)
            status = "DUE FOR FOLLOW-UP" if next_fup <= utc_now() else "PENDING"

            new_thread = EmailThreadModel(
                id=str(uuid.uuid4()),
                user_id=self.account.user_id,
                sending_account_id=self.account.id,
                prospect_id=prospect.id,
                email_provider="HOSTINGER",
                gmail_thread_id=message_id_or_thread_id,
                original_message_id=message_id_or_thread_id,
                gmail_original_message_id=message_id_or_thread_id,
                recipient_address=clean_to,
                original_subject=subject,
                original_body=body_text[:3000] if body_text else "(Sent message)",
                original_sent_at=sent_dt,
                next_followup_at=next_fup,
                followup_count=0,
                status=status
            )
            db.add(new_thread)
            db.flush()

            new_msg = EmailMessageModel(
                thread_record_id=new_thread.id,
                sending_account_id=self.account.id,
                gmail_message_id=message_id_or_thread_id,
                sender=self.account.email_address,
                recipient=clean_to,
                subject=subject,
                body=body_text[:3000] if body_text else "",
                message_type="OUTBOUND_INITIAL",
                sent_at=sent_dt
            )
            db.add(new_msg)

            act = ActivityLogModel(
                user_id=self.account.user_id,
                action="MANUAL_EMAIL_TRACKED",
                description=f"Manually tracked Hostinger email to {clean_to} (Subject: '{subject}')"
            )
            db.add(act)
            db.commit()
            return new_thread
        except Exception as e:
            print(f"[Hostinger track_sent_message error] {e}")
            return None

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
