"""
HospRecruit AI Billing System
Stripe + Supabase Integration Service Layer
"""

import stripe
import logging
from datetime import datetime, timedelta
import hashlib
import hmac
from decimal import Decimal
from typing import Optional, Dict, List, Any
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"

class TierName(str, Enum):
    FREE_TRIAL = "free_trial"
    PILOT = "pilot"
    STARTER = "starter"
    GROWTH = "growth"
    SCALE = "scale"
    ENTERPRISE = "enterprise"

# Tier configuration
TIER_CONFIG = {
    "free_trial": {
        "display_name": "Free Trial",
        "price_monthly": 0,
        "trial_days": 14,
    },
    "pilot": {
        "display_name": "Pilot Program",
        "price_monthly": 99 * 100,  # $99 in cents
        "trial_days": 0,
    },
    "starter": {
        "display_name": "Starter",
        "price_monthly": 149 * 100,  # $149
    },
    "growth": {
        "display_name": "Growth",
        "price_monthly": 499 * 100,  # $499
    },
    "scale": {
        "display_name": "Scale",
        "price_monthly": 999 * 100,  # $999
    },
    "enterprise": {
        "display_name": "Enterprise",
        "price_monthly": 0,  # Custom
    }
}

ANNUAL_DISCOUNT = 0.20  # 20% discount for annual billing
AI_CREDIT_PRICE = 50  # $0.50 per credit (in cents)

# ============================================================================
# STRIPE SERVICE
# ============================================================================

class StripeService:
    """Handles all Stripe operations"""
    
    def __init__(self, api_key: str, webhook_secret: str):
        self.stripe = stripe
        self.stripe.api_key = api_key
        self.webhook_secret = webhook_secret
    
    async def create_customer(
        self,
        db: AsyncSession,
        org_id: str,
        org_name: str,
        email: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """Create or retrieve Stripe customer"""
        try:
            # Check if customer exists
            query = text("""
                SELECT stripe_customer_id 
                FROM organizations 
                WHERE id = :org_id AND stripe_customer_id IS NOT NULL
                LIMIT 1
            """)
            result = await db.execute(query, {"org_id": org_id})
            existing_customer = result.scalar()
            
            if existing_customer:
                logger.info(f"Using existing Stripe customer: {existing_customer}")
                return existing_customer
            
            # Create new customer
            customer_metadata = {
                "org_id": org_id,
                "org_name": org_name,
                **(metadata or {})
            }
            
            customer = self.stripe.Customer.create(
                name=org_name,
                email=email,
                metadata=customer_metadata
            )
            
            # Save customer ID
            update_query = text("""
                UPDATE organizations 
                SET stripe_customer_id = :customer_id, updated_at = NOW()
                WHERE id = :org_id
            """)
            await db.execute(update_query, {
                "customer_id": customer.id,
                "org_id": org_id
            })
            await db.commit()
            
            logger.info(f"Created Stripe customer: {customer.id}")
            return customer.id
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {e}")
            raise
    
    async def create_checkout_session(
        self,
        db: AsyncSession,
        org_id: str,
        tier: str,
        billing_interval: str = "month",
        trial_days: Optional[int] = None,
        promo_code: Optional[str] = None,
        return_url: str = "http://localhost:3000"
    ) -> Dict[str, str]:
        """Create Stripe checkout session"""
        try:
            # Get customer
            query = text("""
                SELECT stripe_customer_id FROM organizations WHERE id = :org_id
            """)
            result = await db.execute(query, {"org_id": org_id})
            customer_id = result.scalar()
            
            if not customer_id:
                raise ValueError("Organization has no Stripe customer ID")
            
            # Build line items
            price_amount = TIER_CONFIG[tier]["price_monthly"]
            
            if billing_interval == "year":
                price_amount = int(price_amount * 12 * (1 - ANNUAL_DISCOUNT))
            
            line_items = [{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"HospRecruit {TIER_CONFIG[tier]['display_name']} Plan",
                        "description": f"Monthly subscription for {tier} tier",
                        "metadata": {"tier": tier, "org_id": org_id}
                    },
                    "unit_amount": price_amount,
                    "recurring": {
                        "interval": billing_interval,
                        "interval_count": 1
                    }
                },
                "quantity": 1
            }]
            
            # Build session params
            session_params = {
                "customer": customer_id,
                "payment_method_types": ["card"],
                "line_items": line_items,
                "mode": "subscription",
                "success_url": f"{return_url}/billing?session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{return_url}/billing",
                "metadata": {
                    "org_id": org_id,
                    "tier": tier,
                    "billing_interval": billing_interval
                }
            }
            
            # Add trial period if new customer
            if trial_days and trial_days > 0:
                session_params["subscription_data"] = {
                    "trial_period_days": trial_days
                }
            
            # Add promo code if provided
            if promo_code:
                # Validate promo code exists
                promo_result = await self._validate_promo_code(db, promo_code, tier)
                if promo_result.get("valid"):
                    session_params["discounts"] = [{
                        "coupon": promo_code
                    }]
            
            session = self.stripe.checkout.Session.create(**session_params)
            logger.info(f"Created checkout session: {session.id}")
            
            return {
                "session_id": session.id,
                "url": session.url
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout: {e}")
            raise
    
    async def create_credit_purchase_session(
        self,
        db: AsyncSession,
        org_id: str,
        num_credits: int,
        return_url: str = "http://localhost:3000"
    ) -> Dict[str, str]:
        """Create checkout session for purchasing AI credits"""
        try:
            query = text("""
                SELECT stripe_customer_id FROM organizations WHERE id = :org_id
            """)
            result = await db.execute(query, {"org_id": org_id})
            customer_id = result.scalar()
            
            if not customer_id:
                raise ValueError("Organization has no Stripe customer ID")
            
            price_amount = num_credits * AI_CREDIT_PRICE
            
            session = self.stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"HospRecruit AI Credits",
                            "description": f"{num_credits} AI Interview credits",
                            "metadata": {"org_id": org_id}
                        },
                        "unit_amount": price_amount
                    },
                    "quantity": 1
                }],
                mode="payment",
                success_url=f"{return_url}/billing/credits?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{return_url}/billing/credits",
                metadata={
                    "org_id": org_id,
                    "type": "credit_purchase",
                    "num_credits": str(num_credits)
                }
            )
            
            logger.info(f"Created credit purchase session: {session.id}")
            return {
                "session_id": session.id,
                "url": session.url
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating credit session: {e}")
            raise
    
    async def cancel_subscription(
        self,
        db: AsyncSession,
        org_id: str,
        at_period_end: bool = True
    ) -> bool:
        """Cancel organization subscription"""
        try:
            # Get subscription
            query = text("""
                SELECT stripe_subscription_id FROM subscriptions 
                WHERE org_id = :org_id AND status = 'active'
                LIMIT 1
            """)
            result = await db.execute(query, {"org_id": org_id})
            subscription_id = result.scalar()
            
            if not subscription_id:
                logger.warning(f"No active subscription for org {org_id}")
                return False
            
            # Cancel
            if at_period_end:
                self.stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                self.stripe.Subscription.delete(subscription_id)
            
            logger.info(f"Canceled subscription: {subscription_id}")
            return True
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error canceling subscription: {e}")
            raise
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify Stripe webhook signature"""
        try:
            computed_signature = hmac.new(
                self.webhook_secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(computed_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

# ============================================================================
# BILLING SERVICE
# ============================================================================

class BillingService:
    """Handles billing business logic"""
    
    def __init__(self, stripe_service: StripeService):
        self.stripe = stripe_service
    
    async def initialize_free_trial(
        self,
        db: AsyncSession,
        org_id: str
    ) -> None:
        """Initialize free trial for organization"""
        try:
            trial_start = datetime.utcnow()
            trial_end = trial_start + timedelta(days=14)
            
            update_query = text("""
                UPDATE organizations 
                SET 
                  tier_name = :tier,
                  subscription_status = :status,
                  trial_started_at = :trial_start,
                  trial_ends_at = :trial_end,
                  updated_at = NOW()
                WHERE id = :org_id
            """)
            
            await db.execute(update_query, {
                "tier": "free_trial",
                "status": "trialing",
                "trial_start": trial_start,
                "trial_end": trial_end,
                "org_id": org_id
            })
            
            # Create usage tracking entry
            current_month = datetime.utcnow().replace(day=1).date()
            insert_query = text("""
                INSERT INTO usage_tracking (org_id, billing_month)
                VALUES (:org_id, :billing_month)
                ON CONFLICT DO NOTHING
            """)
            
            await db.execute(insert_query, {
                "org_id": org_id,
                "billing_month": current_month
            })
            
            await db.commit()
            logger.info(f"Initialized free trial for org {org_id}")
            
        except Exception as e:
            logger.error(f"Error initializing free trial: {e}")
            raise
    
    async def check_tier_limit(
        self,
        db: AsyncSession,
        org_id: str,
        limit_type: str
    ) -> Dict[str, Any]:
        """Check if organization has exceeded tier limit"""
        try:
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
            
            if not row:
                raise ValueError(f"Organization {org_id} not found")
            
            limits = {
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
            
            return {
                "tier": row["tier_name"],
                "limits": limits,
                "exceeded": limits[limit_type]["remaining"] <= 0 if limit_type in limits else False
            }
            
        except Exception as e:
            logger.error(f"Error checking tier limit: {e}")
            raise
    
    async def use_ai_credits(
        self,
        db: AsyncSession,
        org_id: str,
        num_credits: int,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None
    ) -> bool:
        """Use AI credits from org's balance"""
        try:
            # Check available credits
            query = text("""
                SELECT DATE_TRUNC('month', NOW())::DATE as billing_month,
                       COALESCE(ai_credits_used, 0) as used
                FROM usage_tracking
                WHERE org_id = :org_id
            """)
            
            result = await db.execute(query, {"org_id": org_id})
            row = result.mappings().first()
            
            if not row:
                # Create usage tracking entry
                insert_query = text("""
                    INSERT INTO usage_tracking (org_id, billing_month)
                    VALUES (:org_id, DATE_TRUNC('month', NOW())::DATE)
                """)
                await db.execute(insert_query, {"org_id": org_id})
                await db.commit()
                row = {"used": 0}
            
            # Check limit
            tier_info = await self.check_tier_limit(db, org_id, "ai_credits_per_month")
            if tier_info["exceeded"]:
                logger.warning(f"Org {org_id} exceeded AI credits limit")
                return False
            
            # Deduct credits
            update_query = text("""
                UPDATE usage_tracking
                SET ai_credits_used = ai_credits_used + :credits
                WHERE org_id = :org_id
                AND billing_month = DATE_TRUNC('month', NOW())::DATE
            """)
            
            await db.execute(update_query, {
                "org_id": org_id,
                "credits": num_credits
            })
            
            # Add to ledger
            new_balance = row["used"] + num_credits
            ledger_query = text("""
                INSERT INTO ai_credits_ledger (
                  org_id, transaction_type, amount, reference_type,
                  reference_id, description, balance_after
                ) VALUES (
                  :org_id, :type, :amount, :ref_type, :ref_id, :desc, :balance
                )
            """)
            
            await db.execute(ledger_query, {
                "org_id": org_id,
                "type": "usage",
                "amount": -num_credits,
                "ref_type": reference_type,
                "ref_id": reference_id,
                "desc": f"AI interview usage ({num_credits} credits)",
                "balance": new_balance
            })
            
            await db.commit()
            logger.info(f"Used {num_credits} credits for org {org_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error using AI credits: {e}")
            raise
    
    async def add_credits_to_org(
        self,
        db: AsyncSession,
        org_id: str,
        num_credits: int,
        reason: str = "credit_purchase"
    ) -> int:
        """Add credits to organization"""
        try:
            # Get current balance
            query = text("""
                SELECT COALESCE(SUM(CASE WHEN transaction_type = 'usage' THEN -amount ELSE amount END), 0)::INT as balance
                FROM ai_credits_ledger
                WHERE org_id = :org_id
            """)
            
            result = await db.execute(query, {"org_id": org_id})
            balance = result.scalar() or 0
            
            new_balance = balance + num_credits
            
            # Add to ledger
            insert_query = text("""
                INSERT INTO ai_credits_ledger (
                  org_id, transaction_type, amount,
                  description, balance_after
                ) VALUES (
                  :org_id, :type, :amount, :desc, :balance
                )
            """)
            
            await db.execute(insert_query, {
                "org_id": org_id,
                "type": "purchase",
                "amount": num_credits,
                "desc": f"Credit purchase: {reason}",
                "balance": new_balance
            })
            
            await db.commit()
            logger.info(f"Added {num_credits} credits to org {org_id}")
            return new_balance
            
        except Exception as e:
            logger.error(f"Error adding credits: {e}")
            raise
    
    async def _validate_promo_code(
        self,
        db: AsyncSession,
        code: str,
        tier: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate promo code"""
        try:
            query = text("""
                SELECT *
                FROM promo_codes
                WHERE code = UPPER(:code)
                  AND is_active = true
                  AND valid_from <= NOW()
                  AND (valid_until IS NULL OR valid_until > NOW())
                  AND (max_uses IS NULL OR current_uses < max_uses)
                  AND (
                    :tier = ANY(applicable_tiers)
                    OR array_length(applicable_tiers, 1) IS NULL
                  )
            """)
            
            result = await db.execute(query, {
                "code": code,
                "tier": tier or ""
            })
            promo = result.mappings().first()
            
            return {
                "valid": bool(promo),
                "promo": promo
            }
            
        except Exception as e:
            logger.error(f"Error validating promo code: {e}")
            return {"valid": False}
    
    async def get_billing_status(
        self,
        db: AsyncSession,
        org_id: str
    ) -> Dict[str, Any]:
        """Get complete billing status for organization"""
        try:
            query = text("""
                SELECT 
                  o.id,
                  o.tier_name,
                  o.subscription_status,
                  o.trial_started_at,
                  o.trial_ends_at,
                  s.current_period_start,
                  s.current_period_end,
                  s.status,
                  t.display_name as tier_display_name,
                  t.roles_per_month,
                  t.video_interviews_per_month,
                  t.ai_credits_per_month,
                  COALESCE(ut.roles_created, 0) as roles_used,
                  COALESCE(ut.video_interviews_sent, 0) as interviews_used,
                  COALESCE(ut.ai_credits_used, 0) as credits_used
                FROM organizations o
                JOIN tier_limits t ON o.tier_name = t.tier_name
                LEFT JOIN subscriptions s ON o.id = s.org_id AND s.status IN ('active', 'trialing')
                LEFT JOIN usage_tracking ut ON o.id = ut.org_id 
                  AND ut.billing_month = DATE_TRUNC('month', NOW())::DATE
                WHERE o.id = :org_id
            """)
            
            result = await db.execute(query, {"org_id": org_id})
            row = result.mappings().first()
            
            if not row:
                raise ValueError(f"Organization {org_id} not found")
            
            # Check if trial expired
            trial_status = "active"
            if row["trial_ends_at"] and row["trial_ends_at"] < datetime.utcnow():
                trial_status = "expired"
            
            remaining_credits = row["ai_credits_per_month"] - row["credits_used"]
            
            return {
                "tier": row["tier_name"],
                "tier_display": row["tier_display_name"],
                "subscription_status": row["subscription_status"],
                "period_start": row["current_period_start"],
                "period_end": row["current_period_end"],
                "trial": {
                    "status": trial_status,
                    "started_at": row["trial_started_at"],
                    "ends_at": row["trial_ends_at"]
                },
                "usage": {
                    "roles": {
                        "limit": row["roles_per_month"],
                        "used": row["roles_used"],
                        "remaining": row["roles_per_month"] - row["roles_used"]
                    },
                    "video_interviews": {
                        "limit": row["video_interviews_per_month"],
                        "used": row["interviews_used"],
                        "remaining": row["video_interviews_per_month"] - row["interviews_used"]
                    },
                    "ai_credits": {
                        "limit": row["ai_credits_per_month"],
                        "used": row["credits_used"],
                        "remaining": remaining_credits if remaining_credits > 0 else 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting billing status: {e}")
            raise
