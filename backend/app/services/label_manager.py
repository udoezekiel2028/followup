from typing import Optional, Dict, Any
from googleapiclient.errors import HttpError
from app.config import settings

class GmailLabelManager:
    _cached_label_ids: Dict[str, str] = {}

    @classmethod
    def ensure_label_exists(cls, service, label_name: str = None) -> Optional[str]:
        """
        Retrieves or creates the specified Gmail label (default: 'AUTO_FOLLOWUP').
        Returns the Gmail label ID.
        """
        target_name = label_name or settings.GMAIL_LABEL_NAME

        if target_name in cls._cached_label_ids:
            return cls._cached_label_ids[target_name]

        try:
            # List existing labels
            res = service.users().labels().list(userId='me').execute()
            labels = res.get('labels', [])

            for lbl in labels:
                if lbl.get('name', '').lower() == target_name.lower():
                    cls._cached_label_ids[target_name] = lbl['id']
                    return lbl['id']

            # Label does not exist -> create it
            create_body = {
                "name": target_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
                "color": {
                    "backgroundColor": "#4986e7", # Blue label in Gmail
                    "textColor": "#ffffff"
                }
            }
            new_label = service.users().labels().create(userId='me', body=create_body).execute()
            label_id = new_label.get('id')
            if label_id:
                cls._cached_label_ids[target_name] = label_id
            return label_id

        except HttpError as e:
            # If color is disallowed by free Gmail accounts, try without color
            try:
                basic_body = {
                    "name": target_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show"
                }
                new_label = service.users().labels().create(userId='me', body=basic_body).execute()
                label_id = new_label.get('id')
                if label_id:
                    cls._cached_label_ids[target_name] = label_id
                return label_id
            except Exception:
                return None
        except Exception:
            return None

    @classmethod
    def apply_label_to_thread(cls, service, thread_id: str, label_name: str = None) -> bool:
        """Applies AUTO_FOLLOWUP label to a tracked Gmail thread."""
        try:
            label_id = cls.ensure_label_exists(service, label_name)
            if not label_id:
                return False

            service.users().threads().modify(
                userId='me',
                id=thread_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            return True
        except Exception:
            return False

    @classmethod
    def remove_label_from_thread(cls, service, thread_id: str, label_name: str = None) -> bool:
        """Removes AUTO_FOLLOWUP label from an untracked Gmail thread."""
        try:
            label_id = cls.ensure_label_exists(service, label_name)
            if not label_id:
                return False

            service.users().threads().modify(
                userId='me',
                id=thread_id,
                body={'removeLabelIds': [label_id]}
            ).execute()
            return True
        except Exception:
            return False
