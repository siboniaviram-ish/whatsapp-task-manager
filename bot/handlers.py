"""
WhatsApp Task Management Bot - Main Message Handlers
Routes incoming WhatsApp messages to the appropriate logic:
commands, active conversation flows, voice messages, or help.
"""

import logging
from datetime import date, datetime

from config import Config
from database import get_db
from services.task_service import (
    create_task,
    get_tasks,
    complete_task,
    get_today_tasks,
    get_delegated_tasks,
    get_tasks_stats,
)
from services.whatsapp_service import send_message, send_delegation_message, send_meeting_invite, log_message
from services.voice_service import transcribe_audio, extract_task_from_transcript
from services.meeting_service import create_meeting, add_participant
from services.reminder_service import create_reminders_for_task

from bot.templates import (
    WELCOME,
    MAIN_MENU,
    TASK_CREATED,
    TASK_COMPLETED,
    VOICE_CONFIRMED,
    VOICE_FLOW_CONFIRM,
    VOICE_FAILED,
    DELEGATION_SENT,
    DELEGATION_RECEIVED,
    MEETING_CREATED,
    MEETING_INVITE,
    TASKS_LIST,
    TASK_ITEM,
    NO_TASKS,
    ERROR,
    HELP,
    PROMPT_TASK_TITLE,
    PROMPT_TASK_DATE,
    PROMPT_DELEGATE_CONTACT,
    PROMPT_DELEGATE_TASK,
    PROMPT_DELEGATE_DATE,
    PROMPT_MEETING_SUBJECT,
    PROMPT_MEETING_DATE,
    PROMPT_MEETING_TIME,
    PROMPT_MEETING_PARTICIPANTS,
    PROMPT_MEETING_LOCATION,
    PROMPT_VOICE_INSTRUCTION,
    FLOW_CANCELLED,
)
from bot.commands import get_command, is_cancel, get_confirmation
from bot.flows import ConversationFlow

logger = logging.getLogger(__name__)

DASHBOARD_URL = Config.APP_URL


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def handle_incoming_message(from_number, message_body, message_type='text', media_url=None):
    """
    Main entry point for incoming WhatsApp messages.
    """
    try:
        # 1. Get or create the user
        user_id = _get_or_create_user(from_number)

        # 2. Log the incoming message
        try:
            log_message(user_id, 'incoming', message_type, message_body)
        except Exception as e:
            logger.warning("Failed to log incoming message: %s", e)

        # 3. Handle voice messages
        if message_type == 'voice' and media_url:
            # Check if user is in an active flow
            flow_name, flow_data = ConversationFlow.get_flow(user_id)
            if flow_name and flow_name not in ('voice_confirm', 'voice_pending'):
                return _handle_voice_in_flow(user_id, from_number, media_url, flow_name, flow_data)
            else:
                return _handle_voice(user_id, from_number, media_url)

        # Normalize text
        text = message_body.strip() if message_body else ''

        if not text:
            response = WELCOME + "\n\n" + MAIN_MENU
            send_message(from_number, response)
            return response

        # 4. Check for cancel keywords (abort any active flow)
        if is_cancel(text):
            ConversationFlow.clear_flow(user_id)
            response = FLOW_CANCELLED + "\n\n" + MAIN_MENU
            send_message(from_number, response)
            return response

        # 5. Check active conversation flow
        flow_name, flow_data = ConversationFlow.get_flow(user_id)

        if flow_name:
            return _handle_flow(user_id, from_number, text, flow_name, flow_data)

        # 6. Parse as command
        command = get_command(text)
        if command:
            return _handle_command(user_id, from_number, command)

        # 7. Unrecognized input -- show help
        response = HELP + "\n\n" + MAIN_MENU
        send_message(from_number, response)
        return response

    except Exception as e:
        logger.error("Error handling message from %s: %s", from_number, e, exc_info=True)
        try:
            send_message(from_number, ERROR)
        except Exception:
            pass
        return ERROR


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def _get_or_create_user(phone):
    """Find a user by phone number or create a new one."""
    db = None
    try:
        db = get_db()
        row = db.execute(
            "SELECT id FROM users WHERE phone_number = ?", (phone,)
        ).fetchone()

        if row:
            db.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?",
                (row['id'],)
            )
            db.commit()
            return row['id']

        cursor = db.execute(
            "INSERT INTO users (phone_number, whatsapp_verified, last_active) "
            "VALUES (?, 1, CURRENT_TIMESTAMP)",
            (phone,)
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
# Command handler
# ---------------------------------------------------------------------------

def _handle_command(user_id, phone, command):
    """Route a recognized command to the appropriate action."""
    try:
        if command == 'welcome':
            response = WELCOME + "\n\n" + MAIN_MENU
            send_message(phone, response)
            return response

        elif command == 'help':
            response = HELP + "\n\n" + MAIN_MENU
            send_message(phone, response)
            return response

        elif command == 'new_task' or command == 'task_today':
            if command == 'task_today':
                ConversationFlow.set_flow(user_id, 'create_task', {
                    'due_date': date.today().strftime('%d/%m/%Y')
                })
            else:
                ConversationFlow.set_flow(user_id, 'create_task', {})
            response = PROMPT_TASK_TITLE
            send_message(phone, response)
            return response

        elif command == 'task_scheduled':
            ConversationFlow.set_flow(user_id, 'create_task', {})
            response = PROMPT_TASK_TITLE
            send_message(phone, response)
            return response

        elif command == 'task_delegate':
            ConversationFlow.set_flow(user_id, 'delegate_task', {})
            response = PROMPT_DELEGATE_TASK
            send_message(phone, response)
            return response

        elif command == 'schedule_meeting':
            ConversationFlow.set_flow(user_id, 'schedule_meeting', {})
            response = PROMPT_MEETING_SUBJECT
            send_message(phone, response)
            return response

        elif command == 'voice_task':
            response = PROMPT_VOICE_INSTRUCTION
            send_message(phone, response)
            return response

        elif command == 'my_tasks':
            tasks = get_tasks(user_id)
            response = _format_tasks_list(tasks)
            send_message(phone, response)
            return response

        elif command == 'complete':
            tasks = get_today_tasks(user_id)
            pending = [t for t in tasks if t['status'] == 'pending']
            if pending:
                complete_task(pending[0]['id'])
                response = TASK_COMPLETED
            else:
                response = NO_TASKS
            send_message(phone, response)
            return response

        elif command == 'reminders':
            tasks = get_today_tasks(user_id)
            response = _format_tasks_list(tasks)
            send_message(phone, response)
            return response

        elif command == 'meetings':
            db = None
            try:
                db = get_db()
                meetings = db.execute(
                    "SELECT m.title, m.meeting_date, m.start_time, m.location, m.status "
                    "FROM meetings m WHERE m.organizer_id = ? AND m.status = 'scheduled' "
                    "ORDER BY m.meeting_date ASC",
                    (user_id,)
                ).fetchall()
            finally:
                if db:
                    db.close()

            if meetings:
                lines = ["📅 *הפגישות שלך:*\n━━━━━━━━━━━━━━━\n"]
                for m in meetings:
                    location = m['location'] if m['location'] else ''
                    loc_str = f" | 📍 {location}" if location else ''
                    lines.append(
                        f"📌 {m['title']} | 🗓️ {m['meeting_date']} | 🕐 {m['start_time']}{loc_str}\n"
                    )
                response = ''.join(lines)
            else:
                response = "📅 אין פגישות מתוכננות."
            send_message(phone, response)
            return response

        else:
            response = HELP + "\n\n" + MAIN_MENU
            send_message(phone, response)
            return response

    except Exception as e:
        logger.error("Error handling command '%s' for user %s: %s", command, user_id, e, exc_info=True)
        send_message(phone, ERROR)
        return ERROR


# ---------------------------------------------------------------------------
# Voice handler
# ---------------------------------------------------------------------------

def _handle_voice(user_id, phone, media_url):
    """Process an incoming voice message: transcribe, extract task, ask for confirmation."""
    try:
        transcript = transcribe_audio(media_url)

        if not transcript:
            send_message(phone, VOICE_FAILED)
            return VOICE_FAILED

        task_info = extract_task_from_transcript(transcript)

        flow_data = {
            'transcript': transcript,
            'task_title': task_info.get('title', transcript) if isinstance(task_info, dict) else transcript,
            'due_date': task_info.get('due_date', date.today().strftime('%d/%m/%Y')) if isinstance(task_info, dict) else date.today().strftime('%d/%m/%Y'),
        }
        ConversationFlow.set_flow(user_id, 'voice_confirm', flow_data)

        response = VOICE_CONFIRMED.format(transcript=transcript)
        send_message(phone, response)
        return response

    except Exception as e:
        logger.error("Error handling voice from user %s: %s", user_id, e, exc_info=True)
        send_message(phone, ERROR)
        return ERROR


def _handle_voice_in_flow(user_id, phone, media_url, flow_name, flow_data):
    """Handle voice message received while in an active conversation flow."""
    try:
        transcript = transcribe_audio(media_url)

        if not transcript:
            send_message(phone, VOICE_FAILED)
            return VOICE_FAILED

        # Store voice data and original flow
        flow_data['_pending_voice'] = transcript
        flow_data['_return_flow'] = flow_name
        ConversationFlow.set_flow(user_id, 'voice_pending', flow_data)

        response = VOICE_FLOW_CONFIRM.format(transcript=transcript)
        send_message(phone, response)
        return response

    except Exception as e:
        logger.error("Error handling voice in flow for user %s: %s", user_id, e, exc_info=True)
        send_message(phone, ERROR)
        return ERROR


# ---------------------------------------------------------------------------
# Flow handler (dispatcher)
# ---------------------------------------------------------------------------

def _handle_flow(user_id, phone, text, flow_name, flow_data):
    """Continue an active conversation flow based on its current state."""
    try:
        if flow_name == 'voice_pending':
            return _handle_voice_pending(user_id, phone, text, flow_data)

        elif flow_name in ('create_task', 'create_task_date'):
            return _handle_create_task_flow(user_id, phone, text, flow_data)

        elif flow_name in ('delegate_task', 'delegate_contact', 'delegate_details'):
            return _handle_delegate_flow(user_id, phone, text, flow_data)

        elif flow_name in ('schedule_meeting', 'meeting_contact', 'meeting_time', 'meeting_subject', 'meeting_location'):
            return _handle_meeting_flow(user_id, phone, text, flow_data)

        elif flow_name == 'voice_confirm':
            return _handle_voice_confirm_flow(user_id, phone, text, flow_data)

        else:
            ConversationFlow.clear_flow(user_id)
            response = MAIN_MENU
            send_message(phone, response)
            return response

    except Exception as e:
        logger.error("Error in flow '%s' for user %s: %s", flow_name, user_id, e, exc_info=True)
        ConversationFlow.clear_flow(user_id)
        send_message(phone, ERROR)
        return ERROR


# ---------------------------------------------------------------------------
# Voice pending handler (confirmation of voice in active flow)
# ---------------------------------------------------------------------------

def _handle_voice_pending(user_id, phone, text, flow_data):
    """Handle response to voice transcription confirmation in an active flow."""
    cleaned = text.strip()

    if cleaned in ('1', 'כן', 'אשר'):
        # Confirmed - continue with transcription
        transcript = flow_data.pop('_pending_voice', '')
        return_flow = flow_data.pop('_return_flow', None)

        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            response = MAIN_MENU
            send_message(phone, response)
            return response

        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        return _handle_flow(user_id, phone, transcript, return_flow, flow_data)

    elif cleaned in ('2', 'לא'):
        # Denied - go back to original prompt
        flow_data.pop('_pending_voice', None)
        return_flow = flow_data.pop('_return_flow', None)

        if not return_flow:
            ConversationFlow.clear_flow(user_id)
            response = MAIN_MENU
            send_message(phone, response)
            return response

        ConversationFlow.set_flow(user_id, return_flow, flow_data)
        response = _get_step_prompt(return_flow, flow_data)
        send_message(phone, response)
        return response

    else:
        response = "שלח *1* לאישור או *2* להקלדה/הקלטה מחדש."
        send_message(phone, response)
        return response


def _get_step_prompt(flow_name, flow_data):
    """Return the appropriate prompt for the current step in a flow."""
    if flow_name in ('create_task', 'create_task_date'):
        if 'title' not in flow_data:
            return PROMPT_TASK_TITLE
        return PROMPT_TASK_DATE
    elif flow_name in ('delegate_task', 'delegate_contact', 'delegate_details'):
        if 'task_title' not in flow_data:
            return PROMPT_DELEGATE_TASK
        elif 'assignee' not in flow_data:
            return PROMPT_DELEGATE_CONTACT
        return PROMPT_DELEGATE_DATE
    elif flow_name in ('schedule_meeting', 'meeting_contact', 'meeting_time', 'meeting_subject', 'meeting_location'):
        if 'title' not in flow_data:
            return PROMPT_MEETING_SUBJECT
        elif 'date' not in flow_data:
            return PROMPT_MEETING_DATE
        elif 'time' not in flow_data:
            return PROMPT_MEETING_TIME
        elif 'participants' not in flow_data:
            return PROMPT_MEETING_PARTICIPANTS
        return PROMPT_MEETING_LOCATION
    return PROMPT_TASK_TITLE


# ---------------------------------------------------------------------------
# Task creation flow
# ---------------------------------------------------------------------------

def _handle_create_task_flow(user_id, phone, text, flow_data):
    """Handle the multi-step task creation flow."""
    if 'title' not in flow_data:
        # Step 1: We received the task title
        flow_data['title'] = text

        # If we already have a due_date (e.g. "task_today"), create immediately
        if 'due_date' in flow_data:
            return _finalize_task_creation(user_id, phone, flow_data)

        # Otherwise ask for the date
        ConversationFlow.set_flow(user_id, 'create_task_date', flow_data)
        response = PROMPT_TASK_DATE
        send_message(phone, response)
        return response

    else:
        # Step 2: We received the due date
        due_date_str = text.strip()

        if due_date_str in ('היום', 'today'):
            flow_data['due_date'] = date.today().strftime('%d/%m/%Y')
        else:
            flow_data['due_date'] = due_date_str

        return _finalize_task_creation(user_id, phone, flow_data)


def _finalize_task_creation(user_id, phone, flow_data):
    """Create the task in the database and send confirmation."""
    title = flow_data['title']
    due_date_str = flow_data.get('due_date', date.today().strftime('%d/%m/%Y'))

    # Parse date
    try:
        due_date = datetime.strptime(due_date_str, '%d/%m/%Y').date()
    except ValueError:
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
    task = create_task(user_id, task_data)

    try:
        task_id = task if isinstance(task, int) else task.get('id') if isinstance(task, dict) else None
        if task_id:
            create_reminders_for_task(task_id)
    except Exception as e:
        logger.warning("Failed to create reminders for task: %s", e)

    ConversationFlow.clear_flow(user_id)

    display_date = due_date.strftime('%d/%m/%Y')
    response = TASK_CREATED.format(title=title, due_date=display_date, dashboard_url=DASHBOARD_URL)
    send_message(phone, response)
    return response


# ---------------------------------------------------------------------------
# Delegation flow
# ---------------------------------------------------------------------------

def _handle_delegate_flow(user_id, phone, text, flow_data):
    """Handle the multi-step task delegation flow."""
    if 'task_title' not in flow_data:
        # Step 1: collect the task description
        flow_data['task_title'] = text
        ConversationFlow.set_flow(user_id, 'delegate_contact', flow_data)
        response = PROMPT_DELEGATE_CONTACT
        send_message(phone, response)
        return response

    elif 'assignee' not in flow_data:
        # Step 2: collect the assignee contact
        flow_data['assignee'] = text.strip()
        ConversationFlow.set_flow(user_id, 'delegate_details', flow_data)
        response = PROMPT_DELEGATE_DATE
        send_message(phone, response)
        return response

    else:
        # Step 3: collect due date and finalize
        due_date_str = text.strip()
        if due_date_str in ('היום', 'today'):
            due_date_str = date.today().strftime('%d/%m/%Y')
        flow_data['due_date'] = due_date_str

        try:
            due_date = datetime.strptime(due_date_str, '%d/%m/%Y').date()
        except ValueError:
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
        task = create_task(user_id, task_data)

        task_id = task if isinstance(task, int) else task.get('id') if isinstance(task, dict) else None
        assignee = flow_data['assignee']

        if task_id:
            db = None
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, "
                    "status, message_sent_at) VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)",
                    (task_id, user_id, assignee, assignee)
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
        try:
            delegator_name = phone
            send_delegation_message(assignee, delegator_name, flow_data['task_title'], display_date)
        except Exception as e:
            logger.warning("Failed to send delegation message to %s: %s", assignee, e)

        ConversationFlow.clear_flow(user_id)

        response = DELEGATION_SENT.format(
            assignee_name=assignee,
            task_title=flow_data['task_title'],
            due_date=display_date,
            dashboard_url=DASHBOARD_URL,
        )
        send_message(phone, response)
        return response


# ---------------------------------------------------------------------------
# Meeting flow
# ---------------------------------------------------------------------------

def _handle_meeting_flow(user_id, phone, text, flow_data):
    """Handle the multi-step meeting scheduling flow with location."""
    if 'title' not in flow_data:
        # Step 1: collect meeting subject
        flow_data['title'] = text
        ConversationFlow.set_flow(user_id, 'meeting_time', flow_data)
        response = PROMPT_MEETING_DATE
        send_message(phone, response)
        return response

    elif 'date' not in flow_data:
        # Step 2: collect meeting date
        date_str = text.strip()
        if date_str in ('היום', 'today'):
            date_str = date.today().strftime('%d/%m/%Y')
        flow_data['date'] = date_str
        ConversationFlow.set_flow(user_id, 'meeting_time', flow_data)
        response = PROMPT_MEETING_TIME
        send_message(phone, response)
        return response

    elif 'time' not in flow_data:
        # Step 3: collect meeting time
        flow_data['time'] = text.strip()
        ConversationFlow.set_flow(user_id, 'meeting_contact', flow_data)
        response = PROMPT_MEETING_PARTICIPANTS
        send_message(phone, response)
        return response

    elif 'participants' not in flow_data:
        # Step 4: collect participants
        participants_raw = text.strip()
        flow_data['participants'] = [p.strip() for p in participants_raw.split(',') if p.strip()]
        ConversationFlow.set_flow(user_id, 'meeting_location', flow_data)
        response = PROMPT_MEETING_LOCATION
        send_message(phone, response)
        return response

    else:
        # Step 5: collect location and finalize
        location = text.strip()
        if location in ('ללא', 'אין', 'none', '-'):
            location = ''
        flow_data['location'] = location

        # Parse date
        try:
            meeting_date = datetime.strptime(flow_data['date'], '%d/%m/%Y').date()
        except ValueError:
            try:
                meeting_date = datetime.strptime(flow_data['date'], '%Y-%m-%d').date()
            except ValueError:
                meeting_date = date.today()

        # Create the meeting
        meeting_data = {
            'title': flow_data['title'],
            'meeting_date': meeting_date.isoformat(),
            'start_time': flow_data['time'],
            'location': location,
        }
        meeting = create_meeting(user_id, meeting_data)

        meeting_id = meeting if isinstance(meeting, int) else meeting.get('id') if isinstance(meeting, dict) else None

        # Add participants and send invites
        display_date = meeting_date.strftime('%d/%m/%Y')
        participants = flow_data.get('participants', [])
        for participant in participants:
            try:
                if meeting_id:
                    add_participant(meeting_id, participant, participant)
                invite_data = {
                    'title': flow_data['title'],
                    'meeting_date': display_date,
                    'start_time': flow_data['time'],
                    'location': location or 'לא צוין',
                }
                send_meeting_invite(participant, invite_data)
            except Exception as e:
                logger.warning("Failed to invite participant %s: %s", participant, e)

        ConversationFlow.clear_flow(user_id)

        response = MEETING_CREATED.format(
            title=flow_data['title'],
            date=display_date,
            time=flow_data['time'],
            location=location or 'לא צוין',
            dashboard_url=DASHBOARD_URL,
        )
        send_message(phone, response)
        return response


# ---------------------------------------------------------------------------
# Voice confirmation flow
# ---------------------------------------------------------------------------

def _handle_voice_confirm_flow(user_id, phone, text, flow_data):
    """Handle confirmation of a voice-transcribed task."""
    cleaned = text.strip()

    if cleaned in ('1', 'כן', 'אשר'):
        return _finalize_task_creation(user_id, phone, {
            'title': flow_data.get('task_title', flow_data.get('transcript', '')),
            'due_date': flow_data.get('due_date', date.today().strftime('%d/%m/%Y')),
        })
    elif cleaned in ('2', 'לא'):
        ConversationFlow.clear_flow(user_id)
        response = FLOW_CANCELLED + "\n\n" + MAIN_MENU
        send_message(phone, response)
        return response
    else:
        response = "שלח *1* לאישור או *2* לביטול."
        send_message(phone, response)
        return response


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_tasks_list(tasks):
    """Format a list of task records for WhatsApp display."""
    if not tasks:
        return NO_TASKS

    status_icons = {
        'pending': '⏳',
        'in_progress': '🔄',
        'completed': '✅',
        'cancelled': '❌',
        'overdue': '🔴',
    }

    lines = [TASKS_LIST]

    for task in tasks:
        title = task['title'] if 'title' in task.keys() else 'ללא כותרת'
        due_date = task['due_date'] if 'due_date' in task.keys() else '---'
        status = task['status'] if 'status' in task.keys() else 'pending'
        icon = status_icons.get(status, '⏳')

        lines.append(TASK_ITEM.format(
            status_icon=icon,
            title=title,
            due_date=due_date or '---',
        ))

    return ''.join(lines)
