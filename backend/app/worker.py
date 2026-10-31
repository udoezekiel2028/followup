"""
SmartFollow AI — Dedicated Background Worker Process
Handles scheduled hourly outreach monitoring, reply detection, and automated follow-ups.
Can run as a standalone service (e.g. Railway worker service, Docker container, or systemd daemon).
"""

import sys
import time
import signal
import logging
import argparse
from app.database import init_db
from app.services.scheduler import AutomationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SmartFollow-Worker] %(message)s"
)
logger = logging.getLogger("worker")

_is_running = True

def handle_shutdown_signal(sig, frame):
    global _is_running
    signame = signal.Signals(sig).name if hasattr(signal, 'Signals') else str(sig)
    logger.info(f"Received shutdown signal {signame}. Gracefully shutting down worker scheduler...")
    _is_running = False
    AutomationEngine.shutdown()
    logger.info("Worker stopped cleanly.")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="SmartFollow AI Background Worker")
    parser.add_argument(
        "--once", 
        action="store_true", 
        help="Run the follow-up cycle once immediately and exit (useful for cron jobs)"
    )
    args = parser.parse_args()

    # Register POSIX & Windows termination signals
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    logger.info("=" * 60)
    logger.info("SmartFollow AI Background Worker starting...")
    logger.info("Initializing database tables...")
    init_db()

    if args.once:
        logger.info("Running single follow-up cycle (--once mode)...")
        AutomationEngine.run_hourly_job()
        logger.info("Single cycle completed successfully.")
        return

    logger.info("Starting background scheduler...")
    AutomationEngine.start()
    logger.info("Background scheduler active. Monitoring mailboxes every cycle. Press Ctrl+C to terminate.")

    while _is_running:
        try:
            time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            handle_shutdown_signal(signal.SIGINT, None)

if __name__ == "__main__":
    main()
