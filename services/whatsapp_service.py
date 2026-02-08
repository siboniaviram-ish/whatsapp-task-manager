import sqlite3
from datetime import datetime
from database import get_db
from config import Config


def send_message(to_number, body):
    """Send a WhatsApp message via Twilio.

    Gracefully handles missing credentials by logging a warning and returning
    False instead of raising an exception.

    Args:
        to_number: Recipient phone number (e.g. '+972501234567').
        body: Message text to send.

    Returns:
        Message SID string on success, None on failure or missing credentials.
    """
    try:
        account_sid = Config.TWILIO_ACCOUNT_SID
        auth_token = Config.TWILIO_AUTH_TOKEN
        from_number = Config.TWILIO_WHATSAPP_NUMBER

        if not account_sid or not auth_token:
            print("[WhatsApp Service] Twilio credentials not configured. Message not sent.")
            print(f"[WhatsApp Service] Would send to {to_number}: {body}")
            return None

        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        # Ensure WhatsApp prefix
        if not to_number.startswith('whatsapp:'):
            to_number = f"whatsapp:{to_number}"

        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to_number
        )
        return message.sid
    except ImportError:
        print("[WhatsApp Service] Twilio library not installed. Run: pip install twilio")
        return None
    except Exception as e:
        print(f"[WhatsApp Service] Error sending message: {e}")
        return None


def send_reminder(user_id, task):
    """Format and send a task reminder to a user.

    Args:
        user_id: The user's ID.
        task: Dict with task data (title, due_date, due_time, priority).

    Returns:
        Message SID on success, None on failure.
    """
    try:
        db = get_db()
        user = db.execute(
            "SELECT phone_number, name FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        db.close()

        if not user:
            return None

        name = user['name'] or 'there'
        title = task.get('task_title', task.get('title', 'Untitled task'))
        due_date = task.get('due_date', '')
        due_time = task.get('due_time', '')
        priority = task.get('priority', 'medium')

        time_str = f" at {due_time}" if due_time else ''
        priority_label = f" [{priority.upper()}]" if priority in ('high', 'urgent') else ''

        body = (
            f"Hi {name}! Reminder{priority_label}:\n"
            f"Task: {title}\n"
            f"Due: {due_date}{time_str}\n"
            f"\nReply 'done' to mark complete or 'snooze' to postpone."
        )

        sid = send_message(user['phone_number'], body)

        # Log the outgoing message
        log_message(user_id, 'outgoing', 'text', body)

        return sid
    except Exception:
        return None


def send_delegation_message(to_number, from_name, task_title, due_date):
    """Send a delegation notification to an assignee.

    Args:
        to_number: Assignee's phone number.
        from_name: Name of the person delegating.
        task_title: Title of the delegated task.
        due_date: Due date string.

    Returns:
        Message SID on success, None on failure.
    """
    try:
        due_str = f"\nDue: {due_date}" if due_date else ''

        body = (
            f"Hi! {from_name} has assigned you a task:\n"
            f"Task: {task_title}{due_str}\n"
            f"\nReply 'accept' to confirm or 'decline' to reject."
        )

        return send_message(to_number, body)
    except Exception:
        return None


def send_meeting_invite(to_number, meeting_data):
    """Send a meeting invitation message.

    Args:
        to_number: Participant's phone number.
        meeting_data: Dict with meeting info (title, meeting_date, start_time,
                      end_time, location, description).

    Returns:
        Message SID on success, None on failure.
    """
    try:
        title = meeting_data.get('title', 'Meeting')
        meeting_date = meeting_data.get('meeting_date', '')
        start_time = meeting_data.get('start_time', '')
        location = meeting_data.get('location', '')

        location_str = f"\n📍 מיקום: {location}" if location else ''

        body = (
            f"📅 הוזמנת לפגישה!\n\n"
            f"📌 נושא: *{title}*\n"
            f"🗓️ תאריך: {meeting_date}\n"
            f"🕐 שעה: {start_time}"
            f"{location_str}\n\n"
            f"1️⃣ *מאשר*\n"
            f"2️⃣ *לא יכול*"
        )

        return send_message(to_number, body)
    except Exception:
        return None


def log_message(user_id, direction, message_type, content):
    """Log a WhatsApp message to the message_log table.

    Args:
        user_id: The user's ID.
        direction: 'incoming' or 'outgoing'.
        message_type: 'text', 'voice', 'image', or 'interactive'.
        content: The message content.

    Returns:
        The log entry's ID, or None on failure.
    """
    try:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO message_log
               (user_id, direction, message_type, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, direction, message_type, content, datetime.now().isoformat())
        )
        db.commit()
        log_id = cursor.lastrowid
        db.close()
        return log_id
    except Exception:
        return None
