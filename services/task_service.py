import sqlite3
from datetime import datetime, date
from database import get_db


def get_tasks(user_id, filters=None):
    """List tasks for a user with optional filters.

    Args:
        user_id: The user's ID.
        filters: Optional dict with keys: status, task_type, due_date, category, search.

    Returns:
        List of task dicts, or empty list on failure.
    """
    try:
        db = get_db()
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params = [user_id]

        if filters:
            if filters.get('status'):
                query += " AND status = ?"
                params.append(filters['status'])

            if filters.get('task_type'):
                query += " AND task_type = ?"
                params.append(filters['task_type'])

            if filters.get('due_date'):
                query += " AND due_date = ?"
                params.append(filters['due_date'])

            if filters.get('category'):
                query += " AND category = ?"
                params.append(filters['category'])

            if filters.get('search'):
                query += " AND (title LIKE ? OR description LIKE ?)"
                search_term = f"%{filters['search']}%"
                params.append(search_term)
                params.append(search_term)

        query += " ORDER BY created_at DESC"

        rows = db.execute(query, params).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_task(task_id):
    """Get a single task by ID.

    Args:
        task_id: The task's ID.

    Returns:
        Task dict, or None on failure.
    """
    try:
        db = get_db()
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        db.close()
        if row:
            return dict(row)
        return None
    except Exception:
        return None


def create_task(user_id, data):
    """Create a new task.

    Args:
        user_id: The user's ID.
        data: Dict with keys: title, description, task_type, priority, category,
              due_date, due_time, created_via, voice_transcript.

    Returns:
        The new task's ID, or None on failure.
    """
    try:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO tasks
               (user_id, title, description, task_type, priority, category,
                due_date, due_time, created_via, voice_transcript, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                data.get('title', ''),
                data.get('description', ''),
                data.get('task_type', 'today'),
                data.get('priority', 'medium'),
                data.get('category', 'general'),
                data.get('due_date'),
                data.get('due_time'),
                data.get('created_via', 'web'),
                data.get('voice_transcript'),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            )
        )
        db.commit()
        task_id = cursor.lastrowid
        db.close()
        return task_id
    except Exception:
        return None


def update_task(task_id, data):
    """Update an existing task's fields.

    Args:
        task_id: The task's ID.
        data: Dict of field names to new values.

    Returns:
        True on success, False on failure.
    """
    try:
        if not data:
            return False

        allowed_fields = {
            'title', 'description', 'task_type', 'status', 'priority',
            'category', 'due_date', 'due_time', 'recurrence_pattern',
        }
        fields_to_update = {k: v for k, v in data.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        fields_to_update['updated_at'] = datetime.now().isoformat()

        set_clause = ", ".join(f"{field} = ?" for field in fields_to_update)
        values = list(fields_to_update.values())
        values.append(task_id)

        db = get_db()
        db.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            values
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def delete_task(task_id):
    """Delete a task by ID.

    Args:
        task_id: The task's ID.

    Returns:
        True on success, False on failure.
    """
    try:
        db = get_db()
        db.execute("DELETE FROM reminders WHERE task_id = ?", (task_id,))
        db.execute("DELETE FROM delegated_tasks WHERE task_id = ?", (task_id,))
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def complete_task(task_id):
    """Mark a task as completed with a timestamp.

    Args:
        task_id: The task's ID.

    Returns:
        True on success, False on failure.
    """
    try:
        now = datetime.now().isoformat()
        db = get_db()
        db.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, task_id)
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def get_today_tasks(user_id):
    """Get all tasks due today for a user.

    Args:
        user_id: The user's ID.

    Returns:
        List of task dicts, or empty list on failure.
    """
    try:
        today = date.today().isoformat()
        db = get_db()
        rows = db.execute(
            """SELECT * FROM tasks
               WHERE user_id = ? AND due_date = ?
               ORDER BY due_time ASC, priority DESC""",
            (user_id, today)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_overdue_tasks(user_id):
    """Get tasks past their due date that are not completed or cancelled.

    Args:
        user_id: The user's ID.

    Returns:
        List of task dicts, or empty list on failure.
    """
    try:
        today = date.today().isoformat()
        db = get_db()
        rows = db.execute(
            """SELECT * FROM tasks
               WHERE user_id = ?
                 AND due_date < ?
                 AND status NOT IN ('completed', 'cancelled')
               ORDER BY due_date ASC""",
            (user_id, today)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_delegated_tasks(user_id):
    """Get tasks delegated by a user, joined with delegation details.

    Args:
        user_id: The user's ID (the delegator).

    Returns:
        List of task dicts with delegation info, or empty list on failure.
    """
    try:
        db = get_db()
        rows = db.execute(
            """SELECT t.*, d.assignee_phone, d.assignee_name,
                      d.status AS delegation_status, d.message_sent_at,
                      d.accepted_at, d.completed_at AS delegation_completed_at,
                      d.follow_up_count
               FROM tasks t
               JOIN delegated_tasks d ON t.id = d.task_id
               WHERE d.delegator_id = ?
               ORDER BY t.created_at DESC""",
            (user_id,)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_tasks_stats(user_id):
    """Get task statistics for a user.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with active_count, completed_count, overdue_count, delegated_count.
    """
    try:
        today = date.today().isoformat()
        db = get_db()

        active_count = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status IN ('pending', 'in_progress')",
            (user_id,)
        ).fetchone()[0]

        completed_count = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'",
            (user_id,)
        ).fetchone()[0]

        overdue_count = db.execute(
            """SELECT COUNT(*) FROM tasks
               WHERE user_id = ?
                 AND due_date < ?
                 AND status NOT IN ('completed', 'cancelled')""",
            (user_id, today)
        ).fetchone()[0]

        delegated_count = db.execute(
            "SELECT COUNT(*) FROM delegated_tasks WHERE delegator_id = ?",
            (user_id,)
        ).fetchone()[0]

        db.close()

        return {
            'active_count': active_count,
            'completed_count': completed_count,
            'overdue_count': overdue_count,
            'delegated_count': delegated_count,
        }
    except Exception:
        return {
            'active_count': 0,
            'completed_count': 0,
            'overdue_count': 0,
            'delegated_count': 0,
        }
