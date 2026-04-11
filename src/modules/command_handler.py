import os
import re

from modules.system_control import get_top_matches, open_selected_file, open_app
from modules.automation import organize_downloads, create_folder, rename_file
from services.llm_service import detect_intent, ask_ai, ask_ai_with_context, stream_ai, stream_ai_with_context
from services.live_info_service import build_live_context, get_local_datetime_info
from utils.command_learning import get_learned_command
from utils.memory import (
    add_to_memory,
    export_memory_history,
    get_last_file,
    get_recent_context,
    get_user_preferences,
)
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

    if re.search(r"\b(date|time|current time|today(?:'s)? date|what time)\b", lowered):
        return {"intent": "date_time", "target": "local"}

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


def _ask_ai_with_auto_web(user_input):
    prefs = get_user_preferences()
    live_enabled = bool(prefs.get("live_web_access", True))
    web_mode = str(prefs.get("web_search_mode", "smart")).strip().lower()
    news_region = str(prefs.get("preferred_news_region", "in")).strip().lower()
    news_language = str(prefs.get("preferred_news_language", "en")).strip().lower()

    def needs_web_by_query(text):
        lowered = str(text or "").lower()
        return bool(
            re.search(
                r"\b("
                r"latest|current|today|news|price|stock|release|launch|update|recent|breaking|live|"
                r"yesterday|kal|abhi|aaj|past|last|days|din|week|weekend|"
                r"invention|announce|announcement|reported|headline|headlines"
                r")\b",
                lowered,
            )
        )

    def is_casual_smalltalk(text):
        lowered = str(text or "").strip().lower()
        if not lowered:
            return True
        if needs_web_by_query(lowered):
            return False
        return bool(
            re.search(
                r"\b("
                r"hi|hii|hello|hey|yo|sup|kya\s+scene|kaisa|kaisi|"
                r"kuch\s*nahi|kuch\s*nhi|kuch\s+ni|tum\s+batao|you\s+tell|"
                r"bolo|baat\s+karo|just\s+talk|chat"
                r")\b",
                lowered,
            )
        )

    def response_uncertain(text):
        lowered = str(text or "").lower()
        patterns = (
            "i don't know",
            "i do not know",
            "not sure",
            "can't confirm",
            "cannot confirm",
            "no data",
            "not available",
            "as an ai",
            "might be",
            "likely",
            "uncertain",
            "unable to browse",
        )
        return any(p in lowered for p in patterns)

    def infer_recent_topic():
        context = str(get_recent_context() or "")
        user_lines = []
        for line in context.splitlines():
            if line.startswith("User:"):
                user_lines.append(line.replace("User:", "", 1).strip())

        # Walk backwards and pick first meaningful token from most recent user query.
        stopwords = {
            "kya",
            "hai",
            "ka",
            "ke",
            "ki",
            "me",
            "mein",
            "news",
            "latest",
            "update",
            "updates",
            "tell",
            "about",
            "please",
            "aur",
            "or",
            "and",
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "usne",
            "uska",
            "wo",
            "woh",
            "it",
            "that",
        }
        for query in reversed(user_lines):
            tokens = re.findall(r"[a-zA-Z0-9\-\+\.]{3,}", query.lower())
            for token in tokens:
                if token not in stopwords:
                    return token
        return ""

    def resolve_followup_query(raw_query):
        q = str(raw_query or "").strip()
        lowered = q.lower()
        is_ambiguous_followup = bool(
            re.search(r"\b(usne|uska|wo|woh|it|that|unhone|unka)\b", lowered)
        )
        if not is_ambiguous_followup:
            return q

        topic = infer_recent_topic()
        if not topic:
            return q
        return f"{topic} {q}"

    if (not live_enabled) or web_mode == "off":
        return ask_ai(user_input)

    effective_query = resolve_followup_query(user_input)

    if is_casual_smalltalk(user_input):
        return ask_ai_with_context(
            user_input,
            extra_context=(
                "Conversation mode only. User asked casual talk, not current affairs/news. "
                "Do not provide unsolicited news or factual live updates. "
                "Reply friendly, short, and human-like. "
                "Continue the ongoing conversation naturally like a real person. "
                "Do not repeat the same reassurance or closing line from recent replies. "
                "Use the immediate recent chat context and give a fresh, natural continuation."
            ),
        )

    if web_mode == "always":
        live_context = build_live_context(
            effective_query,
            live_web_access=True,
            max_results=4,
            region=news_region,
            language=news_language,
        )
        response = ask_ai_with_context(user_input, extra_context=live_context)
    else:
        if needs_web_by_query(user_input):
            live_context = build_live_context(
                effective_query,
                live_web_access=True,
                max_results=4,
                region=news_region,
                language=news_language,
            )
            response = ask_ai_with_context(user_input, extra_context=live_context)
            if not str(response).startswith("Error: Missing API key"):
                return response

        base_response = ask_ai(user_input)
        if str(base_response).startswith("Error: Missing API key"):
            live_context = build_live_context(
                effective_query,
                live_web_access=True,
                max_results=4,
                region=news_region,
                language=news_language,
            )
            return (
                "AI model key missing. I fetched live internet context below:\n\n"
                f"{live_context}"
            )

        if needs_web_by_query(user_input) or response_uncertain(base_response):
            live_context = build_live_context(
                effective_query,
                live_web_access=True,
                max_results=4,
                region=news_region,
                language=news_language,
            )
            response = ask_ai_with_context(user_input, extra_context=live_context)
        else:
            return base_response

    if str(response).startswith("Error: Missing API key"):
        live_context = build_live_context(
            effective_query,
            live_web_access=True,
            max_results=4,
            region=news_region,
            language=news_language,
        )
        return (
            "AI model key missing. I fetched live internet context below:\n\n"
            f"{live_context}"
        )
    return response


def _stream_ai_with_auto_web(user_input):
    prefs = get_user_preferences()
    live_enabled = bool(prefs.get("live_web_access", True))
    web_mode = str(prefs.get("web_search_mode", "smart")).strip().lower()
    news_region = str(prefs.get("preferred_news_region", "in")).strip().lower()
    news_language = str(prefs.get("preferred_news_language", "en")).strip().lower()

    def needs_web_by_query(text):
        lowered = str(text or "").lower()
        return bool(
            re.search(
                r"\b("
                r"latest|current|today|news|price|stock|release|launch|update|recent|breaking|live|"
                r"yesterday|kal|abhi|aaj|past|last|days|din|week|weekend|"
                r"invention|announce|announcement|reported|headline|headlines"
                r")\b",
                lowered,
            )
        )

    def is_casual_smalltalk(text):
        lowered = str(text or "").strip().lower()
        if not lowered:
            return True
        if needs_web_by_query(lowered):
            return False
        return bool(
            re.search(
                r"\b("
                r"hi|hii|hello|hey|yo|sup|kya\s+scene|kaisa|kaisi|"
                r"kuch\s*nahi|kuch\s*nhi|kuch\s+ni|tum\s+batao|you\s+tell|"
                r"bolo|baat\s+karo|just\s+talk|chat"
                r")\b",
                lowered,
            )
        )

    def response_uncertain(text):
        lowered = str(text or "").lower()
        patterns = (
            "i don't know",
            "i do not know",
            "not sure",
            "can't confirm",
            "cannot confirm",
            "no data",
            "not available",
            "as an ai",
            "might be",
            "likely",
            "uncertain",
            "unable to browse",
        )
        return any(p in lowered for p in patterns)

    def infer_recent_topic():
        context = str(get_recent_context() or "")
        user_lines = []
        for line in context.splitlines():
            if line.startswith("User:"):
                user_lines.append(line.replace("User:", "", 1).strip())

        stopwords = {
            "kya",
            "hai",
            "ka",
            "ke",
            "ki",
            "me",
            "mein",
            "news",
            "latest",
            "update",
            "updates",
            "tell",
            "about",
            "please",
            "aur",
            "or",
            "and",
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "usne",
            "uska",
            "wo",
            "woh",
            "it",
            "that",
        }
        for query in reversed(user_lines):
            tokens = re.findall(r"[a-zA-Z0-9\-\+\.]{3,}", query.lower())
            for token in tokens:
                if token not in stopwords:
                    return token
        return ""

    def resolve_followup_query(raw_query):
        q = str(raw_query or "").strip()
        lowered = q.lower()
        is_ambiguous_followup = bool(
            re.search(r"\b(usne|uska|wo|woh|it|that|unhone|unka)\b", lowered)
        )
        if not is_ambiguous_followup:
            return q

        topic = infer_recent_topic()
        if not topic:
            return q
        return f"{topic} {q}"

    def _yield_once(text):
        yield str(text)

    if (not live_enabled) or web_mode == "off":
        yield from stream_ai(user_input)
        return

    effective_query = resolve_followup_query(user_input)

    if is_casual_smalltalk(user_input):
        yield from stream_ai_with_context(
            user_input,
            extra_context=(
                "Conversation mode only. User asked casual talk, not current affairs/news. "
                "Do not provide unsolicited news or factual live updates. "
                "Reply friendly, short, and human-like. "
                "Continue the ongoing conversation naturally like a real person. "
                "Do not repeat the same reassurance or closing line from recent replies. "
                "Use the immediate recent chat context and give a fresh, natural continuation."
            ),
        )
        return

    if web_mode == "always":
        live_context = build_live_context(
            effective_query,
            live_web_access=True,
            max_results=4,
            region=news_region,
            language=news_language,
        )
        yield from stream_ai_with_context(user_input, extra_context=live_context)
        return

    if needs_web_by_query(user_input):
        live_context = build_live_context(
            effective_query,
            live_web_access=True,
            max_results=4,
            region=news_region,
            language=news_language,
        )
        yield from stream_ai_with_context(user_input, extra_context=live_context)
        return

    yield from stream_ai(user_input)


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

    elif intent == "date_time":
        response = get_local_datetime_info()
        add_to_memory(user_input, response)
        return response

    else:
        response = _ask_ai_with_auto_web(user_input)
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


def _handle_single_command_stream(user_input):
    intent_data = _rule_based_intent(user_input) or detect_intent(user_input)
    intent = intent_data.get("intent")
    if intent not in {
        "open_file",
        "open_app",
        "organize_files",
        "create_folder",
        "rename_file",
        "export_history",
        "date_time",
    }:
        yield from _stream_ai_with_auto_web(user_input)
        return

    response = _handle_single_command(user_input)
    yield str(response)


def handle_command_stream(user_input):
    commands = _split_compound_commands(user_input)
    if len(commands) <= 1:
        yield from _handle_single_command_stream(user_input)
        return

    first = True
    for command in commands:
        if not first:
            yield "\n"
        first = False
        prefix = f"[{command}] -> "
        yielded_any = False
        for chunk in _handle_single_command_stream(command):
            if not yielded_any:
                yield prefix + str(chunk)
                yielded_any = True
            else:
                yield str(chunk)
