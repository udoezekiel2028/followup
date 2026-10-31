import pytest
from app.services.reply_detector import ReplyDetectorService

def test_bounce_detection():
    # Mailer daemon detection
    assert ReplyDetectorService.check_for_bounce_or_optout(
        sender="mailer-daemon@googlemail.com",
        subject="Delivery Status Notification (Failure)",
        body="550 5.1.1 The email account that you tried to reach does not exist."
    ) == "BOUNCED"

    # Postmaster bounce detection
    assert ReplyDetectorService.check_for_bounce_or_optout(
        sender="postmaster@domain.com",
        subject="Undelivered Mail Returned to Sender",
        body="Mailbox unavailable"
    ) == "BOUNCED"

def test_optout_detection():
    # Explicit unsubscribe
    assert ReplyDetectorService.check_for_bounce_or_optout(
        sender="prospect@company.com",
        subject="Re: Lead automation",
        body="Please unsubscribe me from this list. Not interested."
    ) == "UNSUBSCRIBED"

    # Polite removal
    assert ReplyDetectorService.check_for_bounce_or_optout(
        sender="prospect@company.com",
        subject="Re: Lead automation",
        body="Hi, please remove me from your outreach list."
    ) == "UNSUBSCRIBED"

def test_genuine_response_not_flagged_as_bounce_or_optout():
    assert ReplyDetectorService.check_for_bounce_or_optout(
        sender="prospect@company.com",
        subject="Re: Lead automation",
        body="Hi Alex, this sounds interesting! Let's schedule a call on Thursday at 2pm."
    ) is None
