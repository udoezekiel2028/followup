from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db, ActivityLogModel

router = APIRouter(prefix="/api/logs", tags=["Audit & Activity Logs"])

@router.get("")
def get_activity_logs(
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(ActivityLogModel)
    if action and action.upper() != "ALL":
        query = query.filter(ActivityLogModel.action == action.upper())

    logs = query.order_by(ActivityLogModel.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "description": l.description,
            "created_at": l.created_at.isoformat()
        }
        for l in logs
    ]
