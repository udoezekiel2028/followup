-- ==============================================================================
-- SmartFollow AI Database Schema (PostgreSQL / Supabase)
-- Multi-Account Architecture (Gmail + Professional Domain SMTP/IMAP)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------------------------
-- 1. USERS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 2. CONNECTED_EMAIL_ACCOUNTS (Section G Schema)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connected_email_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    email_address VARCHAR(255) NOT NULL,
    provider_type VARCHAR(50) DEFAULT 'GMAIL' NOT NULL, -- 'GMAIL', 'SMTP_IMAP'
    provider_account_identifier VARCHAR(255),
    authentication_type VARCHAR(50) DEFAULT 'OAUTH2' NOT NULL, -- 'OAUTH2', 'PASSWORD'
    encrypted_credentials TEXT NOT NULL,
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,
    token_expiry TIMESTAMPTZ,
    connection_status VARCHAR(50) DEFAULT 'CONNECTED' NOT NULL, -- 'CONNECTED', 'EXPIRED', 'DISCONNECTED', 'ERROR'
    auto_followup_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    daily_sending_limit INT DEFAULT 50 NOT NULL,
    daily_sent_count INT DEFAULT 0 NOT NULL,
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 3. PROSPECTS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prospects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    sending_account_id UUID REFERENCES connected_email_accounts(id) ON DELETE SET NULL,
    name VARCHAR(255),
    email VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    status VARCHAR(50) DEFAULT 'PENDING' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 4. EMAIL_THREADS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    sending_account_id UUID REFERENCES connected_email_accounts(id) ON DELETE CASCADE,
    email_provider VARCHAR(50) DEFAULT 'GMAIL' NOT NULL,
    prospect_id UUID REFERENCES prospects(id) ON DELETE SET NULL,
    recipient_address VARCHAR(255),
    gmail_thread_id VARCHAR(255) NOT NULL,
    gmail_original_message_id VARCHAR(255),
    original_message_id VARCHAR(255),
    original_subject TEXT,
    original_body TEXT,
    original_sent_at TIMESTAMPTZ NOT NULL,
    next_followup_at TIMESTAMPTZ,
    followup_count INT DEFAULT 0 NOT NULL,
    last_followup_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'PENDING' NOT NULL,
    replied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 5. EMAIL_MESSAGES
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sending_account_id UUID REFERENCES connected_email_accounts(id) ON DELETE CASCADE,
    thread_record_id UUID REFERENCES email_threads(id) ON DELETE CASCADE,
    gmail_message_id VARCHAR(255) NOT NULL,
    sender VARCHAR(255) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    subject TEXT,
    body TEXT,
    message_type VARCHAR(50) NOT NULL, -- 'OUTBOUND_INITIAL', 'OUTBOUND_FOLLOWUP', 'INBOUND_REPLY', 'INBOUND_BOUNCE', 'INBOUND_OOO'
    sent_at TIMESTAMPTZ NOT NULL
);

-- ------------------------------------------------------------------------------
-- 6. FOLLOW_UP_LOGS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS follow_up_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sending_account_id UUID REFERENCES connected_email_accounts(id) ON DELETE CASCADE,
    email_thread_id UUID REFERENCES email_threads(id) ON DELETE CASCADE,
    generated_content TEXT,
    gmail_message_id VARCHAR(255),
    sent_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'DRAFT' NOT NULL, -- 'DRAFT', 'SENT', 'FAILED', 'CANCELLED'
    error_message TEXT
);

-- ------------------------------------------------------------------------------
-- 7. SUPPRESSION_LIST
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppression_list (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    reason VARCHAR(100) DEFAULT 'DO_NOT_CONTACT' NOT NULL, -- 'BOUNCED', 'UNSUBSCRIBED', 'DO_NOT_CONTACT', 'MANUAL_EXCLUSION'
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 8. AUTOMATION_SETTINGS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS automation_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    followup_delay_hours INT DEFAULT 72 NOT NULL,
    sending_window VARCHAR(50) DEFAULT '09:00-17:00' NOT NULL,
    timezone VARCHAR(50) DEFAULT 'America/New_York' NOT NULL,
    maximum_followups INT DEFAULT 1 NOT NULL,
    auto_send_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    test_mode BOOLEAN DEFAULT TRUE NOT NULL,
    ai_model VARCHAR(50) DEFAULT 'gpt-4o-mini',
    ai_instructions TEXT DEFAULT 'Generate a brief, natural, high-converting cold email follow-up. Do not sound aggressive or desperate. Reference the original outreach politely.',
    email_signature TEXT DEFAULT 'Best regards,',
    excluded_domains JSONB DEFAULT '["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]'::jsonb,
    excluded_emails JSONB DEFAULT '[]'::jsonb
);

-- ------------------------------------------------------------------------------
-- 9. ACTIVITY_LOGS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ------------------------------------------------------------------------------
-- PERFORMANCE INDEXES
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_accounts_email ON connected_email_accounts(email_address);
CREATE INDEX IF NOT EXISTS idx_accounts_provider ON connected_email_accounts(provider_type);
CREATE INDEX IF NOT EXISTS idx_prospects_email ON prospects(email);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_prospects_sending_account ON prospects(sending_account_id);
CREATE INDEX IF NOT EXISTS idx_threads_status ON email_threads(status);
CREATE INDEX IF NOT EXISTS idx_threads_next_followup ON email_threads(next_followup_at);
CREATE INDEX IF NOT EXISTS idx_threads_gmail_thread ON email_threads(gmail_thread_id);
CREATE INDEX IF NOT EXISTS idx_threads_sending_account ON email_threads(sending_account_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON email_messages(thread_record_id);
CREATE INDEX IF NOT EXISTS idx_messages_sending_account ON email_messages(sending_account_id);
CREATE INDEX IF NOT EXISTS idx_followup_logs_thread ON follow_up_logs(email_thread_id);
CREATE INDEX IF NOT EXISTS idx_followup_logs_sending_account ON follow_up_logs(sending_account_id);
CREATE INDEX IF NOT EXISTS idx_suppression_email ON suppression_list(email);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at DESC);
