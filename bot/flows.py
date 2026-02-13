"""
WhatsApp Task Management Bot - Conversation Flow State Machine
Manages multi-step conversation flows using the 'conversations' table in the database.

Flow names:
    - 'new_task'          : Simplified task creation (input → confirm → reminder → delegate?)
    - 'new_meeting'       : Simplified meeting creation (input → confirm → done)
    - 'delegate_inline'   : Inline delegation after task save (contact → done)
    - 'voice_pending'     : Confirming voice transcription within an active flow
    - 'voice_confirm'     : Standalone voice → task confirmation
    Legacy (kept for backward compatibility):
    - 'create_task'       : Old task creation flow
    - 'delegate'          : Old delegation flow
    - 'meeting'           : Old meeting flow
"""

import json
from database import get_db


# All recognized flow names
VALID_FLOWS = {
    'new_task',
    'new_meeting',
    'delegate_inline',
    'meeting_invite',
    'voice_pending',
    'voice_confirm',
    # Legacy flows
    'create_task',
    'delegate',
    'meeting',
}


class ConversationFlow:
    """Manages conversation flow state per user via the database."""

    @staticmethod
    def get_flow(user_id):
        """
        Get the current conversation flow state for a user.

        Args:
            user_id: The user's database ID.

        Returns:
            tuple: (flow_name, flow_data_dict) where flow_name is a string
                   or None, and flow_data_dict is a dict (possibly empty).
        """
        db = None
        try:
            db = get_db()
            row = db.execute(
                "SELECT current_flow, flow_data FROM conversations "
                "WHERE user_id = ? ORDER BY last_interaction DESC LIMIT 1",
                (user_id,)
            ).fetchone()

            if row and row['current_flow']:
                flow_name = row['current_flow']
                try:
                    flow_data = json.loads(row['flow_data']) if row['flow_data'] else {}
                except (json.JSONDecodeError, TypeError):
                    flow_data = {}
                return flow_name, flow_data

            return None, {}

        except Exception:
            return None, {}
        finally:
            if db:
                db.close()

    @staticmethod
    def set_flow(user_id, flow_name, flow_data=None):
        """
        Set or update the current conversation flow state for a user.
        Creates a new conversation record if none exists; updates the existing one otherwise.

        Args:
            user_id: The user's database ID.
            flow_name: The flow name string (must be in VALID_FLOWS or None).
            flow_data: Optional dict of flow state data to persist.
        """
        if flow_data is None:
            flow_data = {}

        flow_data_json = json.dumps(flow_data, ensure_ascii=False)
        db = None
        try:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM conversations WHERE user_id = ? "
                "ORDER BY last_interaction DESC LIMIT 1",
                (user_id,)
            ).fetchone()

            if existing:
                db.execute(
                    "UPDATE conversations SET current_flow = ?, flow_data = ?, "
                    "last_interaction = CURRENT_TIMESTAMP WHERE id = ?",
                    (flow_name, flow_data_json, existing['id'])
                )
            else:
                db.execute(
                    "INSERT INTO conversations (user_id, current_flow, flow_data, "
                    "started_at, last_interaction) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (user_id, flow_name, flow_data_json)
                )

            db.commit()

        except Exception:
            if db:
                db.rollback()
        finally:
            if db:
                db.close()

    @staticmethod
    def clear_flow(user_id):
        """
        Clear the current conversation flow for a user (set flow to None, data to empty).

        Args:
            user_id: The user's database ID.
        """
        db = None
        try:
            db = get_db()
            db.execute(
                "UPDATE conversations SET current_flow = NULL, flow_data = '{}', "
                "last_interaction = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            db.commit()

        except Exception:
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
