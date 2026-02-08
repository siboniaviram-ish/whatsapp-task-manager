import sqlite3
import calendar
from datetime import datetime, date, timedelta
from database import get_db


def get_dashboard_overview(user_id):
    """Get a high-level dashboard overview for a user.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with total_tasks, completed, pending, overdue, completion_rate.
    """
    try:
        today = date.today().isoformat()
        db = get_db()

        total_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        completed = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'",
            (user_id,)
        ).fetchone()[0]

        pending = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status IN ('pending', 'in_progress')",
            (user_id,)
        ).fetchone()[0]

        overdue = db.execute(
            """SELECT COUNT(*) FROM tasks
               WHERE user_id = ?
                 AND due_date < ?
                 AND status NOT IN ('completed', 'cancelled')""",
            (user_id, today)
        ).fetchone()[0]

        db.close()

        completion_rate = (completed / total_tasks * 100) if total_tasks > 0 else 0.0

        return {
            'total_tasks': total_tasks,
            'completed': completed,
            'pending': pending,
            'overdue': overdue,
            'completion_rate': round(completion_rate, 1),
        }
    except Exception:
        return {
            'total_tasks': 0,
            'completed': 0,
            'pending': 0,
            'overdue': 0,
            'completion_rate': 0.0,
        }


def get_weekly_performance(user_id):
    """Get daily completed/created counts for the current week (Mon-Sun).

    Args:
        user_id: The user's ID.

    Returns:
        List of 7 dicts, each with keys: day, completed, created.
    """
    try:
        today = date.today()
        # Monday = 0, so start of week is today - weekday
        start_of_week = today - timedelta(days=today.weekday())

        db = get_db()
        results = []

        for i in range(7):
            current_day = start_of_week + timedelta(days=i)
            day_str = current_day.isoformat()

            completed = db.execute(
                """SELECT COUNT(*) FROM tasks
                   WHERE user_id = ?
                     AND DATE(completed_at) = ?""",
                (user_id, day_str)
            ).fetchone()[0]

            created = db.execute(
                """SELECT COUNT(*) FROM tasks
                   WHERE user_id = ?
                     AND DATE(created_at) = ?""",
                (user_id, day_str)
            ).fetchone()[0]

            results.append({
                'day': current_day.strftime('%A'),
                'completed': completed,
                'created': created,
            })

        db.close()
        return results
    except Exception:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return [{'day': d, 'completed': 0, 'created': 0} for d in days]


def get_completion_rate(user_id):
    """Calculate the completion rate as a percentage.

    Args:
        user_id: The user's ID.

    Returns:
        Float percentage (0.0 - 100.0).
    """
    try:
        db = get_db()

        total = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        completed = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'",
            (user_id,)
        ).fetchone()[0]

        db.close()

        if total == 0:
            return 0.0

        return round(completed / total * 100, 1)
    except Exception:
        return 0.0


def get_source_flow(user_id):
    """Get task creation source breakdown (voice vs text).

    Args:
        user_id: The user's ID.

    Returns:
        Dict with voice_count, voice_pct, text_count, text_pct.
    """
    try:
        db = get_db()

        total = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        voice_count = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND created_via = 'whatsapp_voice'",
            (user_id,)
        ).fetchone()[0]

        text_count = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND created_via IN ('whatsapp_text', 'web', 'api')",
            (user_id,)
        ).fetchone()[0]

        db.close()

        voice_pct = round(voice_count / total * 100, 1) if total > 0 else 0.0
        text_pct = round(text_count / total * 100, 1) if total > 0 else 0.0

        return {
            'voice_count': voice_count,
            'voice_pct': voice_pct,
            'text_count': text_count,
            'text_pct': text_pct,
        }
    except Exception:
        return {
            'voice_count': 0,
            'voice_pct': 0.0,
            'text_count': 0,
            'text_pct': 0.0,
        }


def get_recent_activity(user_id, limit=10):
    """Get the most recent tasks for a user with their status.

    Args:
        user_id: The user's ID.
        limit: Maximum number of results (default 10).

    Returns:
        List of task dicts, or empty list on failure.
    """
    try:
        db = get_db()
        rows = db.execute(
            """SELECT id, title, status, priority, category, due_date,
                      created_at, completed_at, created_via
               FROM tasks
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit)
        ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def get_admin_stats():
    """Get system-wide statistics for admin use.

    Returns:
        Dict with total_users, total_tasks, completed_tasks, pending_tasks,
        overdue_tasks, completion_rate, total_messages, active_today.
    """
    try:
        today = date.today().isoformat()
        db = get_db()

        total_users = db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        total_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks"
        ).fetchone()[0]

        completed_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
        ).fetchone()[0]

        pending_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'in_progress')"
        ).fetchone()[0]

        overdue_tasks = db.execute(
            """SELECT COUNT(*) FROM tasks
               WHERE due_date < ?
                 AND status NOT IN ('completed', 'cancelled')""",
            (today,)
        ).fetchone()[0]

        total_messages = db.execute(
            "SELECT COUNT(*) FROM message_log"
        ).fetchone()[0]

        active_today = db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM tasks WHERE DATE(created_at) = ?",
            (today,)
        ).fetchone()[0]

        db.close()

        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        return {
            'total_users': total_users,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'pending_tasks': pending_tasks,
            'overdue_tasks': overdue_tasks,
            'completion_rate': round(completion_rate, 1),
            'total_messages': total_messages,
            'active_today': active_today,
        }
    except Exception:
        return {
            'total_users': 0,
            'total_tasks': 0,
            'completed_tasks': 0,
            'pending_tasks': 0,
            'overdue_tasks': 0,
            'completion_rate': 0.0,
            'total_messages': 0,
            'active_today': 0,
        }


def get_calendar_data(user_id, year, month):
    """Get tasks organized by date for a calendar view.

    Args:
        user_id: The user's ID.
        year: Year as integer.
        month: Month as integer (1-12).

    Returns:
        Dict mapping date strings ('YYYY-MM-DD') to lists of task dicts.
    """
    try:
        # Build date range for the given month
        first_day = date(year, month, 1)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = date(year, month, last_day_num)

        db = get_db()
        rows = db.execute(
            """SELECT id, title, status, priority, category, due_date, due_time,
                      task_type
               FROM tasks
               WHERE user_id = ?
                 AND due_date >= ?
                 AND due_date <= ?
               ORDER BY due_time ASC""",
            (user_id, first_day.isoformat(), last_day.isoformat())
        ).fetchall()
        db.close()

        calendar_data = {}
        for row in rows:
            task = dict(row)
            day_key = task['due_date']
            if day_key not in calendar_data:
                calendar_data[day_key] = []
            calendar_data[day_key].append(task)

        return calendar_data
    except Exception:
        return {}
