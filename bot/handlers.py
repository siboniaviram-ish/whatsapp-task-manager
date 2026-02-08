"""
WhatsApp Task Management Bot - Main Message Handlers
Full interactive flow with buttons/lists via Twilio Content API.
Voice input supported at every text-input step.
"""

import re
import logging
from datetime import date, datetime, timedelta

from config import Config
from database import get_db
from services.task_service import create_task, get_tasks, complete_task, get_today_tasks
from services.voice_service import transcribe_audio, extract_task_from_transcript
from services.meeting_service import create_meeting, add_participant
from services.reminder_service import create_reminders_for_task
from services.whatsapp_service import log_message
from services.interactive_service import (
    send_text,
    send_main_menu,
    send_voice_confirm,
    send_date_select,
    send_time_select,
    send_location_select,
    send_task_success,
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

# Map interactive button/list text → action id (fallback when payload missing)
BUTTON_TEXT_MAP = {
    # Main menu list items
    '📝 משימה להיום': 'task_today',
    '📅 משימה מתוזמנת': 'task_scheduled',
    '👥 האצלת משימה': 'task_delegate',
    '🤝 קביעת פגישה': 'schedule_meeting',
    '📋 המשימות שלי': 'my_tasks',
    # Voice confirm
    '✅ אשר': 'confirm_voice',
    '🔄 שוב': 'retry_voice',
    # Date select
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
    '➕ פגישה חדשה': 'schedule_meeting',
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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handle_incoming_message(from_number, message_body, message_type='text',
                            media_url=None, button_payload=None, list_id=None):
    try:
        user_id = _get_or_create_user(from_number)

        try:
            log_message(user_id, 'incoming', message_type, message_body or '')
        except Exception:
            pass

        # --- Voice messages ---
        if message_type == 'voice' and media_url:
            flow_name, flow_data = ConversationFlow.get_flow(user_id)
            if flow_name == 'voice_pending':
                # Re-record while confirming
                return_flow = flow_data.get('_return_flow')
                return _handle_voice_in_flow(user_id, from_number, media_url, return_flow, flow_data)
            elif flow_name == 'voice_confirm':
                # Re-record standalone voice
                return _handle_voice_standalone(user_id, from_number, media_url)
            elif flow_name:
                # Voice input during active flow
                return _handle_voice_in_flow(user_id, from_number, media_url, flow_name, flow_data)
            else:
                return _handle_voice_standalone(user_id, from_number, media_url)

        # --- Text / button messages ---
        text = (message_body or '').strip()
        action_id = _resolve_action_id(button_payload, list_id, text)

        # Cancel
        if is_cancel(text):
            ConversationFlow.clear_flow(user_id)
            send_text(from_number, "❌ הפעולה בוטלה.")
            send_main_menu(from_number)
            return

        # Active flow
        flow_name, flow_data = ConversationFlow.get_flow(user_id)
        if flow_name:
            return _handle_flow(user_id, from_number, text, action_id, flow_name, flow_data)

        # Global actions (from success buttons)
        if action_id in ('main_menu', 'my_tasks', 'new_task', 'my_meetings', 'schedule_meeting'):
            return _handle_global_action(user_id, from_number, action_id)

        # Command
        command = get_command(text) or _action_to_command(action_id)
        if command:
            return _handle_command(user_id, from_number, command)

        # Unrecognized → menu
        if not text:
            send_main_menu(from_number)
        else:
            send_text(from_number, "לא הבנתי. בחר אפשרות מהתפריט:")
            send_main_menu(from_number)

    except Exception as e:
        logger.error("Error handling message from %s: %s", from_number, e, exc_info=True)
        try:
            send_text(from_number, "❌ אירעה שגיאה. נסה שוב או שלח *תפריט*.")
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
        'task_today': 'task_today',
        'task_scheduled': 'task_scheduled',
        'task_delegate': 'task_delegate',
        'schedule_meeting': 'schedule_meeting',
        'my_tasks': 'my_tasks',
        'main_menu': 'welcome',
        'new_task': 'new_task',
        'my_meetings': 'meetings',
    }
    return mapping.get(action_id)


def _get_or_create_user(phone):
    db = None
    try:
        db = get_db()
        row = db.execute("SELECT id FROM users WHERE phone_number = ?", (phone,)).fetchone()
        if row:
            db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (row['id'],))
            db.commit()
            return row['id']
        cursor = db.execute(
            "INSERT INTO users (phone_number, whatsapp_verified, last_active) VALUES (?, 1, CURRENT_TIMESTAMP)",
            (phone,),
        )
        db.commit()
        return cursor.lastrowid
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
        send_main_menu(phone)
    elif action_id == 'my_tasks':
        _show_tasks(user_id, phone)
    elif action_id == 'new_task':
        ConversationFlow.set_flow(user_id, 'create_task', {})
        send_text(phone, "📝 מה המשימה? הקלד או הקלט הודעה קולית:")
    elif action_id == 'my_meetings':
        _show_meetings(user_id, phone)
    elif action_id == 'schedule_meeting':
        ConversationFlow.set_flow(user_id, 'meeting', {})
        send_text(phone, "📌 מה נושא הפגישה? הקלד או הקלט:")


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

def _handle_command(user_id, phone, command):
    try:
        if command == 'welcome':
            send_main_menu(phone)

        elif command in ('new_task', 'task_today'):
            data = {}
            if command == 'task_today':
                data = {'type': 'today', 'due_date': date.today().isoformat()}
            ConversationFlow.set_flow(user_id, 'create_task', data)
            send_text(phone, "📝 מה המשימה? הקלד או הקלט הודעה קולית:")

        elif command == 'task_scheduled':
            ConversationFlow.set_flow(user_id, 'create_task', {'type': 'scheduled'})
            send_text(phone, "📝 מה המשימה? הקלד או הקלט הודעה קולית:")

        elif command == 'task_delegate':
            ConversationFlow.set_flow(user_id, 'delegate', {})
            send_text(phone, "📝 מה המשימה שתרצה להעביר? הקלד או הקלט:")

        elif command == 'schedule_meeting':
            ConversationFlow.set_flow(user_id, 'meeting', {})
            send_text(phone, "📌 מה נושא הפגישה? הקלד או הקלט:")

        elif command == 'my_tasks':
            _show_tasks(user_id, phone)

        elif command == 'help':
            send_text(phone, (
                "ℹ️ *עזרה*\n━━━━━━━━━━━\n\n"
                "שלח *היי* או *תפריט* לתפריט הראשי.\n"
                "שלח הודעה קולית בכל שלב ליצירת משימה.\n"
                "שלח *ביטול* לביטול פעולה נוכחית.\n\n"
                "💡 בכל שלב ניתן להקליד טקסט או לשלוח הודעה קולית."
            ))

        elif command == 'complete':
            tasks = get_today_tasks(user_id)
            pending = [t for t in tasks if t['status'] == 'pending']
            if pending:
                complete_task(pending[0]['id'])
                send_task_success(phone, f"🎉 המשימה \"{pending[0]['title']}\" סומנה כבוצעה! ✔️")
            else:
                send_text(phone, "🎉 אין משימות פתוחות להיום!")

        elif command == 'meetings':
            _show_meetings(user_id, phone)

        else:
            send_main_menu(phone)

    except Exception as e:
        logger.error("Error handling command '%s': %s", command, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


# ---------------------------------------------------------------------------
# Voice handlers
# ---------------------------------------------------------------------------

def _handle_voice_standalone(user_id, phone, media_url):
    try:
        transcript = transcribe_audio(media_url)
        if not transcript:
            send_text(phone, "🎤 לא הצלחתי לזהות את ההודעה הקולית. נסה שוב.")
            return

        task_info = extract_task_from_transcript(transcript)
        flow_data = {
            'transcript': transcript,
            'task_title': task_info.get('title', transcript) if isinstance(task_info, dict) else transcript,
            'due_date': task_info.get('due_date', date.today().isoformat()) if isinstance(task_info, dict) else date.today().isoformat(),
        }
        ConversationFlow.set_flow(user_id, 'voice_confirm', flow_data)
        send_voice_confirm(phone, transcript)
    except Exception as e:
        logger.error("Voice error for user %s: %s", user_id, e, exc_info=True)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")


def _handle_voice_in_flow(user_id, phone, media_url, flow_name, flow_data):
    try:
        transcript = transcribe_audio(media_url)
        if not transcript:
            send_text(phone, "🎤 לא הצלחתי לזהות. נסה שוב.")
            return

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
        elif flow_name == 'create_task':
            return _handle_create_task(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'delegate':
            return _handle_delegate(user_id, phone, text, action_id, flow_data)
        elif flow_name == 'meeting':
            return _handle_meeting(user_id, phone, text, action_id, flow_data)
        else:
            ConversationFlow.clear_flow(user_id)
            send_main_menu(phone)
    except Exception as e:
        logger.error("Flow '%s' error for user %s: %s", flow_name, user_id, e, exc_info=True)
        ConversationFlow.clear_flow(user_id)
        send_text(phone, "❌ אירעה שגיאה. נסה שוב.")
        send_main_menu(phone)


# ---------------------------------------------------------------------------
# Voice pending (confirmation of voice in any flow)
# ---------------------------------------------------------------------------

def _handle_voice_pending(user_id, phone, text, action_id, flow_data):
    if action_id == 'confirm_voice' or text in ('1', 'כן', 'אשר'):
        transcript = flow_data.pop('_pending_voice', '')
        return_flow = flow_data.pop('_return_flow', None)
        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            send_main_menu(phone)
            return
        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        return _handle_flow(user_id, phone, transcript, None, return_flow, flow_data)

    elif action_id == 'retry_voice' or text in ('2', 'לא'):
        flow_data.pop('_pending_voice', None)
        return_flow = flow_data.pop('_return_flow', None)
        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            send_main_menu(phone)
            return
        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        prompt = _get_flow_prompt(return_flow, flow_data)
        send_text(phone, prompt + "\n\n🎤 שלח הודעה קולית או הקלד:")
    else:
        send_text(phone, "שלח *1* לאישור או *2* להקלטה מחדש.")


# ---------------------------------------------------------------------------
# Voice confirm (standalone voice → task)
# ---------------------------------------------------------------------------

def _handle_voice_confirm(user_id, phone, text, action_id, flow_data):
    if action_id == 'confirm_voice' or text in ('1', 'כן', 'אשר'):
        task_data = {
            'title': flow_data.get('task_title', flow_data.get('transcript', '')),
            'type': 'today',
            'due_date': flow_data.get('due_date', date.today().isoformat()),
        }
        return _finalize_task(user_id, phone, task_data)
    elif action_id == 'retry_voice' or text in ('2', 'לא'):
        ConversationFlow.clear_flow(user_id)
        send_text(phone, "🎤 שלח הודעה קולית חדשה:")
    else:
        send_text(phone, "שלח *1* לאישור או *2* להקלטה מחדש.")


# ---------------------------------------------------------------------------
# Create Task flow
# ---------------------------------------------------------------------------

def _handle_create_task(user_id, phone, text, action_id, flow_data):
    # Step 1: title
    if 'title' not in flow_data:
        flow_data['title'] = text
        if flow_data.get('type') == 'today':
            flow_data.setdefault('due_date', date.today().isoformat())
            return _finalize_task(user_id, phone, flow_data)
        # Scheduled task → ask for date
        ConversationFlow.set_flow(user_id, 'create_task', flow_data)
        send_date_select(phone)
        return

    # Step 2: date
    if 'due_date' not in flow_data:
        if flow_data.get('awaiting_custom_date'):
            parsed = _parse_date_text(text)
            if parsed:
                flow_data['due_date'] = parsed
                return _finalize_task(user_id, phone, flow_data)
            send_text(phone, "❌ לא הצלחתי לזהות תאריך.\nהקלד בפורמט: 25/03/2025")
            return

        resolved = _resolve_date(text, action_id)
        if resolved == 'custom':
            flow_data['awaiting_custom_date'] = True
            ConversationFlow.set_flow(user_id, 'create_task', flow_data)
            send_text(phone, "📅 הקלד תאריך (לדוגמה: 25/03/2025):")
            return
        if resolved:
            flow_data['due_date'] = resolved
            return _finalize_task(user_id, phone, flow_data)

        # Unrecognized → resend
        send_date_select(phone)
        return


def _finalize_task(user_id, phone, flow_data):
    title = flow_data.get('title', '')
    due_date_str = flow_data.get('due_date', date.today().isoformat())

    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except ValueError:
        try:
            due_date = datetime.strptime(due_date_str, '%d/%m/%Y').date()
        except ValueError:
            due_date = date.today()

    task_type = 'today' if due_date == date.today() else 'scheduled'
    task_data = {
        'title': title,
        'task_type': task_type,
        'due_date': due_date.isoformat(),
        'created_via': 'whatsapp',
    }
    task_id = create_task(user_id, task_data)
    if task_id:
        try:
            create_reminders_for_task(task_id)
        except Exception as e:
            logger.warning("Failed to create reminders: %s", e)

    ConversationFlow.clear_flow(user_id)

    display_date = due_date.strftime('%d/%m/%Y')
    msg = (
        f"✅ המשימה נשמרה בהצלחה!\n\n"
        f"📌 *{title}*\n"
        f"📅 תאריך יעד: {display_date}\n"
        f"⏰ תזכורת תישלח לפני מועד היעד.\n\n"
        f"📋 {DASHBOARD_URL}/tasks"
    )
    send_task_success(phone, msg)


# ---------------------------------------------------------------------------
# Delegation flow
# ---------------------------------------------------------------------------

def _handle_delegate(user_id, phone, text, action_id, flow_data):
    # Step 1: task title
    if 'task_title' not in flow_data:
        flow_data['task_title'] = text
        ConversationFlow.set_flow(user_id, 'delegate', flow_data)
        send_text(phone, "👤 למי לשלוח? שלח מספר טלפון (למשל: 0501234567):")
        return

    # Step 2: assignee
    if 'assignee' not in flow_data:
        flow_data['assignee'] = text.strip()
        ConversationFlow.set_flow(user_id, 'delegate', flow_data)
        send_date_select(phone)
        return

    # Step 3: due date
    if 'due_date' not in flow_data:
        if flow_data.get('awaiting_custom_date'):
            parsed = _parse_date_text(text)
            if parsed:
                flow_data['due_date'] = parsed
                return _finalize_delegation(user_id, phone, flow_data)
            send_text(phone, "❌ תאריך לא תקין. הקלד בפורמט: 25/03/2025")
            return

        resolved = _resolve_date(text, action_id)
        if resolved == 'custom':
            flow_data['awaiting_custom_date'] = True
            ConversationFlow.set_flow(user_id, 'delegate', flow_data)
            send_text(phone, "📅 הקלד תאריך (לדוגמה: 25/03/2025):")
            return
        if resolved:
            flow_data['due_date'] = resolved
            return _finalize_delegation(user_id, phone, flow_data)

        send_date_select(phone)
        return


def _finalize_delegation(user_id, phone, flow_data):
    due_date_str = flow_data['due_date']
    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    except ValueError:
        due_date = date.today()

    task_data = {
        'title': flow_data['task_title'],
        'task_type': 'delegated',
        'due_date': due_date.isoformat(),
        'created_via': 'whatsapp',
    }
    task_id = create_task(user_id, task_data)
    assignee = flow_data['assignee']

    if task_id:
        db = None
        try:
            db = get_db()
            db.execute(
                "INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, "
                "status, message_sent_at) VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)",
                (task_id, user_id, assignee, assignee),
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to record delegation: %s", e)
            if db:
                db.rollback()
        finally:
            if db:
                db.close()

    display_date = due_date.strftime('%d/%m/%Y')

    # Send invite to assignee
    invite_msg = (
        f"📥 קיבלת משימה חדשה!\n\n"
        f"📌 משימה: *{flow_data['task_title']}*\n"
        f"📅 תאריך יעד: {display_date}"
    )
    try:
        send_delegation_invite(assignee, invite_msg)
    except Exception as e:
        logger.warning("Failed to send delegation invite to %s: %s", assignee, e)

    ConversationFlow.clear_flow(user_id)

    msg = (
        f"✅ המשימה הועברה בהצלחה!\n\n"
        f"👤 נשלח אל: *{assignee}*\n"
        f"📌 משימה: *{flow_data['task_title']}*\n"
        f"📅 תאריך יעד: {display_date}\n\n"
        f"📋 {DASHBOARD_URL}/delegation"
    )
    send_delegate_success(phone, msg)


# ---------------------------------------------------------------------------
# Meeting flow
# ---------------------------------------------------------------------------

def _handle_meeting(user_id, phone, text, action_id, flow_data):
    # Step 1: subject
    if 'title' not in flow_data:
        flow_data['title'] = text
        ConversationFlow.set_flow(user_id, 'meeting', flow_data)
        send_date_select(phone)
        return

    # Step 2: date
    if 'date' not in flow_data:
        if flow_data.get('awaiting_custom_date'):
            parsed = _parse_date_text(text)
            if parsed:
                flow_data['date'] = parsed
                flow_data.pop('awaiting_custom_date', None)
                ConversationFlow.set_flow(user_id, 'meeting', flow_data)
                send_time_select(phone)
                return
            send_text(phone, "❌ תאריך לא תקין. הקלד בפורמט: 25/03/2025")
            return

        resolved = _resolve_date(text, action_id)
        if resolved == 'custom':
            flow_data['awaiting_custom_date'] = True
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_text(phone, "📅 הקלד תאריך (לדוגמה: 25/03/2025):")
            return
        if resolved:
            flow_data['date'] = resolved
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_time_select(phone)
            return

        send_date_select(phone)
        return

    # Step 3: time
    if 'time' not in flow_data:
        time_val = _resolve_time(text, action_id)
        if time_val:
            flow_data['time'] = time_val
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_text(phone, "👥 מי המשתתפים?\nשלח מספרי טלפון מופרדים בפסיקים:")
            return
        send_time_select(phone)
        return

    # Step 4: participants
    if 'participants' not in flow_data:
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if parts:
            flow_data['participants'] = parts
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_location_select(phone)
            return
        send_text(phone, "👥 שלח לפחות מספר טלפון אחד:")
        return

    # Step 5: location
    if 'location' not in flow_data:
        if flow_data.get('awaiting_custom_location'):
            flow_data['location'] = text.strip()
            flow_data.pop('awaiting_custom_location', None)
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_meeting_confirm(phone, _build_meeting_summary(flow_data))
            return

        loc = _resolve_location(text, action_id)
        if loc == '__custom__':
            flow_data['awaiting_custom_location'] = True
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_text(phone, "📍 הקלד את המיקום:")
            return
        if loc is not None:
            flow_data['location'] = loc
            ConversationFlow.set_flow(user_id, 'meeting', flow_data)
            send_meeting_confirm(phone, _build_meeting_summary(flow_data))
            return

        send_location_select(phone)
        return

    # Step 6: confirmation
    if action_id == 'confirm_meeting' or text in ('1', 'אשר'):
        return _finalize_meeting(user_id, phone, flow_data)
    elif action_id == 'cancel_flow' or text in ('2', 'בטל'):
        ConversationFlow.clear_flow(user_id)
        send_text(phone, "❌ הפגישה בוטלה.")
        send_main_menu(phone)
    else:
        send_meeting_confirm(phone, _build_meeting_summary(flow_data))


def _build_meeting_summary(flow_data):
    try:
        d = datetime.strptime(flow_data['date'], '%Y-%m-%d').date()
        display_date = d.strftime('%d/%m/%Y')
    except (ValueError, KeyError):
        display_date = flow_data.get('date', '')

    parts = flow_data.get('participants', [])
    loc = flow_data.get('location', 'לא צוין')
    if not loc:
        loc = 'לא צוין'

    return (
        f"📋 *סיכום פגישה:*\n\n"
        f"📌 נושא: *{flow_data.get('title', '')}*\n"
        f"🗓️ תאריך: {display_date}\n"
        f"🕐 שעה: {flow_data.get('time', '')}\n"
        f"📍 מיקום: {loc}\n"
        f"👥 משתתפים: {', '.join(parts)}"
    )


def _finalize_meeting(user_id, phone, flow_data):
    try:
        meeting_date = datetime.strptime(flow_data['date'], '%Y-%m-%d').date()
    except ValueError:
        meeting_date = date.today()

    meeting_data = {
        'title': flow_data['title'],
        'meeting_date': meeting_date.isoformat(),
        'start_time': flow_data['time'],
        'location': flow_data.get('location', ''),
    }
    meeting_id = create_meeting(user_id, meeting_data)

    display_date = meeting_date.strftime('%d/%m/%Y')
    participants = flow_data.get('participants', [])
    location = flow_data.get('location', 'לא צוין') or 'לא צוין'

    for participant in participants:
        try:
            if meeting_id:
                add_participant(meeting_id, participant, participant)
            invite_msg = (
                f"📅 הוזמנת לפגישה!\n\n"
                f"📌 נושא: *{flow_data['title']}*\n"
                f"🗓️ תאריך: {display_date}\n"
                f"🕐 שעה: {flow_data['time']}\n"
                f"📍 מיקום: {location}"
            )
            send_meeting_invite_interactive(participant, invite_msg)
        except Exception as e:
            logger.warning("Failed to invite %s: %s", participant, e)

    ConversationFlow.clear_flow(user_id)

    msg = (
        f"✅ הפגישה נקבעה בהצלחה!\n\n"
        f"📌 *{flow_data['title']}*\n"
        f"🗓️ תאריך: {display_date}\n"
        f"🕐 שעה: {flow_data['time']}\n"
        f"📍 מיקום: {location}\n"
        f"👥 הזמנות נשלחו ל-{len(participants)} משתתפים ✉️\n\n"
        f"📅 {DASHBOARD_URL}/calendar"
    )
    send_meeting_success(phone, msg)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _show_tasks(user_id, phone):
    tasks = get_tasks(user_id, {'status': 'pending'})
    if not tasks:
        send_task_success(phone, "🎉 אין משימות פתוחות! אתה מעודכן. ✨")
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
    send_task_success(phone, ''.join(lines))


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
        send_meeting_success(phone, "📅 אין פגישות מתוכננות.")
        return

    lines = ["📅 *הפגישות שלך:*\n━━━━━━━━━━━━\n"]
    for m in meetings[:10]:
        loc = f" | 📍 {m['location']}" if m['location'] else ''
        lines.append(f"📌 {m['title']} | 🗓️ {m['meeting_date']} | 🕐 {m['start_time']}{loc}\n")

    lines.append(f"\n📅 צפה בהכל: {DASHBOARD_URL}/calendar")
    send_meeting_success(phone, ''.join(lines))


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

    # Try parsing as a date directly
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


def _parse_date_text(text):
    t = (text or '').strip()
    if t.lower() in ('היום', 'today'):
        return date.today().isoformat()
    if t.lower() in ('מחר', 'tomorrow'):
        return (date.today() + timedelta(days=1)).isoformat()

    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _get_flow_prompt(flow_name, flow_data):
    if flow_name == 'create_task':
        if 'title' not in flow_data:
            return "📝 מה המשימה?"
        return "📅 לאיזה תאריך?"
    elif flow_name == 'delegate':
        if 'task_title' not in flow_data:
            return "📝 מה המשימה שתרצה להעביר?"
        if 'assignee' not in flow_data:
            return "👤 למי לשלוח? שלח מספר טלפון:"
        return "📅 עד מתי?"
    elif flow_name == 'meeting':
        if 'title' not in flow_data:
            return "📌 מה נושא הפגישה?"
        if 'date' not in flow_data:
            return "📅 באיזה תאריך?"
        if 'time' not in flow_data:
            return "🕐 באיזו שעה?"
        if 'participants' not in flow_data:
            return "👥 מי המשתתפים?"
        return "📍 היכן הפגישה?"
    return "📝 מה תרצה לעשות?"
