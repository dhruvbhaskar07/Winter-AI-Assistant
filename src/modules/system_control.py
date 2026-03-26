import os

from utils.file_search import search_file
from utils.command_learning import learn_command
from utils.memory import set_last_file


def get_top_matches(file_name, limit=5):
    matches = search_file(file_name)
    return matches[:limit]


def open_file(file_name):
    try:
        os.startfile(file_name)  # type: ignore
        return f"Opened {file_name}"
    except Exception as e:
        return f"Error opening file: {str(e)}"


def open_selected_file(file_path, alias=None):
    try:
        os.startfile(file_path)  # type: ignore
        set_last_file(file_path)
        if alias:
            learn_command(alias, file_path)
        return f"Opened: {file_path}"
    except Exception as e:
        return f"Error: {str(e)}"


def open_file_by_name(file_name):
    matches = search_file(file_name)

    if not matches:
        return "No file found"

    try:
        os.startfile(matches[0])  # type: ignore
        return f"Opened: {matches[0]}"
    except Exception as e:
        return f"Error: {str(e)}"


def open_app(app_name):
    try:
        os.system(f"start {app_name}")
        return f"Opened {app_name}"
    except Exception as e:
        return f"Error opening app: {str(e)}"
