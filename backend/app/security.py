import json
import base64
import hashlib
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from app.config import settings

def _get_fernet_key() -> bytes:
    # If custom TOKEN_ENCRYPTION_KEY is provided and 32 url-safe base64-encoded bytes
    raw_key = settings.TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY
    # Derive a valid 32-byte urlsafe base64 key using SHA256
    digest = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)

_fernet_instance: Optional[Fernet] = None

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = Fernet(_get_fernet_key())
    return _fernet_instance

def encrypt_token(plain_text: Optional[str]) -> Optional[str]:
    """Encrypts sensitive OAuth tokens or passwords at rest."""
    if not plain_text:
        return None
    try:
        f = get_fernet()
        encrypted = f.encrypt(plain_text.encode('utf-8'))
        return encrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Token encryption failed: {str(e)}")

def decrypt_token(cipher_text: Optional[str]) -> Optional[str]:
    """Decrypts sensitive OAuth tokens or passwords from database."""
    if not cipher_text:
        return None
    try:
        f = get_fernet()
        decrypted = f.decrypt(cipher_text.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Token decryption failed: {str(e)}")

def encrypt_credentials(creds: Dict[str, Any]) -> str:
    """Serializes a dictionary of credentials (OAuth or SMTP/IMAP) and encrypts it with Fernet."""
    if not creds:
        return ""
    serialized = json.dumps(creds)
    return encrypt_token(serialized) or ""

def decrypt_credentials(cipher_text: Optional[str]) -> Dict[str, Any]:
    """Decrypts and parses stored credentials back into a dictionary."""
    if not cipher_text:
        return {}
    decrypted_str = decrypt_token(cipher_text)
    if not decrypted_str:
        return {}
    try:
        return json.loads(decrypted_str)
    except json.JSONDecodeError:
        return {}
