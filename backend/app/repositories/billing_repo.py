"""
Billing & subscription repository (Module 8).
Pain #6: Thin margins → multi-tenant, white-label, Stripe integration.
"""

from supabase import Client
from datetime import datetime
from typing import Optional


class BillingRepository:
    """Repository for subscriptions, white-label config."""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_subscription(
        self,
        org_id: str,
        tier: str,
        billing_email: str,
        stripe_customer_id: str,
    ) -> dict:
        """Create SaaS subscription (Pain #6)."""
        data = {
            "org_id": org_id,
            "tier": tier,
            "billing_email": billing_email,
            "stripe_customer_id": stripe_customer_id,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
        }
        response = self.client.table("subscriptions").insert(data).execute()
        return response.data[0] if response.data else None

    async def get_subscription(self, org_id: str) -> Optional[dict]:
        """Get active subscription for org."""
        response = (
            self.client.table("subscriptions")
            .select("*")
            .eq("org_id", org_id)
            .eq("status", "active")
            .single()
            .execute()
        )
        return response.data

    async def create_white_label_config(
        self,
        org_id: str,
        custom_domain: Optional[str],
        logo_url: Optional[str],
        brand_color: str,
    ) -> dict:
        """
        Create white-label config (Pain #6: reseller model).
        Enables agency/group to rebrand platform.
        """
        data = {
            "org_id": org_id,
            "custom_domain": custom_domain,
            "logo_url": logo_url,
            "brand_color": brand_color,
        }
        response = (
            self.client.table("white_label_configs").insert(data).execute()
        )
        return response.data[0] if response.data else None

    async def get_white_label_config(self, org_id: str) -> Optional[dict]:
        """Fetch white-label customization."""
        response = (
            self.client.table("white_label_configs")
            .select("*")
            .eq("org_id", org_id)
            .single()
            .execute()
        )
        return response.data

    async def generate_api_key(self, org_id: str) -> str:
        """Generate Zapier/Make integration API key (Pain #6)."""
        import secrets

        api_key = secrets.token_urlsafe(32)
        self.client.table("white_label_configs").update({"api_key": api_key}).eq(
            "org_id", org_id
        ).execute()
        return api_key
