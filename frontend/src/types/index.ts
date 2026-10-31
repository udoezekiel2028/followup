export type ThreadStatus = 
  | 'PENDING'
  | 'DUE FOR FOLLOW-UP'
  | 'FOLLOW-UP SENT'
  | 'RESPONDED'
  | 'BOUNCED'
  | 'UNSUBSCRIBED'
  | 'FAILED'
  | 'PAUSED'
  | 'STOPPED';

export type ProspectStatus = ThreadStatus;

export interface TrackedThread {
  id: string;
  sending_account_id?: string | null;
  sending_account_email?: string | null;
  email_provider?: string;
  prospect_id: string | null;
  prospect_name: string | null;
  prospect_email: string;
  prospect_company: string | null;
  gmail_thread_id: string;
  original_subject: string | null;
  original_body: string | null;
  original_sent_at: string;
  next_followup_at: string | null;
  time_remaining: string;
  followup_count: number;
  last_followup_at: string | null;
  status: ThreadStatus;
  replied_at: string | null;
  days_elapsed: number;
}

export interface TrackedThreadListResponse {
  items: TrackedThread[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type Prospect = TrackedThread;
export type ProspectListResponse = TrackedThreadListResponse;

export interface SentExplorerItem {
  gmail_message_id: string;
  gmail_thread_id: string;
  recipient_name: string;
  recipient_email: string;
  subject: string;
  date: string;
  snippet: string;
  is_already_tracked: boolean;
  sending_account?: string;
  sending_account_id?: string;
  sending_account_email?: string;
  provider_type?: string;
}

export interface AccountSummary {
  account_id: string;
  email_address: string;
  provider_type: 'GMAIL' | 'SMTP_IMAP';
  connection_status: 'CONNECTED' | 'EXPIRED' | 'DISCONNECTED' | 'ERROR';
  auto_followup_enabled: boolean;
  daily_sending_limit: number;
  daily_sent_count: number;
  last_sync_at: string | null;
  total_tracked: number;
  pending_followups: number;
  followups_sent: number;
  replies_received: number;
  bounced_emails: number;
}

export interface DashboardStats {
  filter_account_id?: string | null;
  total_tracked: number;
  awaiting_followup: number;
  followups_due_today: number;
  followups_sent: number;
  responded: number;
  bounced: number;
  followup_response_rate: number;
  overall_response_rate: number;
  test_mode_active: boolean;
  auto_send_active: boolean;
  status_counts: Record<string, number>;
  accounts_summary?: AccountSummary[];
  total_connected_accounts?: number;
  recent_activity: ActivityLog[];
}

export interface EmailMessage {
  id: string;
  sending_account_id?: string | null;
  gmail_message_id: string;
  sender: string;
  recipient: string;
  subject: string | null;
  body: string | null;
  message_type: string;
  sent_at: string;
}

export interface FollowUpDraft {
  id: string;
  generated_content: string | null;
  status: string;
  error_message: string | null;
}

export interface ThreadDetail {
  thread: {
    id: string;
    sending_account_id?: string | null;
    sending_account_email?: string | null;
    email_provider?: string;
    gmail_thread_id: string;
    original_subject: string | null;
    original_body: string | null;
    original_sent_at: string;
    status: ThreadStatus;
    followup_count: number;
    replied_at: string | null;
  };
  prospect: {
    id: string | null;
    name: string | null;
    email: string;
    company: string | null;
  };
  messages: EmailMessage[];
  draft: FollowUpDraft | null;
}

export interface ConnectedAccount {
  id: string;
  email_address: string;
  gmail_address: string;
  provider_type: 'GMAIL' | 'SMTP_IMAP';
  provider_account_identifier?: string | null;
  authentication_type: 'OAUTH2' | 'PASSWORD';
  connection_status: 'CONNECTED' | 'EXPIRED' | 'DISCONNECTED' | 'ERROR';
  status: string;
  is_active: boolean;
  auto_followup_enabled: boolean;
  daily_sending_limit: number;
  daily_sent_count: number;
  last_sync_at: string | null;
  created_at: string;
  connected_at?: string;
  stats?: {
    total_tracked: number;
    pending_followups: number;
    followups_sent: number;
    replies_received: number;
    bounced_emails: number;
  };
}

export interface ConnectSmtpImapPayload {
  email_address: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  smtp_encryption: 'SSL' | 'STARTTLS' | 'NONE';
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_password: string;
  imap_encryption: 'SSL' | 'STARTTLS' | 'NONE';
  daily_sending_limit: number;
}

export interface AutomationSettings {
  id: string;
  followup_delay_hours: number;
  sending_window: string;
  timezone: string;
  maximum_followups: number;
  auto_send_enabled: boolean;
  test_mode: boolean;
  ai_model: string;
  ai_instructions: string;
  email_signature: string;
  excluded_domains: string[];
  excluded_emails: string[];
  connected_account: ConnectedAccount | null;
}

export interface SuppressionItem {
  id: string;
  email: string;
  reason: string;
  created_at?: string;
}

export interface ActivityLog {
  id: string;
  event_type: string;
  message: string;
  metadata_json?: Record<string, any>;
  created_at: string;
}

export interface DeliverabilityCheckResult {
  domain: string;
  overall_status: 'EXCELLENT' | 'GOOD' | 'ATTENTION_NEEDED';
  score: number;
  checks: {
    spf: {
      passed: boolean;
      record: string | null;
      recommended_record: string;
    };
    dkim: {
      passed: boolean;
      selector: string;
      record: string | null;
    };
    dmarc: {
      passed: boolean;
      policy: string;
      record: string | null;
      recommended_record: string;
    };
    mx: {
      passed: boolean;
      records: string[];
    };
  };
  recommendations: string[];
  account_id?: string;
  email_address?: string;
  provider_type?: string;
}
