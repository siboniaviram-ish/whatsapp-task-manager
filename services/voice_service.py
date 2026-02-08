import json
import re
from datetime import datetime, date, timedelta
from config import Config


def transcribe_audio(audio_url):
    """Transcribe audio from a URL using OpenAI Whisper API.

    Falls back to a mock transcription when no API key is configured,
    making development and testing possible without external services.

    Args:
        audio_url: URL of the audio file to transcribe.

    Returns:
        Transcription string, or None on failure.
    """
    try:
        api_key = Config.OPENAI_API_KEY

        if not api_key:
            print("[Voice Service] OpenAI API key not configured. Returning mock transcription.")
            return (
                "This is a mock transcription. "
                "Configure OPENAI_API_KEY for real speech-to-text. "
                f"Audio URL: {audio_url}"
            )

        import requests

        # Download the audio file
        audio_response = requests.get(audio_url, timeout=30)
        if audio_response.status_code != 200:
            print(f"[Voice Service] Failed to download audio: HTTP {audio_response.status_code}")
            return None

        # Send to Whisper API
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": ("audio.ogg", audio_response.content, "audio/ogg")}
        data = {"model": "whisper-1"}

        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=60,
        )

        if response.status_code == 200:
            result = response.json()
            return result.get('text', '')
        else:
            print(f"[Voice Service] Whisper API error: {response.status_code} - {response.text}")
            return None

    except ImportError:
        print("[Voice Service] requests library not installed. Run: pip install requests")
        return None
    except Exception as e:
        print(f"[Voice Service] Transcription error: {e}")
        return None


def extract_task_from_transcript(transcript):
    """Extract task information from a voice transcript using basic keyword parsing.

    Looks for patterns indicating title, date references, and priority keywords.

    Args:
        transcript: The transcribed text string.

    Returns:
        Dict with keys: title, description, due_date, priority.
        Returns None on failure.
    """
    try:
        if not transcript or not transcript.strip():
            return None

        text = transcript.strip()
        result = {
            'title': '',
            'description': text,
            'due_date': None,
            'priority': 'medium',
        }

        # --- Extract priority ---
        priority_patterns = {
            'urgent': r'\b(urgent|urgently|asap|immediately|critical)\b',
            'high': r'\b(important|high priority|crucial|essential)\b',
            'low': r'\b(low priority|whenever|no rush|not urgent|eventually)\b',
        }
        for level, pattern in priority_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                result['priority'] = level
                break

        # --- Extract date keywords ---
        today = date.today()

        date_keywords = {
            r'\btoday\b': today,
            r'\btomorrow\b': today + timedelta(days=1),
            r'\bday after tomorrow\b': today + timedelta(days=2),
            r'\bnext week\b': today + timedelta(weeks=1),
            r'\bnext monday\b': _next_weekday(today, 0),
            r'\bnext tuesday\b': _next_weekday(today, 1),
            r'\bnext wednesday\b': _next_weekday(today, 2),
            r'\bnext thursday\b': _next_weekday(today, 3),
            r'\bnext friday\b': _next_weekday(today, 4),
            r'\bnext saturday\b': _next_weekday(today, 5),
            r'\bnext sunday\b': _next_weekday(today, 6),
        }

        for pattern, target_date in date_keywords.items():
            if re.search(pattern, text, re.IGNORECASE):
                result['due_date'] = target_date.isoformat()
                break

        # If no keyword match, try to find an explicit date pattern (YYYY-MM-DD or DD/MM/YYYY)
        if not result['due_date']:
            iso_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
            if iso_match:
                result['due_date'] = iso_match.group(1)
            else:
                slash_match = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
                if slash_match:
                    day = int(slash_match.group(1))
                    month = int(slash_match.group(2))
                    year = int(slash_match.group(3))
                    try:
                        parsed_date = date(year, month, day)
                        result['due_date'] = parsed_date.isoformat()
                    except ValueError:
                        pass

        # --- Extract title ---
        # Use the first sentence or first ~60 chars as the title
        # Remove common prefixes like "remind me to", "I need to", "create a task"
        title_text = text
        remove_prefixes = [
            r'^(remind me to|remind me|please remind me to)\s+',
            r'^(i need to|i have to|i want to|i should)\s+',
            r'^(create a task to|add a task to|add task)\s+',
            r'^(task|note|reminder)[:\s]+',
        ]
        for prefix in remove_prefixes:
            title_text = re.sub(prefix, '', title_text, flags=re.IGNORECASE)

        # Take first sentence or truncate
        sentence_end = re.search(r'[.!?\n]', title_text)
        if sentence_end:
            title_text = title_text[:sentence_end.start()]

        title_text = title_text.strip()
        if len(title_text) > 80:
            title_text = title_text[:77] + '...'

        result['title'] = title_text if title_text else text[:80]

        return result
    except Exception:
        return None


def _next_weekday(from_date, weekday):
    """Calculate the date of the next occurrence of a given weekday.

    Args:
        from_date: The starting date.
        weekday: Target weekday (0=Monday, 6=Sunday).

    Returns:
        date object for the next occurrence of that weekday.
    """
    days_ahead = weekday - from_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return from_date + timedelta(days=days_ahead)
