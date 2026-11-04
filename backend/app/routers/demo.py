"""
FastAPI routes for demo booking and lead capture.
"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import logging

from app.services.email_service import send_demo_booked_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["demo"])


class DemoRequest(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    company_name: str = ""
    phone: Optional[str] = None
    hiring_volume: Optional[str] = None
    current_pain_points: Optional[List[str]] = []
    demo_type: str = "general"
    timezone: Optional[str] = None
    notes: Optional[str] = None
    company_size: Optional[str] = None
    budget_range: Optional[str] = None


@router.post("/request")
async def create_demo_request(demo_req: DemoRequest, background_tasks: BackgroundTasks):
    """Accept a demo booking request from the landing page."""
    background_tasks.add_task(
        send_demo_booked_email,
        email=demo_req.email,
        first_name=demo_req.first_name,
        company_name=demo_req.company_name,
    )
    logger.info(f"Demo request received from {demo_req.email}")
    return {
        "success": True,
        "message": f"Demo request received. We'll reach out to {demo_req.email} within 24 hours.",
    }


@router.get("/health")
async def demo_health():
    return {"status": "ok", "service": "demo_booking"}
