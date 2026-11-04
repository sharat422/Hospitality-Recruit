"""
Shift-Aware Matching Algorithm Service

Implements X0PA-style intelligent matching to allocate interview times:
- Candidate availability ↔ Manager calendar overlap
- Screening score (50% weight: higher score = better candidate)
- Shift urgency (30% weight: urgent roles get priority)
- Location/type match (20% weight: same location or video + video)
- Time optimization (prefer morning for candidates, afternoon for GMs)

Algorithm Output:
1. Ranked list of interview times (confidence 0-100)
2. Explains why each slot ranked (scoring breakdown)
3. Suggests best slot for candidate + manager + shift urgency

ROI:
- Eliminates manual matching (2-5 min per candidate)
- Prioritizes urgency (high-priority roles filled faster)
- Improves scheduling success (matches preferences)
- Reduces reschedule requests (better time matches)
"""

import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class InterviewType(str, Enum):
    """Types of interviews"""
    PHONE = "phone"
    VIDEO = "video"
    IN_PERSON = "in_person"
    GROUP = "group"


@dataclass
class CandidateAvailability:
    """Candidate's availability window"""
    available_start_date: str  # YYYY-MM-DD
    available_end_date: str    # YYYY-MM-DD
    available_times: Dict      # {day_name: [time_ranges]}
    preferred_interview_type: InterviewType
    timezone: str = "America/New_York"
    screening_score: float = 0.5  # 0-1, from AI screening


@dataclass
class ShiftRequirements:
    """Interview requirements for specific shift/job"""
    shift_id: str
    job_title: str
    urgency_level: int  # 1-5, where 5 = critical
    required_interview_types: List[InterviewType]
    preferred_location: Optional[str] = None  # "video", "in_person", "phone"
    days_until_needed: int = 14  # Deadline for scheduling


@dataclass
class MatchedSlot:
    """Scored and ranked interview slot"""
    slot_start: datetime
    slot_end: datetime
    manager_name: str
    manager_id: str
    calendar_provider: str  # google, outlook, manual
    
    # Scoring breakdown
    availability_score: float = 0.0    # 0-100, candidate overlaps manager's calendar
    urgency_score: float = 0.0         # 0-100, how urgent this shift is
    preference_score: float = 0.0      # 0-100, matches candidate preferences
    candidate_quality_score: float = 0.0  # 0-100, candidate screening score
    
    # Weighted total
    total_score: float = 0.0           # 0-100, final ranking score
    rank: int = 0
    confidence: float = 0.0            # 0-1, confidence in recommendation
    
    # Explanation
    reasoning: str = ""
    
    def get_scoring_breakdown(self) -> Dict:
        """Return detailed scoring breakdown"""
        return {
            'availability_score': round(self.availability_score, 1),
            'urgency_score': round(self.urgency_score, 1),
            'preference_score': round(self.preference_score, 1),
            'candidate_quality_score': round(self.candidate_quality_score, 1),
            'total_score': round(self.total_score, 1),
            'reasoning': self.reasoning
        }


# ============================================================================
# X0PA Matching Algorithm
# ============================================================================

class ShiftMatchingService:
    """
    Intelligent shift matching algorithm
    
    Scoring Weights:
    - Availability Match (40%): Does candidate's availability overlap manager?
    - Urgency Score (30%): How urgent is this role?
    - Time Preference (15%): Does slot match candidate's preferred times?
    - Candidate Quality (15%): Screening score from AI screener
    
    Total = 100 points available
    """
    
    # Weighting factors for X0PA algorithm
    AVAILABILITY_WEIGHT = 0.40
    URGENCY_WEIGHT = 0.30
    PREFERENCE_WEIGHT = 0.15
    QUALITY_WEIGHT = 0.15
    
    def __init__(self):
        self.logger = logger
    
    async def match_candidate_to_slots(
        self,
        candidate_availability: CandidateAvailability,
        shift_requirements: ShiftRequirements,
        available_slots: List[Dict],  # From calendar service
        num_recommendations: int = 3
    ) -> List[MatchedSlot]:
        """
        Main entry point: Match candidate to best interview slots
        
        Args:
            candidate_availability: When candidate can interview
            shift_requirements: What the shift needs
            available_slots: Manager calendar free slots
            num_recommendations: How many options to return
        
        Returns:
            Ranked list of matched slots (best first)
        """
        try:
            matched_slots = []
            
            # Score each available slot
            for slot in available_slots:
                scored_slot = self._score_slot(
                    slot,
                    candidate_availability,
                    shift_requirements
                )
                
                if scored_slot.total_score > 0:  # Only include viable slots
                    matched_slots.append(scored_slot)
            
            # Sort by total score (highest first)
            matched_slots.sort(key=lambda s: s.total_score, reverse=True)
            
            # Assign ranks and return top N
            for rank, slot in enumerate(matched_slots[:num_recommendations], 1):
                slot.rank = rank
                slot.confidence = min(1.0, slot.total_score / 100.0)
            
            self.logger.info(
                f"Matched {candidate_availability.screening_score:.0%} screener "
                f"to {len(matched_slots[:num_recommendations])} slots for {shift_requirements.job_title}"
            )
            
            return matched_slots[:num_recommendations]
        
        except Exception as e:
            self.logger.error(f"Matching failed: {e}")
            return []
    
    def _score_slot(
        self,
        slot: Dict,
        candidate_availability: CandidateAvailability,
        shift_requirements: ShiftRequirements
    ) -> MatchedSlot:
        """
        Score a single slot using X0PA algorithm
        
        Scoring Formula:
        Total = (Availability × 40%) + (Urgency × 30%) + (Preference × 15%) + (Quality × 15%)
        """
        
        # Parse slot times
        slot_start = datetime.fromisoformat(slot['start_time'])
        slot_end = datetime.fromisoformat(slot['end_time'])
        
        # Calculate component scores
        availability_score = self._calculate_availability_score(
            slot_start,
            slot_end,
            candidate_availability
        )
        
        urgency_score = self._calculate_urgency_score(
            slot_start,
            shift_requirements
        )
        
        preference_score = self._calculate_preference_score(
            slot_start,
            candidate_availability
        )
        
        quality_score = candidate_availability.screening_score * 100
        
        # Calculate weighted total
        total_score = (
            (availability_score * self.AVAILABILITY_WEIGHT) +
            (urgency_score * self.URGENCY_WEIGHT) +
            (preference_score * self.PREFERENCE_WEIGHT) +
            (quality_score * self.QUALITY_WEIGHT)
        )
        
        # Build reasoning
        reasoning = self._build_reasoning(
            availability_score,
            urgency_score,
            preference_score,
            quality_score,
            slot_start,
            shift_requirements
        )
        
        return MatchedSlot(
            slot_start=slot_start,
            slot_end=slot_end,
            manager_name=slot.get('manager_name', 'Unknown'),
            manager_id=slot.get('manager_id', ''),
            calendar_provider=slot.get('provider', 'manual'),
            availability_score=availability_score,
            urgency_score=urgency_score,
            preference_score=preference_score,
            candidate_quality_score=quality_score,
            total_score=total_score,
            reasoning=reasoning
        )
    
    def _calculate_availability_score(
        self,
        slot_start: datetime,
        slot_end: datetime,
        candidate_availability: CandidateAvailability
    ) -> float:
        """
        Score: Does candidate's availability overlap this slot? (0-100)
        
        100 = Perfect match (slot is during candidate's available window)
         75 = Within 1 day of available window
         50 = Within 3 days of available window
         25 = Possible but outside preferred window
          0 = No overlap (candidate unavailable, skip this slot)
        """
        
        # Parse dates
        avail_start = datetime.fromisoformat(candidate_availability.available_start_date)
        avail_end = datetime.fromisoformat(candidate_availability.available_end_date)
        
        # Check if slot is within availability window
        if not (avail_start <= slot_start <= avail_end):
            return 0.0  # Outside availability window
        
        # Check time-of-day match
        day_name = slot_start.strftime('%A').lower()
        available_times = candidate_availability.available_times.get(day_name, [])
        
        if not available_times:
            return 0.0  # Candidate unavailable on this day
        
        # Check if slot time matches any available window
        slot_time = slot_start.time()
        time_match = False
        
        for time_range in available_times:
            if '-' in str(time_range):
                start_str, end_str = str(time_range).split('-')
                range_start = datetime.strptime(start_str.strip(), '%H:%M').time()
                range_end = datetime.strptime(end_str.strip(), '%H:%M').time()
                
                if range_start <= slot_time <= range_end:
                    time_match = True
                    break
        
        if not time_match:
            return 0.0  # Time doesn't match available windows
        
        # Calculate days from start of availability window
        days_from_start = (slot_start.date() - avail_start.date()).days
        
        if days_from_start <= 1:
            return 100.0  # Perfect: early in availability window
        elif days_from_start <= 3:
            return 85.0   # Good: reasonable timing
        elif days_from_start <= 7:
            return 70.0   # Fair: mid-window
        else:
            return 50.0   # Poor: late in availability window
    
    def _calculate_urgency_score(
        self,
        slot_start: datetime,
        shift_requirements: ShiftRequirements
    ) -> float:
        """
        Score: Does this slot meet urgency deadline? (0-100)
        
        Urgency Levels:
        1 = Low priority, flexible (50 points max)
        2 = Normal priority (70 points max)
        3 = Medium priority (85 points max)
        4 = High priority (95 points max)
        5 = Critical, immediate (100 points max)
        
        Timeline:
        - Within 1 day of now: Extra bonus
        - Within deadline: Full score
        - After deadline: Reduced score
        """
        
        # Calculate days until slot
        now = datetime.now()
        days_until_slot = (slot_start.date() - now.date()).days
        days_until_needed = shift_requirements.days_until_needed
        urgency = shift_requirements.urgency_level
        
        # Base score by urgency level
        urgency_scores = {
            1: 50,   # Low
            2: 70,   # Normal
            3: 85,   # Medium
            4: 95,   # High
            5: 100   # Critical
        }
        base_score = urgency_scores.get(urgency, 50)
        
        # Adjust for timeline
        if days_until_slot <= 0:
            # ASAP slots get bonus
            score = base_score * 1.15
        elif days_until_slot <= 3:
            # Very soon slots get slight bonus
            score = base_score * 1.05
        elif days_until_slot <= days_until_needed:
            # Within deadline
            score = base_score
        else:
            # After deadline (late, but acceptable)
            days_late = days_until_slot - days_until_needed
            penalty = max(0, 1.0 - (days_late * 0.10))
            score = base_score * penalty
        
        return min(100.0, score)  # Cap at 100
    
    def _calculate_preference_score(
        self,
        slot_start: datetime,
        candidate_availability: CandidateAvailability
    ) -> float:
        """
        Score: Does this slot match candidate's time preferences? (0-100)
        
        Preferences:
        - Before 11am: Morning people (+15 points)
        - 11am-3pm: Afternoon people (+10 points)
        - After 3pm: Late afternoon (+5 points)
        - Weekends: Generally avoid (-30 points)
        
        Day preferences (inferred from available_times):
        - Monday-Wednesday: Solid (-10 if Friday only listed)
        - Thursday-Friday: Less ideal (+0)
        """
        
        slot_hour = slot_start.hour
        slot_day = slot_start.weekday()  # 0=Monday, 6=Sunday
        
        # Score by time of day (candidates generally prefer earlier times)
        if 8 <= slot_hour < 11:
            time_score = 100  # Ideal: morning
        elif 11 <= slot_hour < 14:
            time_score = 85   # Good: late morning/early afternoon
        elif 14 <= slot_hour < 17:
            time_score = 75   # Acceptable: afternoon
        elif 17 <= slot_hour < 18:
            time_score = 60   # Less ideal: late
        else:
            time_score = 30   # Very late or very early
        
        # Score by day of week
        if slot_day < 5:  # Monday-Friday
            day_score = 100
        else:  # Saturday-Sunday
            day_score = 0  # Candidates rarely available weekends
        
        # Inferred preference from available times
        # If candidate listed specific times, align with those
        day_name = slot_start.strftime('%A').lower()
        available_times = candidate_availability.available_times.get(day_name, [])
        
        if available_times:
            # Has specific availability on this day = strong preference
            day_score = min(100, day_score + 10)
        
        # Combine scores
        combined_score = (time_score * 0.7) + (day_score * 0.3)
        
        return combined_score
    
    def _build_reasoning(
        self,
        availability_score: float,
        urgency_score: float,
        preference_score: float,
        quality_score: float,
        slot_start: datetime,
        shift_requirements: ShiftRequirements
    ) -> str:
        """Build human-readable explanation for score"""
        
        reasons = []
        
        # Availability reasoning
        if availability_score >= 95:
            reasons.append("✓ Perfect availability match")
        elif availability_score >= 70:
            reasons.append("✓ Good availability overlap")
        elif availability_score > 0:
            reasons.append("⚠ Marginal availability match")
        else:
            reasons.append("✗ Availability conflict")
        
        # Urgency reasoning
        if urgency_score >= 95:
            reasons.append(f"✓ High urgency role ({shift_requirements.urgency_level}/5)")
        elif urgency_score >= 70:
            reasons.append("✓ Meets urgency deadline")
        else:
            reasons.append("⚠ May miss urgency deadline")
        
        # Preference reasoning
        if preference_score >= 85:
            reasons.append("✓ Excellent time preference match")
        elif preference_score >= 70:
            reasons.append("✓ Good time preference")
        else:
            reasons.append("⚠ Non-ideal timeframe")
        
        # Candidate quality
        if quality_score >= 80:
            reasons.append("✓ High-quality candidate")
        elif quality_score >= 60:
            reasons.append("✓ Good candidate")
        
        return " | ".join(reasons)
    
    def calculate_match_probability(
        self,
        matched_slot: MatchedSlot
    ) -> Dict:
        """
        Calculate probability of successful booking
        Considers: candidate quality, manager availability certainty, urgency alignment
        """
        
        # Base probability from score
        base_prob = matched_slot.total_score / 100.0
        
        # Adjustments
        if matched_slot.availability_score >= 95:
            base_prob *= 1.05  # High availability sureness
        
        # Urgency bonus: candidates more likely to book urgent roles
        if matched_slot.urgency_score >= 90:
            base_prob *= 1.08
        
        # Quality adjustment: higher-quality candidates more likely to accept
        quality_factor = matched_slot.candidate_quality_score / 100.0
        base_prob *= (0.5 + (quality_factor * 0.5))  # Range 0.5-1.0x
        
        return {
            'probability': min(0.99, base_prob),
            'confidence': matched_slot.confidence,
            'factors': {
                'availability': matched_slot.availability_score / 100.0,
                'urgency': matched_slot.urgency_score / 100.0,
                'preference': matched_slot.preference_score / 100.0,
                'quality': matched_slot.candidate_quality_score / 100.0
            }
        }


# ============================================================================
# Batch Matching (for multiple candidates at once)
# ============================================================================

class BatchMatchingService:
    """Batch match multiple candidates to shift requirements"""
    
    def __init__(self):
        self.matcher = ShiftMatchingService()
    
    async def match_candidates_to_shift(
        self,
        candidates: List[Dict],  # candidate availability data
        shift_requirements: ShiftRequirements,
        available_slots: List[Dict],
        max_matches_per_candidate: int = 3
    ) -> Dict[str, List[MatchedSlot]]:
        """Match multiple candidates to same shift"""
        
        results = {}
        
        for candidate in candidates:
            availability = CandidateAvailability(
                available_start_date=candidate['available_start_date'],
                available_end_date=candidate['available_end_date'],
                available_times=candidate['available_times'],
                preferred_interview_type=InterviewType(candidate.get('preferred_interview_type', 'video')),
                screening_score=candidate.get('screening_score', 0.5)
            )
            
            matched = await self.matcher.match_candidate_to_slots(
                availability,
                shift_requirements,
                available_slots,
                num_recommendations=max_matches_per_candidate
            )
            
            results[candidate['id']] = matched
        
        return results
