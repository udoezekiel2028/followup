from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc
from datetime import datetime, timezone
from typing import Optional, List
from app.database import (
    get_db, ProspectModel, EmailThreadModel, 
    EmailMessageModel, FollowUpLogModel, ActivityLogModel
)
from app.models.schemas import (
    ProspectResponse, ProspectListResponse, 
    ProspectUpdateStatusRequest, EmailThreadDetailResponse,
    EmailMessageResponse, FollowUpLogResponse,
    FollowUpGenerateRequest, FollowUpSendManualRequest
)
from app.services.ai_followup import AIFollowUpService
from app.services.mailer_service import MailerService
from app.services.reply_detector import ReplyDetectorService

router = APIRouter(prefix="/api/prospects", tags=["Prospects"])

def build_prospect_response(p: ProspectModel) -> ProspectResponse:
    now_utc = datetime.now(timezone.utc)
    sent_at = p.initial_sent_at
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    days_since = max(0, (now_utc - sent_at).days)

    return ProspectResponse(
        id=p.id,
        account_id=p.account_id,
        email=p.email,
        name=p.name,
        company=p.company,
        original_subject=p.original_subject,
        original_body=p.original_body,
        gmail_message_id=p.gmail_message_id,
        gmail_thread_id=p.gmail_thread_id,
        initial_sent_at=p.initial_sent_at,
        status=p.status,
        follow_up_count=p.follow_up_count,
        last_follow_up_at=p.last_follow_up_at,
        reply_detected_at=p.reply_detected_at,
        reply_snippet=p.reply_snippet,
        bounce_reason=p.bounce_reason,
        notes=p.notes,
        days_since_initial=days_since,
        created_at=p.created_at
    )

@router.get("", response_model=ProspectListResponse)
def list_prospects(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: str = Query("initial_sent_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists prospects with robust searching, status filtering, sorting, and pagination."""
    query = db.query(ProspectModel)

    # Search filter
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ProspectModel.email.ilike(search_term),
                ProspectModel.name.ilike(search_term),
                ProspectModel.company.ilike(search_term),
                ProspectModel.original_subject.ilike(search_term)
            )
        )

    # Status filter
    if status and status.upper() != "ALL":
        query = query.filter(ProspectModel.status == status.upper())

    # Sorting
    sort_column = getattr(ProspectModel, sort_by, ProspectModel.initial_sent_at)
    if sort_order.lower() == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    total_pages = max(1, (total + page_size - 1) // page_size)

    return ProspectListResponse(
        items=[build_prospect_response(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/{prospect_id}", response_model=ProspectResponse)
def get_prospect_detail(prospect_id: str, db: Session = Depends(get_db)):
    """Retrieves full details for a single prospect."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return build_prospect_response(prospect)

@router.get("/{prospect_id}/thread", response_model=EmailThreadDetailResponse)
def get_prospect_thread(prospect_id: str, db: Session = Depends(get_db)):
    """Retrieves all conversation messages and latest follow-up draft for a prospect."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    thread = db.query(EmailThreadModel).filter(
        EmailThreadModel.account_id == prospect.account_id,
        EmailThreadModel.gmail_thread_id == prospect.gmail_thread_id
    ).first()

    messages_data: List[EmailMessageResponse] = []
    if thread:
        messages = db.query(EmailMessageModel).filter(
            EmailMessageModel.thread_id == thread.id
        ).order_by(EmailMessageModel.sent_at.asc()).all()
        messages_data = [EmailMessageResponse.model_validate(m) for m in messages]

    # Latest follow-up draft
    draft = db.query(FollowUpLogModel).filter(
        FollowUpLogModel.prospect_id == prospect.id
    ).order_by(FollowUpLogModel.created_at.desc()).first()

    draft_data = FollowUpLogResponse.model_validate(draft) if draft else None

    return EmailThreadDetailResponse(
        id=thread.id if thread else prospect.id,
        gmail_thread_id=prospect.gmail_thread_id,
        subject=prospect.original_subject,
        snippet=prospect.reply_snippet or prospect.original_body[:100] if prospect.original_body else None,
        message_count=len(messages_data) if messages_data else 1,
        has_prospect_reply=(prospect.status == "RESPONDED"),
        prospect=build_prospect_response(prospect),
        messages=messages_data,
        follow_up_draft=draft_data
    )

@router.patch("/{prospect_id}/status", response_model=ProspectResponse)
def update_prospect_status(
    prospect_id: str, 
    req: ProspectUpdateStatusRequest, 
    db: Session = Depends(get_db)
):
    """Manually updates prospect status (e.g. mark RESPONDED, EXCLUDED)."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    old_status = prospect.status
    prospect.status = req.status.value
    if req.notes:
        prospect.notes = req.notes
    if req.status.value == "RESPONDED" and not prospect.reply_detected_at:
        prospect.reply_detected_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(prospect)

    log = ActivityLogModel(
        account_id=prospect.account_id,
        prospect_id=prospect.id,
        event_type="STATUS_CHANGED",
        message=f"Prospect {prospect.email} status changed manually from {old_status} to {req.status.value}"
    )
    db.add(log)
    db.commit()

    return build_prospect_response(prospect)

@router.post("/{prospect_id}/check-reply")
def check_prospect_reply_now(prospect_id: str, db: Session = Depends(get_db)):
    """Explicitly queries Gmail thread to check if a reply was received right now."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    result = ReplyDetectorService.inspect_thread(prospect, db)
    return result

@router.post("/{prospect_id}/generate-draft", response_model=FollowUpLogResponse)
def generate_prospect_draft(
    prospect_id: str, 
    req: FollowUpGenerateRequest = FollowUpGenerateRequest(), 
    db: Session = Depends(get_db)
):
    """Generates an AI follow-up draft for the prospect without sending."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    ai_res = AIFollowUpService.generate_follow_up(
        prospect, 
        custom_instructions=req.custom_instructions
    )

    draft = FollowUpLogModel(
        prospect_id=prospect.id,
        account_id=prospect.account_id,
        generated_subject=ai_res["subject"],
        generated_body=ai_res["body"],
        ai_model_used=ai_res.get("model"),
        prompt_tokens=ai_res.get("prompt_tokens"),
        completion_tokens=ai_res.get("completion_tokens"),
        status="DRAFT",
        is_test_mode=True
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    return FollowUpLogResponse.model_validate(draft)

@router.post("/{prospect_id}/send-followup")
def send_prospect_followup(
    prospect_id: str, 
    req: FollowUpSendManualRequest, 
    db: Session = Depends(get_db)
):
    """Sends or drafts a follow-up email immediately for the prospect."""
    prospect = db.query(ProspectModel).filter(ProspectModel.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    result = MailerService.execute_follow_up_for_prospect(
        prospect=prospect,
        db=db,
        force_live_send=req.force_live_send,
        manual_override_body=req.body,
        manual_override_subject=req.subject
    )
    return result
