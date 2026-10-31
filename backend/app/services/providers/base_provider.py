from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import ConnectedEmailAccountModel, EmailThreadModel

class BaseEmailProvider(ABC):
    """
    Common modular email provider interface strictly adhering to Section 2
    of the Final Implementation Specification.
    Defines the 10 core methods required for all supported providers (Gmail & Hostinger).
    """

    def __init__(self, account: ConnectedEmailAccountModel):
        self.account = account

    # 1. connect_account
    @abstractmethod
    def connect_account(self, credentials_payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Authenticates, encrypts, and links the account."""
        pass

    # 2. disconnect_account
    @abstractmethod
    def disconnect_account(self, db: Session) -> Dict[str, Any]:
        """Revokes tokens/passwords and marks account disconnected safely."""
        pass

    # 3. verify_connection
    @abstractmethod
    def verify_connection(self) -> Tuple[bool, str]:
        """Tests credentials, SSL handshake, and mailbox responsiveness."""
        pass

    # 4. send_email
    @abstractmethod
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
        """Sends an email in-thread from this account's sending identity."""
        pass

    # 5. fetch_sent_emails
    @abstractmethod
    def fetch_sent_emails(self, max_results: int = 25, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Retrieves recently sent messages from the Sent folder for tracking."""
        pass

    # 6. fetch_inbox_emails
    @abstractmethod
    def fetch_inbox_emails(self, max_results: int = 25, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Retrieves incoming messages from the Inbox."""
        pass

    # 7. fetch_conversation
    @abstractmethod
    def fetch_conversation(self, conversation_id: str, db: Session) -> Dict[str, Any]:
        """Retrieves full normalized message history for a conversation thread."""
        pass

    # 8. detect_replies
    @abstractmethod
    def detect_replies(self, thread: EmailThreadModel, db: Session) -> Dict[str, Any]:
        """Inspects incoming messages to detect genuine replies, bounces, or opt-outs."""
        pass

    # 9. synchronize_mailbox
    @abstractmethod
    def synchronize_mailbox(self, db: Session) -> Dict[str, Any]:
        """Synchronizes new messages and updates sync checkpoints (UID/HistoryID)."""
        pass

    # 10. get_message_status
    @abstractmethod
    def get_message_status(self, message_id: str, db: Session) -> Dict[str, Any]:
        """Checks delivery or response status of a message."""
        pass

    # --- Backward compatibility aliases ---
    def test_connection(self) -> Tuple[bool, str]:
        return self.verify_connection()

    def check_for_reply(self, thread: EmailThreadModel, db: Session) -> Dict[str, Any]:
        return self.detect_replies(thread, db)

    def send_followup(self, thread: EmailThreadModel, draft_content: str, db: Session, test_mode: bool = False) -> Dict[str, Any]:
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

        orig_msg_id = thread.original_message_id or thread.gmail_original_message_id or thread.gmail_thread_id
        prospect_email = thread.prospect.email if thread.prospect else (thread.recipient_address or "")
        subject = thread.original_subject or "Following up"
        return self.send_email(
            to_email=prospect_email,
            subject=subject,
            body_text=draft_content,
            in_reply_to_id=orig_msg_id,
            references_id=orig_msg_id,
            thread_id=thread.gmail_thread_id,
            test_mode=test_mode,
            db=db
        )

    def sync_sent_emails(self, db: Session, max_results: int = 20) -> List[Dict[str, Any]]:
        return self.fetch_sent_emails(max_results=max_results, db=db)
