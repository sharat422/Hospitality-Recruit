"""
ATS Router - FastAPI endpoints for Merge.dev ATS integration

Endpoints:
1. GET /oauth-url - Get OAuth URL for ATS connection
2. GET /oauth/callback - Handle OAuth callback from Merge.dev
3. POST /disconnect - Disconnect ATS
4. GET /jobs - Get synced jobs from ATS  
5. POST /jobs/sync - Manually trigger job sync
6. POST /candidates/{id}/push - Push candidate to ATS
7. POST /candidates/{id}/update-stage - Update candidate stage
8. GET /sync-logs - View ATS sync history
9. GET /status - Get current ATS connection status
10. POST /webhook - Webhook endpoint for ATS events
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request
from typing import Optional
from datetime import datetime
import logging

from app.schemas import (
    ATSConnectionResponse,
    ATSJobResponse,
    ATSSyncLogResponse
)
from app.services.ats_merge_dev_service import (
    ATSMergeDeveloperService,
    ATSProvider
)
from app.dependencies import get_current_user, get_db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ats", tags=["ats"])


# ============================================================================
# Dependency Injection
# ============================================================================

async def get_ats_service(
    db = Depends(get_db_service)
) -> ATSMergeDeveloperService:
    """Inject ATS service"""
    import os
    merge_api_key = os.getenv('MERGE_API_KEY')
    
    if not merge_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Merge.dev API key not configured"
        )
    
    return ATSMergeDeveloperService(
        db_service=db,
        merge_api_key=merge_api_key
    )


# ============================================================================
# OAuth & Connection Endpoints
# ============================================================================

@router.get("/oauth-url", response_model=dict)
async def get_oauth_url(
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service)
):
    """
    Get OAuth URL to start ATS connection process
    
    User flow:
    1. Click "Connect ATS"
    2. Frontend calls this endpoint
    3. Get OAuth URL
    4. Redirect to OAuth URL
    5. User authenticates with ATS
    6. Redirected back to /ats/oauth/callback
    
    Response:
    {
        'oauth_url': 'https://app.merge.dev/oauth?...'
    }
    """
    try:
        oauth_url = await ats_service.get_oauth_url(current_user.org_id)
        
        return {
            'oauth_url': oauth_url,
            'message': 'Redirect user to this URL to start ATS connection'
        }
    
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate OAuth URL"
        )


@router.get("/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Handle OAuth callback from Merge.dev
    
    Process:
    1. Exchange code for merge_account_token
    2. Detect ATS provider type
    3. Store in database
    4. Verify connection
    5. Redirect to frontend settings page
    """
    try:
        # Get OAuth config
        oauth_config = await ats_service.handle_oauth_callback(
            org_id=current_user.org_id,
            code=code
        )
        
        # Verify connection
        is_connected, error = await ats_service.verify_ats_connection(
            oauth_config.merge_account_token
        )
        
        if not is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ATS connection verification failed: {error}"
            )
        
        # Check if config already exists for this provider
        existing = await db.ats_configurations.get_by(
            org_id=current_user.org_id,
            ats_provider=oauth_config.provider
        )
        
        if existing:
            # Update existing
            await db.ats_configurations.update(
                existing[0]['id'],
                merge_account_token=oauth_config.merge_account_token,
                merge_integration_id=oauth_config.integration_id,
                is_connected=True,
                connection_verified_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            config_id = existing[0]['id']
        else:
            # Create new
            config = await db.ats_configurations.create(
                org_id=current_user.org_id,
                ats_provider=oauth_config.provider,
                merge_account_token=oauth_config.merge_account_token,
                merge_integration_id=oauth_config.integration_id,
                is_connected=True,
                connection_verified_at=datetime.utcnow(),
                connected_by=current_user.id,
                connected_at=datetime.utcnow()
            )
            config_id = config['id']
        
        logger.info(
            f"ATS connected for org {current_user.org_id}: {oauth_config.provider}"
        )
        
        # Redirect to settings with success message
        return {
            'status': 'success',
            'message': f'{oauth_config.provider} ATS connected successfully',
            'ats_provider': oauth_config.provider,
            'redirect_to': '/settings/ats'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth connection failed. Please try again."
        )


@router.post("/disconnect")
async def disconnect_ats(
    ats_config_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """Disconnect ATS"""
    try:
        config = await db.ats_configurations.get(ats_config_id)
        
        if not config or config['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ATS configuration not found"
            )
        
        # Mark as disconnected
        await db.ats_configurations.update(
            ats_config_id,
            is_connected=False,
            merge_account_token=None
        )
        
        logger.info(f"ATS disconnected for org {current_user.org_id}")
        
        return {
            'status': 'success',
            'message': 'ATS disconnected'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect ATS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect ATS"
        )


# ============================================================================
# Job Sync Endpoints
# ============================================================================

@router.get("/jobs", response_model=dict)
async def get_synced_jobs(
    current_user = Depends(get_current_user),
    db = Depends(get_db_service),
    skip: int = 0,
    limit: int = 50
):
    """
    Get jobs synced from ATS
    
    These are the open jobs that were pulled from the connected ATS.
    """
    try:
        jobs = await db.ats_synced_jobs.list(
            org_id=current_user.org_id,
            is_active=True,
            skip=skip,
            limit=limit
        )
        
        total = await db.ats_synced_jobs.count(
            org_id=current_user.org_id,
            is_active=True
        )
        
        return {
            'items': jobs,
            'total': total,
            'skip': skip,
            'limit': limit
        }
    
    except Exception as e:
        logger.error(f"Failed to get synced jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch jobs"
        )


@router.post("/jobs/sync")
async def sync_jobs_from_ats(
    ats_config_id: str,
    force_full_sync: bool = False,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Manually trigger job sync from ATS
    
    Response:
    {
        'synced': 5,      # newly synced
        'updated': 2,     # updated existing
        'failed': 0
    }
    """
    try:
        config = await db.ats_configurations.get(ats_config_id)
        
        if not config or config['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ATS configuration not found"
            )
        
        if not config['is_connected']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ATS not connected. Please reconnect."
            )
        
        # Sync jobs
        result = await ats_service.sync_jobs_from_ats(
            org_id=current_user.org_id,
            ats_config_id=ats_config_id,
            force_full_sync=force_full_sync
        )
        
        return {
            'status': 'success',
            'message': f"Synced {result['synced']} jobs, updated {result['updated']}",
            'result': result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job sync failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job sync failed"
        )


# ============================================================================
# Candidate Push Endpoints
# ============================================================================

@router.post("/candidates/{candidate_id}/push")
async def push_candidate_to_ats(
    candidate_id: str,
    ats_job_id: str,
    ats_config_id: str,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Push screened candidate to ATS
    
    Creates an application in the ATS for this candidate.
    
    Response:
    {
        'ats_candidate_id': 'from_ats',
        'ats_application_id': 'app_id_from_ats',
        'message': 'Candidate pushed to ATS'
    }
    """
    try:
        # Verify org owns candidate
        candidate = await db.candidates.get(candidate_id)
        
        if candidate['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        # Verify ATS config
        config = await db.ats_configurations.get(ats_config_id)
        
        if not config or config['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ATS configuration not found"
            )
        
        # Push candidate
        ats_candidate_id = await ats_service.push_candidate_to_ats(
            org_id=current_user.org_id,
            candidate_id=candidate_id,
            ats_job_id=ats_job_id,
            ats_config_id=ats_config_id,
            screening_score=candidate.get('screening_score')
        )
        
        return {
            'status': 'success',
            'ats_candidate_id': ats_candidate_id,
            'message': f'Candidate {candidate["first_name"]} pushed to ATS'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to push candidate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to push candidate to ATS"
        )


@router.post("/candidates/{candidate_id}/update-stage")
async def update_candidate_stage(
    candidate_id: str,
    new_stage: str,
    ats_config_id: str,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Update candidate's stage in ATS
    
    Called when candidate moves through HospRecruit pipeline.
    Syncs status to ATS automatically.
    """
    try:
        config = await db.ats_configurations.get(ats_config_id)
        
        if not config or config['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ATS configuration not found"
            )
        
        success = await ats_service.update_candidate_stage_in_ats(
            candidate_id=candidate_id,
            ats_config_id=ats_config_id,
            new_stage=new_stage
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update candidate stage in ATS"
            )
        
        return {
            'status': 'success',
            'message': f'Candidate stage updated to {new_stage} in ATS'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update candidate stage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update candidate stage"
        )


# ============================================================================
# Status & Metrics Endpoints
# ============================================================================

@router.get("/status")
async def get_ats_status(
    current_user = Depends(get_current_user),
    db = Depends(get_db_service)
):
    """
    Get current ATS connection status
    
    Response:
    {
        'connected': true,
        'provider': 'bullhorn',
        'last_sync': '2024-01-15T10:30:00Z',
        'next_sync': '2024-01-15T16:30:00Z',
        'synced_jobs': 42,
        'synced_candidates': 18,
        'pending_syncs': 3
    }
    """
    try:
        configs = await db.ats_configurations.list(
            org_id=current_user.org_id
        )
        
        statuses = []
        
        for config in configs:
            jobs_count = await db.ats_synced_jobs.count(
                org_id=current_user.org_id,
                ats_config_id=config['id'],
                is_active=True
            )
            
            candidates_count = await db.candidate_ats_mappings.count(
                org_id=current_user.org_id,
                ats_config_id=config['id'],
                is_synced=True
            )
            
            pending_count = await db.candidate_ats_mappings.count(
                org_id=current_user.org_id,
                ats_config_id=config['id'],
                requires_resync=True
            )
            
            statuses.append({
                'id': config['id'],
                'provider': config['ats_provider'],
                'is_connected': config['is_connected'],
                'last_sync': config['last_sync_at'],
                'next_sync': config['next_sync_at'],
                'synced_jobs': jobs_count,
                'synced_candidates': candidates_count,
                'pending_syncs': pending_count
            })
        
        return {
            'statuses': statuses,
            'count': len(statuses)
        }
    
    except Exception as e:
        logger.error(f"Failed to get ATS status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get status"
        )


@router.get("/sync-logs")
async def get_sync_logs(
    current_user = Depends(get_current_user),
    db = Depends(get_db_service),
    skip: int = 0,
    limit: int = 100
):
    """
    Get ATS sync operation logs
    
    Useful for debugging sync issues and monitoring sync health.
    """
    try:
        logs = await db.ats_sync_logs.list(
            org_id=current_user.org_id,
            skip=skip,
            limit=limit,
            order_by='-created_at'
        )
        
        total = await db.ats_sync_logs.count(
            org_id=current_user.org_id
        )
        
        return {
            'items': logs,
            'total': total,
            'skip': skip,
            'limit': limit
        }
    
    except Exception as e:
        logger.error(f"Failed to get sync logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch logs"
        )


# ============================================================================
# Webhook Endpoint
# ============================================================================

@router.post("/webhook")
async def handle_ats_webhook(
    request: Request,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Webhook endpoint for ATS events
    
    Called by Merge.dev when:
    - New candidate applied
    - Candidate info updated
    - Application stage changed
    - Job closed/archived
    
    Authentication:
    - Webhook signature verification (HMAC)
    - Org isolation via auth header
    
    This endpoint accepts POST requests from Merge.dev
    """
    try:
        # Get webhook payload
        body = await request.json()
        
        # Get signature from headers
        webhook_signature = request.headers.get('X-Webhook-Signature', '')
        
        # Extract org_id from webhook data
        org_id = body.get('organization_id') or current_user.org_id
        ats_provider = body.get('integration', {}).get('provider')
        
        # Find config
        config = await db.ats_configurations.get_by(
            org_id=org_id,
            ats_provider=ats_provider
        )
        
        if not config:
            logger.warning(f"Webhook received for unknown ATS config")
            return {'status': 'ok'}  # Don't fail webhook validation
        
        # Process webhook
        success = await ats_service.process_webhook_event(
            org_id=org_id,
            ats_config_id=config[0]['id'],
            event_payload=body,
            webhook_signature=webhook_signature
        )
        
        if success:
            logger.info(f"Webhook processed: {body.get('type')}")
        
        return {'status': 'ok'}
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        # Always return 200 to prevent webhook retries on our end
        return {'status': 'error', 'error': str(e)}


# ============================================================================
# Batch Sync Endpoint
# ============================================================================

@router.post("/sync/pending-candidates")
async def sync_pending_candidates(
    ats_config_id: str,
    current_user = Depends(get_current_user),
    ats_service = Depends(get_ats_service),
    db = Depends(get_db_service)
):
    """
    Batch sync candidates with pending changes
    
    Called periodically to sync candidates that need updates.
    """
    try:
        config = await db.ats_configurations.get(ats_config_id)
        
        if not config or config['org_id'] != current_user.org_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ATS configuration not found"
            )
        
        synced_count = await ats_service.sync_pending_candidates(
            org_id=current_user.org_id,
            ats_config_id=ats_config_id
        )
        
        return {
            'status': 'success',
            'synced_count': synced_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch sync failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch sync failed"
        )
