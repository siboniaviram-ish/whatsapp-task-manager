"""
Smart parsing service using OpenAI GPT for Hebrew text/voice input.
Extracts task and meeting details from free-form Hebrew text.
Falls back to regex-based parsing if OpenAI is unavailable.
"""

import json
import logging
from datetime import date, datetime

from config import Config

logger = logging.getLogger(__name__)

# Hebrew day names for the system prompt
HEBREW_DAYS = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']


def _get_system_prompt_auto():
    """System prompt for auto-detecting task vs meeting and parsing in one call."""
    today = date.today()
    day_name = HEBREW_DAYS[today.weekday()]
    return (
        f"היום {today.isoformat()} (יום {day_name}). "
        "אתה מנתח טקסט בעברית שמתאר משימה או פגישה.\n\n"
        "אם זו משימה, החזר:\n"
        '{"type": "task", "title": "כותרת קצרה (עד 80 תווים)", "due_date": "YYYY-MM-DD או null", '
        '"due_time": "HH:MM או null", "priority": "low/medium/high/urgent", "assignee_name": "שם או null"}\n\n'
        "אם זו פגישה, החזר:\n"
        '{"type": "meeting", "title": "נושא (עד 80 תווים)", "date": "YYYY-MM-DD או null", '
        '"time": "HH:MM או null", "location": "מיקום או null", "participants": ["שמות"]}\n\n'
        "חשוב מאוד: אם מוזכרת המילה פגישה, תיאום, להיפגש, לתאם, meeting - זו תמיד פגישה!\n"
        "פגישה: מוזכרים משתתפים, מיקום, נושא דיון, תיאום, פגישה, להיפגש, לתאם.\n"
        "משימה: פעולה לביצוע, תזכורת, דד-ליין, צריך לעשות (ללא אזכור של פגישה/תיאום).\n"
        "אם יש ספק - בדוק אם יש מילה שקשורה לפגישה. אם כן, סמן כ-meeting.\n"
        "החזר רק JSON תקין, בלי הסברים."
    )


def _get_system_prompt_task():
    today = date.today()
    day_name = HEBREW_DAYS[today.weekday()]
    return (
        f"היום {today.isoformat()} (יום {day_name}). "
        "אתה מנתח טקסט בעברית שמתאר משימה. "
        "החזר JSON בלבד עם השדות הבאים:\n"
        '- "title": כותרת קצרה של המשימה (עד 80 תווים)\n'
        '- "due_date": תאריך יעד בפורמט YYYY-MM-DD או null\n'
        '- "due_time": שעה בפורמט HH:MM או null\n'
        '- "priority": "low"/"medium"/"high"/"urgent" (ברירת מחדל medium)\n'
        '- "assignee_name": שם של אדם אם מוזכר, או null\n'
        "החזר רק JSON תקין, בלי הסברים."
    )


def _get_system_prompt_meeting():
    today = date.today()
    day_name = HEBREW_DAYS[today.weekday()]
    return (
        f"היום {today.isoformat()} (יום {day_name}). "
        "אתה מנתח טקסט בעברית שמתאר פגישה. "
        "החזר JSON בלבד עם השדות הבאים:\n"
        '- "title": נושא הפגישה (עד 80 תווים)\n'
        '- "date": תאריך בפורמט YYYY-MM-DD או null\n'
        '- "time": שעה בפורמט HH:MM או null\n'
        '- "location": מיקום או null\n'
        '- "participants": רשימת שמות משתתפים (מערך) או []\n'
        "החזר רק JSON תקין, בלי הסברים."
    )


def _call_openai(system_prompt, user_text):
    """Call OpenAI GPT API and return parsed JSON dict, or None on failure."""
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        logger.warning("OpenAI API key not configured — skipping GPT parse")
        return None

    try:
        import requests
        logger.info("GPT parse request: text='%s'", user_text[:100])
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "temperature": 0,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
            },
            timeout=8,
        )

        if response.status_code != 200:
            logger.warning("OpenAI API error: %s - %s", response.status_code, response.text[:200])
            return None

        content = response.json()["choices"][0]["message"]["content"].strip()
        logger.info("GPT raw response: %s", content[:300])
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        parsed = json.loads(content)
        logger.info("GPT parsed result: %s", parsed)
        return parsed
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("Failed to parse OpenAI response: %s (raw: %s)", e, locals().get('content', 'N/A'))
        return None
    except Exception as e:
        logger.warning("OpenAI call failed: %s", e)
        return None


def parse_task_text(text):
    """Parse free-form Hebrew text into task fields using GPT.

    Args:
        text: Hebrew text describing a task.

    Returns:
        Dict with keys: title, due_date, due_time, priority, assignee_name.
        Falls back to regex-based parsing if GPT fails.
    """
    result = _call_openai(_get_system_prompt_task(), text)

    if result and result.get("title"):
        return {
            "title": result.get("title", text[:80]),
            "due_date": result.get("due_date"),
            "due_time": result.get("due_time"),
            "priority": result.get("priority", "medium"),
            "assignee_name": result.get("assignee_name"),
        }

    # Fallback to regex parser
    from services.voice_service import extract_task_from_transcript
    fallback = extract_task_from_transcript(text)
    if fallback:
        return {
            "title": fallback.get("title", text[:80]),
            "due_date": fallback.get("due_date"),
            "due_time": None,
            "priority": fallback.get("priority", "medium"),
            "assignee_name": None,
        }

    return {
        "title": text[:80],
        "due_date": None,
        "due_time": None,
        "priority": "medium",
        "assignee_name": None,
    }


def parse_meeting_text(text):
    """Parse free-form Hebrew text into meeting fields using GPT.

    Args:
        text: Hebrew text describing a meeting.

    Returns:
        Dict with keys: title, date, time, location, participants.
        Falls back to simple extraction if GPT fails.
    """
    logger.info("parse_meeting_text called with: '%s'", text[:100])
    result = _call_openai(_get_system_prompt_meeting(), text)

    if result and result.get("title"):
        parsed = {
            "title": result.get("title", text[:80]),
            "date": result.get("date"),
            "time": result.get("time"),
            "location": result.get("location"),
            "participants": result.get("participants", []),
        }
        logger.info("parse_meeting_text result: %s", parsed)
        return parsed

    # Fallback: use the text as title
    logger.warning("parse_meeting_text GPT failed, using fallback for: '%s'", text[:100])
    return {
        "title": text[:80],
        "date": None,
        "time": None,
        "location": None,
        "participants": [],
    }


MEETING_KEYWORDS = ['פגישה', 'פגישות', 'תיאום', 'לתאם', 'תאם', 'להיפגש', 'meeting']


def _has_meeting_keywords(text):
    """Check if text contains clear meeting-related keywords."""
    lower = text.lower()
    return any(kw in lower for kw in MEETING_KEYWORDS)


def parse_free_text(text):
    """Auto-detect task vs meeting and parse fields.

    If text contains clear meeting keywords, skip auto-detect and parse
    directly as meeting (single GPT call). Otherwise use auto-detect prompt.

    Returns:
        Dict with "type" key ("task"/"meeting") plus relevant parsed fields.
    """
    logger.info("parse_free_text called with: '%s'", text[:100])
    # Fast path: if text has meeting keywords, parse directly as meeting (1 GPT call)
    if _has_meeting_keywords(text):
        logger.info("Meeting keywords detected — fast path to parse_meeting_text")
        parsed = parse_meeting_text(text)
        parsed["type"] = "meeting"
        return parsed

    # Auto-detect via GPT
    result = _call_openai(_get_system_prompt_auto(), text)

    if result:
        detected_type = result.get("type", "task")

        if detected_type == "meeting":
            return {
                "type": "meeting",
                "title": result.get("title", text[:80]),
                "date": result.get("date"),
                "time": result.get("time"),
                "location": result.get("location"),
                "participants": result.get("participants", []),
            }
        else:
            return {
                "type": "task",
                "title": result.get("title", text[:80]),
                "due_date": result.get("due_date"),
                "due_time": result.get("due_time"),
                "priority": result.get("priority", "medium"),
                "assignee_name": result.get("assignee_name"),
            }

    # Fallback: treat as task
    parsed = parse_task_text(text)
    parsed["type"] = "task"
    return parsed
