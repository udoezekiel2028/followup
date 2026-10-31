from app.database import ConnectedEmailAccountModel
from app.services.providers.base_provider import BaseEmailProvider
from app.services.providers.gmail_provider import GmailEmailProvider
from app.services.providers.hostinger_provider import HostingerEmailProvider
from app.services.providers.imap_smtp_provider import ImapSmtpEmailProvider

def get_email_provider(account: ConnectedEmailAccountModel) -> BaseEmailProvider:
    """
    Factory function returning the specialized email provider instance
    based on the account's provider_type ('GMAIL' vs 'HOSTINGER' / 'SMTP_IMAP').
    """
    p_type = (account.provider_type or "GMAIL").upper()
    if p_type == "GMAIL":
        return GmailEmailProvider(account)
    elif p_type == "HOSTINGER":
        return HostingerEmailProvider(account)
    elif p_type == "SMTP_IMAP":
        return ImapSmtpEmailProvider(account)
    else:
        return GmailEmailProvider(account)
