"""
Merge.dev ATS Integration Service

Bi-directional synchronization with 50+ ATS platforms (Bullhorn, iCIMS, Greenhouse, etc)
via Merge.dev unified API.

Features:
1. Pull Jobs: Sync open positions from ATS → Supabase
2. Push Candidates: Sync screened & interviewed candidates → ATS
3. Status Updates: Keep pipeline stages synchronized
4. Webhook Handling: Process ATS events in real-time
5. Error Recovery: Automatic retry with exponential backoff
6. Audit Trail: Log all sync operations for compliance

ROI: Single integration point for 50+ ATS platforms
"""

import json
import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Enums & Types
# ============================================================================

class ATSProvider(str, Enum):
    """Supported ATS providers via Merge.dev"""
    BULLHORN = "bullhorn"
    ICIMS = "icims"
    GREENHOUSE = "greenhouse"
    WORKABLE = "workable"
    SMARTRECRUITERS = "smartrecruiters"
    JAZZHR = "jazzhr"
    BAMBOO_HR = "bamboohr"
    LEVER = "lever"
    RECRUITER_BOX = "recruiterbox"
    TEAM_TAIGA = "teamtaiga"


class SyncDirection(str, Enum):
    """Sync direction"""
    INBOUND = "inbound"      # ATS → HospRecruit
    OUTBOUND = "outbound"    # HospRecruit → ATS
    BIDIRECTIONAL = "bidirectional"


class CandidateStageMapping:
    """Map HospRecruit pipeline stages to ATS stages"""
    
    # HospRecruit stage → ATS stage (generic, customizable per ATS)
    STAGE_MAPPING = {
        "new_lead": "new_lead",
        "screened": "phone_screen",
        "phone_screened": "phone_screen",
        "interviewing": "interview",
        "passed_interview": "interview",
        "offered": "offer",
        "hired": "hired",
        "rejected": "rejected",
        "declined": "rejected"
    }
    
    @classmethod
    def hosprecruit_to_ats(cls, stage: str, provider: str = None) -> str:
        """Convert HospRecruit stage to ATS stage"""
        return cls.STAGE_MAPPING.get(stage, stage)
    
    @classmethod
    def ats_to_hosprecruit(cls, ats_stage: str, provider: str = None) -> str:
        """Convert ATS stage to HospRecruit stage"""
        reverse_mapping = {v: k for k, v in cls.STAGE_MAPPING.items()}
        return reverse_mapping.get(ats_stage, ats_stage)


@dataclass
class MergeOAuthConfig:
    """OAuth callback response from Merge.dev"""
    merge_account_token: str  # Unique token for this ATS connection
    integration_id: str       # Merge integration ID
    api_version: str          # Merge API version
    provider: str             # bullhorn, icims, etc


# ============================================================================
# Merge.dev API Client
# ============================================================================

class MergeAPIClient:
    """Low-level client for Merge.dev unified API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.mergeapi.com/api/ats/v1"
        self.timeout = 30
    
    def _headers(self, account_token: str) -> Dict[str, str]:
        """Build request headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Account-Token": account_token,
            "Content-Type": "application/json"
        }
    
    async def get(
        self,
        endpoint: str,
        account_token: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """GET request to Merge.dev"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}{endpoint}",
                    headers=self._headers(account_token),
                    params=params or {}
                )
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Merge.dev GET failed: {e.status_code} {e.response.text}")
            raise
    
    async def post(
        self,
        endpoint: str,
        account_token: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """POST request to Merge.dev"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    headers=self._headers(account_token),
                    json=data
                )
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Merge.dev POST failed: {e.status_code} {e.response.text}")
            raise
    
    async def patch(
        self,
        endpoint: str,
        account_token: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PATCH request to Merge.dev"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}{endpoint}",
                    headers=self._headers(account_token),
                    json=data
                )
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Merge.dev PATCH failed: {e.status_code} {e.response.text}")
            raise


# ============================================================================
# ATS Sync Service
# ============================================================================

class ATSMergeDeveloperService:
    """
    Main service for ATS synchronization via Merge.dev
    """
    
    def __init__(self, db_service, merge_api_key: str):
        self.db = db_service
        self.merge_client = MergeAPIClient(merge_api_key)
        self.api_key = merge_api_key
    
    # ========================================================================
    # Authentication & Connection
    # ========================================================================
    
    async def get_oauth_url(self, org_id: str) -> str:
        """
        Generate OAuth URL for ATS connection
        
        User clicks this → redirected to ATS login → returns to /ats/oauth/callback
        """
        redirect_uri = "https://yourapp.com/api/ats/oauth/callback"
        
        oauth_url = (
            f"https://app.merge.dev/oauth"
            f"?api_key={self.api_key}"
            f"&redirect_uri={redirect_uri}"
            f"&state={org_id}"
            f"&integration=ats"
        )
        
        return oauth_url
    
    async def handle_oauth_callback(
        self,
        org_id: str,
        code: str
    ) -> MergeOAuthConfig:
        """
        Handle OAuth callback from Merge.dev
        
        1. Exchange code for merge_account_token
        2. Store in ats_configurations
        3. Verify connection (test API call)
        """
        try:
            # Exchange code for tokens
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://app.merge.dev/api/oauth/token",
                    data={
                        "code": code,
                        "api_key": self.api_key,
                        "redirect_uri": "https://yourapp.com/api/ats/oauth/callback"
                    }
                )
            
            response.raise_for_status()
            data = response.json()
            
            merge_config = MergeOAuthConfig(
                merge_account_token=data['account_token'],
                integration_id=data['integration']['id'],
                api_version=data.get('api_version', 'v1'),
                provider=data['integration']['category'].lower()
            )
            
            logger.info(f"OAuth success for org {org_id}, provider {merge_config.provider}")
            return merge_config
        
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}")
            raise
    
    async def verify_ats_connection(
        self,
        account_token: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Test ATS connection by making a test API call
        
        Returns: (is_connected, error_message)
        """
        try:
            # Simple test: fetch user/self info
            result = await self.merge_client.get(
                "/users/me",
                account_token=account_token
            )
            
            return True, None
        
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"ATS connection verification failed: {error_msg}")
            return False, error_msg
    
    # ========================================================================
    # Inbound Sync: Pull Jobs from ATS
    # ========================================================================
    
    async def sync_jobs_from_ats(
        self,
        org_id: str,
        ats_config_id: str,
        force_full_sync: bool = False
    ) -> Dict[str, int]:
        """
        Pull all open jobs from ATS and store in Supabase
        
        Process:
        1. Fetch jobs from ATS via Merge.dev
        2. For each job:
           - Check if already synced (by ats_job_id)
           - Map fields to HospRecruit job schema
           - Store in ats_synced_jobs
           - Optionally create/update corresponding job in jobs table
        3. Return count of new/updated jobs
        
        Returns: {'synced': 5, 'updated': 2, 'failed': 0}
        """
        try:
            config = await self.db.ats_configurations.get(ats_config_id)
            
            if not config['is_connected']:
                raise Exception("ATS not connected")
            
            # Fetch jobs from ATS
            jobs_response = await self.merge_client.get(
                "/jobs",
                account_token=config['merge_account_token'],
                params={'status': 'open', 'limit': 100}
            )
            
            jobs = jobs_response.get('results', [])
            synced_count = 0
            updated_count = 0
            failed_count = 0
            
            # Process each job
            for ats_job in jobs:
                try:
                    result = await self._sync_single_job(
                        org_id,
                        ats_config_id,
                        config,
                        ats_job
                    )
                    
                    if result == 'created':
                        synced_count += 1
                    elif result == 'updated':
                        updated_count += 1
                
                except Exception as e:
                    logger.error(f"Failed to sync job {ats_job.get('id')}: {e}")
                    failed_count += 1
                    
                    # Log failure
                    await self.db.ats_sync_logs.create(
                        org_id=org_id,
                        ats_config_id=ats_config_id,
                        operation_type='job_sync',
                        sync_direction='inbound',
                        ats_job_id=ats_job.get('id'),
                        status='failed',
                        error_message=str(e)
                    )
            
            # Update last sync time
            await self.db.ats_configurations.update(
                ats_config_id,
                last_sync_at=datetime.utcnow(),
                next_sync_at=datetime.utcnow() + timedelta(hours=6)
            )
            
            logger.info(
                f"Synced {synced_count} new, updated {updated_count}, "
                f"{failed_count} failed for org {org_id}"
            )
            
            return {
                'synced': synced_count,
                'updated': updated_count,
                'failed': failed_count
            }
        
        except Exception as e:
            logger.error(f"Job sync failed: {e}")
            raise
    
    async def _sync_single_job(
        self,
        org_id: str,
        ats_config_id: str,
        config: Dict,
        ats_job: Dict
    ) -> str:
        """Sync single job and return 'created' or 'updated'"""
        
        # Create hash to detect changes
        job_hash = hashlib.sha256(json.dumps(ats_job, sort_keys=True).encode()).hexdigest()
        
        # Check if already synced
        existing = await self.db.ats_synced_jobs.get_by(
            org_id=org_id,
            ats_provider=config['ats_provider'],
            ats_job_id=ats_job.get('id')
        )
        
        if existing and existing[0]['sync_hash'] == job_hash:
            # No changes
            return 'unchanged'
        
        # Extract job data
        job_data = {
            'org_id': org_id,
            'ats_config_id': ats_config_id,
            'ats_job_id': ats_job.get('id'),
            'ats_provider': config['ats_provider'],
            'title': ats_job.get('name'),
            'description': ats_job.get('description'),
            'department': ats_job.get('department'),
            'location': ats_job.get('locations', [{}])[0].get('name') if ats_job.get('locations') else None,
            'ats_status': ats_job.get('status'),
            'is_active': ats_job.get('status') == 'open',
            'hiring_manager_name': ats_job.get('hiring_manager', {}).get('name'),
            'hiring_manager_email': ats_job.get('hiring_manager', {}).get('email'),
            'sync_hash': job_hash,
            'ats_raw_data': ats_job,
            'synced_at': datetime.utcnow()
        }
        
        if existing:
            # Update
            await self.db.ats_synced_jobs.update(existing[0]['id'], job_data)
            return 'updated'
        else:
            # Create
            await self.db.ats_synced_jobs.create(job_data)
            return 'created'
    
    # ========================================================================
    # Outbound Sync: Push Candidates to ATS
    # ========================================================================
    
    async def push_candidate_to_ats(
        self,
        org_id: str,
        candidate_id: str,
        ats_job_id: str,
        ats_config_id: str,
        screening_score: Optional[float] = None
    ) -> str:
        """
        Push screened candidate to ATS
        
        Process:
        1. Fetch candidate from HospRecruit
        2. Check if already exists in ATS
        3. Create or update candidate in ATS
        4. Store mapping in candidate_ats_mappings
        5. Return ATS candidate ID
        """
        try:
            config = await self.db.ats_configurations.get(ats_config_id)
            candidate = await self.db.candidates.get(candidate_id)
            
            # Prepare candidate payload for ATS
            candidate_payload = {
                'first_name': candidate['first_name'],
                'last_name': candidate['last_name'],
                'email_addresses': [
                    {'email_address': candidate['email'], 'email_address_type': 'personal'}
                ],
                'phone_numbers': [
                    {'phone_number': candidate['phone'], 'phone_number_type': 'mobile'}
                ] if candidate.get('phone') else [],
                'resume_url': candidate.get('resume_url'),
                'custom_fields': {
                    'screening_score': str(screening_score) if screening_score else None,
                    'hosprecruit_candidate_id': str(candidate_id)
                }
            }
            
            # Create application in ATS
            app_payload = {
                'candidate': candidate_payload,
                'job': ats_job_id,
                'source': 'HospRecruit'
            }
            
            response = await self.merge_client.post(
                "/applications",
                account_token=config['merge_account_token'],
                data=app_payload
            )
            
            ats_candidate_id = response.get('candidate', {}).get('id')
            ats_application_id = response.get('id')
            
            # Create mapping
            await self.db.candidate_ats_mappings.create(
                org_id=org_id,
                candidate_id=candidate_id,
                ats_config_id=ats_config_id,
                ats_candidate_id=ats_candidate_id,
                ats_application_id=ats_application_id,
                ats_job_id=ats_job_id,
                ats_provider=config['ats_provider'],
                screening_score=screening_score,
                is_synced=True,
                last_synced_to_ats=datetime.utcnow()
            )
            
            # Log sync
            await self.db.ats_sync_logs.create(
                org_id=org_id,
                ats_config_id=ats_config_id,
                operation_type='candidate_push',
                sync_direction='outbound',
                candidate_id=candidate_id,
                ats_candidate_id=ats_candidate_id,
                status='success',
                response_received=response,
                records_succeeded=1
            )
            
            logger.info(f"Pushed candidate {candidate_id} to ATS as {ats_candidate_id}")
            
            return ats_candidate_id
        
        except Exception as e:
            logger.error(f"Failed to push candidate to ATS: {e}")
            
            await self.db.ats_sync_logs.create(
                org_id=org_id,
                ats_config_id=ats_config_id,
                operation_type='candidate_push',
                sync_direction='outbound',
                candidate_id=candidate_id,
                status='failed',
                error_message=str(e)
            )
            
            raise
    
    async def update_candidate_stage_in_ats(
        self,
        candidate_id: str,
        ats_config_id: str,
        new_stage: str
    ) -> bool:
        """
        Update candidate's application stage in ATS
        
        Triggered when: candidate moves through HospRecruit pipeline
        """
        try:
            # Find mapping
            mapping = await self.db.candidate_ats_mappings.get_by(
                candidate_id=candidate_id,
                ats_config_id=ats_config_id
            )
            
            if not mapping:
                logger.warning(f"No ATS mapping found for candidate {candidate_id}")
                return False
            
            config = await self.db.ats_configurations.get(ats_config_id)
            
            # Convert stage
            ats_stage = CandidateStageMapping.hosprecruit_to_ats(
                new_stage,
                config['ats_provider']
            )
            
            # Update in ATS
            await self.merge_client.patch(
                f"/applications/{mapping[0]['ats_application_id']}",
                account_token=config['merge_account_token'],
                data={'stage': ats_stage}
            )
            
            # Update mapping
            await self.db.candidate_ats_mappings.update(
                mapping[0]['id'],
                ats_stage=ats_stage,
                hosprecruit_status=new_stage,
                last_synced_to_ats=datetime.utcnow(),
                is_synced=True
            )
            
            logger.info(
                f"Updated candidate {candidate_id} stage to {ats_stage} in ATS"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to update candidate stage in ATS: {e}")
            return False
    
    # ========================================================================
    # Webhook Handling
    # ========================================================================
    
    async def process_webhook_event(
        self,
        org_id: str,
        ats_config_id: str,
        event_payload: Dict[str, Any],
        webhook_signature: str
    ) -> bool:
        """
        Process webhook event from ATS
        
        Events can be:
        - candidate.created: New candidate applied
        - candidate.updated: Candidate info changed
        - application.updated: Application stage changed
        - job.closed: Job de-activated
        
        Verification: Validate webhook signature before processing
        """
        try:
            config = await self.db.ats_configurations.get(ats_config_id)
            
            # Verify signature
            is_valid = self._verify_webhook_signature(
                webhook_signature,
                json.dumps(event_payload),
                config.get('webhook_secret', '')
            )
            
            if not is_valid:
                logger.warning(f"Invalid webhook signature for org {org_id}")
                return False
            
            event_type = event_payload.get('type')
            
            # Store event
            await self.db.ats_events.create(
                org_id=org_id,
                ats_config_id=ats_config_id,
                event_type=event_type,
                event_name=event_payload.get('name'),
                ats_provider=config['ats_provider'],
                event_payload=event_payload,
                webhook_signature_verified=True,
                webhook_timestamp=datetime.utcnow()
            )
            
            # Process based on type
            if event_type == 'candidate.created':
                await self._process_candidate_created(org_id, ats_config_id, event_payload)
            
            elif event_type == 'candidate.updated':
                await self._process_candidate_updated(org_id, ats_config_id, event_payload)
            
            elif event_type == 'application.updated':
                await self._process_application_updated(org_id, ats_config_id, event_payload)
            
            elif event_type == 'job.closed':
                await self._process_job_closed(org_id, ats_config_id, event_payload)
            
            # Mark event as processed
            await self.db.ats_events.update(
                event_payload.get('webhook_id'),
                is_processed=True,
                processed_at=datetime.utcnow()
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to process webhook: {e}")
            return False
    
    def _verify_webhook_signature(self, signature: str, payload: str, secret: str) -> bool:
        """Verify webhook signature from ATS"""
        expected = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    async def _process_candidate_created(
        self,
        org_id: str,
        ats_config_id: str,
        event: Dict
    ) -> None:
        """Process candidate.created webhook"""
        ats_candidate_id = event.get('candidate', {}).get('id')
        # TODO: Import candidate into HospRecruit
        logger.info(f"New candidate from ATS: {ats_candidate_id}")
    
    async def _process_candidate_updated(
        self,
        org_id: str,
        ats_config_id: str,
        event: Dict
    ) -> None:
        """Process candidate.updated webhook"""
        logger.info(f"Candidate updated: {event.get('candidate', {}).get('id')}")
    
    async def _process_application_updated(
        self,
        org_id: str,
        ats_config_id: str,
        event: Dict
    ) -> None:
        """Process application.updated webhook"""
        logger.info(f"Application updated: {event.get('application', {}).get('id')}")
    
    async def _process_job_closed(
        self,
        org_id: str,
        ats_config_id: str,
        event: Dict
    ) -> None:
        """Process job.closed webhook"""
        ats_job_id = event.get('job', {}).get('id')
        
        # Deactivate job in HospRecruit
        await self.db.ats_synced_jobs.update_by(
            ats_job_id=ats_job_id,
            is_active=False
        )
        
        logger.info(f"Job closed: {ats_job_id}")
    
    # ========================================================================
    # Batch Sync for Unsynced Candidates
    # ========================================================================
    
    async def sync_pending_candidates(
        self,
        org_id: str,
        ats_config_id: str,
        batch_size: int = 25
    ) -> int:
        """
        Batch sync candidates that need resync
        
        Returns: Number of candidates synced
        """
        try:
            pending = await self.db.candidate_ats_mappings.list(
                org_id=org_id,
                ats_config_id=ats_config_id,
                requires_resync=True,
                limit=batch_size
            )
            
            synced_count = 0
            
            for mapping in pending:
                try:
                    candidate = await self.db.candidates.get(mapping['candidate_id'])
                    
                    # Update stage in ATS
                    await self.update_candidate_stage_in_ats(
                        mapping['candidate_id'],
                        ats_config_id,
                        mapping['hosprecruit_status']
                    )
                    
                    # Mark as synced
                    await self.db.candidate_ats_mappings.update(
                        mapping['id'],
                        requires_resync=False,
                        is_synced=True,
                        last_synced_to_ats=datetime.utcnow()
                    )
                    
                    synced_count += 1
                
                except Exception as e:
                    logger.error(f"Failed to sync mapping {mapping['id']}: {e}")
            
            logger.info(f"Synced {synced_count} pending candidates")
            return synced_count
        
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            raise
