"""
WhatsApp Task Management Bot - Main Message Handlers
Simplified flows: one message → smart parse → confirm → done.
Voice input supported at every step.
"""

import re
import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

from config import Config
from database import get_db
from services.task_service import create_task, get_tasks, complete_task, get_today_tasks
from services.voice_service import transcribe_audio
from services.smart_parse_service import parse_task_text, parse_meeting_text, parse_free_text
from services.meeting_service import create_meeting, add_participant
from services.reminder_service import create_reminders_for_task, create_single_reminder
from services.whatsapp_service import log_message
from services.interactive_service import (
    send_text,
    send_main_menu,
    send_voice_confirm,
    send_date_select,
    send_time_select,
    send_location_select,
    send_task_success,
    send_task_confirm,
    send_reminder_select,
    send_delegate_ask,
    send_date_fallback,
    send_meeting_confirm,
    send_meeting_success,
    send_delegate_success,
    send_delegation_invite,
    send_meeting_invite_interactive,
)
from bot.commands import get_command, is_cancel
from bot.flows import ConversationFlow

logger = logging.getLogger(__name__)

DASHBOARD_URL = Config.APP_URL

WELCOME_MSG = (
    "שלום! 👋\n"
    "הגעת למנהל המשימות האישי שלך.\n\n"
    "🎤 אתה יכול *להקליט הודעה* או *לכתוב* ואני אדאג לכל השאר:\n\n"
    "📅 *פגישה* - אמור עם מי, מתי ואיפה ואני כבר אתאם לך את הכל\n\n"
    "📝 *משימה* - אמור מה אתה צריך לבצע ומתי ואני אזכיר לך\n\n"
    "👥 *העברה* - אם יש מישהו שאתה רוצה שיבצע את המשימה, "
    "פשוט צרף את איש הקשר ואני כבר אתאם את כל הפרטים ואזכיר לך\n\n"
    "פשוט תקליט או תכתוב! 🎤"
)

NEXT_PROMPT = (
    "✏️ תכתוב או תקליט הודעה עם המשימה או הפגישה הבאה 🎤\n\n"
    f"📋 כל המשימות: {DASHBOARD_URL}/tasks"
)


def _send_welcome(phone):
    """Send the welcome/intro message."""
    send_text(phone, WELCOME_MSG)


def _send_next_prompt(phone):
    """Send the 'write or record next' prompt (replaces main menu)."""
    send_text(phone, NEXT_PROMPT)


# Map interactive button/list text → action id (fallback when payload missing)
BUTTON_TEXT_MAP = {
    # New main menu (3 items)
    '📝 משימה חדשה': 'new_task',
    '🤝 קביעת פגישה': 'new_meeting',
    '📋 המשימות שלי': 'my_tasks',
    # Legacy main menu items (for backward compat)
    '📝 משימה להיום': 'new_task',
    '📅 משימה מתוזמנת': 'new_task',
    '👥 האצלת משימה': 'new_task',
    # Task confirm
    '✅ אשר': 'confirm_task',
    '🔄 נסה שוב': 'retry_task',
    # Reminder select
    '⏰ שעה לפני': 'remind_1h',
    '⏰ שעתיים לפני': 'remind_2h',
    '⏰ יום לפני': 'remind_24h',
    '🚫 בלי תזכורת': 'remind_none',
    # Delegate ask
    '👥 כן, להעביר': 'delegate_yes',
    '⏭️ לא, סיימתי': 'delegate_no',
    # Voice confirm
    '🔄 שוב': 'retry_voice',
    # Date select / fallback
    '📆 היום': 'date_today',
    '📆 מחר': 'date_tomorrow',
    '📆 סוף השבוע': 'date_this_week',
    '✏️ תאריך אחר': 'date_custom',
    # Location select
    '💻 Zoom': 'loc_zoom',
    '📞 טלפון': 'loc_phone',
    '🏢 משרד': 'loc_office',
    '☕ בית קפה': 'loc_cafe',
    '✏️ מיקום אחר': 'loc_other',
    '⏭️ דלג': 'loc_skip',
    # Success buttons
    '➕ משימה חדשה': 'new_task',
    '🏠 תפריט': 'main_menu',
    '➕ פגישה חדשה': 'new_meeting',
    '📅 הפגישות שלי': 'my_meetings',
    # Meeting confirm
    '✅ אשר ושלח': 'confirm_meeting',
    '❌ בטל': 'cancel_flow',
    # Reminder buttons
    '✅ בוצע': 'task_done',
    "⏰ 30 דק'": 'snooze_30',
    '⏰ שעה': 'snooze_60',
    # Invite responses
    '✅ קיבלתי': 'accept_delegation',
    '✅ מאשר': 'accept_meeting',
    '❌ לא יכול': 'decline',
}

# Actions that take priority over active flows
PRIORITY_ACTIONS = {
    'task_done', 'snooze_30', 'snooze_60',
    'accept_delegation', 'decline_delegation',
    'accept_meeting', 'decline_meeting', 'decline',
    'main_menu',
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handle_incoming_message(from_number, message_body, message_type='text',
                            media_url=None, button_payload=None, list_id=None):
    try:
        user_id, is_new = _get_or_create_user(from_number)

        try:
            log_message(user_id, 'incoming', message_type, message_body or '')
        except Exception:
            pass

        # First-time user → welcome message (then continue processing their message)
        if is_new:
            _send_welcome(from_number)

        # --- Voice messages ---
        if message_type == 'voice' and media_url:
            logger.info("Processing voice message from %s, media_url=%s", from_number, media_url[:60] if media_url else '')
            flow_name, flow_data = ConversationFlow.get_flow(user_id)
            if flow_name == 'voice_pending':
                return_flow = flow_data.get('_return_flow')
                return _handle_voice_in_flow(user_id, from_number, media_url, return_flow, flow_data)
            elif flow_name == 'voice_confirm':
                return _handle_voice_auto(user_id, from_number, media_url)
            elif flow_name:
                return _handle_voice_in_flow(user_id, from_number, media_url, flow_name, flow_data)
            else:
                return _handle_voice_auto(user_id, from_number, media_url)

        # --- Contact shared (vCard) ---
        if message_type == 'contact' and message_body:
            flow_name, flow_data = ConversationFlow.get_flow(user_id)
            if flow_name in ('delegate_inline', 'delegate', 'meeting', 'meeting_invite'):
                text = message_body
                action_id = _resolve_action_id(None, None, text)
                return _handle_flow(user_id, from_number, text, action_id, flow_name, flow_data)
            else:
                vcard_phone, vcard_name = _parse_vcard(message_body)
                if vcard_phone:
                    display = vcard_name or vcard_phone
                    send_text(from_number,
                        f"📱 קיבלתי את איש הקשר *{display}*.\n"
                        "כדי להעביר משימה, קודם צור משימה ואז תוכל לצרף איש קשר.")
                _send_next_prompt(from_number)
                return

        # --- Text / button messages ---
        text = (message_body or '').strip()
        action_id = _resolve_action_id(button_payload, list_id, text)

        # Cancel
        if is_cancel(text):
            ConversationFlow.clear_flow(user_id)
            send_text(from_number, "❌ הפעולה בוטלה.")
            _send_next_prompt(from_number)
            return

        # Priority actions (reminder buttons, delegation/meeting responses)
        if action_id in PRIORITY_ACTIONS:
            if action_id == 'main_menu':
                ConversationFlow.clear_flow(user_id)
                _send_welcome(from_number)
                return
            return _handle_global_action(user_id, from_number, action_id)

        # Active flow
        flow_name, flow_data = ConversationFlow.get_flow(user_id)
        if flow_name:
            return _handle_flow(user_id, from_number, text, action_id, flow_name, flow_data)

        # Global actions (buttons from templates)
        if action_id in ('my_tasks', 'new_task', 'new_meeting',
                         'my_meetings', 'schedule_meeting',
                         'task_done', 'snooze_30', 'snooze_60',
                         'accept_delegation', 'decline_delegation',
                         'accept_meeting', 'decline_meeting', 'decline'):
            return _handle_global_action(user_id, from_number, action_id)

        # Greeting / help commands → welcome message
        command = get_command(text) or _action_to_command(action_id)
        if command in ('welcome', 'help'):
            _send_welcome(from_number)
            return
        if command == 'my_tasks':
            _show_tasks(user_id, from_number)
            return
        if command == 'meetings':
            _show_meetings(user_id, from_number)
            return
        if command == 'complete':
            return _handle_command(user_id, from_number, command)

        # Empty message → welcome
        if not text:
            _send_welcome(from_number)
            return

        # --- AUTO-PARSE: any free text → detect task/meeting → confirm ---
        _handle_text_auto(user_id, from_number, text)

    except Exception as e:
        logger.error("Error handling message from %s: %s", from_number, e, exc_info=True)
        try:
            send_text(from_number, "❌ אירעה שגיאה. נסה שוב.")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_action_id(button_payload, list_id, text):
    if button_payload:
        return button_payload
    if list_id:
        return list_id
    return BUTTON_TEXT_MAP.get(text)


def _action_to_command(action_id):
    mapping = {
        'new_task': 'new_task',
        'new_meeting': 'new_meeting',
        'my_tasks': 'my_tasks',
        'main_menu': 'welcome',
        'my_meetings': 'meetings',
        # Legacy
        'task_today': 'new_task',
        'task_scheduled': 'new_task',
        'task_delegate': 'new_task',
        'schedule_meeting': 'new_meeting',
    }
    return mapping.get(action_id)


def _get_or_create_user(phone):
    """Returns (user_id, is_new) tuple."""
    db = None
    try:
        db = get_db()
        row = db.execute("SELECT id FROM users WHERE phone_number = ?", (phone,)).fetchone()
        if row:
            db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (row['id'],))
            db.commit()
            return row['id'], False
        cursor = db.execute(
            "INSERT INTO users (phone_number, whatsapp_verified, last_active) VALUES (?, 1, CURRENT_TIMESTAMP)",
            (phone,),
        )
        db.commit()
        return cursor.lastrowid, True
    except Exception:
        if db:
            db.rollback()
        raise
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Global actions
# ---------------------------------------------------------------------------

def _handle_global_action(user_id, phone, action_id):
    if action_id == 'main_menu':
        _send_welcome(phone)
    elif action_id == 'my_tasks':
        _show_tasks(user_id, phone)
    elif action_id in ('new_task',):
        ConversationFlow.set_flow(user_id, 'new_task', {})
        send_text(phone, "📝 תאר את המשימה בהודעה אחת.\nלדוגמה: *להתקשר לרופא מחר ב-16:00*\n\nאפשר גם הודעה קולית 🎤")
    elif action_id in ('new_meeting', 'schedule_meeting'):
        ConversationFlow.set_flow(user_id, 'new_meeting', {})
        send_text(phone, "📅 תאר את הפגישה בהודעה אחת.\nלדוגמה: *פגישה עם יוסי מחר ב-14:00 בזום*\n\nאפשר גם הודעה קולית 🎤")
    elif action_id == 'my_meetings':
        _show_meetings(user_id, phone)
    elif action_id == 'task_done':
        _handle_task_done(user_id, phone)
    elif action_id in ('snooze_30', 'snooze_60'):
        minutes = 30 if action_id == 'snooze_30' else 60
        _handle_snooze(user_id, phone, minutes)
    elif action_id == 'accept_delegation':
        _handle_delegation_response(user_id, phone, accepted=True)
    elif action_id == 'decline_delegation':
        _handle_delegation_response(user_id, phone, accepted=False)
    elif action_id == 'decline':
        db = None
        try:
            db = get_db()
            has_meeting = db.execute(
                "SELECT 1 FROM meeting_participants WHERE phone_number = ? AND status = 'pending' LIMIT 1",
                (phone,)
            ).fetchone()
        except Exception:
            has_meeting = None
        finally:
            if db:
                db.close()
        if has_meeting:
            _handle_meeting_response(user_id, phone, accepted=False)
        else:
            _handle_delegation_response(user_id, phone, accepted=False)
    elif action_id == 'accept_meeting':
        _handle_meeting_response(user_id, phone, accepted=True)
    elif action_id == 'decline_meeting':
        _handle_meeting_response(user_id, phone, accepted=False)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def _handle_command(user_id, phone, command):
    try:
        if command == 'welcome':
            _send_welcome(phone)

        elif command == 'new_task':
            ConversationFlow.set_flow(user_id, 'new_task', {})
            send_text(phone, "📝 תאר את המשימה בהודעה אחת.\nלדוגמה: *להתקשר לרופא מחר ב-16:00*\n\nאפשר גם הודעה קולית 🎤")

        elif command == 'new_meeting':
            ConversationFlow.set_flow(user_id, 'new_meeting', {})
            send_text(phone, "📅 תאר את הפגישה בהודעה אחת.\nלדוגמה: *פגישה עם יוסי מחר ב-14:00 בזום*\n\nאפשר גם הודעה קולית 🎤")

        elif command == 'my_tasks':
            _show_tasks(user_id, phone)

        elif command == 'help':
            _send_welcome(phone)

        elif command == 'complete':
            tasks = get_today_tasks(user_id)
            pending = [t for t in tasks if t['status'] == 'pending']
            if pending:
                complete_task(pending[0]['id'])
                send_text(phone, f"🎉 המשימה \"{pending[0]['title']}\" סומנה כבוצעה! ✔️")
                _send_next_prompt(phone)
            else:
                send_text(phone, "🎉 אין משימות פתוחות להיום!")
                _send_next_prompt(phone)

        elif command == 'meetings':
            _show_meetings(user_id, phone)

        # Legacy commands → redirect to new flows
        elif command in ('task_today', 'task_scheduled', 'task_delegate'):
            ConversationFlow.set_flow(user_id, 'new_task', {})
            send_text(phone, "📝 תאר את המשימה בהודעה אחת.\nלדוגמה: *להתקשר לרופא מחר ב-16:00*\n\nאפשר גם הודעה קולית 🎤")

        elif command == 'schedule_meeting':
            ConversationFlow.set_flow(user_id, 'new_meeting', {})
            send_text(phone, "📅 תאר את הפגישה בהודעה אחת.\nלדוגמה: *פגישה עם יוסי מחר ב-14:00 בזום*\n\nאפשר גם הודעה קולית 🎤")

        else:
            _send_welcome(phone)

    except Exception as e:
        logger.error("Error handling command '%s': %s", command, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


# ---------------------------------------------------------------------------
# Voice handlers
# ---------------------------------------------------------------------------

def _handle_voice_standalone(user_id, phone, media_url):
    """Legacy: Transcribe voice → smart parse → enter new_task at confirmation step."""
    return _handle_voice_auto(user_id, phone, media_url)


def _handle_voice_auto(user_id, phone, media_url):
    """Transcribe voice → auto-detect task/meeting → show confirmation."""
    try:
        transcript = transcribe_audio(media_url)
        if not transcript:
            send_text(phone, "🎤 לא הצלחתי לזהות. אנא אמור שוב בקול ברור.")
            return

        parsed = parse_free_text(transcript)
        detected_type = parsed.pop("type", "task")

        if detected_type == "meeting":
            flow_data = {
                'transcript': transcript,
                'parsed': parsed,
                'step': 'confirm',
                'created_via': 'whatsapp_voice',
            }
            ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
            summary = _build_meeting_confirm_summary(parsed)
            send_meeting_confirm(phone, summary)
        else:
            flow_data = {
                'transcript': transcript,
                'parsed': parsed,
                'step': 'confirm',
                'created_via': 'whatsapp_voice',
            }
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            summary = _build_task_confirm_summary(parsed)
            send_task_confirm(phone, summary)
    except Exception as e:
        logger.error("Voice auto error for user %s: %s", user_id, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


def _handle_text_auto(user_id, phone, text):
    """Auto-detect task/meeting from free text → show confirmation."""
    try:
        parsed = parse_free_text(text)
        detected_type = parsed.pop("type", "task")

        if detected_type == "meeting":
            flow_data = {
                'parsed': parsed,
                'step': 'confirm',
                'created_via': 'whatsapp_text',
            }
            ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
            summary = _build_meeting_confirm_summary(parsed)
            send_meeting_confirm(phone, summary)
        else:
            flow_data = {
                'parsed': parsed,
                'step': 'confirm',
                'created_via': 'whatsapp_text',
            }
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            summary = _build_task_confirm_summary(parsed)
            send_task_confirm(phone, summary)
    except Exception as e:
        logger.error("Text auto error for user %s: %s", user_id, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


def _handle_voice_in_flow(user_id, phone, media_url, flow_name, flow_data):
    try:
        transcript = transcribe_audio(media_url)
        if not transcript:
            send_text(phone, "🎤 לא הצלחתי לזהות. אנא אמור שוב בקול ברור.")
            return

        # For new_task/new_meeting: skip voice confirm, go directly to parsed confirmation
        if flow_name == 'new_task':
            parsed = parse_task_text(transcript)
            flow_data['transcript'] = transcript
            flow_data['parsed'] = parsed
            flow_data['step'] = 'confirm'
            flow_data['created_via'] = 'whatsapp_voice'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            summary = _build_task_confirm_summary(parsed)
            send_task_confirm(phone, summary)
            return

        if flow_name == 'new_meeting':
            parsed = parse_meeting_text(transcript)
            flow_data['transcript'] = transcript
            flow_data['parsed'] = parsed
            flow_data['step'] = 'confirm'
            flow_data['created_via'] = 'whatsapp_voice'
            ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
            summary = _build_meeting_confirm_summary(parsed)
            send_task_confirm(phone, summary)
            return

        # Other flows: show voice transcription confirm first
        flow_data['_pending_voice'] = transcript
        flow_data['_return_flow'] = flow_name
        ConversationFlow.set_flow(user_id, 'voice_pending', flow_data)
        send_voice_confirm(phone, transcript)
    except Exception as e:
        logger.error("Voice-in-flow error for user %s: %s", user_id, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


# ---------------------------------------------------------------------------
# Flow dispatcher
# ---------------------------------------------------------------------------

def _handle_flow(user_id, phone, text, action_id, flow_name, flow_data):
    try:
        if flow_name == 'voice_pending':
            return _handle_voice_pending(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'voice_confirm':
            return _handle_voice_confirm(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'new_task':
            return _handle_new_task(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'new_meeting':
            return _handle_new_meeting(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'delegate_inline':
            return _handle_delegate_inline(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'meeting_invite':
            return _handle_meeting_invite(user_id, phone, text, action_id, flow_data)
        # Legacy flows
        elif flow_name == 'create_task':
            return _handle_create_task_legacy(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'delegate':
            return _handle_delegate_legacy(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'meeting':
            return _handle_meeting_legacy(user_id, phone, text, action_id, flow_data)
        else:
            ConversationFlow.clear_flow(user_id)
            _send_next_prompt(phone)
    except Exception as e:
        logger.error("Flow '%s' error for user %s: %s", flow_name, user_id, e, exc_info=True)
        try:
            ConversationFlow.clear_flow(user_id)
        except Exception:
            pass
        try:
            send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
            _send_next_prompt(phone)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Voice pending (confirmation of voice in any flow)
# ---------------------------------------------------------------------------

def _handle_voice_pending(user_id, phone, text, action_id, flow_data):
    if action_id in ('confirm_voice', 'confirm_task') or text in ('1', 'כן', 'אשר'):
        transcript = flow_data.pop('_pending_voice', '')
        return_flow = flow_data.pop('_return_flow', None)
        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            _send_next_prompt(phone)
            return
        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        return _handle_flow(user_id, phone, transcript, None, return_flow, flow_data)

    elif action_id in ('retry_voice', 'retry_task') or text in ('2', 'לא'):
        flow_data.pop('_pending_voice', None)
        return_flow = flow_data.pop('_return_flow', None)
        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            _send_next_prompt(phone)
            return
        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        prompt = _get_flow_prompt(return_flow, flow_data)
        send_text(phone, prompt + "\n\n🎤 שלח הודעה קולית או הקלד:")
    else:
        send_text(phone, "שלח *1* לאישור או *2* להקלטה מחדש.")


# ---------------------------------------------------------------------------
# Voice confirm (standalone voice → task) - legacy compat
# ---------------------------------------------------------------------------

def _handle_voice_confirm(user_id, phone, text, action_id, flow_data):
    """Legacy voice_confirm flow - redirect to new_task confirmation."""
    if action_id in ('confirm_voice', 'confirm_task') or text in ('1', 'כן', 'אשר'):
        parsed = flow_data.get('parsed', {})
        if not parsed.get('title'):
            transcript = flow_data.get('transcript', '')
            parsed = parse_task_text(transcript)
            flow_data['parsed'] = parsed

        # Skip to date/reminder step (already confirmed)
        if not parsed.get('due_date'):
            flow_data['step'] = 'date_fallback'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_date_fallback(phone)
        else:
            flow_data['step'] = 'reminder'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_reminder_select(phone)
    elif action_id in ('retry_voice', 'retry_task') or text in ('2', 'לא'):
        ConversationFlow.clear_flow(user_id)
        send_text(phone, "🎤 שלח הודעה קולית חדשה:")
    else:
        send_text(phone, "שלח *1* לאישור או *2* להקלטה מחדש.")


# ---------------------------------------------------------------------------
# NEW: Simplified Task Flow
# Step 1: User sends text/voice → smart parse → show confirmation
# Step 2: User confirms → if no date, show date fallback; else show reminder
# Step 3: User picks reminder → save task → ask about delegation
# Step 4: User delegates or finishes
# ---------------------------------------------------------------------------

def _handle_new_task(user_id, phone, text, action_id, flow_data):
    step = flow_data.get('step', 'input')

    # Step 1: Input → smart parse → show confirmation
    if step == 'input':
        parsed = parse_task_text(text)
        flow_data['parsed'] = parsed
        flow_data['step'] = 'confirm'
        flow_data.setdefault('created_via', 'whatsapp_text')
        ConversationFlow.set_flow(user_id, 'new_task', flow_data)

        summary = _build_task_confirm_summary(parsed)
        send_task_confirm(phone, summary)
        return

    # Step 2: Confirmation
    if step == 'confirm':
        if action_id == 'confirm_task' or text in ('1', 'כן', 'אשר', '✅ אשר'):
            parsed = flow_data.get('parsed', {})
            # If no date was detected, ask for one
            if not parsed.get('due_date'):
                flow_data['step'] = 'date_fallback'
                ConversationFlow.set_flow(user_id, 'new_task', flow_data)
                send_date_fallback(phone)
                return
            # Date exists → go to reminder selection
            flow_data['step'] = 'reminder'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_reminder_select(phone)
            return

        elif action_id == 'retry_task' or text in ('2', 'לא', '🔄 נסה שוב'):
            flow_data['step'] = 'input'
            flow_data.pop('parsed', None)
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_text(phone, "📝 תאר את המשימה שוב:")
            return

        # Unrecognized
        send_text(phone, "שלח *1* לאישור או *2* לנסות שוב.")
        return

    # Step 2b: Date fallback (when smart parse didn't detect a date)
    if step == 'date_fallback':
        if flow_data.get('awaiting_custom_date'):
            parsed_date = _parse_date_text(text)
            if parsed_date:
                flow_data['parsed']['due_date'] = parsed_date
                flow_data['step'] = 'reminder'
                flow_data.pop('awaiting_custom_date', None)
                ConversationFlow.set_flow(user_id, 'new_task', flow_data)
                send_reminder_select(phone)
                return
            send_text(phone, "❌ לא הצלחתי לזהות תאריך.\nהקלד לדוגמה: 25/3/25 או 25/03/2025 או 25.3")
            return

        resolved = _resolve_date(text, action_id)
        if resolved == 'custom':
            flow_data['awaiting_custom_date'] = True
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_text(phone, "📅 הקלד תאריך (לדוגמה: 25/3/25 או 25/03/2025 או 25.3):")
            return
        if resolved:
            flow_data['parsed']['due_date'] = resolved
            flow_data['step'] = 'reminder'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)
            send_reminder_select(phone)
            return

        send_date_fallback(phone)
        return

    # Step 3: Reminder selection
    if step == 'reminder':
        reminder_map = {
            'remind_1h': 60,
            'remind_2h': 120,
            'remind_24h': 1440,
            'remind_none': None,
        }
        # Check action_id first
        minutes = None
        selected = False
        if action_id in reminder_map:
            minutes = reminder_map[action_id]
            selected = True
        elif text in ('1',):
            minutes = 60
            selected = True
        elif text in ('2',):
            minutes = 120
            selected = True
        elif text in ('3',):
            minutes = 1440
            selected = True
        elif text in ('4',):
            minutes = None
            selected = True

        if selected:
            # Save the task
            parsed = flow_data.get('parsed', {})
            task_id = _save_task(user_id, parsed, flow_data.get('created_via', 'whatsapp_text'))

            # Create single reminder if requested
            if task_id and minutes:
                try:
                    create_single_reminder(task_id, minutes)
                except Exception as e:
                    logger.warning("Failed to create reminder: %s", e)

            # Store task_id for potential delegation
            flow_data['task_id'] = task_id
            flow_data['step'] = 'delegate_ask'
            ConversationFlow.set_flow(user_id, 'new_task', flow_data)

            # Show success + ask about delegation
            display_date = _format_display_date(parsed.get('due_date'))
            reminder_text = _reminder_text(minutes)
            msg = (
                f"✅ המשימה נשמרה!\n\n"
                f"📌 *{parsed.get('title', '')}*\n"
                f"📅 תאריך: {display_date}\n"
                f"⏰ תזכורת: {reminder_text}\n\n"
                f"📋 {DASHBOARD_URL}/tasks"
            )
            send_text(phone, msg)
            send_delegate_ask(phone)
            return

        send_reminder_select(phone)
        return

    # Step 4: Delegation ask
    if step == 'delegate_ask':
        if action_id == 'delegate_yes' or text in ('1', 'כן', 'כן, להעביר', '👥 כן, להעביר'):
            task_id = flow_data.get('task_id')
            parsed = flow_data.get('parsed', {})
            ConversationFlow.set_flow(user_id, 'delegate_inline', {
                'task_id': task_id,
                'task_title': parsed.get('title', ''),
                'due_date': parsed.get('due_date', ''),
            })
            send_text(phone,
                "👤 שתף איש קשר מהטלפון 📱\n\n"
                "💡 או הקלד מספר טלפון (לדוגמה: 0501234567)")
            return

        elif action_id == 'delegate_no' or text in ('2', 'לא', 'סיימתי', '⏭️ לא, סיימתי'):
            ConversationFlow.clear_flow(user_id)
            send_text(phone, "✅ סיימנו! המשימה נשמרה בהצלחה.")
            _send_next_prompt(phone)
            return

        send_delegate_ask(phone)
        return


# ---------------------------------------------------------------------------
# NEW: Inline Delegation (after task save)
# ---------------------------------------------------------------------------

def _handle_delegate_inline(user_id, phone, text, action_id, flow_data):
    """Receive vCard contact or phone number → record delegation → send invite → done."""
    logger.info("Delegation handler called. text length=%d, starts_with_vcard=%s",
                len(text) if text else 0, bool(text and 'BEGIN:VCARD' in text))

    vcard_phone, vcard_name = _parse_vcard(text)

    # Also accept a typed phone number (not just vCard)
    if not vcard_phone and text:
        cleaned = text.strip()
        # Check if user typed a phone number directly
        if re.match(r'^[\d\+\-\s\(\)]{7,}$', cleaned):
            vcard_phone = _normalize_phone(cleaned)
            vcard_name = None
            logger.info("Parsed typed phone number: %s", vcard_phone)

    if not vcard_phone:
        # User typed something that's not a contact — exit flow and process as new request
        ConversationFlow.clear_flow(user_id)
        command = get_command(text.strip()) if text else None
        if command:
            return _handle_command(user_id, phone, command)
        if text and text.strip():
            _handle_text_auto(user_id, phone, text.strip())
            return
        send_text(phone,
            "📱 שתף איש קשר מהטלפון כדי להמשיך.\n"
            "לחץ על 📎 ובחר *איש קשר*.\n\n"
            "💡 או הקלד מספר טלפון (לדוגמה: 0501234567)\n\n"
            "שלח *ביטול* לחזרה.")
        return

    task_id = flow_data.get('task_id')
    task_title = flow_data.get('task_title', '')
    due_date_str = flow_data.get('due_date', '')

    # Record delegation in DB
    if task_id:
        db = None
        try:
            db = get_db()
            db.execute(
                "INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, "
                "status, message_sent_at) VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)",
                (task_id, user_id, vcard_phone, vcard_name or vcard_phone),
            )
            db.execute("UPDATE tasks SET task_type = 'delegated' WHERE id = ?", (task_id,))
            db.commit()
        except Exception as e:
            logger.warning("Failed to record delegation: %s", e)
            if db:
                db.rollback()
        finally:
            if db:
                db.close()

    # Send invite to assignee
    display_date = _format_display_date(due_date_str)
    display_assignee = vcard_name or vcard_phone
    invite_msg = (
        f"📥 קיבלת משימה חדשה!\n\n"
        f"📌 משימה: *{task_title}*\n"
        f"📅 תאריך יעד: {display_date}"
    )
    invite_sent = False
    try:
        result = send_delegation_invite(vcard_phone, invite_msg)
        invite_sent = bool(result)
        logger.info("Delegation invite to %s: result=%s", vcard_phone, result)
    except Exception as e:
        logger.warning("Failed to send delegation invite to %s: %s", vcard_phone, e)

    ConversationFlow.clear_flow(user_id)

    if invite_sent:
        msg = (
            f"✅ המשימה הועברה בהצלחה!\n\n"
            f"👤 נשלח אל: *{display_assignee}*\n"
            f"📌 משימה: *{task_title}*\n"
            f"📅 תאריך יעד: {display_date}\n\n"
            f"📋 {DASHBOARD_URL}/delegation"
        )
    else:
        msg = (
            f"✅ המשימה נשמרה ומוקצת ל-*{display_assignee}*\n\n"
            f"📌 משימה: *{task_title}*\n"
            f"📅 תאריך יעד: {display_date}\n\n"
            f"⚠️ לא הצלחתי לשלוח הזמנה.\n"
            f"ייתכן שהמספר לא רשום במערכת.\n"
            f"שלח את הלינק הזה ידנית:\n"
            f"📋 {DASHBOARD_URL}/delegation"
        )
    send_text(phone, msg)
    _send_next_prompt(phone)


# ---------------------------------------------------------------------------
# Meeting participant invite flow
# User shares contacts → add participant → send invite → repeat
# ---------------------------------------------------------------------------

def _handle_meeting_invite(user_id, phone, text, action_id, flow_data):
    """Collect participant contacts and send meeting invites."""
    stripped = (text or '').strip()

    # Done / finish / skip / no
    _exit_keywords = ('סיימתי', 'ביטול', 'done', 'cancel', 'לא', 'no', 'דלג', 'skip')
    if stripped and stripped in _exit_keywords:
        invited = flow_data.get('invited_count', 0)
        ConversationFlow.clear_flow(user_id)
        if invited > 0:
            send_text(phone, f"✅ נשלחו {invited} הזמנות לפגישה!")
        _send_next_prompt(phone)
        return

    # Try to parse contact from vCard or typed phone number
    vcard_phone, vcard_name = _parse_vcard(text)
    if not vcard_phone and stripped:
        if re.match(r'^[\d\+\-\s\(\)]{7,}$', stripped):
            vcard_phone = _normalize_phone(stripped)
            vcard_name = None

    if not vcard_phone:
        # User typed something that's not a contact — treat as a new request
        # Exit the invite flow and process the text as a new command/auto-parse
        ConversationFlow.clear_flow(user_id)
        invited = flow_data.get('invited_count', 0)
        if invited > 0:
            send_text(phone, f"✅ נשלחו {invited} הזמנות לפגישה!")

        # Check if it's a command
        command = get_command(stripped)
        if command:
            return _handle_command(user_id, phone, command)

        # Otherwise auto-parse as new task/meeting
        _handle_text_auto(user_id, phone, stripped)
        return

    meeting_id = flow_data.get('meeting_id')
    meeting_title = flow_data.get('meeting_title', '')
    meeting_date = flow_data.get('meeting_date', '')
    meeting_time = flow_data.get('meeting_time', '')
    location = flow_data.get('location', '')

    # Add participant to DB
    if meeting_id:
        try:
            add_participant(meeting_id, vcard_phone, vcard_name)
        except Exception as e:
            logger.warning("Failed to add meeting participant: %s", e)

    # Send meeting invite
    display_date = _format_display_date(meeting_date)
    display_name = vcard_name or vcard_phone
    invite_msg = (
        f"📅 הוזמנת לפגישה!\n\n"
        f"📌 נושא: *{meeting_title}*\n"
        f"🗓️ תאריך: {display_date}\n"
        f"🕐 שעה: {meeting_time}"
    )
    if location and location != 'לא צוין':
        invite_msg += f"\n📍 מיקום: {location}"

    invite_sent = False
    try:
        result = send_meeting_invite_interactive(vcard_phone, invite_msg)
        invite_sent = bool(result)
        logger.info("Meeting invite to %s: result=%s", vcard_phone, result)
    except Exception as e:
        logger.warning("Failed to send meeting invite to %s: %s", vcard_phone, e)

    # Update flow state
    flow_data['invited_count'] = flow_data.get('invited_count', 0) + 1
    pending = flow_data.get('pending_names', [])
    if pending:
        # Remove the first matching name (approximate)
        flow_data['pending_names'] = pending[1:] if len(pending) > 1 else []
    ConversationFlow.set_flow(user_id, 'meeting_invite', flow_data)

    if invite_sent:
        send_text(phone, f"✅ נשלחה הזמנה ל-*{display_name}*!")
    else:
        send_text(phone,
            f"✅ *{display_name}* נוסף/ה לפגישה.\n"
            f"⚠️ לא הצלחתי לשלוח הזמנה - ייתכן שהמספר לא רשום במערכת.")

    remaining = flow_data.get('pending_names', [])
    if remaining:
        send_text(phone,
            f"📱 שתף את איש הקשר הבא: *{remaining[0]}*\n"
            f"או שלח *סיימתי* לסיום.")
    else:
        send_text(phone, "📱 שתף עוד אנשי קשר או שלח *סיימתי* לסיום.")


# ---------------------------------------------------------------------------
# NEW: Simplified Meeting Flow
# Step 1: User sends text/voice → smart parse → show confirmation
# Step 2: User confirms → save meeting → done
# ---------------------------------------------------------------------------

def _handle_new_meeting(user_id, phone, text, action_id, flow_data):
    step = flow_data.get('step', 'input')

    # Step 1: Input → smart parse → show confirmation
    if step == 'input':
        parsed = parse_meeting_text(text)
        flow_data['parsed'] = parsed
        flow_data['step'] = 'confirm'
        ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)

        summary = _build_meeting_confirm_summary(parsed)
        send_meeting_confirm(phone, summary)
        return

    # Step 2: Confirmation
    if step == 'confirm':
        if action_id == 'confirm_meeting' or text in ('1', 'כן', 'אשר', '✅ אשר ושלח'):
            parsed = flow_data.get('parsed', {})

            # If no date, ask for one
            if not parsed.get('date'):
                flow_data['step'] = 'date_fallback'
                ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
                send_date_fallback(phone)
                return

            # If no time, ask for one
            if not parsed.get('time'):
                flow_data['step'] = 'time_select'
                ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
                send_time_select(phone)
                return

            return _finalize_new_meeting(user_id, phone, flow_data)

        elif action_id == 'cancel_flow' or text in ('2', 'בטל', '❌ בטל'):
            ConversationFlow.clear_flow(user_id)
            send_text(phone, "❌ הפגישה בוטלה.")
            _send_next_prompt(phone)
            return

        send_meeting_confirm(phone, _build_meeting_confirm_summary(flow_data.get('parsed', {})))
        return

    # Date fallback for meeting
    if step == 'date_fallback':
        if flow_data.get('awaiting_custom_date'):
            parsed_date = _parse_date_text(text)
            if parsed_date:
                flow_data['parsed']['date'] = parsed_date
                flow_data.pop('awaiting_custom_date', None)
                # Check if time is also missing
                if not flow_data['parsed'].get('time'):
                    flow_data['step'] = 'time_select'
                    ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
                    send_time_select(phone)
                    return
                return _finalize_new_meeting(user_id, phone, flow_data)
            send_text(phone, "❌ לא הצלחתי לזהות תאריך.\nהקלד לדוגמה: 25/3/25 או 25/03/2025 או 25.3")
            return

        resolved = _resolve_date(text, action_id)
        if resolved == 'custom':
            flow_data['awaiting_custom_date'] = True
            ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
            send_text(phone, "📅 הקלד תאריך (לדוגמה: 25/3/25 או 25/03/2025 או 25.3):")
            return
        if resolved:
            flow_data['parsed']['date'] = resolved
            if not flow_data['parsed'].get('time'):
                flow_data['step'] = 'time_select'
                ConversationFlow.set_flow(user_id, 'new_meeting', flow_data)
                send_time_select(phone)
                return
            return _finalize_new_meeting(user_id, phone, flow_data)

        send_date_fallback(phone)
        return

    # Time select for meeting
    if step == 'time_select':
        time_val = _resolve_time(text, action_id)
        if time_val:
            flow_data['parsed']['time'] = time_val
            return _finalize_new_meeting(user_id, phone, flow_data)
        send_time_select(phone)
        return


def _finalize_new_meeting(user_id, phone, flow_data):
    """Save the meeting, send Google Calendar link, then ask for participant contacts."""
    parsed = flow_data.get('parsed', {})

    try:
        meeting_date = datetime.strptime(parsed.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        meeting_date = date.today()

    meeting_data = {
        'title': parsed.get('title', ''),
        'meeting_date': meeting_date.isoformat(),
        'start_time': parsed.get('time', ''),
        'location': parsed.get('location', ''),
    }
    meeting_id = create_meeting(user_id, meeting_data)

    display_date = meeting_date.strftime('%d/%m/%Y')
    location = parsed.get('location', 'לא צוין') or 'לא צוין'
    time_str = parsed.get('time', '')
    participant_names = parsed.get('participants', [])

    parts_text = ''
    if participant_names:
        parts_text = f"\n👥 משתתפים: {', '.join(participant_names)}"

    # Build Google Calendar link
    gcal_link = _build_gcal_link(
        parsed.get('title', ''),
        meeting_date,
        time_str,
        location if location != 'לא צוין' else '',
    )

    msg = (
        f"✅ הפגישה נקבעה בהצלחה!\n\n"
        f"📌 *{parsed.get('title', '')}*\n"
        f"🗓️ תאריך: {display_date}\n"
        f"🕐 שעה: {time_str}\n"
        f"📍 מיקום: {location}"
        f"{parts_text}\n\n"
        f"📅 הוסף ליומן: {gcal_link}"
    )
    send_text(phone, msg)

    # Always enter invite flow to collect participant contacts
    if meeting_id:
        ConversationFlow.set_flow(user_id, 'meeting_invite', {
            'meeting_id': meeting_id,
            'meeting_title': parsed.get('title', ''),
            'meeting_date': meeting_date.isoformat(),
            'meeting_time': time_str,
            'location': location,
            'pending_names': participant_names,
            'invited_count': 0,
        })
        if participant_names:
            names_list = ', '.join(participant_names)
            send_text(phone,
                f"📱 שתף את אנשי הקשר של המשתתפים ואני אשלח להם הזמנה:\n"
                f"👥 {names_list}\n\n"
                f"שתף איש קשר מהטלפון 📎 או הקלד מספר טלפון.\n"
                f"שלח *סיימתי* לסיום.")
        else:
            send_text(phone,
                "📱 רוצה להזמין משתתפים לפגישה?\n"
                "שתף איש קשר מהטלפון 📎 או הקלד מספר טלפון.\n\n"
                "שלח *סיימתי* לסיום.")
    else:
        ConversationFlow.clear_flow(user_id)
        _send_next_prompt(phone)


# ---------------------------------------------------------------------------
# Legacy flows (for active sessions during deployment)
# ---------------------------------------------------------------------------

def _handle_create_task_legacy(user_id, phone, text, action_id, flow_data):
    """Legacy create_task flow - redirect to new flow."""
    # If user is mid-flow, complete it simply
    if 'title' not in flow_data:
        flow_data['title'] = text
    if flow_data.get('type') == 'today':
        flow_data.setdefault('due_date', date.today().isoformat())
        return _finalize_task_legacy(user_id, phone, flow_data)
    if 'due_date' not in flow_data:
        resolved = _resolve_date(text, action_id)
        if resolved and resolved != 'custom':
            flow_data['due_date'] = resolved
            return _finalize_task_legacy(user_id, phone, flow_data)
        send_date_select(phone)
        return
    return _finalize_task_legacy(user_id, phone, flow_data)


def _finalize_task_legacy(user_id, phone, flow_data):
    title = flow_data.get('title', '')
    due_date_str = flow_data.get('due_date', date.today().isoformat())
    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except ValueError:
        due_date = date.today()

    task_type = 'today' if due_date == date.today() else 'scheduled'
    task_data = {
        'title': title,
        'task_type': task_type,
        'due_date': due_date.isoformat(),
        'created_via': 'whatsapp_text',
    }
    task_id = create_task(user_id, task_data)
    if task_id:
        try:
            create_reminders_for_task(task_id)
        except Exception:
            pass

    ConversationFlow.clear_flow(user_id)
    display_date = due_date.strftime('%d/%m/%Y')
    msg = (
        f"✅ המשימה נשמרה!\n\n"
        f"📌 *{title}*\n"
        f"📅 תאריך יעד: {display_date}\n\n"
        f"📋 {DASHBOARD_URL}/tasks"
    )
    send_text(phone, msg)
    _send_next_prompt(phone)


def _handle_delegate_legacy(user_id, phone, text, action_id, flow_data):
    """Legacy delegation flow."""
    if 'task_title' not in flow_data:
        flow_data['task_title'] = text
        ConversationFlow.set_flow(user_id, 'delegate', flow_data)
        send_text(phone, "👤 שתף איש קשר מהטלפון 📱")
        return

    if 'assignee' not in flow_data:
        vcard_phone, vcard_name = _parse_vcard(text)
        if vcard_phone:
            flow_data['assignee'] = vcard_phone
            if vcard_name:
                flow_data['assignee_name'] = vcard_name
            flow_data['due_date'] = date.today().isoformat()
            return _finalize_delegation_legacy(user_id, phone, flow_data)
        send_text(phone, "📱 שתף איש קשר מהטלפון.")
        return

    return _finalize_delegation_legacy(user_id, phone, flow_data)


def _finalize_delegation_legacy(user_id, phone, flow_data):
    due_date_str = flow_data.get('due_date', date.today().isoformat())
    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except ValueError:
        due_date = date.today()

    task_data = {
        'title': flow_data['task_title'],
        'task_type': 'delegated',
        'due_date': due_date.isoformat(),
        'created_via': 'whatsapp_text',
    }
    task_id = create_task(user_id, task_data)
    assignee = flow_data['assignee']
    assignee_name = flow_data.get('assignee_name', '')

    if task_id:
        db = None
        try:
            db = get_db()
            db.execute(
                "INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, "
                "status, message_sent_at) VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)",
                (task_id, user_id, assignee, assignee_name or assignee),
            )
            db.commit()
        except Exception:
            if db:
                db.rollback()
        finally:
            if db:
                db.close()

    ConversationFlow.clear_flow(user_id)
    display_date = due_date.strftime('%d/%m/%Y')
    display_assignee = assignee_name or assignee
    msg = (
        f"✅ המשימה הועברה!\n\n"
        f"👤 נשלח אל: *{display_assignee}*\n"
        f"📌 *{flow_data['task_title']}*\n"
        f"📅 {display_date}\n\n"
        f"📋 {DASHBOARD_URL}/delegation"
    )
    send_text(phone, msg)
    _send_next_prompt(phone)


def _handle_meeting_legacy(user_id, phone, text, action_id, flow_data):
    """Legacy meeting flow - simplified."""
    if 'title' not in flow_data:
        flow_data['title'] = text
        ConversationFlow.set_flow(user_id, 'meeting', flow_data)
        send_date_select(phone)
        return
    if 'date' not in flow_data:
        resolved = _resolve_date(text, action_id)
        if resolved and resolved != 'custom':
            flow_data['date'] = resolved
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_time_select(phone)
            return
        send_date_select(phone)
        return
    if 'time' not in flow_data:
        time_val = _resolve_time(text, action_id)
        if time_val:
            flow_data['time'] = time_val
            flow_data['location'] = ''
            flow_data['participants'] = []
            return _finalize_meeting_legacy(user_id, phone, flow_data)
        send_time_select(phone)
        return
    if action_id == 'confirm_meeting' or text in ('1', 'כן', 'אשר'):
        return _finalize_meeting_legacy(user_id, phone, flow_data)
    _send_next_prompt(phone)


def _finalize_meeting_legacy(user_id, phone, flow_data):
    try:
        meeting_date = datetime.strptime(flow_data['date'], '%Y-%m-%d').date()
    except ValueError:
        meeting_date = date.today()

    title = flow_data.get('title', '')
    time_str = flow_data.get('time', '')
    location = flow_data.get('location', '')

    meeting_data = {
        'title': title,
        'meeting_date': meeting_date.isoformat(),
        'start_time': time_str,
        'location': location,
    }
    meeting_id = create_meeting(user_id, meeting_data)

    display_date = meeting_date.strftime('%d/%m/%Y')
    gcal_link = _build_gcal_link(title, meeting_date, time_str, location)

    msg = (
        f"✅ הפגישה נקבעה בהצלחה!\n\n"
        f"📌 *{title}*\n"
        f"🗓️ תאריך: {display_date}\n"
        f"🕐 שעה: {time_str}\n"
        f"📍 מיקום: {location or 'לא צוין'}\n\n"
        f"📅 הוסף ליומן: {gcal_link}"
    )
    send_text(phone, msg)

    # Enter invite flow to collect participant contacts
    if meeting_id:
        ConversationFlow.set_flow(user_id, 'meeting_invite', {
            'meeting_id': meeting_id,
            'meeting_title': title,
            'meeting_date': meeting_date.isoformat(),
            'meeting_time': time_str,
            'location': location,
            'pending_names': [],
            'invited_count': 0,
        })
        send_text(phone,
            "📱 רוצה להזמין משתתפים לפגישה?\n"
            "שתף איש קשר מהטלפון 📎 או הקלד מספר טלפון.\n\n"
            "שלח *סיימתי* לסיום.")
    else:
        ConversationFlow.clear_flow(user_id)
        _send_next_prompt(phone)


# ---------------------------------------------------------------------------
# Reminder / Invite response handlers
# ---------------------------------------------------------------------------

def _handle_task_done(user_id, phone):
    db = None
    try:
        db = get_db()
        task = db.execute(
            "SELECT id, title FROM tasks WHERE user_id = ? AND status = 'pending' "
            "ORDER BY due_date ASC, created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if task:
            complete_task(task['id'])
            send_text(phone, f"🎉 המשימה \"{task['title']}\" סומנה כבוצעה! ✔️")
        else:
            send_text(phone, "🎉 אין משימות פתוחות!")
    except Exception as e:
        logger.error("Error marking task done: %s", e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
    finally:
        if db:
            db.close()
    _send_next_prompt(phone)


def _handle_snooze(user_id, phone, minutes):
    db = None
    try:
        db = get_db()
        task = db.execute(
            "SELECT id, title FROM tasks WHERE user_id = ? AND status = 'pending' "
            "ORDER BY due_date ASC, created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if task:
            scheduled_time = (datetime.now() + timedelta(minutes=minutes)).isoformat()
            db.execute(
                "INSERT INTO reminders (task_id, user_id, reminder_type, scheduled_time, status, message_template) "
                "VALUES (?, ?, 'follow_up', ?, 'pending', ?)",
                (task['id'], user_id, scheduled_time, f"Snooze reminder for {task['title']}"),
            )
            db.commit()
            send_text(phone, f"⏰ תזכורת נדחתה ב-{minutes} דקות למשימה \"{task['title']}\".")
        else:
            send_text(phone, "אין משימות פתוחות לדחיית תזכורת.")
    except Exception as e:
        logger.error("Error snoozing: %s", e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
    finally:
        if db:
            db.close()


def _handle_delegation_response(user_id, phone, accepted):
    db = None
    try:
        db = get_db()
        delegation = db.execute(
            "SELECT dt.id, dt.task_id, dt.delegator_id, t.title "
            "FROM delegated_tasks dt JOIN tasks t ON dt.task_id = t.id "
            "WHERE dt.assignee_phone = ? AND dt.status = 'pending' "
            "ORDER BY dt.message_sent_at DESC LIMIT 1",
            (phone,),
        ).fetchone()
        if not delegation:
            send_text(phone, "אין הזמנות ממתינות.")
            _send_next_prompt(phone)
            return

        new_status = 'accepted' if accepted else 'rejected'
        db.execute(
            "UPDATE delegated_tasks SET status = ?, accepted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, delegation['id']),
        )
        db.commit()

        if accepted:
            send_text(phone, f"✅ קיבלת את המשימה \"{delegation['title']}\"!")
        else:
            send_text(phone, f"❌ דחית את המשימה \"{delegation['title']}\".")

        delegator = db.execute(
            "SELECT phone_number FROM users WHERE id = ?",
            (delegation['delegator_id'],),
        ).fetchone()
        if delegator:
            status_text = "קיבל/ה" if accepted else "דחה/תה"
            send_text(
                delegator['phone_number'],
                f"📬 {phone} {status_text} את המשימה \"{delegation['title']}\".",
            )
    except Exception as e:
        logger.error("Error handling delegation response: %s", e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
    finally:
        if db:
            db.close()
    _send_next_prompt(phone)


def _handle_meeting_response(user_id, phone, accepted):
    from services.meeting_service import respond_to_meeting
    db = None
    try:
        db = get_db()
        participant = db.execute(
            "SELECT mp.meeting_id, m.title, m.organizer_id "
            "FROM meeting_participants mp JOIN meetings m ON mp.meeting_id = m.id "
            "WHERE mp.phone_number = ? AND mp.status = 'pending' "
            "ORDER BY m.meeting_date ASC LIMIT 1",
            (phone,),
        ).fetchone()
        if not participant:
            send_text(phone, "אין הזמנות לפגישות ממתינות.")
            _send_next_prompt(phone)
            return

        new_status = 'accepted' if accepted else 'declined'
        respond_to_meeting(participant['meeting_id'], phone, new_status)

        if accepted:
            send_text(phone, f"✅ אישרת את הפגישה \"{participant['title']}\"!")
        else:
            send_text(phone, f"❌ דחית את הפגישה \"{participant['title']}\".")

        organizer = db.execute(
            "SELECT phone_number FROM users WHERE id = ?",
            (participant['organizer_id'],),
        ).fetchone()
        if organizer:
            status_text = "אישר/ה" if accepted else "דחה/תה"
            send_text(
                organizer['phone_number'],
                f"📬 {phone} {status_text} את הפגישה \"{participant['title']}\".",
            )
    except Exception as e:
        logger.error("Error handling meeting response: %s", e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
    finally:
        if db:
            db.close()
    _send_next_prompt(phone)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _show_tasks(user_id, phone):
    tasks = get_tasks(user_id, {'status': 'pending'})
    if not tasks:
        send_text(phone, "🎉 אין משימות פתוחות! אתה מעודכן. ✨")
        _send_next_prompt(phone)
        return

    icons = {'pending': '⏳', 'in_progress': '🔄', 'completed': '✅', 'overdue': '🔴'}
    lines = ["📋 *המשימות שלך:*\n━━━━━━━━━━━━\n"]
    for t in tasks[:10]:
        icon = icons.get(t.get('status', 'pending'), '⏳')
        title = t.get('title', 'ללא כותרת')
        due = t.get('due_date', '---') or '---'
        lines.append(f"{icon} {title} | 📅 {due}\n")

    if len(tasks) > 10:
        lines.append(f"\n...ועוד {len(tasks) - 10} משימות")

    lines.append(f"\n📋 צפה בהכל: {DASHBOARD_URL}/tasks")
    send_text(phone, ''.join(lines))
    _send_next_prompt(phone)


def _show_meetings(user_id, phone):
    db = None
    try:
        db = get_db()
        meetings = db.execute(
            "SELECT title, meeting_date, start_time, location FROM meetings "
            "WHERE organizer_id = ? AND status = 'scheduled' ORDER BY meeting_date ASC",
            (user_id,),
        ).fetchall()
    finally:
        if db:
            db.close()

    if not meetings:
        send_text(phone, "📅 אין פגישות מתוכננות.")
        _send_next_prompt(phone)
        return

    lines = ["📅 *הפגישות שלך:*\n━━━━━━━━━━━━\n"]
    for m in meetings[:10]:
        loc = f" | 📍 {m['location']}" if m['location'] else ''
        lines.append(f"📌 {m['title']} | 🗓️ {m['meeting_date']} | 🕐 {m['start_time']}{loc}\n")

    lines.append(f"\n📅 צפה בהכל: {DASHBOARD_URL}/calendar")
    send_text(phone, ''.join(lines))
    _send_next_prompt(phone)


# ---------------------------------------------------------------------------
# Task save helper
# ---------------------------------------------------------------------------

def _save_task(user_id, parsed, created_via='whatsapp_text'):
    """Save a task from parsed data and return the task_id."""
    title = parsed.get('title', '')
    due_date_str = parsed.get('due_date', date.today().isoformat())

    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        due_date = date.today()

    task_type = 'today' if due_date == date.today() else 'scheduled'
    due_time = parsed.get('due_time')
    priority = parsed.get('priority', 'medium')

    task_data = {
        'title': title,
        'task_type': task_type,
        'due_date': due_date.isoformat(),
        'due_time': due_time,
        'priority': priority,
        'created_via': created_via,
    }
    return create_task(user_id, task_data)


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_task_confirm_summary(parsed):
    """Build a confirmation summary string from parsed task data."""
    title = parsed.get('title', '')
    due_date = _format_display_date(parsed.get('due_date'))
    due_time = parsed.get('due_time', '')
    priority = parsed.get('priority', 'medium')

    priority_labels = {'low': '🟢 נמוכה', 'medium': '🟡 רגילה', 'high': '🟠 גבוהה', 'urgent': '🔴 דחוף'}
    priority_text = priority_labels.get(priority, '🟡 רגילה')

    time_str = f"\n🕐 שעה: {due_time}" if due_time else ''
    assignee = parsed.get('assignee_name')
    assignee_str = f"\n👤 להעביר: {assignee}" if assignee else ''

    return (
        f"📋 *זיהיתי:*\n\n"
        f"📌 *{title}*\n"
        f"📅 תאריך: {due_date}"
        f"{time_str}\n"
        f"⚡ עדיפות: {priority_text}"
        f"{assignee_str}\n\n"
        f"הכל נכון?"
    )


def _build_meeting_confirm_summary(parsed):
    """Build a confirmation summary for a meeting."""
    title = parsed.get('title', '')
    meeting_date = _format_display_date(parsed.get('date'))
    time_str = parsed.get('time', 'לא צוין')
    location = parsed.get('location', 'לא צוין') or 'לא צוין'
    participants = parsed.get('participants', [])

    parts_str = f"\n👥 משתתפים: {', '.join(participants)}" if participants else ''

    return (
        f"📋 *זיהיתי פגישה:*\n\n"
        f"📌 נושא: *{title}*\n"
        f"🗓️ תאריך: {meeting_date}\n"
        f"🕐 שעה: {time_str}\n"
        f"📍 מיקום: {location}"
        f"{parts_str}\n\n"
        f"לאשר?"
    )


# ---------------------------------------------------------------------------
# Date / time / location resolvers
# ---------------------------------------------------------------------------

def _resolve_date(text, action_id):
    aid = action_id or ''
    t = (text or '').strip()

    if aid == 'date_today' or t in ('1', 'היום', '📆 היום'):
        return date.today().isoformat()
    if aid == 'date_tomorrow' or t in ('2', 'מחר', '📆 מחר'):
        return (date.today() + timedelta(days=1)).isoformat()
    if aid == 'date_this_week' or t in ('3', 'סוף השבוע', '📆 סוף השבוע'):
        today = date.today()
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        return (today + timedelta(days=days_until_friday)).isoformat()
    if aid == 'date_custom' or t in ('4', 'תאריך אחר', '✏️ תאריך אחר'):
        return 'custom'

    parsed = _parse_date_text(t)
    if parsed:
        return parsed

    return None


def _resolve_time(text, action_id):
    aid = action_id or ''
    t = (text or '').strip()

    if aid.startswith('time_'):
        hour = aid.replace('time_', '')
        return f"{hour}:00"

    if re.match(r'^\d{1,2}:\d{2}$', t):
        return t

    return None


def _resolve_location(text, action_id):
    aid = action_id or ''
    t = (text or '').strip()

    LOC_MAP = {
        'loc_zoom': 'Zoom',
        'loc_phone': 'טלפון',
        'loc_office': 'משרד',
        'loc_cafe': 'בית קפה',
        'loc_other': '__custom__',
        'loc_skip': '',
    }
    if aid in LOC_MAP:
        return LOC_MAP[aid]

    TEXT_MAP = {
        '1': 'Zoom', '💻 Zoom': 'Zoom',
        '2': 'טלפון', '📞 טלפון': 'טלפון',
        '3': 'משרד', '🏢 משרד': 'משרד',
        '4': 'בית קפה', '☕ בית קפה': 'בית קפה',
        '5': '__custom__', '✏️ מיקום אחר': '__custom__',
        '6': '', '⏭️ דלג': '',
    }
    if t in TEXT_MAP:
        return TEXT_MAP[t]

    return None


def _parse_vcard(text):
    if not text or 'BEGIN:VCARD' not in text:
        return None, None

    phone = None
    name = None

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith('FN:'):
            name = line[3:].strip()
        elif line.upper().startswith('TEL'):
            colon_idx = line.rfind(':')
            if colon_idx != -1:
                raw_phone = line[colon_idx + 1:].strip()
                if raw_phone:
                    phone = _normalize_phone(raw_phone)

    return phone, name


def _normalize_phone(text):
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith('+'):
        digits = '+' + re.sub(r'[^\d]', '', cleaned[1:])
    else:
        digits = re.sub(r'[^\d]', '', cleaned)

    if not digits:
        return None

    if digits.startswith('+972') and len(digits) >= 13:
        return digits
    if digits.startswith('972') and len(digits) >= 12:
        return '+' + digits
    if digits.startswith('0') and len(digits) == 10:
        return '+972' + digits[1:]
    if len(digits) == 9 and digits.startswith('5'):
        return '+972' + digits

    if len(digits) >= 10:
        if not digits.startswith('+'):
            return '+' + digits
        return digits

    return None


def _parse_date_text(text):
    t = (text or '').strip()
    if not t:
        return None

    low = t.lower()
    if low in ('היום', 'today'):
        return date.today().isoformat()
    if low in ('מחר', 'tomorrow'):
        return (date.today() + timedelta(days=1)).isoformat()

    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue

    m = re.match(r'^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$', t)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    m2 = re.match(r'^(\d{1,2})[/.\-](\d{1,2})$', t)
    if m2:
        day, month = int(m2.group(1)), int(m2.group(2))
        today = date.today()
        try:
            d = date(today.year, month, day)
            if d < today:
                d = date(today.year + 1, month, day)
            return d.isoformat()
        except ValueError:
            pass

    return None


def _format_display_date(date_str):
    """Format a YYYY-MM-DD string to DD/MM/YYYY for display."""
    if not date_str:
        return 'לא צוין'
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        return d.strftime('%d/%m/%Y')
    except ValueError:
        return date_str


def _reminder_text(minutes):
    """Human-readable reminder text."""
    if minutes is None:
        return 'ללא תזכורת'
    if minutes >= 1440:
        return 'יום לפני'
    if minutes >= 120:
        return 'שעתיים לפני'
    if minutes >= 60:
        return 'שעה לפני'
    return f'{minutes} דקות לפני'


def _build_gcal_link(title, meeting_date, time_str, location=''):
    """Build a Google Calendar 'add event' link."""
    try:
        # Parse start time
        if time_str and ':' in time_str:
            parts = time_str.split(':')
            hour, minute = int(parts[0]), int(parts[1])
        else:
            hour, minute = 9, 0  # default 09:00

        start_dt = datetime(meeting_date.year, meeting_date.month, meeting_date.day, hour, minute)
        end_dt = start_dt + timedelta(hours=1)  # 1 hour default

        # Google Calendar date format: YYYYMMDDTHHmmSS
        date_fmt = '%Y%m%dT%H%M%S'
        dates = f"{start_dt.strftime(date_fmt)}/{end_dt.strftime(date_fmt)}"

        params = (
            f"https://calendar.google.com/calendar/render?"
            f"action=TEMPLATE"
            f"&text={quote(title)}"
            f"&dates={dates}"
        )
        if location:
            params += f"&location={quote(location)}"

        return params
    except Exception:
        # Fallback: date-only link
        date_str = meeting_date.strftime('%Y%m%d')
        return (
            f"https://calendar.google.com/calendar/render?"
            f"action=TEMPLATE&text={quote(title)}&dates={date_str}/{date_str}"
        )


def _get_flow_prompt(flow_name, flow_data):
    if flow_name == 'new_task':
        return "📝 תאר את המשימה בהודעה אחת:"
    elif flow_name == 'new_meeting':
        return "📅 תאר את הפגישה בהודעה אחת:"
    elif flow_name == 'delegate_inline':
        return "👤 שתף איש קשר מהטלפון 📱"
    # Legacy
    elif flow_name == 'create_task':
        if 'title' not in flow_data:
            return "📝 מה המשימה?"
        return "📅 לאיזה תאריך?"
    elif flow_name == 'delegate':
        if 'task_title' not in flow_data:
            return "📝 מה המשימה שתרצה להעביר?"
        if 'assignee' not in flow_data:
            return "👤 שתף איש קשר מהטלפון 📱"
        return "📅 עד מתי?"
    elif flow_name == 'meeting':
        if 'title' not in flow_data:
            return "📌 מה נושא הפגישה?"
        if 'date' not in flow_data:
            return "📅 באיזה תאריך?"
        if 'time' not in flow_data:
            return "🕐 באיזו שעה?"
        return "📍 היכן?"
    return "📝 מה תרצה לעשות?"
