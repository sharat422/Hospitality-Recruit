"""
HospRecruit AI Billing Router
FastAPI endpoints for subscription and billing management
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from app.core.dependencies import get_db
from app.core.security import get_current_user
from app.services.stripe_service import StripeService, BillingService
from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PricingTierResponse(BaseModel):
    tier_name: str
    display_name: str
    description: Optional[str]
    price_monthly: int
    price_annual: int
    roles_per_month: int
    video_interviews_per_month: int
    ai_credits_per_month: int
    features: Dict[str, bool]

class CheckoutRequest(BaseModel):
    tier: str
    billing_interval: str = Field(default="month", pattern="^(month|year)$")
    promo_code: Optional[str] = None
    return_url: Optional[str] = None

class CreditPurchaseRequest(BaseModel):
    num_credits: int = Field(gt=0, description="Number of credits to purchase")

class CancelSubscriptionRequest(BaseModel):
    at_period_end: bool = Field(default=True, description="Cancel at end of billing period")

class BillingStatusResponse(BaseModel):
    tier: str
    tier_display: str
    subscription_status: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    trial: Dict[str, Any]
    usage: Dict[str, Dict[str, int]]

class InvoiceResponse(BaseModel):
    id: str
    org_id: str
    stripe_invoice_id: Optional[str]
    amount_total: int
    amount_paid: int
    currency: str
    issue_date: datetime
    status: str
    paid_date: Optional[datetime]
    pdf_url: Optional[str]

# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(prefix="/billing", tags=["billing"])

# Initialize services (in production, use dependency injection)
stripe_service = StripeService(
    api_key=settings.STRIPE_SECRET_KEY or "",
    webhook_secret=settings.STRIPE_WEBHOOK_SECRET or ""
)
billing_service = BillingService(stripe_service)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_org_id_from_user(
    db: AsyncSession,
    user_id: str
) -> str:
    """Get organization ID for current user"""
    query = text("""
        SELECT DISTINCT organization_id 
        FROM users 
        WHERE id = :user_id
        LIMIT 1
    """)
    result = await db.execute(query, {"user_id": user_id})
    org_id = result.scalar()
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User organization not found"
        )
    
    return org_id

# ============================================================================
# PRICING & PLANS ENDPOINTS
# ============================================================================

@router.get("/pricing/tiers", response_model=List[PricingTierResponse])
async def get_pricing_tiers(db: AsyncSession = Depends(get_db)):
    """Get all available pricing tiers"""
    try:
        query = text("""
            SELECT 
              tier_name,
              display_name,
              description,
              base_price_monthly,
              base_price_annual,
              roles_per_month,
              video_interviews_per_month,
              ai_credits_per_month,
              custom_branding,
              sso_enabled,
              api_access,
              priority_support
            FROM tier_limits
            WHERE tier_name != 'free_trial'
            ORDER BY base_price_monthly ASC
        """)
        
        result = await db.execute(query)
        tiers = result.mappings().all()
        
        response = []
        for tier in tiers:
            response.append(PricingTierResponse(
                tier_name=tier["tier_name"],
                display_name=tier["display_name"],
                description=tier["description"],
                price_monthly=tier["base_price_monthly"],
                price_annual=tier["base_price_annual"],
                roles_per_month=tier["roles_per_month"],
                video_interviews_per_month=tier["video_interviews_per_month"],
                ai_credits_per_month=tier["ai_credits_per_month"],
                features={
                    "custom_branding": tier["custom_branding"],
                    "sso_enabled": tier["sso_enabled"],
                    "api_access": tier["api_access"],
                    "priority_support": tier["priority_support"]
                }
            ))
        
        return response
        
    except Exception as e:
        logger.error(f"Error fetching pricing tiers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pricing tiers"
        )

# ============================================================================
# CHECKOUT ENDPOINTS
# ============================================================================

@router.post("/checkout")
async def create_checkout_session(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create Stripe checkout session for subscription upgrade"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        # Validate tier exists
        tier_query = text("""
            SELECT tier_name FROM tier_limits WHERE tier_name = :tier LIMIT 1
        """)
        result = await db.execute(tier_query, {"tier": request.tier})
        if not result.scalar():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tier"
            )
        
        # Ensure customer exists
        org_query = text("""
            SELECT name, email FROM organizations WHERE id = :org_id
        """)
        result = await db.execute(org_query, {"org_id": org_id})
        org = result.mappings().first()
        
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found"
            )
        
        customer_id = await stripe_service.create_customer(
            db, org_id, org["name"], org["email"]
        )
        
        # Get trial days for free trial tier
        trial_days = None
        if request.tier == "free_trial":
            trial_days = 14
        elif request.tier == "pilot":
            trial_days = 1
        
        # Create checkout session
        checkout_session = await stripe_service.create_checkout_session(
            db=db,
            org_id=org_id,
            tier=request.tier,
            billing_interval=request.billing_interval,
            trial_days=trial_days,
            promo_code=request.promo_code,
            return_url=request.return_url or "http://localhost:3000"
        )
        
        return {
            "session_id": checkout_session["session_id"],
            "url": checkout_session["url"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )

@router.post("/checkout/credits")
async def create_credit_purchase_session(
    request: CreditPurchaseRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create checkout session for purchasing AI credits"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        # Get org name and email
        org_query = text("""
            SELECT name, email FROM organizations WHERE id = :org_id
        """)
        result = await db.execute(org_query, {"org_id": org_id})
        org = result.mappings().first()
        
        # Ensure customer exists
        await stripe_service.create_customer(
            db, org_id, org["name"], org["email"]
        )
        
        # Create checkout session
        checkout_session = await stripe_service.create_credit_purchase_session(
            db=db,
            org_id=org_id,
            num_credits=request.num_credits,
            return_url="http://localhost:3000"
        )
        
        return {
            "session_id": checkout_session["session_id"],
            "url": checkout_session["url"],
            "amount_usd": (request.num_credits * 0.50)
        }
        
    except Exception as e:
        logger.error(f"Error creating credit purchase session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create credit purchase session"
        )

# ============================================================================
# SUBSCRIPTION ENDPOINTS
# ============================================================================

@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current billing status and usage"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        status_info = await billing_service.get_billing_status(db, org_id)
        return status_info
        
    except Exception as e:
        logger.error(f"Error fetching billing status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch billing status"
        )

@router.get("/invoices", response_model=List[InvoiceResponse])
async def get_invoices(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get invoice history for organization"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        query = text("""
            SELECT 
              id, org_id, stripe_invoice_id, amount_total, amount_paid,
              currency, issue_date, status, paid_date, pdf_url
            FROM invoices
            WHERE org_id = :org_id
            ORDER BY issue_date DESC
            LIMIT :limit OFFSET :skip
        """)
        
        result = await db.execute(query, {
            "org_id": org_id,
            "limit": limit,
            "skip": skip
        })
        invoices = result.mappings().all()
        
        return [InvoiceResponse(**inv) for inv in invoices]
        
    except Exception as e:
        logger.error(f"Error fetching invoices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch invoices"
        )

@router.post("/cancel-subscription")
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel subscription"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        success = await stripe_service.cancel_subscription(
            db, org_id, at_period_end=request.at_period_end
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription to cancel"
            )
        
        return {
            "status": "success",
            "message": "Subscription canceled" if not request.at_period_end else 
                      "Subscription scheduled for cancellation at period end"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription"
        )

# ============================================================================
# USAGE & LIMITS ENDPOINTS
# ============================================================================

@router.get("/limits")
async def get_tier_limits(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tier limits and current usage"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        query = text("""
            SELECT 
              o.tier_name,
              t.roles_per_month,
              t.video_interviews_per_month,
              t.ai_credits_per_month,
              COALESCE(ut.roles_created, 0) as roles_used,
              COALESCE(ut.video_interviews_sent, 0) as interviews_used,
              COALESCE(ut.ai_credits_used, 0) as credits_used
            FROM organizations o
            JOIN tier_limits t ON o.tier_name = t.tier_name
            LEFT JOIN usage_tracking ut ON o.id = ut.org_id 
              AND ut.billing_month = DATE_TRUNC('month', NOW())::DATE
            WHERE o.id = :org_id
        """)
        
        result = await db.execute(query, {"org_id": org_id})
        row = result.mappings().first()
        
        return {
            "tier": row["tier_name"],
            "limits": {
                "roles_per_month": {
                    "limit": row["roles_per_month"],
                    "used": row["roles_used"],
                    "remaining": row["roles_per_month"] - row["roles_used"]
                },
                "video_interviews_per_month": {
                    "limit": row["video_interviews_per_month"],
                    "used": row["interviews_used"],
                    "remaining": row["video_interviews_per_month"] - row["interviews_used"]
                },
                "ai_credits_per_month": {
                    "limit": row["ai_credits_per_month"],
                    "used": row["credits_used"],
                    "remaining": row["ai_credits_per_month"] - row["credits_used"]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching tier limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tier limits"
        )

@router.post("/use-ai-credits")
async def use_ai_credits(
    num_credits: int = 1,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Deduct AI credits from org (used internally by video interview system)"""
    try:
        org_id = await get_org_id_from_user(db, current_user["id"])
        
        success = await billing_service.use_ai_credits(
            db, org_id, num_credits,
            reference_type="video_interview",
            reference_id=None
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient AI credits"
            )
        
        # Get updated status
        status_info = await billing_service.get_billing_status(db, org_id)
        
        return {
            "success": True,
            "credits_used": num_credits,
            "remaining_credits": status_info["usage"]["ai_credits"]["remaining"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error using AI credits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to use AI credits"
        )

# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@router.post("/webhook")
async def handle_stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle Stripe webhook events"""
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        if not sig_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing signature header"
            )
        
        # Construct event (Stripe library does verification)
        try:
            event = stripe_service.stripe.Webhook.construct_event(
                payload,
                sig_header,
                stripe_service.webhook_secret
            )
        except stripe_service.stripe.error.SignatureVerificationError:
            logger.warning("Invalid webhook signature")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )
        
        # Route by event type
        event_type = event["type"]
        data = event["data"]["object"]
        
        logger.info(f"Processing webhook event: {event_type}")
        
        # Import webhook handlers
        from app.services.stripe_webhooks import handle_webhook_event
        
        await handle_webhook_event(db, event_type, data)
        
        return {"received": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Always return 200 to Stripe, even on error
        return {"received": True}
