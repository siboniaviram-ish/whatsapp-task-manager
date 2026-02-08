"""
WhatsApp Task Management Bot - Command Routing
Maps Hebrew and English text commands (and menu selections) to internal command names.
"""

# Hebrew text commands -> internal command names
HEBREW_COMMANDS = {
    'משימה חדשה': 'new_task',
    'המשימות שלי': 'my_tasks',
    'עזרה': 'help',
    'היי': 'welcome',
    'שלום': 'welcome',
    'תפריט': 'welcome',
    'בוצע': 'complete',
    'תזכורות': 'reminders',
    'פגישות': 'meetings',
}

# English text commands -> internal command names
ENGLISH_COMMANDS = {
    'new task': 'new_task',
    'my tasks': 'my_tasks',
    'help': 'help',
    'hi': 'welcome',
    'hello': 'welcome',
    'done': 'complete',
}

# Numeric menu selections -> internal command names
MENU_SELECTIONS = {
    '1': 'task_today',
    '2': 'task_scheduled',
    '3': 'task_delegate',
    '4': 'schedule_meeting',
    '5': 'my_tasks',
}

# Confirmation responses used in flows
CONFIRMATIONS = {
    'כן': True,
    'לא': False,
    'yes': True,
    'no': False,
    'קיבלתי': True,
    'לא יכול': False,
    'מאשר': True,
}

# Cancel keywords that abort any active flow
CANCEL_KEYWORDS = {'ביטול', 'בטל', 'cancel', 'חזור'}


def get_command(text):
    """
    Parse user input and return the internal command name, or None if not recognized.

    Checks in order:
    1. Hebrew commands
    2. English commands
    3. Menu numeric selections

    Args:
        text: Raw message text from the user.

    Returns:
        str or None: Internal command name (e.g. 'new_task', 'welcome') or None.
    """
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # Check Hebrew commands (exact match, case/whitespace normalized)
    for keyword, command in HEBREW_COMMANDS.items():
        if cleaned == keyword:
            return command

    # Check English commands (case-insensitive)
    lower = cleaned.lower()
    for keyword, command in ENGLISH_COMMANDS.items():
        if lower == keyword:
            return command

    # Check menu selections
    if cleaned in MENU_SELECTIONS:
        return MENU_SELECTIONS[cleaned]

    return None


def is_command(text):
    """
    Check whether the given text matches any recognized command.

    Args:
        text: Raw message text from the user.

    Returns:
        bool: True if text is a recognized command, False otherwise.
    """
    return get_command(text) is not None


def is_cancel(text):
    """
    Check whether the given text is a cancel/abort keyword.

    Args:
        text: Raw message text from the user.

    Returns:
        bool: True if the user wants to cancel the current flow.
    """
    if not text or not isinstance(text, str):
        return False
    return text.strip().lower() in CANCEL_KEYWORDS or text.strip() in CANCEL_KEYWORDS


def get_confirmation(text):
    """
    Parse a confirmation response.

    Args:
        text: Raw message text from the user.

    Returns:
        bool or None: True for yes/confirm, False for no/decline, None if not recognized.
    """
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # Check Hebrew confirmations
    if cleaned in CONFIRMATIONS:
        return CONFIRMATIONS[cleaned]

    # Check case-insensitive English confirmations
    lower = cleaned.lower()
    if lower in CONFIRMATIONS:
        return CONFIRMATIONS[lower]

    return None
