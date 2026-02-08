import sqlite3
from datetime import datetime
from database import get_db


def create_meeting(organizer_id, data):
    """Create a meeting and an associated task of type 'meeting'.

    Args:
        organizer_id: The organizer's user ID.
        data: Dict with keys: title, description, meeting_date, start_time,
              end_time, location.

    Returns:
        The new meeting's ID, or None on failure.
    """
    try:
        db = get_db()
        now = datetime.now().isoformat()

        # Create the associated task first
        task_cursor = db.execute(
            """INSERT INTO tasks
               (user_id, title, description, task_type, status, priority,
                due_date, due_time, created_via, created_at, updated_at)
               VALUES (?, ?, ?, 'meeting', 'pending', 'medium', ?, ?, 'web', ?, ?)""",
            (
                organizer_id,
                data.get('title', ''),
                data.get('description', ''),
                data.get('meeting_date'),
                data.get('start_time'),
                now,
                now,
            )
        )
        task_id = task_cursor.lastrowid

        # Create the meeting record
        meeting_cursor = db.execute(
            """INSERT INTO meetings
               (task_id, organizer_id, title, description,
                meeting_date, start_time, end_time, location, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')""",
            (
                task_id,
                organizer_id,
                data.get('title', ''),
                data.get('description', ''),
                data.get('meeting_date'),
                data.get('start_time'),
                data.get('end_time'),
                data.get('location', ''),
            )
        )
        meeting_id = meeting_cursor.lastrowid

        db.commit()
        db.close()
        return meeting_id
    except Exception:
        return None


def get_meetings(user_id):
    """List all meetings for a user (as organizer).

    Args:
        user_id: The user's ID.

    Returns:
        List of meeting dicts, or empty list on failure.
    """
    try:
        db = get_db()
        rows = db.execute(
            """SELECT m.*, t.status AS task_status
               FROM meetings m
               JOIN tasks t ON m.task_id = t.id
               WHERE m.organizer_id = ?
               ORDER BY m.meeting_date ASC, m.start_time ASC""",
            (user_id,)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_meeting(meeting_id):
    """Get a single meeting with its participants.

    Args:
        meeting_id: The meeting's ID.

    Returns:
        Dict with meeting data and a 'participants' key containing a list
        of participant dicts, or None on failure.
    """
    try:
        db = get_db()
        meeting_row = db.execute(
            """SELECT m.*, t.status AS task_status
               FROM meetings m
               JOIN tasks t ON m.task_id = t.id
               WHERE m.id = ?""",
            (meeting_id,)
        ).fetchone()

        if not meeting_row:
            db.close()
            return None

        meeting = dict(meeting_row)

        participant_rows = db.execute(
            "SELECT * FROM meeting_participants WHERE meeting_id = ?",
            (meeting_id,)
        ).fetchall()
        meeting['participants'] = [dict(p) for p in participant_rows]

        db.close()
        return meeting
    except Exception:
        return None


def update_meeting(meeting_id, data):
    """Update an existing meeting's fields.

    Args:
        meeting_id: The meeting's ID.
        data: Dict of field names to new values.

    Returns:
        True on success, False on failure.
    """
    try:
        if not data:
            return False

        allowed_fields = {
            'title', 'description', 'meeting_date', 'start_time',
            'end_time', 'location', 'status',
        }
        fields_to_update = {k: v for k, v in data.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ", ".join(f"{field} = ?" for field in fields_to_update)
        values = list(fields_to_update.values())
        values.append(meeting_id)

        db = get_db()
        db.execute(
            f"UPDATE meetings SET {set_clause} WHERE id = ?",
            values
        )

        # Also update the associated task if date/time changed
        if 'title' in fields_to_update or 'meeting_date' in fields_to_update or 'start_time' in fields_to_update:
            meeting = db.execute(
                "SELECT task_id FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
            if meeting:
                task_updates = {'updated_at': datetime.now().isoformat()}
                if 'title' in fields_to_update:
                    task_updates['title'] = fields_to_update['title']
                if 'meeting_date' in fields_to_update:
                    task_updates['due_date'] = fields_to_update['meeting_date']
                if 'start_time' in fields_to_update:
                    task_updates['due_time'] = fields_to_update['start_time']

                task_set = ", ".join(f"{f} = ?" for f in task_updates)
                task_vals = list(task_updates.values())
                task_vals.append(meeting['task_id'])
                db.execute(
                    f"UPDATE tasks SET {task_set} WHERE id = ?",
                    task_vals
                )

        db.commit()
        db.close()
        return True
    except Exception:
        return False


def cancel_meeting(meeting_id):
    """Cancel a meeting and update its associated task.

    Args:
        meeting_id: The meeting's ID.

    Returns:
        True on success, False on failure.
    """
    try:
        db = get_db()
        now = datetime.now().isoformat()

        meeting = db.execute(
            "SELECT task_id FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()

        if not meeting:
            db.close()
            return False

        db.execute(
            "UPDATE meetings SET status = 'cancelled' WHERE id = ?",
            (meeting_id,)
        )
        db.execute(
            "UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now, meeting['task_id'])
        )

        db.commit()
        db.close()
        return True
    except Exception:
        return False


def add_participant(meeting_id, phone, name):
    """Add a participant to a meeting.

    Args:
        meeting_id: The meeting's ID.
        phone: The participant's phone number.
        name: The participant's name.

    Returns:
        The new participant record's ID, or None on failure.
    """
    try:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO meeting_participants
               (meeting_id, phone_number, name, status)
               VALUES (?, ?, ?, 'pending')""",
            (meeting_id, phone, name)
        )
        db.commit()
        participant_id = cursor.lastrowid
        db.close()
        return participant_id
    except Exception:
        return None


def respond_to_meeting(meeting_id, phone, response_status):
    """Update a participant's response status for a meeting.

    Args:
        meeting_id: The meeting's ID.
        phone: The participant's phone number.
        response_status: One of 'accepted', 'declined', 'tentative'.

    Returns:
        True on success, False on failure.
    """
    try:
        now = datetime.now().isoformat()
        db = get_db()
        db.execute(
            """UPDATE meeting_participants
               SET status = ?, responded_at = ?
               WHERE meeting_id = ? AND phone_number = ?""",
            (response_status, now, meeting_id, phone)
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False
