"""
Google Calendar integration via OAuth2.
Allows the bot to create calendar events directly for connected users.
"""

import json
import logging
from datetime import datetime, timedelta

import requests

from config import Config
from database import get_db

logger = logging.getLogger(__name__)

SCOPES = 'https://www.googleapis.com/auth/calendar.events'
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
CALENDAR_API = 'https://www.googleapis.com/calendar/v3'


def is_configured():
    """Check if Google Calendar OAuth2 credentials are set."""
    return bool(Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET)


def _get_redirect_uri():
    return f"{Config.APP_URL}/auth/google/callback"


def get_auth_url(user_id):
    """Generate Google OAuth2 authorization URL for a user."""
    if not is_configured():
        return None

    params = {
        'client_id': Config.GOOGLE_CLIENT_ID,
        'redirect_uri': _get_redirect_uri(),
        'response_type': 'code',
        'scope': SCOPES,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': str(user_id),
    }
    query = '&'.join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def handle_callback(code, state):
    """Exchange authorization code for tokens and store them.

    Args:
        code: Authorization code from Google.
        state: User ID passed as state parameter.

    Returns:
        user_id on success, None on failure.
    """
    if not is_configured():
        return None

    try:
        user_id = int(state)
    except (ValueError, TypeError):
        logger.warning("Invalid state in Google callback: %s", state)
        return None

    try:
        resp = requests.post(TOKEN_URL, data={
            'code': code,
            'client_id': Config.GOOGLE_CLIENT_ID,
            'client_secret': Config.GOOGLE_CLIENT_SECRET,
            'redirect_uri': _get_redirect_uri(),
            'grant_type': 'authorization_code',
        }, timeout=10)

        if resp.status_code != 200:
            logger.warning("Google token exchange failed: %s - %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        access_token = data['access_token']
        refresh_token = data.get('refresh_token', '')
        expires_in = data.get('expires_in', 3600)
        expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        _store_tokens(user_id, access_token, refresh_token, expiry)
        logger.info("Google Calendar connected for user %s", user_id)
        return user_id

    except Exception as e:
        logger.warning("Google OAuth callback error: %s", e)
        return None


def _store_tokens(user_id, access_token, refresh_token, expiry):
    """Store or update Google tokens in the database."""
    db = get_db()
    try:
        db.execute(
            """INSERT INTO google_tokens (user_id, access_token, refresh_token, expiry, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
               access_token = excluded.access_token,
               refresh_token = CASE WHEN excluded.refresh_token != '' THEN excluded.refresh_token ELSE google_tokens.refresh_token END,
               expiry = excluded.expiry,
               updated_at = CURRENT_TIMESTAMP""",
            (user_id, access_token, refresh_token, expiry),
        )
        db.commit()
    finally:
        db.close()


def _get_tokens(user_id):
    """Retrieve stored tokens for a user."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT access_token, refresh_token, expiry FROM google_tokens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        db.close()


def _refresh_access_token(user_id, refresh_token):
    """Refresh an expired access token."""
    try:
        resp = requests.post(TOKEN_URL, data={
            'client_id': Config.GOOGLE_CLIENT_ID,
            'client_secret': Config.GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }, timeout=10)

        if resp.status_code != 200:
            logger.warning("Google token refresh failed: %s", resp.status_code)
            return None

        data = resp.json()
        access_token = data['access_token']
        expires_in = data.get('expires_in', 3600)
        expiry = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()

        _store_tokens(user_id, access_token, '', expiry)
        return access_token

    except Exception as e:
        logger.warning("Token refresh error: %s", e)
        return None


def _get_valid_token(user_id):
    """Get a valid access token, refreshing if needed."""
    tokens = _get_tokens(user_id)
    if not tokens:
        return None

    # Check if token is expired
    expiry_str = tokens.get('expiry', '')
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
            if datetime.utcnow() >= expiry - timedelta(minutes=5):
                # Token expired or about to expire — refresh
                refreshed = _refresh_access_token(user_id, tokens['refresh_token'])
                if refreshed:
                    return refreshed
                return None
        except ValueError:
            pass

    return tokens['access_token']


def is_connected(user_id):
    """Check if a user has connected their Google Calendar."""
    if not is_configured():
        return False
    tokens = _get_tokens(user_id)
    return tokens is not None and bool(tokens.get('refresh_token'))


def create_event(user_id, title, event_date, start_time=None, location=None, description=None):
    """Create a Google Calendar event for a connected user.

    Args:
        user_id: The user's ID.
        title: Event title.
        event_date: Date string (YYYY-MM-DD).
        start_time: Time string (HH:MM) or None for all-day event.
        location: Location string or None.
        description: Description or None.

    Returns:
        Event HTML link on success, None on failure.
    """
    access_token = _get_valid_token(user_id)
    if not access_token:
        return None

    try:
        event = {'summary': title}

        if start_time:
            # Timed event (1 hour duration)
            start_dt = f"{event_date}T{start_time}:00"
            end_hour = int(start_time.split(':')[0]) + 1
            end_min = start_time.split(':')[1]
            end_dt = f"{event_date}T{end_hour:02d}:{end_min}:00"
            event['start'] = {'dateTime': start_dt, 'timeZone': 'Asia/Jerusalem'}
            event['end'] = {'dateTime': end_dt, 'timeZone': 'Asia/Jerusalem'}
        else:
            # All-day event
            event['start'] = {'date': event_date}
            event['end'] = {'date': event_date}

        if location:
            event['location'] = location
        if description:
            event['description'] = description

        resp = requests.post(
            f"{CALENDAR_API}/calendars/primary/events",
            headers={
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
            },
            json=event,
            timeout=10,
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            link = result.get('htmlLink', '')
            logger.info("Google Calendar event created for user %s: %s", user_id, link)
            return link
        else:
            logger.warning("Google Calendar API error: %s - %s", resp.status_code, resp.text[:200])
            return None

    except Exception as e:
        logger.warning("Google Calendar create_event error: %s", e)
        return None
