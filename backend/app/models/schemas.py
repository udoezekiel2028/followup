from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class ProspectStatus(str, Enum):
    PENDING = "PENDING"
    DUE_FOR_FOLLOW_UP = "DUE FOR FOLLOW-UP"
    FOLLOW_UP_SENT = "FOLLOW-UP SENT"
    RESPONDED = "RESPONDED"
    BOUNCED = "BOUNCED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    FAILED = "FAILED"
    EXCLUDED = "EXCLUDED"

# ------------------------------------------------------------------------------
# User & Account Schemas
# ------------------------------------------------------------------------------
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    created_at: datetime

class ConnectedAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email_address: str
    provider: str
    is_active: bool
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[str] = "IDLE"
    error_message: Optional[str] = None
    created_at: datetime

class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    state: str

# ------------------------------------------------------------------------------
# Prospect Schemas
# ------------------------------------------------------------------------------
class ProspectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    account_id: str
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
    original_subject: Optional[str] = None
    original_body: Optional[str] = None
    gmail_message_id: Optional[str] = None
    gmail_thread_id: str
    initial_sent_at: datetime
    status: str
    follow_up_count: int
    last_follow_up_at: Optional[datetime] = None
    reply_detected_at: Optional[datetime] = None
    reply_snippet: Optional[str] = None
    bounce_reason: Optional[str] = None
    notes: Optional[str] = None
    days_since_initial: Optional[int] = None
    created_at: datetime

class ProspectListResponse(BaseModel):
    items: List[ProspectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class ProspectUpdateStatusRequest(BaseModel):
    status: ProspectStatus
    notes: Optional[str] = None

# ------------------------------------------------------------------------------
# Follow-Up Log Schemas
# ------------------------------------------------------------------------------
class FollowUpLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    prospect_id: str
    account_id: str
    generated_subject: Optional[str] = None
    generated_body: Optional[str] = None
    ai_model_used: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    gmail_message_id: Optional[str] = None
    is_test_mode: bool
    error_message: Optional[str] = None
    created_at: datetime

class FollowUpGenerateRequest(BaseModel):
    custom_instructions: Optional[str] = None
    tone: Optional[str] = None

class FollowUpSendManualRequest(BaseModel):
    subject: str
    body: str
    force_live_send: bool = False

# ------------------------------------------------------------------------------
# Thread & Message Schemas
# ------------------------------------------------------------------------------
class EmailMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    thread_id: str
    gmail_message_id: str
    sender: str
    recipient: str
    subject: Optional[str] = None
    snippet: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    direction: str
    is_initial_outreach: bool
    is_follow_up: bool
    is_reply: bool
    sent_at: datetime

class EmailThreadDetailResponse(BaseModel):
    id: str
    gmail_thread_id: str
    subject: Optional[str] = None
    snippet: Optional[str] = None
    message_count: int
    has_prospect_reply: bool
    prospect: Optional[ProspectResponse] = None
    messages: List[EmailMessageResponse] = []
    follow_up_draft: Optional[FollowUpLogResponse] = None

# ------------------------------------------------------------------------------
# Settings Schemas
# ------------------------------------------------------------------------------
class AutomationSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    account_id: str
    follow_up_delay_hours: int = 72
    send_window_start: str = "09:00"
    send_window_end: str = "17:00"
    timezone: str = "America/New_York"
    ai_model: str = "gpt-4o-mini"
    ai_instructions: str
    email_signature: str
    max_email_length: int = 120
    auto_send_enabled: bool = False
    test_mode: bool = True
    excluded_domains: List[str] = []
    excluded_emails: List[str] = []
    updated_at: datetime

class AutomationSettingsUpdate(BaseModel):
    follow_up_delay_hours: Optional[int] = Field(None, ge=1, le=720)
    send_window_start: Optional[str] = None
    send_window_end: Optional[str] = None
    timezone: Optional[str] = None
    ai_model: Optional[str] = None
    ai_instructions: Optional[str] = None
    email_signature: Optional[str] = None
    max_email_length: Optional[int] = Field(None, ge=30, le=500)
    auto_send_enabled: Optional[bool] = None
    test_mode: Optional[bool] = None
    excluded_domains: Optional[List[str]] = None
    excluded_emails: Optional[List[str]] = None

# ------------------------------------------------------------------------------
# Dashboard Statistics
# ------------------------------------------------------------------------------
class DashboardStatsResponse(BaseModel):
    total_tracked: int
    awaiting_followup: int
    followups_sent: int
    responded: int
    bounced: int
    followup_success_rate: float
    overall_response_rate: float
    test_mode_active: bool
    auto_send_active: bool
    status_counts: Dict[str, int]
    recent_activity: List[Dict[str, Any]] = []

# ------------------------------------------------------------------------------
# Suppression List Schemas
# ------------------------------------------------------------------------------
class SuppressionCreate(BaseModel):
    email_or_domain: str
    type: str = "EMAIL"
    reason: str = "DO_NOT_CONTACT"

class SuppressionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email_or_domain: str
    type: str
    reason: str
    created_at: datetime

# ------------------------------------------------------------------------------
# Activity Logs
# ------------------------------------------------------------------------------
class ActivityLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    message: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
