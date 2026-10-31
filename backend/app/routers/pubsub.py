import base64
import json
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db, ConnectedEmailAccountModel, EmailThreadModel, ActivityLogModel
from app.services.oauth_service import GoogleOAuthService
from app.services.reply_detector import ReplyDetectorService

router = APIRouter(prefix="/api/gmail", tags=["Gmail Watch & Pub/Sub Push"])

@router.post("/watch")
def setup_gmail_watch(topic_name: str, db: Session = Depends(get_db)):
    """
    Subscribes Gmail account to Google Cloud Pub/Sub notifications for incoming replies.
    Renews watch subscription.
    """
    account = db.query(ConnectedEmailAccountModel).filter(
        ConnectedEmailAccountModel.status == "ACTIVE"
    ).first()
    if not account:
        raise HTTPException(status_code=400, detail="No active Gmail account connected")

    try:
        service = GoogleOAuthService.get_gmail_service(account, db)
        req_body = {
            'topicName': topic_name,
            'labelIds': ['INBOX']
        }
        watch_res = service.users().watch(userId='me', body=req_body).execute()

        act = ActivityLogModel(
            user_id=account.user_id,
            action="WATCH_ESTABLISHED",
            description=f"Gmail Watch subscription activated on Pub/Sub topic {topic_name}. Expiration: {watch_res.get('expiration')}"
        )
        db.add(act)
        db.commit()

        return {
            "status": "success",
            "history_id": watch_res.get("historyId"),
            "expiration": watch_res.get("expiration")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enable Gmail watch: {str(e)}")

@router.post("/webhook")
async def gmail_pubsub_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives real-time Google Cloud Pub/Sub push notifications.
    Processes mailbox changes with users.history.list and checks tracked threads.
    """
    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        return {"status": "ignored", "reason": "No data in pubsub message"}

    try:
        data_json = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        email_address = data_json.get("emailAddress")
        history_id = data_json.get("historyId")

        account = db.query(ConnectedEmailAccountModel).filter(
            ConnectedEmailAccountModel.gmail_address == email_address
        ).first()

        if not account or account.status != "ACTIVE":
            return {"status": "ignored", "reason": "Account not found or inactive"}

        # Check pending tracked threads for replies
        tracked_threads = db.query(EmailThreadModel).filter(
            EmailThreadModel.status.in_(["PENDING", "DUE FOR FOLLOW-UP"])
        ).all()

        replies_found = 0
        for t in tracked_threads:
            res = ReplyDetectorService.inspect_thread(t, db)
            if res.get("has_replied"):
                replies_found += 1

        return {
            "status": "processed",
            "history_id": history_id,
            "replies_detected": replies_found
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
