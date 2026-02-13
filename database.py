import sqlite3
import os
from config import Config


def get_db():
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        -- Users
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT,
            email TEXT,
            whatsapp_verified INTEGER DEFAULT 0,
            language TEXT DEFAULT 'he',
            timezone TEXT DEFAULT 'Asia/Jerusalem',
            notification_preferences TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP
        );

        -- Tasks
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT,
            task_type TEXT CHECK(task_type IN ('today', 'scheduled', 'recurring', 'someday', 'delegated', 'meeting')),
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled', 'overdue')),
            priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
            category TEXT DEFAULT 'general',
            due_date DATE,
            due_time TIME,
            recurrence_pattern TEXT,
            created_via TEXT CHECK(created_via IN ('whatsapp_text', 'whatsapp_voice', 'web', 'api')),
            voice_transcript TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP
        );

        -- Delegated Tasks
        CREATE TABLE IF NOT EXISTS delegated_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            delegator_id INTEGER REFERENCES users(id),
            assignee_phone TEXT NOT NULL,
            assignee_name TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'rejected', 'completed')),
            message_sent_at TIMESTAMP,
            accepted_at TIMESTAMP,
            completed_at TIMESTAMP,
            follow_up_count INTEGER DEFAULT 0
        );

        -- Meetings
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            organizer_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT,
            meeting_date DATE,
            start_time TIME,
            end_time TIME,
            location TEXT,
            status TEXT DEFAULT 'scheduled'
        );

        -- Meeting Participants
        CREATE TABLE IF NOT EXISTS meeting_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER REFERENCES meetings(id),
            phone_number TEXT NOT NULL,
            name TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'declined', 'tentative')),
            notified_at TIMESTAMP,
            responded_at TIMESTAMP
        );

        -- Reminders
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            user_id INTEGER REFERENCES users(id),
            reminder_type TEXT CHECK(reminder_type IN ('before_task', 'follow_up', 'overdue', 'delegation')),
            scheduled_time TIMESTAMP NOT NULL,
            sent_at TIMESTAMP,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'acknowledged', 'cancelled')),
            message_template TEXT
        );

        -- WhatsApp Messages Log
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            direction TEXT CHECK(direction IN ('incoming', 'outgoing')),
            message_type TEXT CHECK(message_type IN ('text', 'voice', 'image', 'interactive', 'contact')),
            content TEXT,
            voice_duration INTEGER,
            transcription TEXT,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- User Sessions/Conversations
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            current_flow TEXT,
            flow_data TEXT DEFAULT '{}',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_interaction TIMESTAMP
        );

        -- Analytics Events
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            event_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_time);
        CREATE INDEX IF NOT EXISTS idx_messages_user ON message_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_delegated_task ON delegated_tasks(task_id);
        CREATE INDEX IF NOT EXISTS idx_meeting_task ON meetings(task_id);

        -- Performance indexes
        CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_user_due ON tasks(user_id, due_date);
        CREATE INDEX IF NOT EXISTS idx_reminders_user_status ON reminders(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_reminders_status_time ON reminders(status, scheduled_time);
        CREATE INDEX IF NOT EXISTS idx_delegated_assignee ON delegated_tasks(assignee_phone);
        CREATE INDEX IF NOT EXISTS idx_meetings_organizer ON meetings(organizer_id, status);
        CREATE INDEX IF NOT EXISTS idx_meeting_participants_phone ON meeting_participants(phone_number);
        CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, last_interaction);
    ''')

    # Google Calendar tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS google_tokens (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expiry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migrations: add new columns (safe to re-run)
    migrations = [
        "ALTER TABLE tasks ADD COLUMN reminder_before INTEGER",
        "ALTER TABLE users ADD COLUMN weekly_summary_enabled INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN weekly_summary_day INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN weekly_summary_time TEXT DEFAULT '08:00'",
    ]
    for sql in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
