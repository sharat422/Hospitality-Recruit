"""
Billing & white-label service (Module 8).
Pain #6: Thin margins → multi-tenant SaaS + white-label + reseller.
"""

import stripe
from app.repositories.billing_repo import BillingRepository
from app.core.config import settings
from datetime import datetime, timedelta
from typing import Optional


# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY or ""


class BillingService:
    """SaaS billing + subscription management (Pain #6)."""

    def __init__(self, billing_repo: BillingRepository):
        self.repo = billing_repo
        self.stripe = stripe

    async def create_subscription(
        self,
        org_id: str,
        org_email: str,
        tier: str,  # starter, growth, enterprise
    ) -> dict:
        """
        Create Stripe subscription (Pain #6).
        Multi-tenant: each org gets isolated tenant + custom domain option.
        """
        # Create Stripe customer
        customer = stripe.Customer.create(
            email=org_email,
            metadata={"org_id": org_id},
        )

        # Get price_id for tier
        price_mapping = {
            "starter": "price_starter_monthly",
            "growth": "price_growth_monthly",
            "enterprise": "price_enterprise_monthly",
        }

        price_id = price_mapping.get(tier, price_mapping["starter"])

        # Create subscription
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )

        # Save to DB
        db_subscription = await self.repo.create_subscription(
            org_id, tier, org_email, customer.id
        )

        return {
            "subscription_id": subscription.id,
            "stripe_customer_id": customer.id,
            "tier": tier,
            "status": subscription.status,
            "next_billing_date": datetime.fromtimestamp(
                subscription.current_period_end
            ),
        }

    async def get_subscription_features(self, org_id: str) -> dict:
        """
        Get feature access based on tier (Pain #6).
        Starter: basic screening + SMS
        Growth: + shift matching + analytics
        Enterprise: + white-label + API + custom integrations
        """
        sub = await self.repo.get_subscription(org_id)
        if not sub:
            return {}

        tier = sub.get("tier", "starter")

        features = {
            "starter": [
                "ai_screening",
                "sms_recruiting",
                "basic_dashboard",
                "up_to_50_hires_month",
            ],
            "growth": [
                "ai_screening",
                "sms_recruiting",
                "shift_matching",
                "advanced_dashboard",
                "up_to_200_hires_month",
                "talent_pool_retention",
            ],
            "enterprise": [
                "ai_screening",
                "sms_recruiting",
                "shift_matching",
                "advanced_dashboard",
                "talent_pool_retention",
                "white_label",
                "rest_api",
                "zapier_integration",
                "unlimited_hires",
                "priority_support",
            ],
        }

        return {
            "tier": tier,
            "features": features.get(tier, []),
        }

    async def setup_white_label(
        self,
        org_id: str,
        custom_domain: Optional[str],
        logo_url: Optional[str],
        brand_color: str,
    ) -> dict:
        """
        Configure white-label (Pain #6: reseller/agency model).
        Allows staffing agencies to rebrand HospRecruit as their own.
        """
        # Verify org is on enterprise tier
        sub = await self.repo.get_subscription(org_id)
        if not sub or sub.get("tier") != "enterprise":
            raise ValueError("White-label only available on enterprise tier")

        # Create config
        config = await self.repo.create_white_label_config(
            org_id, custom_domain, logo_url, brand_color
        )

        # Generate API key for integrations
        api_key = await self.repo.generate_api_key(org_id)

        return {
            "org_id": org_id,
            "custom_domain": custom_domain,
            "brand_color": brand_color,
            "api_key": api_key,
        }
