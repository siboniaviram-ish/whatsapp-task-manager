import sqlite3
from datetime import datetime, timedelta
from database import get_db


def create_reminders_for_task(task_id):
    """Auto-create reminders for a task: 1 day before, 1 hour before,
    15 minutes before, and at the due time.

    Args:
        task_id: The task's ID.

    Returns:
        List of created reminder IDs, or empty list on failure.
    """
    try:
        db = get_db()
        task = db.execute(
            "SELECT id, user_id, due_date, due_time FROM tasks WHERE id = ?",
            (task_id,)
        ).fetchone()

        if not task:
            db.close()
            return []

        if not task['due_date']:
            db.close()
            return []

        due_time_str = task['due_time'] if task['due_time'] else '09:00'
        due_datetime = datetime.strptime(
            f"{task['due_date']} {due_time_str}", "%Y-%m-%d %H:%M"
        )

        offsets = [
            (timedelta(days=1), 'before_task', 'Reminder: task due tomorrow'),
            (timedelta(hours=1), 'before_task', 'Reminder: task due in 1 hour'),
            (timedelta(minutes=15), 'before_task', 'Reminder: task due in 15 minutes'),
            (timedelta(0), 'before_task', 'Reminder: task is due now'),
        ]

        now = datetime.now()
        reminder_ids = []

        for offset, reminder_type, template in offsets:
            scheduled_time = due_datetime - offset
            if scheduled_time <= now:
                continue

            cursor = db.execute(
                """INSERT INTO reminders
                   (task_id, user_id, reminder_type, scheduled_time, status, message_template)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (
                    task_id,
                    task['user_id'],
                    reminder_type,
                    scheduled_time.isoformat(),
                    template,
                )
            )
            reminder_ids.append(cursor.lastrowid)

        db.commit()
        db.close()
        return reminder_ids
    except Exception:
        return []


def get_pending_reminders():
    """Get reminders where scheduled_time <= now and status is 'pending'.

    Returns:
        List of reminder dicts, or empty list on failure.
    """
    try:
        now = datetime.now().isoformat()
        db = get_db()
        rows = db.execute(
            """SELECT * FROM reminders
               WHERE scheduled_time <= ? AND status = 'pending'
               ORDER BY scheduled_time ASC""",
            (now,)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def mark_reminder_sent(reminder_id):
    """Mark a reminder as sent with the current timestamp.

    Args:
        reminder_id: The reminder's ID.

    Returns:
        True on success, False on failure.
    """
    try:
        now = datetime.now().isoformat()
        db = get_db()
        db.execute(
            "UPDATE reminders SET status = 'sent', sent_at = ? WHERE id = ?",
            (now, reminder_id)
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def cancel_task_reminders(task_id):
    """Cancel all pending reminders for a given task.

    Args:
        task_id: The task's ID.

    Returns:
        True on success, False on failure.
    """
    try:
        db = get_db()
        db.execute(
            "UPDATE reminders SET status = 'cancelled' WHERE task_id = ? AND status = 'pending'",
            (task_id,)
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def process_due_reminders():
    """Find all due reminders and return enriched data with reminder, task,
    and user information.

    Returns:
        List of dicts, each containing reminder, task, and user details.
        Returns empty list on failure.
    """
    try:
        now = datetime.now().isoformat()
        db = get_db()
        rows = db.execute(
            """SELECT r.id AS reminder_id,
                      r.reminder_type,
                      r.scheduled_time,
                      r.message_template,
                      t.id AS task_id,
                      t.title AS task_title,
                      t.description AS task_description,
                      t.due_date,
                      t.due_time,
                      t.priority,
                      t.status AS task_status,
                      u.id AS user_id,
                      u.phone_number,
                      u.name AS user_name,
                      u.language
               FROM reminders r
               JOIN tasks t ON r.task_id = t.id
               JOIN users u ON r.user_id = u.id
               WHERE r.scheduled_time <= ?
                 AND r.status = 'pending'
               ORDER BY r.scheduled_time ASC""",
            (now,)
        ).fetchall()
        db.close()

        results = []
        for row in rows:
            results.append({
                'reminder_id': row['reminder_id'],
                'reminder_type': row['reminder_type'],
                'scheduled_time': row['scheduled_time'],
                'message_template': row['message_template'],
                'task_id': row['task_id'],
                'task_title': row['task_title'],
                'task_description': row['task_description'],
                'due_date': row['due_date'],
                'due_time': row['due_time'],
                'priority': row['priority'],
                'task_status': row['task_status'],
                'user_id': row['user_id'],
                'phone_number': row['phone_number'],
                'user_name': row['user_name'],
                'language': row['language'],
            })

        return results
    except Exception:
        return []
