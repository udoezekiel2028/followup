import base64
import email
from email.utils import parseaddr, parsedate_to_datetime
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.database import (
    ConnectedEmailAccountModel, ProspectModel, EmailThreadModel, 
    EmailMessageModel, SuppressionModel, AutomationSettingsModel, 
    ActivityLogModel
)
from app.services.oauth_service import GoogleOAuthService
from app.services.label_manager import GmailLabelManager
from app.config import settings

class GmailMonitorService:
    NEWSLETTER_HEADERS = [
        'list-unsubscribe', 'list-id', 'list-post', 'x-campaign', 
        'x-mailer-campaign', 'precedence', 'x-mailgun-tag'
    ]
    
    NON_COLD_SUBJECT_KEYWORDS = [
        'receipt', 'invoice', 'order confirmation', 'your order', 'billing', 
        'payment', 'password reset', 'verify your email', 'welcome to', 
        'security alert', 'statement', 'newsletter', 'digest', 'invitation to edit',
        'calendar event', 'accepted:', 'declined:', 'notification', 'support ticket',
        'shipping confirmation', 'two-factor', '2fa', 'verification code'
    ]

    NON_COLD_SENDER_KEYWORDS = [
        'noreply', 'no-reply', 'notifications', 'billing', 'support', 
        'newsletters', 'updates', 'mailer-daemon', 'postmaster', 'alert'
    ]

    @staticmethod
    def clean_email(raw_addr: str) -> Tuple[str, str]:
        name, addr = parseaddr(raw_addr)
        return name.strip(), addr.strip().lower()

    @staticmethod
    def extract_company_from_email_or_domain(email_addr: str) -> Optional[str]:
        if '@' not in email_addr:
            return None
        domain = email_addr.split('@')[-1].lower()
        generic_domains = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'aol.com', 'mail.com', 'protonmail.com'}
        if domain in generic_domains:
            return None
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[0].capitalize()
        return None

    @staticmethod
    def extract_body_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
        text_body = ""
        html_body = ""

        def decode_data(data_str: str) -> str:
            try:
                decoded_bytes = base64.urlsafe_b64decode(data_str.encode('ASCII'))
                return decoded_bytes.decode('utf-8', errors='replace')
            except Exception:
                return ""

        parts = [payload]
        while parts:
            part = parts.pop(0)
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data', '')

            if body_data:
                decoded = decode_data(body_data)
                if 'text/plain' in mime_type and not text_body:
                    text_body = decoded
                elif 'text/html' in mime_type and not html_body:
                    html_body = decoded

            sub_parts = part.get('parts', [])
            if sub_parts:
                parts.extend(sub_parts)

        return text_body.strip(), html_body.strip()

    @classmethod
    def is_eligible_cold_outreach(
        cls, 
        recipient_email: str, 
        sender_email: str, 
        subject: str, 
        headers: Dict[str, str], 
        body_text: str,
        settings_model: AutomationSettingsModel,
        suppressions: List[str]
    ) -> Tuple[bool, Optional[str]]:
        recipient_clean = recipient_email.lower().strip()
        recipient_domain = recipient_clean.split('@')[-1] if '@' in recipient_clean else ""
        sender_clean = sender_email.lower().strip()
        sender_domain = sender_clean.split('@')[-1] if '@' in sender_clean else ""

        if recipient_clean == sender_clean:
            return False, "Self-sent email"
        if sender_domain and recipient_domain == sender_domain:
            return False, "Internal company domain email"

        if recipient_clean in suppressions:
            return False, f"Recipient {recipient_clean} is on suppression list"
        if recipient_domain in suppressions:
            return False, f"Domain {recipient_domain} is on suppression list"

        if settings_model.excluded_emails and recipient_clean in [e.lower() for e in settings_model.excluded_emails]:
            return False, f"Recipient {recipient_clean} in excluded emails list"
        if settings_model.excluded_domains and recipient_domain in [d.lower() for d in settings_model.excluded_domains]:
            return False, f"Domain {recipient_domain} in excluded domains list"

        for h_key in headers:
            if h_key.lower() in cls.NEWSLETTER_HEADERS:
                return False, f"Contains bulk/newsletter header '{h_key}'"

        subj_lower = (subject or "").lower()
        for kw in cls.NON_COLD_SUBJECT_KEYWORDS:
            if kw in subj_lower:
                return False, f"Subject matches non-outreach keyword '{kw}'"

        for kw in cls.NON_COLD_SENDER_KEYWORDS:
            if kw in recipient_clean.split('@')[0]:
                return False, f"Recipient appears to be an automated mailbox: '{recipient_clean}'"

        if len(body_text.strip()) < 15:
            return False, "Email body too short to qualify as cold outreach"

        return True, None

    @classmethod
    def track_conversation(
        cls, 
        account: ConnectedEmailAccountModel, 
        thread_id: str, 
        db: Session,
        manual: bool = False
    ) -> Optional[EmailThreadModel]:
        """
        Tracks an email thread, creates prospect and thread records,
        and applies the AUTO_FOLLOWUP label in Gmail.
        """
        service = GoogleOAuthService.get_gmail_service(account, db)

        # Check if already tracked
        existing_thread = db.query(EmailThreadModel).filter(
            EmailThreadModel.gmail_thread_id == thread_id
        ).first()
        if existing_thread:
            return existing_thread

        # Fetch thread messages
        thread_data = service.users().threads().get(userId='me', id=thread_id, format='full').execute()
        messages = thread_data.get('messages', [])
        if not messages:
            return None

        # The initial outreach message in the thread
        initial_msg = messages[0]
        msg_id = initial_msg['id']
        payload = initial_msg.get('payload', {})
        raw_headers = payload.get('headers', [])
        headers_dict = {h['name']: h['value'] for h in raw_headers}

        to_header = headers_dict.get('To', '')
        from_header = headers_dict.get('From', account.gmail_address)
        subject = headers_dict.get('Subject', '(No Subject)')
        date_header = headers_dict.get('Date', '')

        recipient_name, recipient_email = cls.clean_email(to_header)
        sender_name, sender_email = cls.clean_email(from_header)

        if not recipient_email or '@' not in recipient_email:
            return None

        try:
            sent_dt = parsedate_to_datetime(date_header).astimezone(timezone.utc)
        except Exception:
            internal_ms = int(initial_msg.get('internalDate', 0))
            sent_dt = datetime.fromtimestamp(internal_ms / 1000.0, tz=timezone.utc) if internal_ms else datetime.now(timezone.utc)

        text_body, html_body = cls.extract_body_from_payload(payload)
        snippet = initial_msg.get('snippet', '')

        # Prospect name derivation
        if not recipient_name or '@' in recipient_name:
            salutation_match = re.search(r'(?:hi|hello|hey|dear)\s+([A-Z][a-z]+)', text_body, re.IGNORECASE)
            if salutation_match:
                recipient_name = salutation_match.group(1).capitalize()

        company = cls.extract_company_from_email_or_domain(recipient_email)

        # 1. Create Prospect Record
        prospect = db.query(ProspectModel).filter(
            ProspectModel.email == recipient_email
        ).first()

        if not prospect:
            prospect = ProspectModel(
                user_id=account.user_id,
                name=recipient_name or None,
                email=recipient_email,
                company=company,
                status="PENDING"
            )
            db.add(prospect)
            db.flush()

        # Follow-up waiting delay (default 72 hours)
        delay_hours = 72
        user_settings = db.query(AutomationSettingsModel).first()
        if user_settings and user_settings.followup_delay_hours:
            delay_hours = user_settings.followup_delay_hours

        next_followup = sent_dt + timedelta(hours=delay_hours)

        # 2. Create Email Thread Record
        new_thread = EmailThreadModel(
            user_id=account.user_id,
            prospect_id=prospect.id,
            gmail_thread_id=thread_id,
            gmail_original_message_id=msg_id,
            original_subject=subject,
            original_body=text_body or snippet,
            original_sent_at=sent_dt,
            next_followup_at=next_followup,
            followup_count=0,
            status="PENDING"
        )
        db.add(new_thread)
        db.flush()

        # 3. Create Email Message Record
        new_msg = EmailMessageModel(
            thread_record_id=new_thread.id,
            gmail_message_id=msg_id,
            sender=sender_email,
            recipient=recipient_email,
            subject=subject,
            body=text_body or snippet,
            message_type="OUTBOUND_INITIAL",
            sent_at=sent_dt
        )
        db.add(new_msg)
        db.commit()

        # 4. Apply AUTO_FOLLOWUP label in Gmail
        GmailLabelManager.apply_label_to_thread(service, thread_id)

        # Log Activity
        action_name = "MANUAL_EMAIL_TRACKED" if manual else "AUTO_EMAIL_TRACKED"
        act = ActivityLogModel(
            user_id=account.user_id,
            action=action_name,
            description=f"Now tracking outreach email to {recipient_email} in thread {thread_id} with label AUTO_FOLLOWUP"
        )
        db.add(act)
        db.commit()

        return new_thread

    @classmethod
    def list_recent_sent_emails(cls, account: ConnectedEmailAccountModel, db: Session, max_results: int = 25) -> List[Dict[str, Any]]:
        """
        Retrieves recent sent emails from Gmail for manual inspection and tracking.
        """
        service = GoogleOAuthService.get_gmail_service(account, db)
        results = service.users().messages().list(
            userId='me',
            q='in:sent',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        tracked_thread_ids = {
            t.gmail_thread_id for t in db.query(EmailThreadModel.gmail_thread_id).all()
        }

        sent_list = []
        for m in messages:
            msg_id = m['id']
            thread_id = m['threadId']

            try:
                full_msg = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='metadata',
                    metadataHeaders=['To', 'From', 'Subject', 'Date']
                ).execute()

                headers = {h['name']: h['value'] for h in full_msg.get('payload', {}).get('headers', [])}
                to_addr = headers.get('To', '')
                subj = headers.get('Subject', '(No Subject)')
                date_str = headers.get('Date', '')

                name, clean_to = cls.clean_email(to_addr)

                sent_list.append({
                    "gmail_message_id": msg_id,
                    "gmail_thread_id": thread_id,
                    "recipient_name": name,
                    "recipient_email": clean_to,
                    "subject": subj,
                    "date": date_str,
                    "snippet": full_msg.get('snippet', ''),
                    "is_already_tracked": thread_id in tracked_thread_ids
                })
            except Exception:
                continue

        return sent_list

    @classmethod
    def sync_sent_messages(cls, account: ConnectedEmailAccountModel, db: Session, max_results: int = 30) -> Dict[str, Any]:
        """
        Automatic Tracking Engine: Scans sent emails, applies cold outreach filters,
        and automatically tracks eligible cold email threads.
        """
        stats = {"scanned": 0, "identified_cold_emails": 0, "skipped": 0, "errors": 0}
        
        try:
            service = GoogleOAuthService.get_gmail_service(account, db)
            settings_model = db.query(AutomationSettingsModel).first()
            if not settings_model:
                settings_model = AutomationSettingsModel(user_id=account.user_id)
                db.add(settings_model)
                db.commit()

            suppressions = [
                s.email.lower() 
                for s in db.query(SuppressionModel).all()
            ]

            results = service.users().messages().list(
                userId='me',
                q='in:sent',
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])
            stats["scanned"] = len(messages)

            for msg_meta in messages:
                thread_id = msg_meta['threadId']

                # Check if thread is already tracked
                existing_thread = db.query(EmailThreadModel).filter(
                    EmailThreadModel.gmail_thread_id == thread_id
                ).first()
                if existing_thread:
                    stats["skipped"] += 1
                    continue

                full_msg = service.users().messages().get(
                    userId='me',
                    id=msg_meta['id'],
                    format='full'
                ).execute()

                payload = full_msg.get('payload', {})
                raw_headers = payload.get('headers', [])
                headers_dict = {h['name']: h['value'] for h in raw_headers}

                to_header = headers_dict.get('To', '')
                from_header = headers_dict.get('From', account.gmail_address)
                subject = headers_dict.get('Subject', '(No Subject)')
                text_body, _ = cls.extract_body_from_payload(payload)

                _, recipient_email = cls.clean_email(to_header)
                _, sender_email = cls.clean_email(from_header)

                if not recipient_email or '@' not in recipient_email:
                    stats["skipped"] += 1
                    continue

                is_cold, reason = cls.is_eligible_cold_outreach(
                    recipient_email=recipient_email,
                    sender_email=sender_email,
                    subject=subject,
                    headers=headers_dict,
                    body_text=text_body or full_msg.get('snippet', ''),
                    settings_model=settings_model,
                    suppressions=suppressions
                )

                if not is_cold:
                    stats["skipped"] += 1
                    continue

                # Eligible -> track conversation
                cls.track_conversation(account, thread_id, db, manual=False)
                stats["identified_cold_emails"] += 1

        except Exception as e:
            stats["errors"] += 1
            stats["error"] = str(e)

        return stats
