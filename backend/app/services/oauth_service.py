import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from app.config import settings
from app.security import encrypt_token, decrypt_token, encrypt_credentials, decrypt_credentials
from app.database import ConnectedEmailAccountModel, AutomationSettingsModel, ActivityLogModel, utc_now

class GoogleOAuthService:
    @staticmethod
    def get_oauth_flow(state: Optional[str] = None) -> Flow:
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID or "placeholder-client-id",
                "client_secret": settings.GOOGLE_CLIENT_SECRET or "placeholder-client-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=settings.GOOGLE_SCOPES,
            state=state
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        return flow

    @staticmethod
    def get_authorization_url(state: Optional[str] = None) -> Dict[str, str]:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            return {
                "auth_url": f"{settings.FRONTEND_URL}/accounts?error=missing_google_credentials",
                "state": state or "no-creds",
                "warning": "Google OAuth credentials not configured in backend/.env"
            }
        
        flow = GoogleOAuthService.get_oauth_flow(state=state)
        authorization_url, generated_state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account consent' # Enables multi-account chooser and guarantees refresh_token
        )
        return {
            "auth_url": authorization_url,
            "state": generated_state
        }

    @staticmethod
    def exchange_code_for_tokens(code: str, db: Session) -> ConnectedEmailAccountModel:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ValueError("Google Client ID and Client Secret must be configured in environment.")

        flow = GoogleOAuthService.get_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Retrieve user profile from Google
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        gmail_address = user_info.get("email")

        if not gmail_address:
            raise ValueError("Could not retrieve email address from Google OAuth profile.")

        gmail_address_clean = gmail_address.strip().lower()

        # Check if connected account exists
        account = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.email_address == gmail_address_clean
        ).first()

        expiry_dt = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None

        # Encrypt tokens before saving to database
        enc_access = encrypt_token(credentials.token)
        enc_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else None
        
        creds_dict = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": expiry_dt.isoformat() if expiry_dt else None
        }
        enc_credentials_json = encrypt_credentials(creds_dict)

        if not account:
            account = ConnectedEmailAccountModel(
                email_address=gmail_address_clean,
                provider_type="GMAIL",
                provider_account_identifier=user_info.get("id", gmail_address_clean),
                authentication_type="OAUTH2",
                encrypted_credentials=enc_credentials_json,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                token_expiry=expiry_dt,
                connection_status="CONNECTED",
                auto_followup_enabled=True,
                daily_sending_limit=50
            )
            db.add(account)
            db.flush()

            # Ensure default automation settings exist
            automation_settings = db.query(AutomationSettingsModel).first()
            if not automation_settings:
                automation_settings = AutomationSettingsModel(
                    user_id=account.user_id,
                    followup_delay_hours=settings.DEFAULT_FOLLOW_UP_DELAY_HOURS,
                    test_mode=settings.DEFAULT_TEST_MODE,
                    auto_send_enabled=settings.DEFAULT_AUTO_SEND
                )
                db.add(automation_settings)
        else:
            account.encrypted_credentials = enc_credentials_json
            account.encrypted_access_token = enc_access
            if enc_refresh:
                account.encrypted_refresh_token = enc_refresh
            account.token_expiry = expiry_dt
            account.connection_status = "CONNECTED"

        account.last_sync_at = utc_now()
        db.commit()
        db.refresh(account)

        # Log activity
        log = ActivityLogModel(
            user_id=account.user_id,
            action="ACCOUNT_CONNECTED",
            description=f"Connected Gmail account {gmail_address_clean} via OAuth 2.0 with encrypted credentials"
        )
        db.add(log)
        db.commit()

        return account

    @staticmethod
    def get_credentials(account: ConnectedEmailAccountModel, db: Session) -> Credentials:
        """Decrypts tokens and returns valid Google Credentials, automatically refreshing if expired."""
        expiry = account.token_expiry
        if expiry and expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

        # Attempt to decrypt from encrypted_credentials JSON, fallback to legacy token columns
        plain_access = None
        plain_refresh = None
        if account.encrypted_credentials:
            creds_data = decrypt_credentials(account.encrypted_credentials)
            plain_access = creds_data.get("token")
            plain_refresh = creds_data.get("refresh_token")

        if not plain_access:
            plain_access = decrypt_token(account.encrypted_access_token)
        if not plain_refresh:
            plain_refresh = decrypt_token(account.encrypted_refresh_token)

        creds = Credentials(
            token=plain_access,
            refresh_token=plain_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=settings.GOOGLE_SCOPES,
            expiry=expiry
        )

        # Refresh token if expired or close to expiry
        if creds.expired or (expiry and expiry < datetime.utcnow()):
            if creds.refresh_token:
                try:
                    creds.refresh(Request())
                    account.encrypted_access_token = encrypt_token(creds.token)
                    if creds.expiry:
                        account.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
                    account.encrypted_credentials = encrypt_credentials({
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "expiry": creds.expiry.isoformat() if creds.expiry else None
                    })
                    account.connection_status = "CONNECTED"
                    db.commit()
                except Exception as e:
                    account.connection_status = "ERROR"
                    db.commit()
                    raise RuntimeError(f"Failed to refresh Google OAuth token for {account.email_address}: {str(e)}")
            else:
                account.connection_status = "EXPIRED"
                db.commit()
                raise RuntimeError(f"Refresh token missing for {account.email_address}. Please re-authenticate your Gmail account.")

        return creds

    @staticmethod
    def get_gmail_service(account: ConnectedEmailAccountModel, db: Session):
        creds = GoogleOAuthService.get_credentials(account, db)
        return build('gmail', 'v1', credentials=creds)
