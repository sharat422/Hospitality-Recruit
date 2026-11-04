"""
NPS Service — candidate experience scoring and feedback theme clustering.
Pain Point #5: High turnover = poor candidate experience → NPS tracks this.
"""

import anthropic
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def calculate_nps(scores: list) -> float:
    """Calculate Net Promoter Score from list of 0-10 integer scores."""
    if not scores:
        return 0.0
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return round(((promoters - detractors) / len(scores)) * 100, 1)


async def cluster_feedback_themes(feedback_list: list, stage: str) -> list:
    """Use Claude to identify top 5 recurring themes in candidate feedback."""
    if not feedback_list:
        return []
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        feedback_text = "\n".join(f"- {f}" for f in feedback_list[:50])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": (
                    f"Here are {len(feedback_list)} pieces of candidate feedback about their "
                    f"{stage.replace('_', ' ').lower()} experience at a hospitality company:\n"
                    f"{feedback_text}\n"
                    "Identify the top 5 recurring themes. Return ONLY a valid JSON array:\n"
                    '[{"theme": "string", "count": number, "sentiment": "positive|negative|neutral", '
                    '"exampleQuotes": ["string"]}]'
                ),
            }],
        )
        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"NPS theme clustering error: {e}")
        return []
