import os
import re

from modules.system_control import get_top_matches, open_selected_file, open_app
from modules.automation import organize_downloads, create_folder, rename_file
from services.llm_service import detect_intent, ask_ai
from utils.command_learning import get_learned_command
from utils.memory import add_to_memory, export_memory_history, get_last_file
from utils.safety import confirm_action

_FILE_SELECTION_HANDLER = None


def set_file_selection_handler(handler):
    global _FILE_SELECTION_HANDLER
    _FILE_SELECTION_HANDLER = handler


def clear_file_selection_handler():
    global _FILE_SELECTION_HANDLER
    _FILE_SELECTION_HANDLER = None


def _select_file_index(matches, target_text):
    if _FILE_SELECTION_HANDLER is not None:
        try:
            selected = _FILE_SELECTION_HANDLER(matches, target_text)
            if selected is None:
                return None
            if isinstance(selected, int) and 0 <= selected < len(matches):
                return selected
        except Exception:
            pass

    print("\nFound files:")
    for i, file in enumerate(matches):
        print(f"{i + 1}. {file}")

    try:
        choice = int(input("\nSelect file number: "))
        if 1 <= choice <= len(matches):
            return choice - 1
    except Exception:
        pass

    return None


def _split_compound_commands(user_input):
    text = str(user_input).strip()
    if not text:
        return []

    splitter = re.compile(
        r"\s+(?:and then|then|after that|and|aur|phir|fir|uske baad)\s+",
        flags=re.IGNORECASE,
    )
    parts = [part.strip(" .") for part in splitter.split(text) if part.strip(" .")]
    return parts if parts else [text]


def _extract_folder_details(user_input, target):
    text = str(user_input).strip()
    target_text = str(target).strip()
    lowered = text.lower()

    base_map = {
        "desktop": os.path.expanduser("~/Desktop"),
        "downloads": os.path.expanduser("~/Downloads"),
        "documents": os.path.expanduser("~/Documents"),
        "pictures": os.path.expanduser("~/Pictures"),
        "videos": os.path.expanduser("~/Videos"),
    }

    base_path = "."
    for key, resolved in base_map.items():
        if key in lowered:
            base_path = resolved
            break

    if "," in target_text:
        left, right = [part.strip() for part in target_text.split(",", 1)]
        if left.lower() in base_map and right:
            return right, base_map[left.lower()]
        if os.path.isabs(left) and right:
            return right, left
        if right:
            return right, base_path

    match = re.search(
        r"(?:named\s+as|named|name\s+as|called|name\s+rakho|naam\s+rakho|uska\s+name\s+rakho)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        folder_name = match.group(1).strip().strip("\"'")
        if folder_name:
            return folder_name, base_path

    cleaned_target = target_text.strip().strip("\"'")
    return cleaned_target, base_path


def _rule_based_intent(user_input):
    lowered = str(user_input).lower()

    if "export" in lowered and ("history" in lowered or "chat" in lowered or "conversation" in lowered):
        if "pdf" in lowered:
            return {"intent": "export_history", "target": "pdf"}
        return {"intent": "export_history", "target": "doc"}

    if re.search(r"\borgani[sz](e|ed|ing)?\b", lowered) and re.search(r"\bdownload(s)?\b", lowered):
        return {"intent": "organize_files", "target": "downloads"}
    if ("clean" in lowered or "sort" in lowered) and "download" in lowered:
        return {"intent": "organize_files", "target": "downloads"}

    if ("create" in lowered or "bna" in lowered or "banao" in lowered or "bana" in lowered) and (
        "folder" in lowered or "directory" in lowered
    ):
        return {"intent": "create_folder", "target": user_input}

    rename_match = re.search(
        r"rename\s+file\s+(.+?)\s+to\s+(.+)$",
        str(user_input),
        flags=re.IGNORECASE,
    )
    if rename_match:
        old_name = rename_match.group(1).strip().strip("\"'")
        new_name = rename_match.group(2).strip().strip("\"'")
        return {"intent": "rename_file", "target": f"{old_name},{new_name}"}

    return None


def _handle_single_command(user_input):
    intent_data = _rule_based_intent(user_input) or detect_intent(user_input)
    intent = intent_data.get("intent")
    target = intent_data.get("target", user_input)

    if intent == "open_file":
        target_text = str(target).strip()
        target_lower = target_text.lower()

        learned = get_learned_command(target_text)
        if learned:
            response = open_selected_file(learned)
            add_to_memory(user_input, response)
            return response

        if target_text == "__last_file__" or target_lower in ["that file", "previous file", "last file"]:
            last_file = get_last_file()
            if last_file:
                response = open_selected_file(last_file)
            else:
                response = "No previous file found"
            add_to_memory(user_input, response)
            return response

        matches = get_top_matches(target_text)

        if not matches:
            response = "No file found"
            add_to_memory(user_input, response)
            return response

        selected_index = _select_file_index(matches, target_text)
        if selected_index is None:
            response = "Invalid selection"
        else:
            response = open_selected_file(matches[selected_index], alias=target_text)

        add_to_memory(user_input, response)
        return response

    elif intent == "open_app":
        response = open_app(target)
        add_to_memory(user_input, response)
        return response

    elif intent == "organize_files":
        if not confirm_action("This will organize your Downloads folder. Continue?", use_voice=True):
            response = "Action cancelled"
        else:
            response = organize_downloads()
        add_to_memory(user_input, response)
        return response

    elif intent == "create_folder":
        folder_name, base_path = _extract_folder_details(user_input, target)
        if not folder_name:
            response = "Folder name missing"
        else:
            display_path = os.path.join(base_path, folder_name)
            if not confirm_action(f"Create folder '{display_path}'?", use_voice=True):
                response = "Action cancelled"
            else:
                response = create_folder(folder_name, base_path=base_path)
        add_to_memory(user_input, response)
        return response

    elif intent == "rename_file":
        try:
            old_name, new_name = str(target).split(",", 1)
            old_name = old_name.strip()
            new_name = new_name.strip()
            if not confirm_action(f"Rename '{old_name}' to '{new_name}'?", use_voice=True):
                response = "Action cancelled"
            else:
                response = rename_file(old_name, new_name)
        except Exception:
            response = "Invalid rename format"

        add_to_memory(user_input, response)
        return response

    elif intent == "export_history":
        export_format = str(target).strip().lower() if target else "pdf"
        if export_format not in {"pdf", "doc"}:
            export_format = "pdf"
        response = export_memory_history(export_format=export_format)
        add_to_memory(user_input, response)
        return response

    else:
        response = ask_ai(user_input)
        add_to_memory(user_input, response)
        return response


def handle_command(user_input):
    commands = _split_compound_commands(user_input)
    if len(commands) <= 1:
        return _handle_single_command(user_input)

    responses = []
    for command in commands:
        responses.append(f"[{command}] -> {_handle_single_command(command)}")
    return "\n".join(responses)
