import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'whatsapp-task-manager-secret-key-2024')
    DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'database.db')

    # Twilio WhatsApp Configuration
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    # OpenAI (Whisper) for Speech-to-Text
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

    # App Settings
    DEFAULT_LANGUAGE = 'he'
    DEFAULT_TIMEZONE = 'Asia/Jerusalem'
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')

    # Reminder Settings
    REMINDER_CHECK_INTERVAL = 60  # seconds
