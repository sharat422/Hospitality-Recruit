import requests
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'zh', 'ar', 'pt', 'de', 'it', 'ja', 'ko', 'pl', 'ro']


def translate_text(text: str, target_lang: str) -> str:
    """Translate text using DeepL API or fall back to Claude."""
    if not text or target_lang == 'en':
        return text

    # Try DeepL if configured
    deepl_key = getattr(settings, 'DEEPL_API_KEY', None)
    if deepl_key:
        try:
            resp = requests.post(
                'https://api-free.deepl.com/v2/translate',
                data={'auth_key': deepl_key, 'text': text, 'target_lang': target_lang.upper()},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()['translations'][0]['text']
        except Exception as e:
            logger.warning(f"DeepL failed: {e}")

    # Fallback: use Claude
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"Translate this text to {target_lang}. Return ONLY the translation, nothing else:\n\n{text}"
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return text
