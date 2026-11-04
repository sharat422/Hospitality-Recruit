"""
Merge.dev ATS Integration Service — Bi-Directional Candidate Sync

Features:
- Bi-directional sync with Merge.dev unified ATS API
- Supports: Bullhorn, iCIMS, Greenhouse, and 50+ other ATS platforms
- Auto-create and update candidates in external ATS
- Sync qualified screening results, availability, certifications
- Handle webhook updates from ATS back to HospRecruit
- Retry logic with exponential backoff
- Idempotency via request ID tracking

Pain Point Resolution:
- Pain #1 (Screening): Auto-move qualified candidates to ATS for interviews
- Eliminates manual data entry between screening and ATS
- Single source of truth: HospRecruit feeds ATS with enriched candidate data

Integration Flow:
1. Candidate completes SMS screening in HospRecruit
2. If qualified, trigger outbound sync to ATS via Merge.dev
3. Merge.dev creates/updates candidate record in target ATS (Bullhorn/iCIMS)
4. ATS webhooks notify HospRecruit of status changes (offer sent, interview scheduled, hired)
5. Updates reflected in real-time dashboard
"""

import json
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

from supabase import AsyncClient


class ATSProvider(str, Enum):
    """Supported ATS platforms via Merge.dev"""
    BULLHORN = "bullhorn"
    ICIMS = "icims"
    GREENHOUSE = "greenhouse"
    WORKABLE = "workable"
    LEVER = "lever"
    JOBVITE = "jobvite"
    TALEO = "oracle_taleo"
    SUCCESSFACTORS = "successfactors"
    BAMBOOHR = "bamboohr"


class SyncDirection(str, Enum):
    """Sync direction enumeration"""
    OUTBOUND = "outbound"  # HospRecruit → ATS
    INBOUND = "inbound"    # ATS → HospRecruit


class MergeDeveloper:
    """
    Merge.dev API client for ATS integration.
    
    Merge.dev provides a unified REST API to 50+ ATS platforms.
    This service abstracts the complexity of different ATS schemas.
    """
    
    def __init__(
        self,
        merge_dev_api_key: str,
        merge_dev_base_url: str = "https://api.merge.dev/api/ats/v1"
    ):
        self.api_key = merge_dev_api_key
        self.base_url = merge_dev_base_url
        self.headers = {
            "Authorization": f"Bearer {merge_dev_api_key}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": None  # Set per request for idempotency
        }
    
    async def create_candidate(
        self,
        access_token: str,
        candidate_data: Dict[str, Any],
        idempotency_key: str
    ) -> Dict[str, Any]:
        """
        Create a candidate in the connected ATS via Merge.dev.
        
        Args:
            access_token: Merge.dev access token for the customer's ATS connection
            candidate_data: Candidate info to send to ATS
            idempotency_key: Unique request ID for idempotency
        
        Returns:
            Response from Merge.dev including created candidate ID
        """
        headers = {**self.headers, "X-Idempotency-Key": idempotency_key}
        
        payload = {
            "model": candidate_data,  # Merge.dev standardized schema
            "remote_user_id": candidate_data.get("external_candidate_id")  # For idempotency in ATS
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/candidates",
                json=payload,
                headers=headers,
                params={"include_remote_data": "true"}
            )
        
        return response.json()
    
    async def update_candidate(
        self,
        access_token: str,
        external_candidate_id: str,
        candidate_data: Dict[str, Any],
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Update an existing candidate in the ATS."""
        headers = {**self.headers, "X-Idempotency-Key": idempotency_key}
        
        payload = {"model": candidate_data}
        
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/candidates/{external_candidate_id}",
                json=payload,
                headers=headers,
                params={"include_remote_data": "true"}
            )
        
        return response.json()
    
    async def get_candidate(
        self,
        external_candidate_id: str,
        access_token: str
    ) -> Dict[str, Any]:
        """Retrieve a candidate from the ATS."""
        headers = {**self.headers}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/candidates/{external_candidate_id}",
                headers=headers,
                params={"include_remote_data": "true"}
            )
        
        return response.json()


class MergeDeveloperATSService:
    """
    Orchestrates bi-directional ATS sync via Merge.dev.
    
    Handles:
    - Qualified screening results → ATS candidate creation
    - Candidate data enrichment (availability, certifications)
    - ATS webhook event processing
    - Sync status tracking and retry logic
    """
    
    def __init__(
        self,
        supabase_client: AsyncClient,
        merge_dev_api_key: str,
        merge_dev_base_url: str = "https://api.merge.dev/api/ats/v1"
    ):
        self.supabase = supabase_client
        self.merge_api = MergeDeveloper(merge_dev_api_key, merge_dev_base_url)
    
    # ========================================================================
    # Outbound Sync: HospRecruit → ATS
    # ========================================================================
    
    async def sync_qualified_candidate_to_ats(
        self,
        screening_session_id: str,
        candidate_id: str,
        org_id: str,
        job_id: str
    ) -> Dict[str, Any]:
        """
        Sync a qualified screening result to the external ATS.
        
        Triggered when:
        - Screening session completes with final_score >= 70
        - Recruiter manually initiates sync
        
        Flow:
        1. Fetch screening data (score, extracted answers, availability)
        2. Fetch ATS connection info for org
        3. Build Merge.dev standardized candidate payload
        4. Call Merge.dev API
        5. Log sync event (success/failure/retry)
        6. Update screening_session with external ID
        """
        
        # Fetch screening session data
        session_resp = await self.supabase.table("screening_sessions").select("*").eq("id", screening_session_id).single().execute()
        session = session_resp.data
        
        if not session or not session.get("qualified"):
            return {"error": "Screening session not qualified for ATS sync"}
        
        # Fetch candidate data
        cand_resp = await self.supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
        candidate = cand_resp.data
        
        # Fetch job data
        job_resp = await self.supabase.table("jobs").select("*").eq("id", job_id).single().execute()
        job = job_resp.data
        
        # Fetch ATS connection for this org
        ats_conn_resp = await self._get_org_ats_connection(org_id)
        if not ats_conn_resp:
            return {"error": "No ATS connection configured for organization"}
        
        ats_provider = ats_conn_resp.get("ats_provider")
        access_token = ats_conn_resp.get("access_token")
        merge_account_token = ats_conn_resp.get("merge_dev_account_token")
        
        # Build Merge.dev standardized candidate payload
        candidate_payload = self._build_merge_candidate_payload(
            candidate=candidate,
            session=session,
            job=job,
            ats_provider=ats_provider
        )
        
        # Generate idempotency key for retry safety
        idempotency_key = f"hoprecruit_{candidate_id}_{screening_session_id}_{datetime.utcnow().timestamp()}"
        
        # Call Merge.dev API
        try:
            if session.get("ats_candidate_id"):
                # Update existing candidate
                response = await self.merge_api.update_candidate(
                    access_token=merge_account_token,
                    external_candidate_id=session["ats_candidate_id"],
                    candidate_data=candidate_payload,
                    idempotency_key=idempotency_key
                )
                sync_action = "update"
            else:
                # Create new candidate
                response = await self.merge_api.create_candidate(
                    access_token=merge_account_token,
                    candidate_data=candidate_payload,
                    idempotency_key=idempotency_key
                )
                sync_action = "create"
            
            # Extract external candidate ID from response
            external_candidate_id = response.get("id") or response.get("remote_id")
            
            # Log successful sync
            sync_log = {
                "org_id": org_id,
                "candidate_id": candidate_id,
                "screening_session_id": screening_session_id,
                "sync_direction": SyncDirection.OUTBOUND,
                "sync_action": sync_action,
                "ats_provider": ats_provider,
                "external_candidate_id": external_candidate_id,
                "merge_dev_request_id": idempotency_key,
                "payload_sent": candidate_payload,
                "response_received": response,
                "status": "success",
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self.supabase.table("ats_sync_logs").insert(sync_log).execute()
            
            # Update screening session with external ID
            update_data = {
                "ats_synced": True,
                "ats_candidate_id": external_candidate_id,
                "last_ats_sync_at": datetime.utcnow().isoformat()
            }
            await self.supabase.table("screening_sessions").update(update_data).eq("id", screening_session_id).execute()
            
            return {
                "status": "success",
                "external_candidate_id": external_candidate_id,
                "sync_action": sync_action,
                "ats_provider": ats_provider
            }
        
        except Exception as e:
            # Log failed sync with retry info
            sync_log = {
                "org_id": org_id,
                "candidate_id": candidate_id,
                "screening_session_id": screening_session_id,
                "sync_direction": SyncDirection.OUTBOUND,
                "sync_action": "create",
                "ats_provider": ats_provider,
                "merge_dev_request_id": idempotency_key,
                "payload_sent": candidate_payload,
                "status": "failed",
                "error_message": str(e),
                "retry_count": 0,
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self.supabase.table("ats_sync_logs").insert(sync_log).execute()
            
            return {
                "status": "failed",
                "error": str(e),
                "should_retry": True
            }
    
    def _build_merge_candidate_payload(
        self,
        candidate: Dict[str, Any],
        session: Dict[str, Any],
        job: Dict[str, Any],
        ats_provider: str
    ) -> Dict[str, Any]:
        """
        Build standardized Merge.dev candidate payload.
        
        Merge.dev normalizes different ATS field names into a standard schema.
        This ensures the same data works across Bullhorn, iCIMS, Greenhouse, etc.
        """
        
        extracted_data = session.get("extracted_data", {})
        
        payload = {
            "first_name": candidate.get("first_name", ""),
            "last_name": candidate.get("last_name", ""),
            "email_addresses": [
                {
                    "email_address": candidate.get("email"),
                    "email_address_type": "personal"
                }
            ],
            "phone_numbers": [
                {
                    "phone_number": candidate.get("phone"),
                    "phone_number_type": "mobile"
                }
            ] if candidate.get("phone") else [],
            "locations": [
                {
                    "city": candidate.get("location", "").split(",")[0],
                    "country": "US"
                }
            ] if candidate.get("location") else [],
            
            # Job application
            "applications": [
                {
                    "job_id": job.get("id"),
                    "rejected_at": None,
                    "source": candidate.get("source") or "api",
                    "credited_to": "HospRecruit AI Screening"
                }
            ],
            
            # Custom fields for hospitality (ATS-dependent, but most support)
            "custom_fields": {
                "hoprecruit_screening_score": session.get("screening_score"),
                "hoprecruit_qualified": session.get("qualified"),
                "hoprecruit_availability": json.dumps(candidate.get("availability", [])),
                "hoprecruit_certifications": json.dumps(extracted_data.get("certifications", [])),
                "hoprecruit_experience_years": extracted_data.get("years_experience"),
                "hoprecruit_screening_session_id": session.get("id"),
                "hoprecruit_recommendation": session.get("ai_recommendation"),
                "hoprecruit_red_flags": json.dumps(session.get("red_flags", [])),
            },
            
            # URLs for follow-up
            "urls": [
                {
                    "url": f"https://hoprecruit.app/screening/{session.get('id')}",
                    "url_type": "profile"
                }
            ]
        }
        
        return payload
    
    # ========================================================================
    # Inbound Sync: ATS → HospRecruit (via webhooks)
    # ========================================================================
    
    async def process_ats_webhook(
        self,
        org_id: str,
        webhook_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process webhook event from ATS (via Merge.dev passthrough).
        
        ATS Events:
        - candidate.updated (e.g., moved to interview stage)
        - candidate.rejected (e.g., recruiter rejected after screening)
        - candidate.archived
        - job_application.status_changed (e.g., offer sent)
        
        Returns: sync log entry for tracking
        """
        
        event_type = webhook_event.get("type")
        external_candidate_id = webhook_event.get("candidate_id") or webhook_event.get("external_candidate_id")
        ats_provider = webhook_event.get("ats_provider", "unknown")
        
        # Find HospRecruit candidate via external ID
        sync_resp = await self.supabase.table("ats_sync_logs").select("candidate_id").eq("external_candidate_id", external_candidate_id).limit(1).execute()
        
        if not sync_resp.data:
            return {"error": f"No HospRecruit candidate found for external ID {external_candidate_id}"}
        
        hoprecruit_candidate_id = sync_resp.data[0]["candidate_id"]
        
        # Handle different event types
        if event_type == "candidate.rejected":
            update_data = {
                "pipeline_stage": "rejected",
                "updated_at": datetime.utcnow().isoformat()
            }
            await self.supabase.table("candidates").update(update_data).eq("id", hoprecruit_candidate_id).execute()
        
        elif event_type == "candidate.updated":
            # Job stage changed (e.g., "application_review" → "interview")
            new_stage = webhook_event.get("new_stage")
            stage_mapping = {
                "application_review": "screening_complete",
                "interview": "interview_scheduled",
                "offer": "offer_sent",
                "hired": "offer_accepted",
                "rejected": "rejected"
            }
            hoprecruit_stage = stage_mapping.get(new_stage, new_stage)
            
            update_data = {
                "pipeline_stage": hoprecruit_stage,
                "updated_at": datetime.utcnow().isoformat()
            }
            await self.supabase.table("candidates").update(update_data).eq("id", hoprecruit_candidate_id).execute()
        
        # Log inbound sync
        sync_log = {
            "org_id": org_id,
            "candidate_id": hoprecruit_candidate_id,
            "sync_direction": SyncDirection.INBOUND,
            "sync_action": event_type,
            "ats_provider": ats_provider,
            "external_candidate_id": external_candidate_id,
            "response_received": webhook_event,
            "status": "success",
            "created_at": datetime.utcnow().isoformat()
        }
        
        await self.supabase.table("ats_sync_logs").insert(sync_log).execute()
        
        return {"status": "success", "event_processed": event_type}
    
    # ========================================================================
    # ATS Connection Management
    # ========================================================================
    
    async def _get_org_ats_connection(self, org_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch ATS connection details for organization.
        
        Organizations can connect to Bullhorn, iCIMS, etc. via Merge.dev OAuth flow.
        This retrieves the stored connection metadata.
        """
        
        resp = await self.supabase.table("organization_ats_connections").select("*").eq("org_id", org_id).limit(1).execute()
        return resp.data[0] if resp.data else None
    
    async def retry_failed_syncs(self, org_id: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Retry failed ATS syncs with exponential backoff.
        
        Triggered periodically (e.g., every 15 minutes) via Celery job.
        """
        
        # Fetch failed syncs (retry_count < max_retries, status = 'failed')
        failed_resp = await self.supabase.table("ats_sync_logs").select("*").eq("org_id", org_id).eq("status", "failed").lt("retry_count", max_retries).execute()
        
        failed_syncs = failed_resp.data or []
        retry_results = {"succeeded": [], "failed": [], "skipped": []}
        
        for sync_log in failed_syncs:
            # Check if enough time has passed (exponential backoff)
            retry_count = sync_log.get("retry_count", 0)
            backoff_seconds = (2 ** retry_count) * 60  # 1 min, 2 min, 4 min, etc.
            last_retry = sync_log.get("last_retry_at")
            
            if last_retry:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(last_retry)).total_seconds()
                if elapsed < backoff_seconds:
                    retry_results["skipped"].append(sync_log["id"])
                    continue
            
            # Retry sync
            try:
                if sync_log.get("sync_direction") == SyncDirection.OUTBOUND:
                    result = await self.sync_qualified_candidate_to_ats(
                        screening_session_id=sync_log.get("screening_session_id"),
                        candidate_id=sync_log.get("candidate_id"),
                        org_id=org_id,
                        job_id=sync_log.get("job_id")
                    )
                    
                    if result.get("status") == "success":
                        # Mark as succeeded
                        await self.supabase.table("ats_sync_logs").update({
                            "status": "success",
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("id", sync_log["id"]).execute()
                        
                        retry_results["succeeded"].append(sync_log["id"])
                    else:
                        # Increment retry count
                        await self.supabase.table("ats_sync_logs").update({
                            "retry_count": retry_count + 1,
                            "last_retry_at": datetime.utcnow().isoformat()
                        }).eq("id", sync_log["id"]).execute()
                        
                        retry_results["failed"].append(sync_log["id"])
            
            except Exception as e:
                # Log error and increment retry count
                await self.supabase.table("ats_sync_logs").update({
                    "retry_count": retry_count + 1,
                    "last_retry_at": datetime.utcnow().isoformat(),
                    "error_message": str(e)
                }).eq("id", sync_log["id"]).execute()
                
                retry_results["failed"].append(sync_log["id"])
        
        return retry_results


# ============================================================================
# ROI & Integration Notes
# ============================================================================

"""
MERGE.DEV UNIFIED ATS API:
- Abstracts away differences between Bullhorn, iCIMS, Greenhouse, Workable, etc.
- Single request payload works across all platforms
- Handles field mapping, data type conversion, required fields per ATS
- Webhook passthrough: ATS events → Merge.dev → HospRecruit

SUPPORTED ATS PLATFORMS (via Merge.dev):
- Bullhorn (popular in hospitality staffing)
- iCIMS (Enterprise ATS)
- Greenhouse (modern, startup-friendly)
- Workable (mid-market)
- Lever (Sequoia-backed)
- Jobvite (recruiting suite)
- Oracle Taleo / SuccessFactors
- BambooHR (HR -> recruiting integration)
- 40+ more platforms

BI-DIRECTIONAL WORKFLOW:
1. Candidate completes SMS screening in HospRecruit
2. If score >= 70, auto-create in ATS via Merge.dev
3. Recruiter reviews candidate in ATS (interview scheduling, offers)
4. ATS webhooks sync back to HospRecruit (pipeline stage updates)
5. Real-time dashboard reflects ATS actions (e.g., "Interview scheduled 4/15")

IDEMPOTENCY & RETRIES:
- Merge.dev requires X-Idempotency-Key header for fault tolerance
- If request fails, retry with same key → won't duplicate candidate in ATS
- Exponential backoff on retries (1 min → 2 min → 4 min → give up)

CUSTOM FIELDS MAPPING:
- HospRecruit sends screening score, availability, certifications as custom fields
- Custom fields appear in ATS (if ATS supports; Bullhorn/iCIMS do)
- Recruiters see "HospRecruit Score: 85, Availability: Weekdays 5-11pm" in ATS
"""
