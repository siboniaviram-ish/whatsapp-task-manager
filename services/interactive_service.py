"""
Twilio Content API integration for WhatsApp interactive messages.
Provides buttons (quick-reply) and lists (list-picker) with automatic
fallback to numbered text options when Content API is unavailable.
"""

import json
import logging
import requests as http_requests
from config import Config

logger = logging.getLogger(__name__)

CONTENT_API_URL = "https://content.twilio.com/v1/Content"

# In-memory cache: friendly_name -> content SID
_template_cache = {}
_templates_loaded = False

# Cached Twilio client instance
_twilio_client = None


# ============ Template Definitions ============

TEMPLATE_DEFS = {
    "wt_main_menu": {
        "friendly_name": "wt_main_menu",
        "language": "he",
        "types": {
            "twilio/list-picker": {
                "body": "שלום! 👋 מה תרצה לעשות?",
                "button": "📋 תפריט",
                "items": [
                    {"id": "task_today", "item": "📝 משימה להיום", "description": "יצירת משימה חדשה להיום"},
                    {"id": "task_scheduled", "item": "📅 משימה מתוזמנת", "description": "משימה לתאריך מסוים"},
                    {"id": "task_delegate", "item": "👥 האצלת משימה", "description": "שליחת משימה למישהו אחר"},
                    {"id": "schedule_meeting", "item": "🤝 קביעת פגישה", "description": "תיאום פגישה חדשה"},
                    {"id": "my_tasks", "item": "📋 המשימות שלי", "description": "צפייה וניהול משימות"},
                ]
            }
        }
    },
    "wt_voice_confirm": {
        "friendly_name": "wt_voice_confirm",
        "language": "he",
        "variables": {"1": "טקסט לדוגמה"},
        "types": {
            "twilio/quick-reply": {
                "body": "🎤 זיהיתי:\n\n\"{{1}}\"\n\nזה נכון?",
                "actions": [
                    {"id": "confirm_voice", "title": "✅ אשר"},
                    {"id": "retry_voice", "title": "🔄 שוב"},
                ]
            }
        }
    },
    "wt_date_select": {
        "friendly_name": "wt_date_select",
        "language": "he",
        "types": {
            "twilio/list-picker": {
                "body": "📅 לאיזה תאריך?",
                "button": "בחר תאריך",
                "items": [
                    {"id": "date_today", "item": "📆 היום"},
                    {"id": "date_tomorrow", "item": "📆 מחר"},
                    {"id": "date_this_week", "item": "📆 סוף השבוע"},
                    {"id": "date_custom", "item": "✏️ תאריך אחר"},
                ]
            }
        }
    },
    "wt_time_select": {
        "friendly_name": "wt_time_select",
        "language": "he",
        "types": {
            "twilio/list-picker": {
                "body": "🕐 באיזו שעה?",
                "button": "בחר שעה",
                "items": [
                    {"id": "time_08", "item": "08:00", "description": "בוקר"},
                    {"id": "time_09", "item": "09:00", "description": "בוקר"},
                    {"id": "time_10", "item": "10:00", "description": "בוקר"},
                    {"id": "time_11", "item": "11:00", "description": "לפני הצהריים"},
                    {"id": "time_12", "item": "12:00", "description": "צהריים"},
                    {"id": "time_13", "item": "13:00", "description": "אחה\"צ"},
                    {"id": "time_14", "item": "14:00", "description": "אחה\"צ"},
                    {"id": "time_15", "item": "15:00", "description": "אחה\"צ"},
                    {"id": "time_16", "item": "16:00", "description": "אחה\"צ"},
                    {"id": "time_17", "item": "17:00", "description": "ערב"},
                ]
            }
        }
    },
    "wt_location_select": {
        "friendly_name": "wt_location_select",
        "language": "he",
        "types": {
            "twilio/list-picker": {
                "body": "📍 היכן הפגישה?",
                "button": "בחר מיקום",
                "items": [
                    {"id": "loc_zoom", "item": "💻 Zoom", "description": "פגישה וירטואלית"},
                    {"id": "loc_phone", "item": "📞 טלפון", "description": "שיחה טלפונית"},
                    {"id": "loc_office", "item": "🏢 משרד", "description": "פגישה במשרד"},
                    {"id": "loc_cafe", "item": "☕ בית קפה", "description": "פגישה בבית קפה"},
                    {"id": "loc_other", "item": "✏️ מיקום אחר", "description": "הקלד מיקום"},
                    {"id": "loc_skip", "item": "⏭️ דלג", "description": "ללא מיקום"},
                ]
            }
        }
    },
    "wt_task_success": {
        "friendly_name": "wt_task_success",
        "language": "he",
        "variables": {"1": "המשימה נשמרה בהצלחה!"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "my_tasks", "title": "📋 המשימות שלי"},
                    {"id": "new_task", "title": "➕ משימה חדשה"},
                    {"id": "main_menu", "title": "🏠 תפריט"},
                ]
            }
        }
    },
    "wt_meeting_confirm": {
        "friendly_name": "wt_meeting_confirm",
        "language": "he",
        "variables": {"1": "סיכום פגישה"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "confirm_meeting", "title": "✅ אשר ושלח"},
                    {"id": "cancel_flow", "title": "❌ בטל"},
                ]
            }
        }
    },
    "wt_meeting_success": {
        "friendly_name": "wt_meeting_success",
        "language": "he",
        "variables": {"1": "הפגישה נקבעה בהצלחה!"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "my_meetings", "title": "📅 הפגישות שלי"},
                    {"id": "schedule_meeting", "title": "➕ פגישה חדשה"},
                    {"id": "main_menu", "title": "🏠 תפריט"},
                ]
            }
        }
    },
    "wt_delegate_success": {
        "friendly_name": "wt_delegate_success",
        "language": "he",
        "variables": {"1": "המשימה הועברה בהצלחה!"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "my_tasks", "title": "📋 המשימות שלי"},
                    {"id": "new_task", "title": "➕ משימה חדשה"},
                    {"id": "main_menu", "title": "🏠 תפריט"},
                ]
            }
        }
    },
    "wt_reminder": {
        "friendly_name": "wt_reminder",
        "language": "he",
        "variables": {"1": "תזכורת למשימה"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "task_done", "title": "✅ בוצע"},
                    {"id": "snooze_30", "title": "⏰ 30 דק'"},
                    {"id": "snooze_60", "title": "⏰ שעה"},
                ]
            }
        }
    },
    "wt_delegation_invite": {
        "friendly_name": "wt_delegation_invite",
        "language": "he",
        "variables": {"1": "קיבלת משימה חדשה"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "accept_delegation", "title": "✅ קיבלתי"},
                    {"id": "decline_delegation", "title": "❌ לא יכול"},
                ]
            }
        }
    },
    "wt_meeting_invite": {
        "friendly_name": "wt_meeting_invite",
        "language": "he",
        "variables": {"1": "הוזמנת לפגישה"},
        "types": {
            "twilio/quick-reply": {
                "body": "{{1}}",
                "actions": [
                    {"id": "accept_meeting", "title": "✅ מאשר"},
                    {"id": "decline_meeting", "title": "❌ לא יכול"},
                ]
            }
        }
    },
}


# ============ Internal Helpers ============

def _get_auth():
    sid = Config.TWILIO_ACCOUNT_SID
    token = Config.TWILIO_AUTH_TOKEN
    if not sid or not token:
        return None
    return (sid, token)


def _load_existing_templates():
    """Fetch all existing content templates and populate the cache."""
    global _templates_loaded
    if _templates_loaded:
        return

    auth = _get_auth()
    if not auth:
        _templates_loaded = True
        return

    try:
        resp = http_requests.get(CONTENT_API_URL, auth=auth, timeout=10)
        if resp.status_code == 200:
            for item in resp.json().get('contents', []):
                name = item.get('friendly_name', '')
                sid = item.get('sid', '')
                if name and sid:
                    _template_cache[name] = sid
            logger.info("Loaded %d content templates from Twilio", len(_template_cache))
    except Exception as e:
        logger.warning("Failed to load content templates: %s", e)

    _templates_loaded = True


def _create_template(template_def):
    """Create a content template via Twilio Content API."""
    auth = _get_auth()
    if not auth:
        return None

    try:
        resp = http_requests.post(
            CONTENT_API_URL,
            json=template_def,
            auth=auth,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            sid = resp.json().get('sid')
            if sid:
                _template_cache[template_def['friendly_name']] = sid
                logger.info("Created template '%s' -> %s", template_def['friendly_name'], sid)
                return sid
        else:
            logger.warning(
                "Failed to create template '%s': %s %s",
                template_def['friendly_name'], resp.status_code, resp.text[:300],
            )
    except Exception as e:
        logger.warning("Error creating template '%s': %s", template_def['friendly_name'], e)

    return None


def _get_template_sid(template_name):
    """Get or create a template SID by friendly_name."""
    _load_existing_templates()

    if template_name in _template_cache:
        return _template_cache[template_name]

    tpl_def = TEMPLATE_DEFS.get(template_name)
    if not tpl_def:
        return None

    return _create_template(tpl_def)


def _get_twilio_client():
    """Get or create a cached Twilio Client instance."""
    global _twilio_client
    if _twilio_client is None:
        from twilio.rest import Client
        _twilio_client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    return _twilio_client


def _send_with_content_sid(to_number, content_sid, variables=None):
    """Send a WhatsApp message using a Content template SID."""
    try:
        client = _get_twilio_client()

        if not to_number.startswith('whatsapp:'):
            to_number = f"whatsapp:{to_number}"

        kwargs = {
            "content_sid": content_sid,
            "from_": Config.TWILIO_WHATSAPP_NUMBER,
            "to": to_number,
        }
        if variables:
            kwargs["content_variables"] = json.dumps(variables)

        message = client.messages.create(**kwargs)
        return message.sid
    except Exception as e:
        logger.error("Failed to send interactive message: %s", e)
        return None


def _send_interactive(template_name, to_number, variables=None, fallback_text=""):
    """Try to send an interactive message; fall back to plain text."""
    sid = _get_template_sid(template_name)
    if sid:
        result = _send_with_content_sid(to_number, sid, variables)
        if result:
            return result

    # Fallback to plain text
    if fallback_text:
        from services.whatsapp_service import send_message
        return send_message(to_number, fallback_text)
    return None


# ============ Public API ============

def send_text(to_number, text):
    """Send a plain text message."""
    from services.whatsapp_service import send_message
    return send_message(to_number, text)


def send_main_menu(to_number):
    """Send the main menu as an interactive list."""
    fallback = (
        "שלום! 👋 מה תרצה לעשות?\n\n"
        "1️⃣ 📝 משימה להיום\n"
        "2️⃣ 📅 משימה לתאריך מסוים\n"
        "3️⃣ 👥 משימה למישהו אחר\n"
        "4️⃣ 🤝 קביעת פגישה\n"
        "5️⃣ 📋 המשימות שלי\n\n"
        "👆 שלח מספר לבחירה"
    )
    return _send_interactive("wt_main_menu", to_number, fallback_text=fallback)


def send_voice_confirm(to_number, transcript):
    """Send voice transcription confirmation with buttons."""
    fallback = (
        f"🎤 זיהיתי:\n\n\"{transcript}\"\n\nזה נכון?\n\n"
        "1️⃣ ✅ אשר\n"
        "2️⃣ 🔄 הקלט שוב"
    )
    return _send_interactive("wt_voice_confirm", to_number, {"1": transcript}, fallback)


def send_date_select(to_number):
    """Send date selection as an interactive list."""
    fallback = (
        "📅 לאיזה תאריך?\n\n"
        "1️⃣ היום\n"
        "2️⃣ מחר\n"
        "3️⃣ סוף השבוע\n"
        "4️⃣ ✏️ תאריך אחר\n\n"
        "👆 שלח מספר לבחירה"
    )
    return _send_interactive("wt_date_select", to_number, fallback_text=fallback)


def send_time_select(to_number):
    """Send time selection as an interactive list."""
    fallback = (
        "🕐 באיזו שעה?\n\n"
        "08:00 | 09:00 | 10:00\n"
        "11:00 | 12:00 | 13:00\n"
        "14:00 | 15:00 | 16:00\n"
        "17:00\n\n"
        "👆 שלח את השעה (למשל: 14:00)"
    )
    return _send_interactive("wt_time_select", to_number, fallback_text=fallback)


def send_location_select(to_number):
    """Send location selection as an interactive list."""
    fallback = (
        "📍 היכן הפגישה?\n\n"
        "1️⃣ 💻 Zoom\n"
        "2️⃣ 📞 טלפון\n"
        "3️⃣ 🏢 משרד\n"
        "4️⃣ ☕ בית קפה\n"
        "5️⃣ ✏️ מיקום אחר\n"
        "6️⃣ ⏭️ דלג\n\n"
        "👆 שלח מספר לבחירה"
    )
    return _send_interactive("wt_location_select", to_number, fallback_text=fallback)


def send_task_success(to_number, message):
    """Send task success with action buttons."""
    return _send_interactive("wt_task_success", to_number, {"1": message}, message)


def send_meeting_confirm(to_number, summary):
    """Send meeting summary with confirm/cancel buttons."""
    fallback = summary + "\n\n1️⃣ ✅ אשר ושלח\n2️⃣ ❌ בטל"
    return _send_interactive("wt_meeting_confirm", to_number, {"1": summary}, fallback)


def send_meeting_success(to_number, message):
    """Send meeting success with action buttons."""
    return _send_interactive("wt_meeting_success", to_number, {"1": message}, message)


def send_delegate_success(to_number, message):
    """Send delegation success with action buttons."""
    return _send_interactive("wt_delegate_success", to_number, {"1": message}, message)


def send_reminder_interactive(to_number, message):
    """Send reminder with done/snooze buttons."""
    fallback = message + "\n\n1️⃣ ✅ בוצע\n2️⃣ ⏰ 30 דק'\n3️⃣ ⏰ שעה"
    return _send_interactive("wt_reminder", to_number, {"1": message}, fallback)


def send_delegation_invite(to_number, message):
    """Send delegation invite with accept/decline buttons."""
    fallback = message + "\n\n1️⃣ ✅ קיבלתי\n2️⃣ ❌ לא יכול"
    return _send_interactive("wt_delegation_invite", to_number, {"1": message}, fallback)


def send_meeting_invite_interactive(to_number, message):
    """Send meeting invite with accept/decline buttons."""
    fallback = message + "\n\n1️⃣ ✅ מאשר\n2️⃣ ❌ לא יכול"
    return _send_interactive("wt_meeting_invite", to_number, {"1": message}, fallback)


def preload_templates():
    """Pre-load all content templates at startup for faster first use."""
    try:
        _load_existing_templates()
        logger.info("Templates pre-loaded: %d cached", len(_template_cache))
    except Exception as e:
        logger.warning("Failed to pre-load templates: %s", e)
