import os

from utils.memory import load_memory


DOWNLOADS_PATH = os.path.expanduser("~/Downloads")


def get_action_suggestions():
    memory = load_memory()
    history = memory.get("history", [])
    actions = []

    try:
        files = os.listdir(DOWNLOADS_PATH)
        if len(files) > 20:
            actions.append(
                {
                    "type": "organize_downloads",
                    "message": "Your Downloads folder is cluttered. Organize now?",
                }
            )
    except Exception:
        pass

    if len(history) >= 3:
        last_commands = [str(item.get("user", "")).strip().lower() for item in history[-3:]]
        if last_commands and len(set(last_commands)) == 1:
            actions.append(
                {
                    "type": "repeat_warning",
                    "message": "You are repeating the same command. Do you want to automate it?",
                }
            )

    return actions
