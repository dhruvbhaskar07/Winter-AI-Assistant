import json
import os

SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
COMMANDS_FILE = os.path.join(DATA_DIR, "learned_commands.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_commands():
    if not os.path.exists(COMMANDS_FILE):
        return {}

    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_commands(commands):
    _ensure_data_dir()
    with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(commands, f, indent=4)


def learn_command(name, value):
    commands = load_commands()
    commands[str(name).lower()] = value
    save_commands(commands)


def get_learned_command(name):
    commands = load_commands()
    return commands.get(str(name).lower())
