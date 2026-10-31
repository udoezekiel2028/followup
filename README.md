# AI-Powered Cold Email Follow-Up Automation System

A production-ready SaaS application that automatically monitors outbound cold emails sent to prospects from your Gmail or Google Workspace account, detects whether they have replied within 72 hours, and sends personalized AI-generated follow-up emails in the original conversation thread.

---

## 🌟 Key Features

1. **Automatic Outbound Cold Email Detection**:
   - Connects securely via **Google OAuth 2.0**.
   - Filters out personal emails, newsletters (`List-Unsubscribe`), receipts, billing notifications, and internal coworker emails.
   - Automatically parses prospect name, email, company, subject, original outreach message, Gmail message ID, thread ID, and sent timestamp.
2. **72-Hour Reply & Thread Intelligence**:
   - Hourly background worker scans active prospect threads.
   - Accurately checks whether any inbound messages have arrived from the prospect after the initial email.
   - Marks status as **`RESPONDED`** and halts future follow-ups.
   - Automatically detects **Bounces / Delivery Status Notifications (NDR)** -> Marks as **`BOUNCED`** and adds to suppression list.
   - Automatically detects **Opt-Out / Unsubscribe Requests** -> Marks as **`UNSUBSCRIBED`** and adds to suppression list.
3. **AI Follow-Up Copywriting (OpenAI)**:
   - Analyzes original email context, value proposition, prospect name, and company.
   - Adheres to custom tone, word length limit, and user signature.
   - Strictly enforces rules: no desperation, no hallucinations, no verbatim repetition.
4. **Safety & Duplicate Prevention**:
   - **Test Mode Default**: Generates and saves follow-up drafts to the database without sending live emails until explicitly toggled.
   - **Single Follow-Up Guarantee**: Strictly enforces a maximum of 1 automatic follow-up per cold outreach email.
   - Concurrency locking prevents double processing.
   - Suppresses excluded emails, excluded domains, and blacklisted contacts.
5. **Modern Dashboard & Studio (React + TypeScript + Tailwind CSS)**:
   - Analytics overview cards: Total Tracked, Awaiting Follow-Up, Follow-Ups Sent, Responded, Bounced, Success Rate.
   - Rich prospect table with search, status filters, sorting, and pagination.
   - Interactive modals to view conversation threads and edit/generate AI drafts in real-time.
   - Full configuration for Google OAuth, delay duration (default 72h), send window, timezone, and suppression list.
6. **Deployable to Railway & Cloud**:
   - Multi-stage `Dockerfile`, `railway.json`, and `Procfile`.

---

## 🏗️ Technology Stack

- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite, Lucide Icons
- **Backend**: Python 3.11+, FastAPI, Pydantic V2, SQLAlchemy
- **Database**: Supabase / PostgreSQL (with local SQLite fallback for instant zero-dependency testing)
- **Email Integration**: Gmail API (`google-api-python-client`, Google OAuth 2.0)
- **AI Integration**: OpenAI API (`gpt-4o-mini`, `gpt-4o`)
- **Background Scheduler**: APScheduler (hourly automated execution)
- **Deployment**: Railway / Docker

---

## 📁 Project Structure

```
.
├── Dockerfile                  # Multi-stage production container
├── railway.json                # Railway configuration manifest
├── Procfile                    # Web service process command
├── backend/
│   ├── .env.example            # Environment configuration template
│   ├── pytest.ini              # Pytest configuration
│   ├── requirements.txt        # Backend dependencies
│   ├── supabase_schema.sql     # Complete Supabase PostgreSQL schema with RLS & 9 tables
│   ├── app/
│   │   ├── main.py             # FastAPI entrypoint, lifespan & SPA serving
│   │   ├── config.py           # Pydantic BaseSettings configuration
│   │   ├── database.py         # SQLAlchemy & Supabase connection layer (9 tables)
│   │   ├── models/schemas.py   # Pydantic request & response models
│   │   ├── routers/            # API endpoints
│   │   │   ├── auth.py         # Google OAuth 2.0 URL & callback
│   │   │   ├── dashboard.py    # Analytics overview & statistics
│   │   │   ├── prospects.py    # Prospect CRUD, search, thread & draft endpoints
│   │   │   ├── settings.py     # Configuration, AI rules, and suppression lists
│   │   │   ├── automation.py   # Manual sync trigger, cycle trigger & demo seed
│   │   │   └── logs.py         # Audit trail activity logs
│   │   └── services/           # Core domain logic
│   │       ├── oauth_service.py   # Google OAuth flow & token refresh
│   │       ├── gmail_monitor.py   # Outbound sent message heuristic filter
│   │       ├── reply_detector.py  # Thread inspection, reply & bounce detector
│   │       ├── ai_followup.py     # OpenAI contextual follow-up generator
│   │       ├── mailer_service.py  # In-thread RFC 2822 sender & draft saver
│   │       └── scheduler.py       # Hourly background worker
│   └── tests/                  # Automated pytest suite
│       ├── test_reply_detector.py
│       ├── test_ai_followup.py
│       ├── test_duplicate_prevention.py
│       └── test_endpoints.py
└── frontend/
    ├── package.json            # React & Vite dependencies
    ├── vite.config.ts          # Vite configuration with /api proxy
    ├── tailwind.config.js      # Tailwind CSS configuration
    └── src/
        ├── types/              # TypeScript interfaces
        ├── services/api.ts     # Axios API client
        ├── components/         # Navbar, StatusBadge, ThreadModal, DraftModal
        └── pages/              # Dashboard, Prospects, Settings, Logs
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Node.js**: v18+ or v20+
- **Python**: 3.11+

### 2. Backend Setup
1. Open a terminal in the project directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .\.venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```
5. Run the backend development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   FastAPI interactive documentation will be available at: `http://localhost:8000/docs`

### 3. Frontend Setup
1. In a separate terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
2. Open your browser at `http://localhost:3000`

---

## 🔑 Credential Configuration

Edit `backend/.env` with your API credentials:

```env
# Application
APP_ENV=development
PORT=8000
FRONTEND_URL=http://localhost:3000
SECRET_KEY=your-secure-random-32-char-secret-key

# Supabase (PostgreSQL)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
DATABASE_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres

# OpenAI API
OPENAI_API_KEY=sk-proj-your-openai-api-key
OPENAI_DEFAULT_MODEL=gpt-4o-mini

# Google OAuth 2.0 (Gmail API)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

# Automation Defaults
DEFAULT_FOLLOW_UP_DELAY_HOURS=72
DEFAULT_TEST_MODE=True
DEFAULT_AUTO_SEND=False
```

### Setting Up Google OAuth 2.0 Credentials:
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a Project (e.g. `Cold Email Follow-Up System`).
3. Enable the **Gmail API** under **APIs & Services > Library**.
4. Go to **APIs & Services > OAuth consent screen**:
   - User Type: **External** (or Internal if using Google Workspace).
   - Add scopes: `.../auth/gmail.modify`, `.../auth/gmail.send`, `.../auth/userinfo.email`.
5. Go to **APIs & Services > Credentials > Create Credentials > OAuth Client ID**:
   - Application Type: **Web application**.
   - Authorized Redirect URI: `http://localhost:8000/api/auth/google/callback` (or your Railway production URL).
6. Copy the **Client ID** and **Client Secret** into your `backend/.env`.

### Setting Up Supabase Database:
1. In your [Supabase Dashboard](https://supabase.com/), open the **SQL Editor**.
2. Open `backend/supabase_schema.sql` and run the script.
3. This creates all 9 tables, indexes, and Row Level Security (RLS) policies.

---

## 🧪 Testing the 72-Hour Follow-Up Logic

We have included automated unit tests and a demo seeder for immediate end-to-end verification without waiting 3 days:

### 1. Run Automated Unit Tests:
```bash
cd backend
.\.venv\Scripts\pytest
```
Tests verify:
- ✅ Mailer-Daemon and Postmaster bounce detection.
- ✅ Unsubscribe and opt-out keyword detection.
- ✅ Contextual AI follow-up prompt builder & length enforcement.
- ✅ Strict duplicate follow-up prevention.
- ✅ Terminal status safeguards (`RESPONDED`, `BOUNCED`, `UNSUBSCRIBED`).

### 2. Verify in the Web Dashboard:
1. Open `http://localhost:3000`.
2. Click **"Seed Demo Data (72h+)"** on the dashboard.
3. This seeds 4 realistic prospects:
   - Sarah Jenkins (sent 75h ago -> **`DUE FOR FOLLOW-UP`**).
   - Elena Rostova (sent 40h ago -> **`PENDING`**, not due yet).
   - David Miller (sent 80h ago -> **`RESPONDED`**, reply detected).
   - Michael Chang (sent 80h ago).
4. Click **"Run Automation"** in the top bar to trigger the 72-hour cycle.
5. In **Test Mode**, watch drafts automatically generate and save without sending.
6. Open the **AI Follow-Up Studio** on any prospect to preview, tweak, or test live dispatch.

---

## 🚢 Railway Deployment

1. Create a new project on [Railway.app](https://railway.app/).
2. Connect your GitHub repository.
3. Railway automatically detects the root `Dockerfile` and builds both frontend and backend.
4. Under **Variables** in Railway, add:
   - `OPENAI_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI` (e.g. `https://your-app.up.railway.app/api/auth/google/callback`)
   - `DATABASE_URL` (Supabase connection string)
   - `SECRET_KEY`
5. Railway provides automatic HTTPS and continuous deployment on every git commit.
