import os
import json
import sqlite3
import logging
from datetime import datetime, date, time, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from database import get_db, init_db
from config import Config

# Ensure logs directory exists before configuring file logging
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    filename='logs/app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize database on startup
with app.app_context():
    init_db()


# ============ HELPER ============
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime('%H:%M')
    if isinstance(obj, sqlite3.Row):
        return dict(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ============ HEALTH CHECK ============

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'ok',
        'version': '3.0.1',
        'app_url': Config.APP_URL,
        'twilio_configured': bool(Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN),
        'twilio_sid_prefix': Config.TWILIO_ACCOUNT_SID[:6] + '...' if Config.TWILIO_ACCOUNT_SID else 'NOT SET',
        'whatsapp_number': Config.TWILIO_WHATSAPP_NUMBER or 'NOT SET',
        'openai_configured': bool(Config.OPENAI_API_KEY),
        'openai_key_prefix': Config.OPENAI_API_KEY[:8] + '...' if Config.OPENAI_API_KEY else 'NOT SET',
        'env_openai_raw': bool(os.environ.get('OPENAI_API_KEY')),
    })


# ============ PAGE ROUTES ============

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/dashboard')
def dashboard():
    user_id = request.args.get('user_id', 1, type=int)
    return render_template('dashboard.html', user_id=user_id)


@app.route('/tasks')
def tasks_page():
    user_id = request.args.get('user_id', 1, type=int)
    return render_template('tasks.html', user_id=user_id)


@app.route('/calendar')
def calendar_page():
    user_id = request.args.get('user_id', 1, type=int)
    return render_template('calendar.html', user_id=user_id)


@app.route('/analytics')
def analytics_page():
    user_id = request.args.get('user_id', 1, type=int)
    return render_template('analytics.html', user_id=user_id)


@app.route('/delegation')
def delegation_page():
    user_id = request.args.get('user_id', 1, type=int)
    return render_template('delegation.html', user_id=user_id)


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        phone = data.get('phone_number', '').strip()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()

        if not phone:
            return render_template('register.html', error='Phone number is required')

        db = get_db()
        try:
            existing = db.execute('SELECT id FROM users WHERE phone_number = ?', (phone,)).fetchone()
            if existing:
                return redirect(url_for('dashboard', user_id=existing['id']))

            db.execute(
                'INSERT INTO users (phone_number, name, email, whatsapp_verified, last_active) VALUES (?, ?, ?, 1, ?)',
                (phone, name, email, datetime.now().isoformat())
            )
            db.commit()
            user = db.execute('SELECT id FROM users WHERE phone_number = ?', (phone,)).fetchone()
            return redirect(url_for('dashboard', user_id=user['id']))
        finally:
            db.close()

    return render_template('register.html')


# ============ WHATSAPP WEBHOOK ============

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        from bot.handlers import handle_incoming_message
        import requests as http_requests

        from_number = request.values.get('From', '')
        body = request.values.get('Body', '')
        num_media = int(request.values.get('NumMedia', 0))

        # Always check for media URL (some edge cases report NumMedia=0 with media)
        media_url = request.values.get('MediaUrl0', None)
        media_type = request.values.get('MediaContentType0', '') or ''

        # Interactive message responses (buttons / lists)
        button_payload = request.values.get('ButtonPayload', '') or None
        list_id = request.values.get('ListId', '') or None

        # Clean phone number
        phone = from_number.replace('whatsapp:', '')

        logger.info(
            "Webhook received: From=%s, Body=%s, NumMedia=%s, MediaType=%s, MediaUrl=%s, ButtonPayload=%s, ListId=%s",
            from_number, body[:50] if body else '', num_media, media_type,
            media_url[:60] if media_url else '', button_payload, list_id,
        )

        # Determine message type
        message_type = 'text'
        if media_url and 'audio' in media_type.lower():
            message_type = 'voice'
        elif media_url and 'vcard' in media_type.lower():
            # Shared contact: download vCard content and put it in the body
            message_type = 'contact'
            try:
                auth = None
                if Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN:
                    auth = (Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
                vcard_resp = http_requests.get(media_url, auth=auth, timeout=10)
                if vcard_resp.status_code == 200:
                    body = vcard_resp.text
                    logger.info("Downloaded vCard content: %s", body[:100])
                else:
                    logger.warning("Failed to download vCard: HTTP %s", vcard_resp.status_code)
            except Exception as e:
                logger.warning("Error downloading vCard: %s", e)

        handle_incoming_message(phone, body, message_type, media_url, button_payload, list_id)

        # Return empty TwiML response (messages are sent via REST API)
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>', 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>', 200, {'Content-Type': 'text/xml'}


@app.route('/debug/send-test', methods=['POST'])
def debug_send_test():
    """Debug endpoint: simulate processing a message and return diagnostics."""
    phone = request.values.get('phone', '')
    body = request.values.get('body', 'היי')
    results = {'phone': phone, 'body': body, 'steps': []}

    if not phone:
        return jsonify({'error': 'phone parameter required'}), 400

    # Step 1: Test plain text send
    try:
        from services.whatsapp_service import send_message
        sid = send_message(phone, f"🔧 Debug test message")
        results['steps'].append({'send_message': 'OK' if sid else 'FAILED', 'sid': sid})
    except Exception as e:
        results['steps'].append({'send_message': f'ERROR: {e}'})

    # Step 2: Test interactive send
    try:
        from services.interactive_service import send_main_menu
        sid2 = send_main_menu(phone)
        results['steps'].append({'send_main_menu': 'OK' if sid2 else 'FAILED', 'sid': sid2})
    except Exception as e:
        results['steps'].append({'send_main_menu': f'ERROR: {e}'})

    return jsonify(results)


@app.route('/webhook/whatsapp/status', methods=['POST'])
def whatsapp_status():
    message_sid = request.values.get('MessageSid', '')
    status = request.values.get('MessageStatus', '')
    logger.info(f"Message {message_sid} status: {status}")
    return '', 200


# ============ TASKS API ============

@app.route('/api/tasks', methods=['GET'])
def api_list_tasks():
    user_id = request.args.get('user_id', 1, type=int)
    status = request.args.get('status')
    task_type = request.args.get('task_type')
    category = request.args.get('category')
    search = request.args.get('search')
    due_date = request.args.get('due_date')

    from services.task_service import get_tasks
    filters = {}
    if status:
        filters['status'] = status
    if task_type:
        filters['task_type'] = task_type
    if category:
        filters['category'] = category
    if search:
        filters['search'] = search
    if due_date:
        filters['due_date'] = due_date

    tasks = get_tasks(user_id, filters)
    return jsonify(tasks)


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    data = request.get_json()
    user_id = data.get('user_id', 1)

    from services.task_service import create_task
    from services.reminder_service import create_reminders_for_task

    task_id = create_task(user_id, data)
    if task_id and data.get('due_date'):
        create_reminders_for_task(task_id)

    return jsonify({'id': task_id, 'success': True}), 201


@app.route('/api/tasks/<int:task_id>', methods=['GET'])
def api_get_task(task_id):
    from services.task_service import get_task
    task = get_task(task_id)
    if task:
        return jsonify(task)
    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    data = request.get_json()
    from services.task_service import update_task
    success = update_task(task_id, data)
    return jsonify({'success': success})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    from services.task_service import delete_task
    success = delete_task(task_id)
    return jsonify({'success': success})


@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def api_complete_task(task_id):
    from services.task_service import complete_task
    success = complete_task(task_id)
    return jsonify({'success': success})


@app.route('/api/tasks/<int:task_id>/delegate', methods=['POST'])
def api_delegate_task(task_id):
    data = request.get_json()
    assignee_phone = data.get('assignee_phone')
    assignee_name = data.get('assignee_name', '')

    if not assignee_phone:
        return jsonify({'error': 'assignee_phone required'}), 400

    db = get_db()
    try:
        task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        db.execute(
            '''INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, message_sent_at)
               VALUES (?, ?, ?, ?, ?)''',
            (task_id, task['user_id'], assignee_phone, assignee_name, datetime.now().isoformat())
        )
        db.execute('UPDATE tasks SET task_type = ? WHERE id = ?', ('delegated', task_id))
        db.commit()

        from services.whatsapp_service import send_delegation_message
        user = db.execute('SELECT name FROM users WHERE id = ?', (task['user_id'],)).fetchone()
        send_delegation_message(assignee_phone, user['name'] if user else 'Someone', task['title'], task['due_date'])

        return jsonify({'success': True})
    finally:
        db.close()


# ============ MEETINGS API ============

@app.route('/api/meetings', methods=['GET'])
def api_list_meetings():
    user_id = request.args.get('user_id', 1, type=int)
    from services.meeting_service import get_meetings
    meetings = get_meetings(user_id)
    return jsonify(meetings)


@app.route('/api/meetings', methods=['POST'])
def api_create_meeting():
    data = request.get_json()
    organizer_id = data.get('organizer_id', 1)
    from services.meeting_service import create_meeting
    meeting_id = create_meeting(organizer_id, data)
    return jsonify({'id': meeting_id, 'success': True}), 201


@app.route('/api/meetings/<int:meeting_id>', methods=['GET'])
def api_get_meeting(meeting_id):
    from services.meeting_service import get_meeting
    meeting = get_meeting(meeting_id)
    if meeting:
        return jsonify(meeting)
    return jsonify({'error': 'Meeting not found'}), 404


@app.route('/api/meetings/<int:meeting_id>', methods=['DELETE'])
def api_cancel_meeting(meeting_id):
    from services.meeting_service import cancel_meeting
    success = cancel_meeting(meeting_id)
    return jsonify({'success': success})


@app.route('/api/meetings/<int:meeting_id>/respond', methods=['POST'])
def api_respond_meeting(meeting_id):
    data = request.get_json()
    phone = data.get('phone_number')
    status = data.get('status')
    from services.meeting_service import respond_to_meeting
    success = respond_to_meeting(meeting_id, phone, status)
    return jsonify({'success': success})


# ============ REMINDERS API ============

@app.route('/api/reminders', methods=['GET'])
def api_list_reminders():
    user_id = request.args.get('user_id', 1, type=int)
    db = get_db()
    try:
        reminders = db.execute(
            '''SELECT r.*, t.title as task_title FROM reminders r
               LEFT JOIN tasks t ON r.task_id = t.id
               WHERE r.user_id = ? ORDER BY r.scheduled_time''',
            (user_id,)
        ).fetchall()
        return jsonify(rows_to_list(reminders))
    finally:
        db.close()


@app.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
def api_cancel_reminder(reminder_id):
    db = get_db()
    try:
        db.execute("UPDATE reminders SET status = 'cancelled' WHERE id = ?", (reminder_id,))
        db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


# ============ USER API ============

@app.route('/api/user/profile', methods=['GET'])
def api_user_profile():
    user_id = request.args.get('user_id', 1, type=int)
    db = get_db()
    try:
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            return jsonify(row_to_dict(user))
        return jsonify({'error': 'User not found'}), 404
    finally:
        db.close()


@app.route('/api/user/profile', methods=['PUT'])
def api_update_profile():
    data = request.get_json()
    user_id = data.get('user_id', 1)
    db = get_db()
    try:
        fields = []
        values = []
        for key in ['name', 'email', 'language', 'timezone', 'notification_preferences']:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if fields:
            values.append(user_id)
            db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
            db.commit()
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/user/stats', methods=['GET'])
def api_user_stats():
    user_id = request.args.get('user_id', 1, type=int)
    from services.task_service import get_tasks_stats
    stats = get_tasks_stats(user_id)
    return jsonify(stats)


# ============ DASHBOARD API ============

@app.route('/api/dashboard/overview', methods=['GET'])
def api_dashboard_overview():
    user_id = request.args.get('user_id', 1, type=int)
    from services.analytics_service import get_dashboard_overview
    overview = get_dashboard_overview(user_id)
    return jsonify(overview)


@app.route('/api/dashboard/tasks-today', methods=['GET'])
def api_dashboard_today():
    user_id = request.args.get('user_id', 1, type=int)
    from services.task_service import get_today_tasks
    tasks = get_today_tasks(user_id)
    return jsonify(tasks)


@app.route('/api/dashboard/calendar', methods=['GET'])
def api_dashboard_calendar():
    user_id = request.args.get('user_id', 1, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    from services.analytics_service import get_calendar_data
    data = get_calendar_data(user_id, year, month)
    return jsonify(data)


@app.route('/api/dashboard/delegated', methods=['GET'])
def api_dashboard_delegated():
    user_id = request.args.get('user_id', 1, type=int)
    from services.task_service import get_delegated_tasks
    tasks = get_delegated_tasks(user_id)
    return jsonify(tasks)


@app.route('/api/dashboard/weekly-performance', methods=['GET'])
def api_weekly_performance():
    user_id = request.args.get('user_id', 1, type=int)
    from services.analytics_service import get_weekly_performance
    data = get_weekly_performance(user_id)
    return jsonify(data)


@app.route('/api/dashboard/source-flow', methods=['GET'])
def api_source_flow():
    user_id = request.args.get('user_id', 1, type=int)
    from services.analytics_service import get_source_flow
    data = get_source_flow(user_id)
    return jsonify(data)


@app.route('/api/dashboard/recent-activity', methods=['GET'])
def api_recent_activity():
    user_id = request.args.get('user_id', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    from services.analytics_service import get_recent_activity
    data = get_recent_activity(user_id, limit)
    return jsonify(data)


# ============ ADMIN/ANALYTICS API ============

@app.route('/api/admin/stats', methods=['GET'])
def api_admin_stats():
    from services.analytics_service import get_admin_stats
    stats = get_admin_stats()
    return jsonify(stats)


@app.route('/api/admin/users', methods=['GET'])
def api_admin_users():
    db = get_db()
    try:
        users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        return jsonify(rows_to_list(users))
    finally:
        db.close()


# ============ VOICE API ============

@app.route('/api/voice/transcribe', methods=['POST'])
def api_transcribe():
    data = request.get_json()
    audio_url = data.get('audio_url')
    from services.voice_service import transcribe_audio
    transcript = transcribe_audio(audio_url)
    return jsonify({'transcript': transcript})


@app.route('/api/voice/parse-task', methods=['POST'])
def api_parse_task():
    data = request.get_json()
    transcript = data.get('transcript', '')
    from services.voice_service import extract_task_from_transcript
    task_data = extract_task_from_transcript(transcript)
    return jsonify(task_data)


# ============ SCHEDULER FOR REMINDERS ============

def setup_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from services.reminder_service import process_due_reminders, mark_reminder_sent
        from services.interactive_service import send_reminder_interactive

        scheduler = BackgroundScheduler()

        def check_reminders():
            with app.app_context():
                due = process_due_reminders()
                for reminder in due:
                    try:
                        title = reminder.get('task_title', reminder.get('title', 'משימה'))
                        due_date = reminder.get('due_date', '')
                        due_time = reminder.get('due_time', '')
                        time_str = f" בשעה {due_time}" if due_time else ''

                        msg = (
                            f"⏰ *תזכורת!*\n\n"
                            f"📌 משימה: *{title}*\n"
                            f"📅 תאריך יעד: {due_date}{time_str}"
                        )

                        # Get the user's phone number
                        db = get_db()
                        user = db.execute(
                            "SELECT phone_number FROM users WHERE id = ?",
                            (reminder['user_id'],)
                        ).fetchone()
                        db.close()

                        if user:
                            send_reminder_interactive(user['phone_number'], msg)
                    except Exception as e:
                        logger.error(f"Failed to send reminder: {e}")
                    finally:
                        try:
                            mark_reminder_sent(reminder['reminder_id'])
                        except Exception:
                            pass

        def send_weekly_summaries():
            """Send weekly task/meeting summary to users who opted in (Sunday 08:00)."""
            with app.app_context():
                try:
                    from services.whatsapp_service import send_message
                    db = get_db()
                    users = db.execute(
                        "SELECT id, phone_number, name FROM users WHERE weekly_summary_enabled = 1"
                    ).fetchall()

                    for user in users:
                        try:
                            now_date = date.today()
                            next_week = (now_date + timedelta(days=7)).isoformat()
                            today_str = now_date.isoformat()

                            tasks = db.execute(
                                "SELECT title, due_date, due_time, priority, status FROM tasks "
                                "WHERE user_id = ? AND status IN ('pending', 'in_progress') "
                                "AND due_date BETWEEN ? AND ? ORDER BY due_date, due_time",
                                (user['id'], today_str, next_week)
                            ).fetchall()

                            meetings = db.execute(
                                "SELECT m.title, m.meeting_date, m.start_time, m.location FROM meetings m "
                                "WHERE m.organizer_id = ? AND m.status = 'scheduled' "
                                "AND m.meeting_date BETWEEN ? AND ? ORDER BY m.meeting_date, m.start_time",
                                (user['id'], today_str, next_week)
                            ).fetchall()

                            if not tasks and not meetings:
                                continue

                            name = user['name'] or 'שלום'
                            lines = [f"📋 *סיכום שבועי - {name}*\n"]

                            if tasks:
                                lines.append(f"📌 *{len(tasks)} משימות השבוע:*")
                                for t in tasks[:10]:
                                    time_str = f" {t['due_time']}" if t['due_time'] else ""
                                    priority_icon = {'urgent': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(t['priority'], '⚪')
                                    lines.append(f"  {priority_icon} {t['title']} - {t['due_date']}{time_str}")
                                if len(tasks) > 10:
                                    lines.append(f"  ...ועוד {len(tasks) - 10} משימות")

                            if meetings:
                                lines.append(f"\n📅 *{len(meetings)} פגישות השבוע:*")
                                for m in meetings[:5]:
                                    loc = f" 📍{m['location']}" if m['location'] else ""
                                    lines.append(f"  🕐 {m['title']} - {m['meeting_date']} {m['start_time']}{loc}")

                            lines.append(f"\nשבוע פרודוקטיבי! 💪")

                            send_message(user['phone_number'], "\n".join(lines))
                            logger.info("Weekly summary sent to user %s", user['id'])
                        except Exception as e:
                            logger.error("Failed to send weekly summary to user %s: %s", user['id'], e)

                    db.close()
                except Exception as e:
                    logger.error("Weekly summary job failed: %s", e)

        scheduler.add_job(check_reminders, 'interval', seconds=Config.REMINDER_CHECK_INTERVAL)
        scheduler.add_job(send_weekly_summaries, 'cron', day_of_week='sun', hour=8, minute=0)
        scheduler.start()
        logger.info("Reminder scheduler started (with weekly summary)")
    except Exception as e:
        logger.warning(f"Scheduler not started: {e}")


# Start scheduler and pre-load templates
setup_scheduler()
try:
    from services.interactive_service import preload_templates
    preload_templates()
except Exception as e:
    logger.warning(f"Template pre-load failed: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
