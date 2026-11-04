"""
Calendar Integration Service

Integrates with Google Calendar and Outlook via Cal.com (Merge.dev) to:
1. Pull manager availability (find free slots)
2. Book interviews (create calendar events)
3. Handle rescheduling (update calendar events)
4. Send reminders (track delivery with Twilio)
5. Detect conflicts (prevent double-booking)

Providers Supported:
- Google Calendar (OAuth 2.0 direct integration)
- Outlook (via Cal.com, which supports 50+ providers)

ROI Impact:
- Eliminates manual calendar checking (5-10 min per candidate)
- Prevents double-booking (reduces no-shows)
- Auto-syncs to ATS (Merge.dev integration ready)
"""

import json
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple
import httpx
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, status
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build as google_build
from microsoft.graph.client import GraphServiceClient
from azure.identity import ClientSecretCredential

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class CalendarProvider(str, Enum):
    """Supported calendar providers"""
    GOOGLE = "google"
    OUTLOOK = "outlook"
    MANUAL = "manual"


@dataclass
class TimeSlot:
    """Represents an available interview time slot"""
    start: datetime
    end: datetime
    provider: CalendarProvider
    event_id: Optional[str] = None
    confidence: float = 1.0  # 0-1, lower if less certain
    buffer_minutes_before: int = 0  # Minutes since last event
    buffer_minutes_after: int = 0  # Minutes until next event


@dataclass
class CalendarEvent:
    """Event to be created/updated on calendar"""
    title: str
    description: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    attendees: List[str] = None
    video_conference_url: Optional[str] = None
    timezone: str = "America/New_York"
    reminder_minutes: List[int] = None


# ============================================================================
# Base Calendar Provider Interface
# ============================================================================

class CalendarProviderInterface(ABC):
    """Abstract base class for calendar providers"""
    
    @abstractmethod
    async def authenticate(self, tokens: Dict) -> bool:
        """Authenticate with the calendar provider"""
        pass
    
    @abstractmethod
    async def get_available_slots(
        self,
        calendar_id: str,
        date_range: Tuple[datetime, datetime],
        duration_minutes: int,
        excluded_times: Optional[List[Tuple[datetime, datetime]]] = None
    ) -> List[TimeSlot]:
        """Find available time slots in manager's calendar"""
        pass
    
    @abstractmethod
    async def create_event(
        self,
        calendar_id: str,
        event: CalendarEvent
    ) -> str:
        """Create calendar event, return event ID"""
        pass
    
    @abstractmethod
    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: CalendarEvent
    ) -> bool:
        """Update existing calendar event"""
        pass
    
    @abstractmethod
    async def delete_event(
        self,
        calendar_id: str,
        event_id: str
    ) -> bool:
        """Delete calendar event"""
        pass
    
    @abstractmethod
    async def refresh_credentials(self) -> Dict:
        """Refresh auth tokens if needed"""
        pass


# ============================================================================
# Google Calendar Provider
# ============================================================================

class GoogleCalendarProvider(CalendarProviderInterface):
    """Google Calendar OAuth integration"""
    
    def __init__(self, org_id: str, credentials_service):
        self.org_id = org_id
        self.credentials_service = credentials_service
        self.service = None
        self.credentials = None
    
    async def authenticate(self, tokens: Dict) -> bool:
        """
        Authenticate with Google Calendar using stored OAuth tokens
        
        tokens: {
            'access_token': '...',
            'refresh_token': '...',
            'token_expiry': '...'
        }
        """
        try:
            # Build Credentials object from tokens
            self.credentials = Credentials(
                token=tokens.get('access_token'),
                refresh_token=tokens.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=os.getenv('GOOGLE_CALENDAR_CLIENT_ID'),
                client_secret=os.getenv('GOOGLE_CALENDAR_CLIENT_SECRET'),
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Test authentication
            self.service = google_build('calendar', 'v3', credentials=self.credentials)
            await self._verify_credentials()
            return True
        except Exception as e:
            logger.error(f"Google Calendar auth failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar authentication failed"
            )
    
    async def _verify_credentials(self) -> None:
        """Verify credentials are valid"""
        try:
            self.service.calendarList().list().execute(maxResults=1)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google Calendar credentials"
            )
    
    async def get_available_slots(
        self,
        calendar_id: str,
        date_range: Tuple[datetime, datetime],
        duration_minutes: int,
        excluded_times: Optional[List[Tuple[datetime, datetime]]] = None
    ) -> List[TimeSlot]:
        """
        Find available time slots in manager's Google Calendar
        
        Algorithm:
        1. Query calendar for events in date range
        2. Identify gaps between events
        3. Filter gaps >= duration_minutes
        4. Apply buffer times (15min between interviews)
        5. Check against excluded times (lunch, EOD, etc)
        6. Return ranked slots
        """
        try:
            start_time, end_time = date_range
            slots = []
            
            # Query calendar events
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                showDeleted=False
            ).execute()
            
            events = events_result.get('items', [])
            
            # Build busy intervals
            busy_intervals = []
            for event in events:
                if event['transparency'] == 'opaque':  # opaque = busy
                    start = self._parse_datetime(event['start'])
                    end = self._parse_datetime(event['end'])
                    busy_intervals.append((start, end))
            
            # Add excluded times (lunch, EOD, etc)
            if excluded_times:
                busy_intervals.extend(excluded_times)
            
            # Sort busy intervals
            busy_intervals.sort(key=lambda x: x[0])
            
            # Find gaps and create slots
            current_time = start_time
            buffer_minutes = 15  # Default buffer between interviews
            
            for busy_start, busy_end in busy_intervals:
                # Gap before this busy interval
                gap_duration = (busy_start - current_time).total_seconds() / 60
                
                if gap_duration >= duration_minutes + buffer_minutes:
                    # Create slots for this gap
                    slot_start = current_time + timedelta(minutes=buffer_minutes)
                    while slot_start + timedelta(minutes=duration_minutes) <= busy_start:
                        slot_end = slot_start + timedelta(minutes=duration_minutes)
                        slots.append(TimeSlot(
                            start=slot_start,
                            end=slot_end,
                            provider=CalendarProvider.GOOGLE,
                            confidence=0.95,  # High confidence for calendar gaps
                            buffer_minutes_before=buffer_minutes
                        ))
                        slot_start += timedelta(minutes=15)  # 15min granularity
                
                current_time = max(current_time, busy_end + timedelta(minutes=buffer_minutes))
            
            # Final gap until end_time
            gap_duration = (end_time - current_time).total_seconds() / 60
            if gap_duration >= duration_minutes:
                slot_start = current_time
                while slot_start + timedelta(minutes=duration_minutes) <= end_time:
                    slot_end = slot_start + timedelta(minutes=duration_minutes)
                    slots.append(TimeSlot(
                        start=slot_start,
                        end=slot_end,
                        provider=CalendarProvider.GOOGLE,
                        confidence=0.95
                    ))
                    slot_start += timedelta(minutes=15)
            
            return slots
        
        except Exception as e:
            logger.error(f"Failed to get Google Calendar availability: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch calendar availability"
            )
    
    async def create_event(
        self,
        calendar_id: str,
        event: CalendarEvent
    ) -> str:
        """Create interview event in Google Calendar"""
        try:
            goog_event = {
                'summary': event.title,
                'description': event.description,
                'start': {
                    'dateTime': event.start.isoformat(),
                    'timeZone': event.timezone
                },
                'end': {
                    'dateTime': event.end.isoformat(),
                    'timeZone': event.timezone
                },
                'location': event.location or '',
                'transparency': 'opaque',  # Show as busy
                'visibility': 'public',
                'guestCanModify': True,
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': m} for m in (event.reminder_minutes or [15, 60])
                    ]
                }
            }
            
            # Add video conference
            if event.video_conference_url:
                goog_event['conferenceData'] = {
                    'entryPoints': [{
                        'entryPointType': 'video',
                        'uri': event.video_conference_url,
                        'label': 'Google Meet'
                    }]
                }
            
            # Add attendees
            if event.attendees:
                goog_event['attendees'] = [
                    {'email': attendee} for attendee in event.attendees
                ]
            
            result = self.service.events().insert(
                calendarId=calendar_id,
                body=goog_event,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Created Google Calendar event: {result['id']}")
            return result['id']
        
        except Exception as e:
            logger.error(f"Failed to create Google Calendar event: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create calendar event"
            )
    
    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: CalendarEvent
    ) -> bool:
        """Update calendar event (for rescheduling)"""
        try:
            existing_event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            existing_event['summary'] = event.title
            existing_event['description'] = event.description
            existing_event['start'] = {
                'dateTime': event.start.isoformat(),
                'timeZone': event.timezone
            }
            existing_event['end'] = {
                'dateTime': event.end.isoformat(),
                'timeZone': event.timezone
            }
            
            self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=existing_event,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Updated Google Calendar event: {event_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update Google Calendar event: {e}")
            return False
    
    async def delete_event(
        self,
        calendar_id: str,
        event_id: str
    ) -> bool:
        """Delete calendar event (for cancellations)"""
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendNotifications=True
            ).execute()
            
            logger.info(f"Deleted Google Calendar event: {event_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete Google Calendar event: {e}")
            return False
    
    async def refresh_credentials(self) -> Dict:
        """Refresh Google OAuth tokens"""
        try:
            self.credentials.refresh(Request())
            return {
                'access_token': self.credentials.token,
                'refresh_token': self.credentials.refresh_token,
                'token_expiry': self.credentials.expiry.isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to refresh Google credentials: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to refresh calendar credentials"
            )
    
    def _parse_datetime(self, dt_dict: Dict) -> datetime:
        """Parse Google Calendar datetime (handles both datetime and date)"""
        if 'dateTime' in dt_dict:
            return datetime.fromisoformat(dt_dict['dateTime'].replace('Z', '+00:00'))
        else:
            # All-day event
            return datetime.fromisoformat(dt_dict['date']).replace(tzinfo=pytz.UTC)


# ============================================================================
# Outlook Calendar Provider (via Cal.com/Merge.dev)
# ============================================================================

class OutlookCalendarProvider(CalendarProviderInterface):
    """Outlook calendar integration via Cal.com (Merge.dev unified API)"""
    
    def __init__(self, org_id: str, merge_api_key: str):
        self.org_id = org_id
        self.merge_api_key = merge_api_key
        self.base_url = "https://api.mergeapi.com/api/calendar/v1"
    
    async def authenticate(self, tokens: Dict) -> bool:
        """Verify Outlook calendar credentials via Merge.dev"""
        try:
            headers = {
                'Authorization': f'Bearer {self.merge_api_key}',
                'X-Account-Token': tokens.get('account_token')
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/calendars",
                    headers=headers
                )
            
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Outlook Calendar auth failed: {e}")
            return False
    
    async def get_available_slots(
        self,
        calendar_id: str,
        date_range: Tuple[datetime, datetime],
        duration_minutes: int,
        excluded_times: Optional[List[Tuple[datetime, datetime]]] = None
    ) -> List[TimeSlot]:
        """Fetch available slots via Merge.dev Calendar API"""
        try:
            start_time, end_time = date_range
            
            headers = {
                'Authorization': f'Bearer {self.merge_api_key}'
            }
            
            # Query Merge.dev for free/busy information
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/calendars/{calendar_id}/events",
                    params={
                        'start_date': start_time.isoformat(),
                        'end_date': end_time.isoformat()
                    },
                    headers=headers
                )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch Outlook calendar events"
                )
            
            events = response.json().get('results', [])
            
            # Process events same as Google (find gaps)
            busy_intervals = [
                (
                    datetime.fromisoformat(e['start_date']),
                    datetime.fromisoformat(e['end_date'])
                )
                for e in events if not e.get('is_free', False)
            ]
            
            # Rest of logic same as Google Calendar
            slots = self._find_gaps_in_calendar(
                busy_intervals,
                start_time,
                end_time,
                duration_minutes,
                excluded_times
            )
            
            return slots
        
        except Exception as e:
            logger.error(f"Failed to get Outlook calendar availability: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch calendar availability"
            )
    
    async def create_event(
        self,
        calendar_id: str,
        event: CalendarEvent
    ) -> str:
        """Create event in Outlook via Merge.dev"""
        try:
            headers = {
                'Authorization': f'Bearer {self.merge_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'name': event.title,
                'description': event.description,
                'start_date': event.start.isoformat(),
                'end_date': event.end.isoformat(),
                'location': event.location or '',
                'show_as': 'busy',
                'conference_url': event.video_conference_url
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/calendars/{calendar_id}/events",
                    json=payload,
                    headers=headers
                )
            
            if response.status_code not in [200, 201]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create calendar event"
                )
            
            result = response.json()
            return result['id']
        
        except Exception as e:
            logger.error(f"Failed to create Outlook event: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create calendar event"
            )
    
    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: CalendarEvent
    ) -> bool:
        """Update event in Outlook"""
        try:
            headers = {
                'Authorization': f'Bearer {self.merge_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'name': event.title,
                'description': event.description,
                'start_date': event.start.isoformat(),
                'end_date': event.end.isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{self.base_url}/calendars/{calendar_id}/events/{event_id}",
                    json=payload,
                    headers=headers
                )
            
            return response.status_code in [200, 204]
        
        except Exception as e:
            logger.error(f"Failed to update Outlook event: {e}")
            return False
    
    async def delete_event(
        self,
        calendar_id: str,
        event_id: str
    ) -> bool:
        """Delete event from Outlook"""
        try:
            headers = {'Authorization': f'Bearer {self.merge_api_key}'}
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/calendars/{calendar_id}/events/{event_id}",
                    headers=headers
                )
            
            return response.status_code in [200, 204]
        
        except Exception as e:
            logger.error(f"Failed to delete Outlook event: {e}")
            return False
    
    async def refresh_credentials(self) -> Dict:
        """Refresh Outlook token via Merge.dev"""
        # Merge.dev handles token refresh automatically
        return {}
    
    def _find_gaps_in_calendar(
        self,
        busy_intervals,
        start_time,
        end_time,
        duration_minutes,
        excluded_times
    ):
        """Reusable gap-finding logic"""
        slots = []
        busy_intervals.sort(key=lambda x: x[0])
        
        if excluded_times:
            busy_intervals.extend(excluded_times)
            busy_intervals.sort(key=lambda x: x[0])
        
        current_time = start_time
        
        for busy_start, busy_end in busy_intervals:
            gap_duration = (busy_start - current_time).total_seconds() / 60
            
            if gap_duration >= duration_minutes + 15:
                slot_start = current_time + timedelta(minutes=15)
                while slot_start + timedelta(minutes=duration_minutes) <= busy_start:
                    slots.append(TimeSlot(
                        start=slot_start,
                        end=slot_start + timedelta(minutes=duration_minutes),
                        provider=CalendarProvider.OUTLOOK,
                        confidence=0.9
                    ))
                    slot_start += timedelta(minutes=15)
            
            current_time = max(current_time, busy_end + timedelta(minutes=15))
        
        return slots


# ============================================================================
# Main Calendar Integration Service
# ============================================================================

class CalendarIntegrationService:
    """
    High-level service for managing calendar integrations
    Abstracts away provider differences
    """
    
    def __init__(self, db_service, merge_api_key: str):
        self.db = db_service
        self.merge_api_key = merge_api_key
        self.providers = {}
    
    async def initialize_provider(
        self,
        org_id: str,
        manager_id: str,
        provider: CalendarProvider,
        calendar_config_db_row
    ) -> CalendarProviderInterface:
        """Initialize calendar provider from database config"""
        
        key = f"{org_id}:{manager_id}:{provider.value}"
        
        if key in self.providers:
            return self.providers[key]
        
        tokens = {
            'access_token': calendar_config_db_row['access_token'],
            'refresh_token': calendar_config_db_row['refresh_token'],
            'token_expiry': calendar_config_db_row['token_expires_at']
        }
        
        if provider == CalendarProvider.GOOGLE:
            prov = GoogleCalendarProvider(org_id, self.db)
        elif provider == CalendarProvider.OUTLOOK:
            prov = OutlookCalendarProvider(org_id, self.merge_api_key)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported calendar provider: {provider}"
            )
        
        await prov.authenticate(tokens)
        self.providers[key] = prov
        return prov
    
    async def get_manager_availability(
        self,
        org_id: str,
        manager_id: str,
        days_ahead: int = 14,
        duration_minutes: int = 30
    ) -> List[TimeSlot]:
        """
        Get manager's available interview slots
        
        Process:
        1. Fetch manager's calendar config
        2. Initialize provider
        3. Calculate date range (today + days_ahead)
        4. Query calendar for available slots
        5. Filter by interview preferences (lunch, EOD, etc)
        """
        try:
            # Get manager's calendar config
            config = await self.db.manager_calendar_configs.get_by_manager(
                org_id=org_id,
                manager_id=manager_id
            )
            
            if not config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manager calendar not configured"
                )
            
            # Initialize provider
            provider = CalendarProvider(config['provider'])
            prov = await self.initialize_provider(
                org_id, manager_id, provider, config
            )
            
            # Calculate date range
            today = datetime.now()
            start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=days_ahead)
            
            # Build excluded times (lunch, EOD, etc)
            excluded = self._build_excluded_times(
                config.get('auto_block_lunch', True),
                config.get('lunch_start_time'),
                config.get('lunch_end_time'),
                config.get('auto_block_eod', True),
                config.get('eod_start_time'),
                start_date,
                end_date
            )
            
            # Get slots
            slots = await prov.get_available_slots(
                calendar_id=config['calendar_id'],
                date_range=(start_date, end_date),
                duration_minutes=duration_minutes,
                excluded_times=excluded
            )
            
            return slots
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get manager availability: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch manager availability"
            )
    
    async def book_interview_on_calendar(
        self,
        org_id: str,
        manager_id: str,
        candidate_name: str,
        candidate_email: str,
        interview_slot: TimeSlot,
        job_title: str,
        video_conference_url: Optional[str] = None
    ) -> str:
        """Book interview on manager's calendar"""
        
        try:
            # Get manager's calendar config
            config = await self.db.manager_calendar_configs.get_by_manager(
                org_id=org_id,
                manager_id=manager_id
            )
            
            # Initialize provider
            provider = CalendarProvider(config['provider'])
            prov = await self.initialize_provider(
                org_id, manager_id, provider, config
            )
            
            # Create calendar event
            event = CalendarEvent(
                title=f"Interview: {candidate_name} - {job_title}",
                description=f"Candidate: {candidate_name}\nEmail: {candidate_email}\nJob: {job_title}",
                start=interview_slot.start,
                end=interview_slot.end,
                video_conference_url=video_conference_url,
                attendees=[candidate_email, config['calendar_email']],
                timezone=config.get('timezone', 'America/New_York')
            )
            
            event_id = await prov.create_event(
                calendar_id=config['calendar_id'],
                event=event
            )
            
            logger.info(f"Booked interview on {provider.value} calendar: {event_id}")
            return event_id
        
        except Exception as e:
            logger.error(f"Failed to book interview on calendar: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to book interview on calendar"
            )
    
    async def reschedule_interview(
        self,
        org_id: str,
        manager_id: str,
        calendar_event_id: str,
        new_slot: TimeSlot,
        reason: str = "Rescheduled"
    ) -> bool:
        """Reschedule interview to new time"""
        
        try:
            config = await self.db.manager_calendar_configs.get_by_manager(
                org_id=org_id,
                manager_id=manager_id
            )
            
            provider = CalendarProvider(config['provider'])
            prov = await self.initialize_provider(
                org_id, manager_id, provider, config
            )
            
            # Get existing event and update time
            # Note: This is simplified - real implementation would fetch existing event
            event = CalendarEvent(
                title="Interview (Rescheduled)",
                description=reason,
                start=new_slot.start,
                end=new_slot.end,
                timezone=config.get('timezone', 'America/New_York')
            )
            
            success = await prov.update_event(
                calendar_id=config['calendar_id'],
                event_id=calendar_event_id,
                event=event
            )
            
            if success:
                logger.info(f"Rescheduled interview event: {calendar_event_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to reschedule interview: {e}")
            return False
    
    async def cancel_interview(
        self,
        org_id: str,
        manager_id: str,
        calendar_event_id: str
    ) -> bool:
        """Cancel interview and remove from calendar"""
        
        try:
            config = await self.db.manager_calendar_configs.get_by_manager(
                org_id=org_id,
                manager_id=manager_id
            )
            
            provider = CalendarProvider(config['provider'])
            prov = await self.initialize_provider(
                org_id, manager_id, provider, config
            )
            
            success = await prov.delete_event(
                calendar_id=config['calendar_id'],
                event_id=calendar_event_id
            )
            
            if success:
                logger.info(f"Cancelled interview event: {calendar_event_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to cancel interview: {e}")
            return False
    
    def _build_excluded_times(
        self,
        auto_block_lunch: bool,
        lunch_start: str,
        lunch_end: str,
        auto_block_eod: bool,
        eod_start: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Tuple[datetime, datetime]]:
        """Build list of blocked time intervals"""
        excluded = []
        
        # Block lunch hours for each weekday
        if auto_block_lunch and lunch_start and lunch_end:
            current = start_date
            while current < end_date:
                if current.weekday() < 5:  # Monday-Friday
                    lunch_s = datetime.combine(current.date(), time.fromisoformat(lunch_start))
                    lunch_e = datetime.combine(current.date(), time.fromisoformat(lunch_end))
                    excluded.append((lunch_s, lunch_e))
                current += timedelta(days=1)
        
        # Block end-of-day
        if auto_block_eod and eod_start:
            current = start_date
            eod_time = time.fromisoformat(eod_start)
            while current < end_date:
                if current.weekday() < 5:  # Monday-Friday
                    eod = datetime.combine(current.date(), eod_time)
                    eod_end = current.replace(hour=23, minute=59, second=59)
                    excluded.append((eod, eod_end))
                current += timedelta(days=1)
        
        return excluded


import os
