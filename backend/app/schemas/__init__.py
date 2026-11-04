"""
Pydantic v2 schemas for HospRecruit AI modules.
Each schema maps to Supabase tables with RLS policies.
"""

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


# ============================================================================
# Module 1: AI Screening & Candidate Qualification (Pain #1: 100-500 apps/role)
# ============================================================================


class CandidateBase(BaseModel):
    """Base candidate data."""

    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    location: str


class CandidateCreate(CandidateBase):
    """Create candidate via inbound SMS/web form."""

    job_id: str
    source: str = "sms"  # sms, web_form, ai_referral
    raw_data: Optional[dict] = None


class CandidateScreening(BaseModel):
    """AI screening result (Pain #1: reduce 65% screening time)."""

    candidate_id: str
    ai_score: float = Field(..., ge=0, le=100)
    ai_model: str
    screening_prompt: str
    key_qualifications: list[str]
    red_flags: list[str]
    recommend_proceed: bool
    screening_duration_seconds: float


class CandidateRead(CandidateBase):
    """Full candidate record."""

    id: str
    job_id: str
    source: str
    qualified: bool
    screening: Optional[CandidateScreening]
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Module 2: Shift Matching & Availability Management (Pain #2: seasonal chaos)
# ============================================================================


class ShiftType(str, Enum):
    """Shift types for hospitality roles."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    SEASONAL = "seasonal"
    ON_CALL = "on_call"
    FLEXIBLE = "flexible"


class ShiftCreate(BaseModel):
    """Create a job shift."""

    job_id: str
    role: str
    shift_type: ShiftType
    start_date: datetime
    end_date: datetime
    hours_per_week: float
    urgency: str = "normal"  # low, normal, urgent (Pain #2)


class ShiftMatch(BaseModel):
    """Match candidate to shift based on availability."""

    candidate_id: str
    shift_id: str
    availability_score: float = Field(..., ge=0, le=100)
    conflicts: list[str] = []  # overlapping shifts etc
    recommended: bool


# ============================================================================
# Module 3: Mobile Candidate Portal + Module 4: SMS/Conversational Recruiting
# ============================================================================


class CandidateProfileUpdate(BaseModel):
    """Update candidate profile via mobile/SMS."""

    availability: list[dict]  # [{day: "Monday", start: "09:00", end: "17:00"}, ...]
    current_role: Optional[str] = None
    years_experience: Optional[int] = None
    certifications: list[str] = []  # ServSafe, food handler, etc (Pain #5)
    willing_relocate: bool = False
    preferred_locations: list[str] = []


class SMSMessage(BaseModel):
    """Inbound/outbound SMS tracking."""

    from_number: str
    to_number: str
    body: str
    direction: str  # inbound, outbound
    candidate_id: Optional[str] = None
    twilio_message_sid: str
    created_at: datetime


class ConversationTurn(BaseModel):
    """Single turn in SMS/AI conversation."""

    candidate_id: str
    user_message: str
    ai_response: str
    intent: str  # apply, availability, questions, decline
    context: dict = {}  # extracted data


# ============================================================================
# Module 5: Onboarding & Compliance Workflow (Pain #5: compliance drag)
# ============================================================================


class ComplianceCheckType(str, Enum):
    """Compliance checks for hospitality."""

    BACKGROUND_CHECK = "background_check"
    SERVSAFE = "servsafe"
    FOOD_HANDLER = "food_handler"
    DUI_CHECK = "dui_check"
    REFERENCE_CHECK = "reference_check"


class OnboardingTask(BaseModel):
    """Single onboarding task (Pain #5)."""

    candidate_id: str
    job_id: str
    task_type: ComplianceCheckType
    status: str = "pending"  # pending, in_progress, completed, failed
    due_date: datetime
    result: Optional[dict] = None
    notes: Optional[str] = None


class OnboardingFlow(BaseModel):
    """Complete onboarding sequence."""

    candidate_id: str
    job_id: str
    status: str = "not_started"
    tasks: list[OnboardingTask]
    estimated_completion: datetime
    progress_percent: float = 0.0


# ============================================================================
# Module 6: Manager Dashboard & Analytics (Pain #3: manager burnout)
# ============================================================================


class DashboardMetrics(BaseModel):
    """Real-time dashboard for hiring managers (Pain #3)."""

    total_applications: int
    qualified_candidates: int
    avg_qualification_score: float
    candidates_in_pipeline: int
    open_shifts: int
    avg_fill_time_days: float  # Cost per hire metric
    fill_rate_percent: float
    no_show_rate_percent: float  # Pain #2


class PipelineStageMetrics(BaseModel):
    """Metrics by pipeline stage."""

    stage: str  # applied, screened, interviewed, offered, accepted, filled
    count: int
    avg_days_in_stage: float


# ============================================================================
# Module 7: Talent Pool & Retention (Pain #4: talent evaporates between seasons)
# ============================================================================


class TalentPoolCohort(BaseModel):
    """Seasonal talent pool cohort."""

    cohort_name: str  # "Spring 2026", "Holiday 2025"
    season: str
    candidates: int
    avg_retention_rate: float
    last_engagement: datetime


class EngagementCampaign(BaseModel):
    """Off-season engagement campaign (Pain #4)."""

    name: str
    target_cohort: str
    message: str
    channel: str  # sms, email, push
    scheduled_date: datetime
    recipient_count: int


# ============================================================================
# Module 8: Billing & White-Label (SaaS + Multi-tenant)
# ============================================================================


class PricingTier(str, Enum):
    """SaaS pricing tiers."""

    STARTER = "starter"  # 1-50 hires/month
    GROWTH = "growth"  # 50-200 hires/month
    ENTERPRISE = "enterprise"  # 200+ hires/month


class SubscriptionPlan(BaseModel):
    """Subscription for restaurant group/staffing agency."""

    org_id: str
    tier: PricingTier
    billing_email: str
    stripe_customer_id: str
    status: str = "active"  # active, cancelled, past_due
    monthly_cost: float
    features_enabled: list[str]
    created_at: datetime
    renewal_date: datetime


class WhiteLabelConfig(BaseModel):
    """White-label customization (Pain #6: thin margins → reseller model)."""

    org_id: str
    custom_domain: Optional[str] = None
    logo_url: Optional[str] = None
    brand_color: str = "#000000"
    custom_terms: Optional[str] = None
    api_key: str  # For Zapier/Make integration


# ============================================================================
# Authentication & User Management
# ============================================================================


class UserRole(str, Enum):
    """Role-based access (maps to RLS policies)."""

    ADMIN = "admin"
    HIRING_MANAGER = "hiring_manager"
    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


class UserBase(BaseModel):
    """Base user model."""

    email: EmailStr
    full_name: str
    role: UserRole


class UserCreate(UserBase):
    """Create user (Supabase auth via JWT)."""

    password: str


class UserRead(UserBase):
    """User profile."""

    id: str
    org_id: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
