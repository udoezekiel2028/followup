import os
import uuid
from datetime import datetime, timezone
from typing import Generator, Optional
from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, Integer, 
    DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from app.config import settings

db_url = settings.DATABASE_URL or "sqlite:///./cold_email.db"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# ------------------------------------------------------------------------------
# 1. users
# ------------------------------------------------------------------------------
class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    accounts = relationship("ConnectedEmailAccountModel", back_populates="user", cascade="all, delete-orphan")
    prospects = relationship("ProspectModel", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("EmailThreadModel", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("AutomationSettingsModel", back_populates="user", uselist=False, cascade="all, delete-orphan")
    suppressions = relationship("SuppressionModel", back_populates="user", cascade="all, delete-orphan")

# ------------------------------------------------------------------------------
# 2. connected_email_accounts (Multi-Account Support: Gmail + SMTP/IMAP)
# ------------------------------------------------------------------------------
class ConnectedEmailAccountModel(Base):
    __tablename__ = "connected_email_accounts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    email_address = Column(String(255), nullable=False, index=True)
    provider_type = Column(String(50), default="GMAIL", nullable=False) # 'GMAIL', 'SMTP_IMAP'
    provider_account_identifier = Column(String(255), nullable=True) # e.g. Google sub ID or SMTP host
    authentication_type = Column(String(50), default="OAUTH2", nullable=False) # 'OAUTH2', 'PASSWORD'
    encrypted_credentials = Column(Text, nullable=False, default="") # Fernet encrypted JSON string
    
    # Backwards-compatibility tokens
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    
    connection_status = Column(String(50), default="CONNECTED", nullable=False) # 'CONNECTED', 'EXPIRED', 'DISCONNECTED', 'ERROR'
    auto_followup_enabled = Column(Boolean, default=True, nullable=False)
    daily_sending_limit = Column(Integer, default=50, nullable=False)
    daily_sent_count = Column(Integer, default=0, nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Aliases for backwards compatibility
    @property
    def gmail_address(self) -> str:
        return self.email_address

    @gmail_address.setter
    def gmail_address(self, value: str):
        self.email_address = value

    @property
    def status(self) -> str:
        # Maps CONNECTED -> ACTIVE for backwards compatibility
        if self.connection_status == "CONNECTED":
            return "ACTIVE"
        return self.connection_status

    @status.setter
    def status(self, value: str):
        if value == "ACTIVE":
            self.connection_status = "CONNECTED"
        else:
            self.connection_status = value

    @property
    def connected_at(self) -> datetime:
        return self.created_at

    user = relationship("UserModel", back_populates="accounts")
    threads = relationship("EmailThreadModel", back_populates="sending_account", cascade="all, delete-orphan", foreign_keys="[EmailThreadModel.sending_account_id]")
    messages = relationship("EmailMessageModel", back_populates="sending_account", cascade="all, delete-orphan", foreign_keys="[EmailMessageModel.sending_account_id]")
    follow_ups = relationship("FollowUpLogModel", back_populates="sending_account", cascade="all, delete-orphan", foreign_keys="[FollowUpLogModel.sending_account_id]")
    prospects = relationship("ProspectModel", back_populates="sending_account", foreign_keys="[ProspectModel.sending_account_id]")

# ------------------------------------------------------------------------------
# 3. prospects
# ------------------------------------------------------------------------------
class ProspectModel(Base):
    __tablename__ = "prospects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    sending_account_id = Column(String(36), ForeignKey("connected_email_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=True)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("UserModel", back_populates="prospects")
    sending_account = relationship("ConnectedEmailAccountModel", back_populates="prospects", foreign_keys=[sending_account_id])
    threads = relationship("EmailThreadModel", back_populates="prospect", cascade="all, delete-orphan")

# ------------------------------------------------------------------------------
# 4. email_threads
# ------------------------------------------------------------------------------
class EmailThreadModel(Base):
    __tablename__ = "email_threads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    sending_account_id = Column(String(36), ForeignKey("connected_email_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    email_provider = Column(String(50), default="GMAIL", nullable=False) # 'GMAIL', 'SMTP_IMAP'
    prospect_id = Column(String(36), ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True)
    recipient_address = Column(String(255), nullable=True, index=True)
    gmail_thread_id = Column(String(255), nullable=False, index=True) # Stores Gmail threadId or IMAP Conversation ID / Message-ID
    gmail_original_message_id = Column(String(255), nullable=True)
    original_message_id = Column(String(255), nullable=True, index=True)
    original_subject = Column(Text, nullable=True)
    original_body = Column(Text, nullable=True)
    original_sent_at = Column(DateTime(timezone=True), nullable=False)
    next_followup_at = Column(DateTime(timezone=True), nullable=True, index=True)
    followup_count = Column(Integer, default=0, nullable=False)
    last_followup_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="PENDING", nullable=False, index=True) # PENDING, DUE FOR FOLLOW-UP, FOLLOW-UP SENT, RESPONDED, BOUNCED, UNSUBSCRIBED, PAUSED, STOPPED
    replied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user = relationship("UserModel", back_populates="threads")
    sending_account = relationship("ConnectedEmailAccountModel", back_populates="threads", foreign_keys=[sending_account_id])
    prospect = relationship("ProspectModel", back_populates="threads")
    messages = relationship("EmailMessageModel", back_populates="thread", cascade="all, delete-orphan")
    follow_ups = relationship("FollowUpLogModel", back_populates="thread", cascade="all, delete-orphan")

# ------------------------------------------------------------------------------
# 5. email_messages
# ------------------------------------------------------------------------------
class EmailMessageModel(Base):
    __tablename__ = "email_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sending_account_id = Column(String(36), ForeignKey("connected_email_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    thread_record_id = Column(String(36), ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    gmail_message_id = Column(String(255), nullable=False, index=True)
    sender = Column(String(255), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    message_type = Column(String(50), nullable=False) # 'OUTBOUND_INITIAL', 'OUTBOUND_FOLLOWUP', 'INBOUND_REPLY', 'INBOUND_BOUNCE', 'INBOUND_OOO'
    sent_at = Column(DateTime(timezone=True), nullable=False)

    sending_account = relationship("ConnectedEmailAccountModel", back_populates="messages", foreign_keys=[sending_account_id])
    thread = relationship("EmailThreadModel", back_populates="messages")

# ------------------------------------------------------------------------------
# 6. follow_up_logs
# ------------------------------------------------------------------------------
class FollowUpLogModel(Base):
    __tablename__ = "follow_up_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sending_account_id = Column(String(36), ForeignKey("connected_email_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    email_thread_id = Column(String(36), ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_content = Column(Text, nullable=True)
    gmail_message_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="DRAFT", nullable=False) # 'DRAFT', 'SENT', 'FAILED', 'CANCELLED'
    error_message = Column(Text, nullable=True)

    sending_account = relationship("ConnectedEmailAccountModel", back_populates="follow_ups", foreign_keys=[sending_account_id])
    thread = relationship("EmailThreadModel", back_populates="follow_ups")

# ------------------------------------------------------------------------------
# 7. suppression_list
# ------------------------------------------------------------------------------
class SuppressionModel(Base):
    __tablename__ = "suppression_list"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    reason = Column(String(100), default="DO_NOT_CONTACT", nullable=False) # 'BOUNCED', 'UNSUBSCRIBED', 'DO_NOT_CONTACT', 'MANUAL_EXCLUSION'
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("UserModel", back_populates="suppressions")

# ------------------------------------------------------------------------------
# 8. automation_settings
# ------------------------------------------------------------------------------
class AutomationSettingsModel(Base):
    __tablename__ = "automation_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True)
    followup_delay_hours = Column(Integer, default=72, nullable=False) # default 3 days
    sending_window = Column(String(50), default="09:00-17:00", nullable=False)
    timezone = Column(String(50), default="America/New_York", nullable=False)
    maximum_followups = Column(Integer, default=1, nullable=False)
    auto_send_enabled = Column(Boolean, default=False, nullable=False)
    test_mode = Column(Boolean, default=True, nullable=False)
    ai_model = Column(String(50), default="gpt-4o-mini")
    ai_instructions = Column(Text, default="Generate a brief, natural, high-converting cold email follow-up. Do not sound aggressive or desperate. Reference the original outreach politely.")
    email_signature = Column(Text, default="Best regards,")
    excluded_domains = Column(JSON, default=lambda: ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"])
    excluded_emails = Column(JSON, default=list)

    user = relationship("UserModel", back_populates="settings")

# ------------------------------------------------------------------------------
# 9. activity_logs
# ------------------------------------------------------------------------------
class ActivityLogModel(Base):
    __tablename__ = "activity_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True)

    user = relationship("UserModel")

def init_db():
    Base.metadata.create_all(bind=engine)
