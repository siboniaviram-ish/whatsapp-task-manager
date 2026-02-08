"""
Comprehensive seed data generator for WhatsApp Task Manager.
Creates demo users, tasks, meetings, delegations, reminders, messages, and analytics.
"""
import sqlite3
import random
import json
from datetime import datetime, date, timedelta, time
from database import get_db, init_db


def seed():
    init_db()
    db = get_db()
    cursor = db.cursor()

    # Clear existing data
    tables = ['analytics', 'conversations', 'message_log', 'reminders',
              'meeting_participants', 'meetings', 'delegated_tasks', 'tasks', 'users']
    for table in tables:
        cursor.execute(f'DELETE FROM {table}')

    now = datetime.now()
    today = date.today()

    # ============ USERS (25) ============
    users = [
        ('+972501234567', 'Alex Thompson', 'alex@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972502345678', 'Sarah Miller', 'sarah@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972503456789', 'John Doe', 'john@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972504567890', 'Marcus Wright', 'marcus@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972505678901', 'Sarah Lee', 'slee@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972506789012', 'Danny Cohen', 'danny@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972507890123', 'Yossi Levi', 'yossi@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972508901234', 'Maya Chen', 'maya@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972509012345', 'Alex Rivera', 'arivera@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972510123456', 'Noa Ben-David', 'noa@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972511234567', 'Avi Goldstein', 'avi@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972512345678', 'Tamar Shapira', 'tamar@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972513456789', 'Eyal Katz', 'eyal@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972514567890', 'Lior Dahan', 'lior@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972515678901', 'Michal Rosen', 'michal@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972516789012', 'Oren Mizrahi', 'oren@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972517890123', 'Shira Azulay', 'shira@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972518901234', 'Tom Baker', 'tom@example.com', 1, 'en', 'Asia/Jerusalem'),
        ('+972519012345', 'Nir Peretz', 'nir@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972520123456', 'Hila Friedman', 'hila@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972521234567', 'David Stern', 'david@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972522345678', 'Gal Levy', 'gal@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972523456789', 'Rotem Alon', 'rotem@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972524567890', 'Amit Baruch', 'amit@example.com', 1, 'he', 'Asia/Jerusalem'),
        ('+972525678901', 'Chen Tal', 'chen@example.com', 1, 'he', 'Asia/Jerusalem'),
    ]

    for phone, name, email, verified, lang, tz in users:
        days_ago = random.randint(0, 90)
        created = (now - timedelta(days=days_ago)).isoformat()
        last_active = (now - timedelta(hours=random.randint(0, 72))).isoformat()
        cursor.execute(
            'INSERT INTO users (phone_number, name, email, whatsapp_verified, language, timezone, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (phone, name, email, verified, lang, tz, created, last_active)
        )

    # ============ TASKS (120+) ============
    task_templates = [
        # (title, description, category, priority)
        ('Review Q3 Budget Plan', 'Submit to finance team for final approval before EOD.', 'work', 'high'),
        ('Prepare Client Brief', 'Summarized from your 3min voice note this morning.', 'work', 'medium'),
        ('Buy groceries for dinner', 'Milk, bread, vegetables, and chicken', 'personal', 'low'),
        ('Update team on project status', 'Weekly sync with engineering team', 'work', 'medium'),
        ('Call Dentist', 'Annual checkup appointment scheduling', 'health', 'medium'),
        ('Send invoice to Sarah', 'Q3 consulting invoice - net 30', 'work', 'high'),
        ('Finalize Q4 Marketing Deck', 'Include new market research data', 'work', 'high'),
        ('Review technical documentation', 'API docs review for v2.0 release', 'work', 'medium'),
        ('Call vendor for shipment update', 'Office supplies order #4521', 'work', 'high'),
        ('Q4 Strategy Sync', 'Prioritize mobile redesign and finalize API docs by Friday', 'work', 'urgent'),
        ('Review marketing proposal', 'New campaign for Q1 launch', 'work', 'medium'),
        ('Landing Page Feedback', 'Hero section needs more contrast, CTA bigger', 'work', 'medium'),
        ('Send client invoice', 'Monthly retainer invoice for October', 'work', 'high'),
        ('Submit Q3 Financial Report', 'Quarterly financial summary for board', 'work', 'urgent'),
        ('Client Review: Project Phoenix', 'Final deliverables review session', 'work', 'high'),
        ('Finalize Marketing Assets', 'Social media banners and ad copy', 'work', 'medium'),
        ('Update API Documentation', 'Endpoint changes from sprint 14', 'work', 'medium'),
        ('Review Project Specs', 'Details from WhatsApp group Product-Team', 'work', 'high'),
        ('Internal Team Meeting', 'Discussing Q4 roadmap and priorities', 'work', 'urgent'),
        ('Buy birthday gift for mom', 'Something nice from the jewelry store', 'personal', 'medium'),
        ('Schedule car maintenance', 'Oil change and tire rotation', 'personal', 'low'),
        ('Prepare presentation slides', 'For the investor meeting next week', 'work', 'high'),
        ('Book flight tickets', 'Conference in Tel Aviv next month', 'personal', 'medium'),
        ('Update LinkedIn profile', 'Add new certifications and projects', 'personal', 'low'),
        ('Fix login page bug', 'Users getting 500 error on mobile Safari', 'work', 'urgent'),
        ('Write blog post', 'Product update announcement for v3.0', 'work', 'medium'),
        ('Organize team building event', 'Escape room or cooking class for 15 people', 'work', 'low'),
        ('Review insurance policy', 'Annual renewal is coming up next month', 'personal', 'medium'),
        ('Setup new dev environment', 'Docker + Node.js + PostgreSQL stack', 'work', 'medium'),
        ('Clean up email inbox', 'Archive old threads and unsubscribe from newsletters', 'personal', 'low'),
        ('Prepare budget forecast', 'Q1 2025 budget projections', 'work', 'high'),
        ('Review pull requests', '3 PRs waiting from the frontend team', 'work', 'medium'),
        ('Schedule dentist appointment', 'Routine cleaning - overdue by 2 months', 'health', 'medium'),
        ('Order new office chair', 'Ergonomic chair - budget up to $500', 'personal', 'low'),
        ('Backup important files', 'Photos and documents to cloud storage', 'personal', 'medium'),
        ('Research competitor pricing', 'Comparison spreadsheet for leadership', 'work', 'high'),
        ('Plan weekend trip', 'Check hotels in Eilat for the long weekend', 'personal', 'low'),
        ('Debug payment processing', 'Intermittent timeout errors on checkout', 'work', 'urgent'),
        ('Update security certificates', 'SSL certs expiring next week', 'work', 'urgent'),
        ('Create onboarding guide', 'For new team members joining in January', 'work', 'medium'),
    ]

    sources = ['whatsapp_text', 'whatsapp_voice', 'web', 'whatsapp_text', 'whatsapp_voice']
    statuses_weights = [('pending', 35), ('completed', 40), ('in_progress', 10), ('overdue', 10), ('cancelled', 5)]
    statuses = []
    for s, w in statuses_weights:
        statuses.extend([s] * w)

    task_types = ['today', 'scheduled', 'scheduled', 'recurring', 'someday', 'scheduled']

    for i in range(120):
        template = task_templates[i % len(task_templates)]
        title, description, category, priority = template

        # Vary the data slightly
        if i >= len(task_templates):
            title = title + f' (#{i - len(task_templates) + 2})'

        user_id = random.randint(1, 10)  # Focus tasks on first 10 users
        status = random.choice(statuses)
        created_via = random.choice(sources)
        task_type = random.choice(task_types)

        # Generate dates
        days_offset = random.randint(-7, 14)
        due_date = (today + timedelta(days=days_offset)).isoformat()
        hours = random.randint(8, 18)
        minutes = random.choice([0, 15, 30, 45])
        due_time = f'{hours:02d}:{minutes:02d}'

        created_days_ago = random.randint(0, 14)
        created_at = (now - timedelta(days=created_days_ago, hours=random.randint(0, 12))).isoformat()

        completed_at = None
        if status == 'completed':
            completed_at = (now - timedelta(days=random.randint(0, created_days_ago), hours=random.randint(0, 6))).isoformat()

        # If overdue, make sure due_date is in the past
        if status == 'overdue':
            due_date = (today - timedelta(days=random.randint(1, 5))).isoformat()

        voice_transcript = None
        if created_via == 'whatsapp_voice':
            voice_transcript = description

        cursor.execute(
            '''INSERT INTO tasks (user_id, title, description, task_type, status, priority, category,
               due_date, due_time, created_via, voice_transcript, created_at, completed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, title, description, task_type, status, priority, category,
             due_date, due_time, created_via, voice_transcript, created_at, completed_at, now.isoformat())
        )

    # ============ DELEGATED TASKS (20) ============
    assignees = [
        ('+972502345678', 'Sarah Miller'),
        ('+972503456789', 'John Doe'),
        ('+972504567890', 'Marcus Wright'),
        ('+972505678901', 'Sarah Lee'),
        ('+972506789012', 'Danny Cohen'),
        ('+972507890123', 'Yossi Levi'),
        ('+972508901234', 'Maya Chen'),
        ('+972509012345', 'Alex Rivera'),
    ]

    delegation_statuses = ['pending', 'pending', 'accepted', 'completed', 'pending']

    for i in range(20):
        task_id = random.randint(1, 60)  # Delegate from first 60 tasks
        delegator_id = 1  # Alex Thompson
        assignee = random.choice(assignees)
        d_status = random.choice(delegation_statuses)
        sent_at = (now - timedelta(hours=random.randint(1, 72))).isoformat()

        cursor.execute(
            '''INSERT INTO delegated_tasks (task_id, delegator_id, assignee_phone, assignee_name, status, message_sent_at, follow_up_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (task_id, delegator_id, assignee[0], assignee[1], d_status, sent_at, random.randint(0, 3))
        )

    # ============ MEETINGS (18) ============
    meeting_data = [
        ('Internal Team Meeting', 'Discussing Q4 roadmap and priorities', '13:00', '14:00', 'Conference Room A'),
        ('Client Review: Project Phoenix', 'Final deliverables walkthrough', '10:00', '11:00', 'Zoom'),
        ('Sprint Planning', 'Plan sprint 15 backlog items', '09:00', '10:30', 'Main Office'),
        ('1:1 with Danny', 'Performance review discussion', '15:00', '15:30', 'Office 204'),
        ('Product Demo', 'Demo new features to stakeholders', '11:00', '12:00', 'Zoom'),
        ('Design Review', 'Review new UI mockups', '14:00', '15:00', 'Design Lab'),
        ('Budget Planning', 'Q1 2025 budget review', '10:00', '11:30', 'Board Room'),
        ('Security Audit Review', 'Review penetration test results', '09:00', '10:00', 'Conference Room B'),
        ('Marketing Sync', 'Campaign performance review', '14:00', '14:30', 'Zoom'),
        ('Investor Meeting', 'Q3 results presentation', '11:00', '12:30', 'Main Office'),
        ('Team Building Planning', 'Plan Q4 team event', '16:00', '16:30', 'Lounge'),
        ('Architecture Review', 'Microservices migration plan', '10:00', '11:00', 'Conference Room A'),
        ('HR Policy Update', 'New remote work policy discussion', '13:00', '13:30', 'Zoom'),
        ('Client Onboarding', 'New client kickoff meeting', '09:00', '10:00', 'Main Office'),
        ('Code Review Session', 'Review authentication module', '15:00', '16:00', 'Zoom'),
        ('Weekly Standup', 'Team weekly status update', '09:30', '09:45', 'Slack'),
        ('Sales Pipeline Review', 'Q4 pipeline analysis', '14:00', '15:00', 'Board Room'),
        ('DevOps Sync', 'Infrastructure updates and CI/CD', '11:00', '11:30', 'Zoom'),
    ]

    for i, (title, desc, start, end, location) in enumerate(meeting_data):
        days_offset = random.randint(-3, 10)
        meeting_date = (today + timedelta(days=days_offset)).isoformat()
        organizer_id = random.randint(1, 5)
        m_status = 'scheduled' if days_offset >= 0 else 'completed'

        # Create associated task
        cursor.execute(
            '''INSERT INTO tasks (user_id, title, description, task_type, status, priority, category,
               due_date, due_time, created_via, created_at, updated_at)
               VALUES (?, ?, ?, 'meeting', ?, 'high', 'work', ?, ?, 'web', ?, ?)''',
            (organizer_id, title, desc, 'pending' if m_status == 'scheduled' else 'completed',
             meeting_date, start, now.isoformat(), now.isoformat())
        )
        task_id = cursor.lastrowid

        cursor.execute(
            '''INSERT INTO meetings (task_id, organizer_id, title, description, meeting_date, start_time, end_time, location, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (task_id, organizer_id, title, desc, meeting_date, start, end, location, m_status)
        )
        meeting_id = cursor.lastrowid

        # Add participants
        num_participants = random.randint(2, 5)
        for _ in range(num_participants):
            p = random.choice(assignees)
            p_status = random.choice(['accepted', 'pending', 'accepted', 'tentative'])
            cursor.execute(
                '''INSERT INTO meeting_participants (meeting_id, phone_number, name, status, notified_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (meeting_id, p[0], p[1], p_status, now.isoformat())
            )

    # ============ REMINDERS (40) ============
    reminder_types = ['before_task', 'follow_up', 'overdue', 'delegation']
    for i in range(40):
        task_id = random.randint(1, 80)
        user_id = random.randint(1, 10)
        r_type = random.choice(reminder_types)
        hours_offset = random.randint(-24, 48)
        scheduled = (now + timedelta(hours=hours_offset)).isoformat()
        r_status = 'sent' if hours_offset < 0 else 'pending'
        sent_at = scheduled if r_status == 'sent' else None

        cursor.execute(
            '''INSERT INTO reminders (task_id, user_id, reminder_type, scheduled_time, sent_at, status)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (task_id, user_id, r_type, scheduled, sent_at, r_status)
        )

    # ============ MESSAGE LOG (250+) ============
    message_contents = [
        ('משימה חדשה', 'text'),
        ('המשימות שלי', 'text'),
        ('היי', 'text'),
        ('1', 'text'),
        ('2', 'text'),
        ('3', 'text'),
        ('בוצע', 'text'),
        ('כן', 'text'),
        ('להתקשר לרופא שיניים מחר', 'text'),
        ('לשלוח את הדוח עד יום שלישי', 'text'),
        ('Voice message transcribed: Review Q3 budget plan', 'voice'),
        ('Voice message transcribed: Schedule meeting with Danny', 'voice'),
        ('Voice message transcribed: Prepare client brief for tomorrow', 'voice'),
    ]

    outgoing_messages = [
        'היי! אני Task Hub Bot. מה תרצה לעשות?',
        'מעולה! מה המשימה?',
        'המשימה נוצרה בהצלחה!',
        'תזכורת: להתקשר לרופא שיניים',
        'הנה המשימות שלך להיום:',
        'הודעה נשלחה ליוסי',
        'פגישה נקבעה בהצלחה!',
    ]

    for i in range(250):
        user_id = random.randint(1, 15)
        direction = random.choice(['incoming', 'incoming', 'outgoing'])
        hours_ago = random.randint(0, 168)
        created = (now - timedelta(hours=hours_ago)).isoformat()

        if direction == 'incoming':
            msg = random.choice(message_contents)
            content = msg[0]
            msg_type = msg[1]
        else:
            content = random.choice(outgoing_messages)
            msg_type = 'text'

        voice_duration = random.randint(5, 30) if msg_type == 'voice' else None

        cursor.execute(
            '''INSERT INTO message_log (user_id, direction, message_type, content, voice_duration, processed, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)''',
            (user_id, direction, msg_type, content, voice_duration, created)
        )

    # ============ CONVERSATIONS ============
    for user_id in range(1, 11):
        cursor.execute(
            '''INSERT INTO conversations (user_id, current_flow, flow_data, started_at, last_interaction)
               VALUES (?, NULL, '{}', ?, ?)''',
            (user_id, now.isoformat(), now.isoformat())
        )

    # ============ ANALYTICS EVENTS (100) ============
    event_types = ['task_created', 'task_completed', 'task_delegated', 'meeting_created',
                   'voice_transcribed', 'reminder_sent', 'login', 'dashboard_viewed']

    for i in range(100):
        user_id = random.randint(1, 15)
        event_type = random.choice(event_types)
        hours_ago = random.randint(0, 336)
        created = (now - timedelta(hours=hours_ago)).isoformat()

        cursor.execute(
            '''INSERT INTO analytics (user_id, event_type, event_data, created_at)
               VALUES (?, ?, '{}', ?)''',
            (user_id, event_type, created)
        )

    db.commit()
    db.close()
    print("Seed data generated successfully!")
    print("  - 25 users")
    print("  - 120+ tasks")
    print("  - 20 delegated tasks")
    print("  - 18 meetings with participants")
    print("  - 40 reminders")
    print("  - 250+ message log entries")
    print("  - 100 analytics events")


if __name__ == '__main__':
    seed()
