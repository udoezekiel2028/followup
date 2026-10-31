import threading
from datetime import datetime, timezone, timedelta
import pytz
from typing import Dict, Any, List
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.config import settings
from app.database import (
    SessionLocal, ConnectedEmailAccountModel, EmailThreadModel, 
    AutomationSettingsModel, ActivityLogModel, utc_now
)
from app.services.providers.factory import get_email_provider
from app.services.mailer_service import MailerService

_account_locks: Dict[str, threading.Lock] = {}
_account_locks_guard = threading.Lock()
_active_thread_processing = set()

def _get_account_lock(account_id: str) -> threading.Lock:
    with _account_locks_guard:
        if account_id not in _account_locks:
            _account_locks[account_id] = threading.Lock()
        return _account_locks[account_id]

class AutomationEngine:
    scheduler = BackgroundScheduler()

    @classmethod
    def start(cls):
        if not cls.scheduler.running:
            cls.scheduler.add_job(
                cls.run_hourly_job,
                'interval',
                minutes=settings.SCHEDULER_INTERVAL_MINUTES,
                id='hourly_followup_cycle',
                replace_existing=True
            )
            cls.scheduler.start()

    @classmethod
    def shutdown(cls):
        if cls.scheduler.running:
            cls.scheduler.shutdown()

    @classmethod
    def is_within_send_window(cls, settings_model: AutomationSettingsModel) -> bool:
        try:
            tz = pytz.timezone(settings_model.timezone or 'UTC')
            now_tz = datetime.now(tz)
            curr_time_str = now_tz.strftime('%H:%M')

            window = settings_model.sending_window or "09:00-17:00"
            if '-' in window:
                start_str, end_str = window.split('-')
                return start_str.strip() <= curr_time_str <= end_str.strip()
            return True
        except Exception:
            return True

    @classmethod
    def run_hourly_job(cls):
        """Standard hourly background worker trigger running across all connected accounts."""
        db = SessionLocal()
        try:
            accounts = db.query(ConnectedEmailAccountModel).filter(
                ConnectedEmailAccountModel.connection_status.in_(["CONNECTED", "ACTIVE"]),
                ConnectedEmailAccountModel.auto_followup_enabled == True
            ).all()

            for account in accounts:
                # Error isolation: wrap each account execution so failure in one mailbox never stops others
                try:
                    cls.run_cycle_for_account(account.id, db)
                except Exception as e:
                    account.connection_status = "ERROR"
                    db.commit()
                    log = ActivityLogModel(
                        user_id=account.user_id,
                        action="ACCOUNT_AUTOMATION_ERROR",
                        description=f"Isolated error in mailbox {account.email_address}: {str(e)}. Other accounts continuing."
                    )
                    db.add(log)
                    db.commit()
        finally:
            db.close()

    @classmethod
    def run_cycle_for_account(cls, account_id: str, db: Session) -> Dict[str, Any]:
        """
        Executes a complete monitoring, reply checking, and follow-up cycle for an individual mailbox.
        Guarantees strict error isolation and account-specific daily sending limit checks.
        """
        lock = _get_account_lock(account_id)
        if not lock.acquire(blocking=False):
            return {"status": "busy", "message": f"Automation cycle already active for account {account_id}"}

        summary = {
            "account_id": account_id,
            "email_address": "",
            "synced_new_emails": 0,
            "replies_detected": 0,
            "bounces_detected": 0,
            "unsubscribes_detected": 0,
            "followups_drafted": 0,
            "followups_sent": 0,
            "skipped_reasons": []
        }

        try:
            account = db.query(ConnectedEmailAccountModel).filter(
                ConnectedEmailAccountModel.id == account_id
            ).first()
            if not account or account.connection_status not in ["CONNECTED", "ACTIVE"]:
                summary["skipped_reasons"].append("Account inactive or disconnected")
                return summary

            summary["email_address"] = account.email_address

            # Check if account has automation enabled
            if not account.auto_followup_enabled:
                summary["skipped_reasons"].append("Automation is paused for this account")
                return summary

            account_settings = db.query(AutomationSettingsModel).first()
            if not account_settings:
                account_settings = AutomationSettingsModel(user_id=account.user_id)
                db.add(account_settings)
                db.commit()

            provider = get_email_provider(account)

            # 1. Sent Mailbox Sync
            try:
                sent_items = provider.sync_sent_emails(db, max_results=25)
                summary["synced_new_emails"] = len(sent_items)
            except Exception as e:
                summary["skipped_reasons"].append(f"Sent sync notice: {str(e)}")

            # 2. Query eligible threads strictly belonging to this account
            delay_hours = account_settings.followup_delay_hours or 72
            cutoff = utc_now() - timedelta(hours=delay_hours)

            eligible_threads = db.query(EmailThreadModel).filter(
                (EmailThreadModel.sending_account_id == account.id) | (EmailThreadModel.sending_account_id == None),
                EmailThreadModel.status.in_(["PENDING", "DUE FOR FOLLOW-UP"]),
                EmailThreadModel.followup_count == 0,
                EmailThreadModel.original_sent_at <= cutoff
            ).all()

            in_window = cls.is_within_send_window(account_settings)

            for thread in eligible_threads:
                # Link thread to account if unassigned
                if not thread.sending_account_id:
                    thread.sending_account_id = account.id
                    db.commit()

                if thread.id in _active_thread_processing:
                    continue
                _active_thread_processing.add(thread.id)

                try:
                    # 3. Inspect thread for replies, bounces, or OOO via this account's provider
                    thread_res = provider.check_for_reply(thread, db)

                    if thread_res.get("status") == "RESPONDED" or thread_res.get("has_replied"):
                        summary["replies_detected"] += 1
                        continue

                    if thread_res.get("status") == "BOUNCED":
                        summary["bounces_detected"] += 1
                        continue

                    if thread_res.get("status") == "UNSUBSCRIBED":
                        summary["unsubscribes_detected"] += 1
                        continue

                    # 4. Check sending window if live sending
                    if account_settings.auto_send_enabled and not account_settings.test_mode and not in_window:
                        summary["skipped_reasons"].append(f"Thread {thread.gmail_thread_id} held: outside sending window")
                        continue

                    # 5. Check daily sending limit for this mailbox
                    if not account_settings.test_mode and account_settings.auto_send_enabled:
                        if account.daily_sent_count >= account.daily_sending_limit:
                            summary["skipped_reasons"].append(f"Daily limit ({account.daily_sending_limit}) reached for {account.email_address}")
                            continue

                    # 6. Execute Follow-up strictly via this account's mailbox
                    res = MailerService.execute_follow_up_for_thread(thread, db)
                    if res.get("is_test_mode"):
                        summary["followups_drafted"] += 1
                    elif res.get("success"):
                        summary["followups_sent"] += 1

                finally:
                    _active_thread_processing.discard(thread.id)

            account.last_sync_at = utc_now()
            db.commit()

            # Record activity summary for this mailbox
            act = ActivityLogModel(
                user_id=account.user_id,
                action="AUTOMATION_CYCLE_COMPLETED",
                description=(
                    f"Mailbox {account.email_address} cycle complete: {summary['replies_detected']} replies, "
                    f"{summary['followups_drafted']} drafts, {summary['followups_sent']} sent."
                )
            )
            db.add(act)
            db.commit()

        finally:
            lock.release()

        return summary
