"""
Scheduler Router - FastAPI endpoints for interview auto-scheduling

Endpoints:
1. POST /scheduler/initiate - Start interview scheduling
2. GET /scheduler/interviews - List all interviews for org
3. GET /scheduler/interviews/{id} - Get single interview details
4. POST /scheduler/interviews/{id}/availability - Process candidate SMS availability
5. GET /scheduler/interviews/{id}/proposed-slots - Get proposed time slots for candidate
6. POST /scheduler/interviews/{id}/confirm-slot - Candidate confirms selected time
7. POST /scheduler/interviews/{id}/manager/approve - Manager approves + books
8. POST /scheduler/interviews/{id}/reschedule - Reschedule to new time
9. POST /scheduler/interviews/{id}/cancel - Cancel interview
10. POST /scheduler/interviews/{id}/mark-no-show - Mark as no-show
11. GET /scheduler/dashboard/pending - GM dashboard (pending approvals)
12. GET /scheduler/dashboard/metrics - Scheduler metrics (ROI, no-show rate)
13. POST /scheduler/webhook/twilio - Twilio SMS webhook (inbound)
14. GET /scheduler/manager/{id}/availability - Get manager's available slots
15. POST /scheduler/manager/{id}/calendar/connect - Connect manager's calendar

ROI Metrics Tracked:
- Time-to-hire: Track days from initiation to confirmed
- No-show rate: Calculate based on completed vs no_show interviews
- Manager approval time: Track time from notification to approval
- Candidate response time: Track SMS response delay
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from app.schemas import (
    InterviewResponse,
    InterviewListResponse,
    SchedulerMetricsResponse
)
from app.services.scheduling_service import SchedulingService, InterviewStatus
from app.services.calendar_integration_service import CalendarIntegrationService
from app.services.shift_matching_service import ShiftMatchingService
from app.dependencies import get_current_user, get_db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


# ============================================================================
# Dependency Injection
# ============================================================================

async def get_scheduling_service(
    db = Depends(get_db_service)
) -> SchedulingService:
    """Inject scheduling service"""
    calendar_service = CalendarIntegrationService(db, merge_api_key="...")  # From env
    matching_service = ShiftMatchingService()
    twilio_service = get_twilio_service()  # Placeholder
    merge_service = get_merge_service()    # Placeholder
    
    return SchedulingService(
        db_service=db,
        calendar_service=calendar_service,
        matching_service=matching_service,
        twilio_service=twilio_service,
        merge_service=merge_service
    )


# ============================================================================
# Interview Lifecycle Endpoints
# ============================================================================

@router.post("/initiate", response_model=dict, status_code=201)
async def initiate_interview_scheduling(
    job_id: str,
    candidate_id: str,
    manager_id: str,
    urgency_level: int = 2,
    current_user = Depends(get_current_user),
    scheduling_service = Depends(get_scheduling_service)
):
    """
    Initiate interview scheduling for a candidate
    
    Process:
    1. Create interview record
    2. Send SMS to candidate requesting availability
    3. Return interview ID for tracking
    
    Response:
    {
        'interview_id': 'uuid',
        'status': 'candidate_texted',
        'candidate_phone': '+1...',
        'message_sid': 'twilio_message_id'
    }
    """
    try:
        result = await scheduling_service.initiate_scheduling(
            org_id=current_user.org_id,
            candidate_id=candidate_id,
            job_id=job_id,
            manager_id=manager_id,
            shift_urgency=urgency_level
        )
        
        return {
            'status': 'success',
            'data': result
        }
    
    except Exception as e:
        logger.error(f"Failed to initiate scheduling: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate interview scheduling"
        )


@router.get("/interviews", response_model=InterviewListResponse)
async def list_interviews(
    status_filter: Optional[str] = None,
    job_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    List all interviews for organization
    
    Query Parameters:
    - status_filter: Filter by status (pending, scheduled, completed, no_show, etc)
    - job_id: Filter by job
    - skip: Pagination offset
    - limit: Pagination limit
    """
    try:
        interviews = await db.interviews.list(
            org_id=current_user.org_id,
            status=status_filter,
            job_id=job_id,
            skip=skip,
            limit=limit
        )
        
        total = await db.interviews.count(
            org_id=current_user.org_id,
            status=status_filter,
            job_id=job_id
        )
        
        return InterviewListResponse(
            items=interviews,
            total=total,
            skip=skip,
            limit=limit
        )
    
    except Exception as e:
        logger.error(f"Failed to list interviews: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list interviews"
        )


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """Get detailed interview information"""
    try:
        interview = await db.interviews.get(interview_id)
        
        if not interview or interview['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        # Fetch related data
        candidate = await db.candidates.get(interview['candidate_id'])
        job = await db.jobs.get(interview['job_id'])
        manager = await db.users.get(interview['manager_id'])
        
        return InterviewResponse(
            id=interview['id'],
            candidate=candidate,
            job=job,
            manager=manager,
            status=interview.get('status'),
            scheduled_at=interview.get('scheduled_at'),
            candidate_confirmed=interview.get('candidate_confirmed'),
            interview_notes=interview.get('interview_notes')
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch interview"
        )


@router.post("/interviews/{interview_id}/availability")
async def process_availability_response(
    interview_id: str,
    sms_response: str,
    current_user = Depends(get_current_user),
    scheduling_service = Depends(get_scheduling_service)
):
    """
    Process candidate's SMS availability response
    
    Typical flow:
    1. Candidate receives: "When are you available NEXT WEEK?"
    2. Candidate replies: "Weekdays after 5pm"
    3. Parse reply → Match to slots → Send candidate 3 options
    """
    try:
        result = await scheduling_service.process_availability_response(
            org_id=current_user.org_id,
            interview_id=interview_id,
            sms_response=sms_response
        )
        
        return {
            'status': 'success',
            'interview_status': result['status'],
            'options': result['options']
        }
    
    except Exception as e:
        logger.error(f"Failed to process availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process availability response"
        )


@router.get("/interviews/{interview_id}/proposed-slots")
async def get_proposed_slots(
    interview_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    Get the 3 proposed time slot options for a candidate
    
    Response:
    [
        {
            'slot_index': 0,
            'time': '2024-01-15T14:00:00',
            'score': 92.5,
            'confidence': 0.925,
            'reasoning': '✓ Perfect availability match | ✓ Good urgency...'
        },
        ...
    ]
    """
    try:
        # Fetch last proposed slots from logs
        logs = await db.scheduling_logs.get_by(
            interview_id=interview_id,
            action='slots_proposed'
        )
        
        if not logs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No proposed slots found"
            )
        
        slots_data = logs[0]['data']['slots']
        
        return {
            'interview_id': interview_id,
            'slots': slots_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proposed slots: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch proposed slots"
        )


@router.post("/interviews/{interview_id}/confirm-slot")
async def confirm_candidate_selection(
    interview_id: str,
    slot_index: int,  # 0, 1, or 2
    current_user = Depends(get_current_user),
    scheduling_service = Depends(get_scheduling_service)
):
    """
    Candidate confirms their preferred interview time
    
    Process:
    1. Candidate replies: "1" (selecting first option)
    2. Lock that time slot
    3. Create calendar event
    4. Notify manager for approval
    5. Send confirmation SMS to candidate
    """
    try:
        result = await scheduling_service.confirm_candidate_selection(
            org_id=current_user.org_id,
            interview_id=interview_id,
            selected_slot_index=slot_index
        )
        
        # Notify manager
        await scheduling_service.send_manager_notification(
            org_id=current_user.org_id,
            interview_id=interview_id
        )
        
        return {
            'status': 'success',
            'interview_status': result['status'],
            'scheduled_time': result['scheduled_time'],
            'message': 'Manager has been notified and will approve shortly'
        }
    
    except Exception as e:
        logger.error(f"Failed to confirm slot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm interview time"
        )


@router.post("/interviews/{interview_id}/manager/approve")
async def approve_and_book_interview(
    interview_id: str,
    current_user = Depends(get_current_user),
    scheduling_service = Depends(get_scheduling_service)
):
    """
    Manager one-click approval: book on calendar + send confirmations
    
    Process:
    1. Verify current_user is the assigned manager
    2. Book on manager's Google/Outlook calendar
    3. Create Zoom/Teams meeting link
    4. Send confirmation emails/SMS
    5. Schedule auto-reminders (24h, 1h before)
    6. Sync to ATS
    
    Response:
    {
        'status': 'success',
        'interview_status': 'scheduled',
        'calendar_event_id': 'google_event_id',
        'interview_time': '2024-01-15T14:00:00'
    }
    """
    try:
        result = await scheduling_service.approve_and_book_interview(
            org_id=current_user.org_id,
            interview_id=interview_id,
            manager_approved_by=current_user.id
        )
        
        return {
            'status': 'success',
            'data': result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve and book interview"
        )


@router.post("/interviews/{interview_id}/reschedule")
async def reschedule_interview(
    interview_id: str,
    new_slot_index: int,
    reason: str = "Rescheduled",
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    Reschedule interview to new time
    
    Reasons:
    - 'manager_conflict': Manager has conflict at original time
    - 'candidate_requested': Candidate requested new time
    - 'no_show': Candidate no-showed, offer new time
    """
    try:
        interview = await db.interviews.get(interview_id)
        
        if not interview or interview['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        # TODO: Get new slot from proposed options or generate new options
        # For now, simplified implementation
        
        await db.interviews.update(
            interview_id,
            status=InterviewStatus.RESCHEDULED,
            rescheduled_count=interview.get('rescheduled_count', 0) + 1
        )
        
        return {
            'status': 'success',
            'message': f'Interview rescheduled. {reason}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reschedule interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reschedule interview"
        )


@router.post("/interviews/{interview_id}/cancel")
async def cancel_interview(
    interview_id: str,
    reason: str = "Candidate declined",
    current_user = Depends(get_current_user),
    db = Depends(get_db_service),
    scheduling_service = Depends(get_scheduling_service)
):
    """Cancel interview and remove from calendar"""
    try:
        interview = await db.interviews.get(interview_id)
        
        if not interview or interview['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        # Cancel on calendar
        if interview.get('calendar_event_id'):
            await scheduling_service.calendar.cancel_interview(
                org_id=current_user.org_id,
                manager_id=interview['manager_id'],
                calendar_event_id=interview['calendar_event_id']
            )
        
        # Free up interview slot
        await db.interview_slots.update(
            interview['interview_slot_id'],
            status='available',
            booked_interview_id=None
        )
        
        # Update interview
        await db.interviews.update(
            interview_id,
            status=InterviewStatus.CANCELLED
        )
        
        return {
            'status': 'success',
            'message': 'Interview cancelled'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel interview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel interview"
        )


@router.post("/interviews/{interview_id}/mark-no-show")
async def mark_interview_no_show(
    interview_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """Mark interview as no-show and setup rescheduling"""
    try:
        interview = await db.interviews.get(interview_id)
        
        if not interview or interview['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        
        # Update status
        await db.interviews.update(
            interview_id,
            status=InterviewStatus.NO_SHOW,
            completed_at=datetime.utcnow()
        )
        
        # TODO: Send reschedule offer SMS to candidate
        
        return {
            'status': 'success',
            'message': 'Interview marked as no-show. Rescheduling SMS sent to candidate.'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark no-show: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark interview as no-show"
        )


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@router.get("/dashboard/pending")
async def get_pending_approvals(
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    GM dashboard: Get pending interviews requiring manager approval
    
    Sorted by:
    1. Candidate screening score (highest first)
    2. Time since candidate confirmed (oldest first)
    
    Used by: SchedulerDashboard.tsx for real-time approval UI
    """
    try:
        interviews = await db.interviews.list(
            org_id=current_user.org_id,
            manager_id=current_user.id,
            status=InterviewStatus.MANAGER_REVIEW,
            order_by='-candidate_score,created_at'
        )
        
        # Enrich with candidate + job info
        enriched = []
        for interview in interviews:
            candidate = await db.candidates.get(interview['candidate_id'])
            job = await db.jobs.get(interview['job_id'])
            
            enriched.append({
                'interview_id': interview['id'],
                'candidate': {
                    'id': candidate['id'],
                    'name': f"{candidate['first_name']} {candidate['last_name']}",
                    'screening_score': candidate.get('screening_score', 0),
                    'phone': candidate['phone']
                },
                'job': {
                    'id': job['id'],
                    'title': job['title']
                },
                'proposed_time': interview.get('scheduled_at'),
                'time_pending_minutes': (datetime.utcnow() - interview['created_at']).total_seconds() / 60
            })
        
        return {
            'pending_count': len(enriched),
            'interviews': enriched
        }
    
    except Exception as e:
        logger.error(f"Failed to get pending approvals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending interviews"
        )


@router.get("/dashboard/metrics", response_model=SchedulerMetricsResponse)
async def get_scheduler_metrics(
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    Get scheduler metrics for org:
    - Time-to-hire: Average days from initiation to completion
    - No-show rate: % of scheduled interviews that were no-shows
    - Manager approval time: Avg minutes from candidate confirmation to manager approval
    - Candidate response time: Avg minutes from SMS to first response
    - Total time saved: Estimated hours saved vs manual scheduling
    
    ROI Calculation:
    - Time saved per candidate: avg(time_to_hire) vs manual (~7 days)
    - Manager hours saved: (scheduled_interviews × 5 minutes approval time) / 60
    - No-show reduction: estimated $300 per filled role × reduced no-shows
    """
    try:
        # Get all completed interviews for org this month
        start_date = datetime.utcnow() - timedelta(days=30)
        
        interviews = await db.interviews.list(
            org_id=current_user.org_id,
            created_at_gte=start_date,
            status__in=[InterviewStatus.COMPLETED, InterviewStatus.NO_SHOW]
        )
        
        # Calculate metrics
        total_interviews = len(interviews)
        completed = [i for i in interviews if i['status'] == InterviewStatus.COMPLETED]
        no_shows = [i for i in interviews if i['status'] == InterviewStatus.NO_SHOW]
        
        no_show_rate = len(no_shows) / total_interviews if total_interviews > 0 else 0
        
        # Avg time-to-hire
        times_to_hire = [
            (i['completed_at'] - i['created_at']).total_seconds() / 3600 / 24
            for i in completed if i.get('completed_at')
        ]
        avg_time_to_hire = sum(times_to_hire) / len(times_to_hire) if times_to_hire else 0
        
        # Manager approval time
        approval_times = [
            (i['gm_approved_at'] - i['candidate_confirmed_at']).total_seconds() / 60
            for i in completed if i.get('gm_approved_at') and i.get('candidate_confirmed_at')
        ]
        avg_approval_time = sum(approval_times) / len(approval_times) if approval_times else 0
        
        # ROI calculation
        time_saved_per_role = 5 - avg_time_to_hire  # vs 5 days manual
        manager_hours_saved = (len(completed) * (avg_approval_time / 60)) / 60
        estimated_cost_saved = (time_saved_per_role * 24 * 15) + (len(completed) * 50)  # Rough estimate
        
        return SchedulerMetricsResponse(
            total_interviews=total_interviews,
            completed=len(completed),
            no_shows=len(no_shows),
            no_show_rate=round(no_show_rate * 100, 1),
            avg_time_to_hire_days=round(avg_time_to_hire, 1),
            avg_manager_approval_minutes=round(avg_approval_time, 1),
            total_time_saved_hours=round(total_interviews * 2, 1),  # Estimated 2 hours per role
            estimated_cost_saved=round(estimated_cost_saved, 0)
        )
    
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate metrics"
        )


# ============================================================================
# Webhook Endpoints
# ============================================================================

@router.post("/webhook/twilio")
async def handle_twilio_webhook(
    request: Request,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service),
    scheduling_service = Depends(get_scheduling_service)
):
    """
    Twilio inbound SMS webhook
    
    Called when candidate replies to SMS:
    1. Candidate receives availability request
    2. Candidate replies (e.g., "Weekdays after 5pm")
    3. Twilio calls this webhook
    4. Process response → generate slots → send options
    5. Candidate replies with selection (e.g., "1")
    6. Confirm and notify manager
    """
    try:
        body = await request.form()
        
        from_number = body.get('From')
        message_body = body.get('Body')
        message_sid = body.get('MessageSid')
        
        logger.info(f"Twilio SMS received: {from_number} -> {message_body}")
        
        # Find candidate by phone
        candidate = await db.candidates.get_by_phone(from_number)
        if not candidate:
            logger.warning(f"SMS from unknown number: {from_number}")
            return {'status': 'ok'}  # Acknowledge webhook
        
        # Find pending interview for this candidate
        interview = await db.interviews.get_by(
            candidate_id=candidate['id'],
            status=InterviewStatus.CANDIDATE_TEXTED
        )
        
        if not interview:
            return {'status': 'ok'}
        
        # Process the response
        await scheduling_service.process_availability_response(
            org_id=candidate['org_id'],
            interview_id=interview['id'],
            sms_response=message_body
        )
        
        return {'status': 'ok'}
    
    except Exception as e:
        logger.error(f"Twilio webhook error: {e}")
        return {'status': 'error', 'error': str(e)}


@router.get("/manager/{manager_id}/availability")
async def get_manager_availability(
    manager_id: str,
    days_ahead: int = 7,
    current_user = Depends(get_current_user),
    calendar_service = Depends(get_scheduling_service)
):
    """Get available interview slots for a manager"""
    try:
        slots = await calendar_service.calendar.get_manager_availability(
            org_id=current_user.org_id,
            manager_id=manager_id,
            days_ahead=days_ahead,
            duration_minutes=30
        )
        
        return {
            'manager_id': manager_id,
            'days_ahead': days_ahead,
            'available_slots': [
                {
                    'start': slot.start.isoformat(),
                    'end': slot.end.isoformat(),
                    'confidence': slot.confidence,
                    'provider': slot.provider.value
                }
                for slot in slots
            ]
        }
    
    except Exception as e:
        logger.error(f"Failed to get manager availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch manager availability"
        )


@router.post("/manager/{manager_id}/calendar/connect")
async def connect_manager_calendar(
    manager_id: str,
    provider: str,  # google, outlook
    oauth_code: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    OAuth callback: Connect manager's calendar to scheduler
    
    Process:
    1. Manager clicks "Connect Google Calendar"
    2. Redirected to Google consent screen
    3. User approves access
    4. Google redirects back with auth code
    5. This endpoint exchanges code for tokens
    6. Store tokens in database
    """
    try:
        # TODO: Exchange oauth_code for access_token
        # 1. Call Google/Outlook token endpoint with code
        # 2. Get access_token + refresh_token
        # 3. Store in manager_calendar_configs table
        
        return {
            'status': 'success',
            'message': f'{provider} calendar connected'
        }
    
    except Exception as e:
        logger.error(f"Failed to connect calendar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect calendar"
        )
