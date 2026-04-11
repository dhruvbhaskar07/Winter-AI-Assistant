import requests
import os
import json
from dotenv import dotenv_values, load_dotenv
from utils.memory import get_long_term_context, get_recent_context, get_user_profile_context, get_user_preferences
from utils.personas import get_persona_meta, normalize_persona_id

SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_ROOT)
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(dotenv_path=ENV_FILE)

MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
INTENT_MODEL = os.getenv("INTENT_MODEL", MODEL)
BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Winter")
ASSISTANT_BOSS_NAME = os.getenv("ASSISTANT_BOSS_NAME", "WINTER")


def _assistant_system_prompt():
    prefs = get_user_preferences()
    persona_id = normalize_persona_id(prefs.get("assistant_persona", "balanced"))
    persona = get_persona_meta(persona_id)
    return (
        f"You are {ASSISTANT_NAME}, a real conversational AI assistant (not a generic chatbot). "
        "Identity: female assistant, warm, friend-like, and practical. "
        f"Primary user is your boss: {ASSISTANT_BOSS_NAME}. "
        "Treat boss context as important and personalize accordingly. "
        f"Selected persona: {persona.get('label', 'Balanced')}. "
        f"{persona.get('system_prompt', '')} "
        f"Persona style rules: {persona.get('style_rules', '')} "
        f"Persona speech habits: {persona.get('speech_habits', '')} "
        f"Persona avoid rules: {persona.get('avoid_style', '')} "
        f"Persona examples: {persona.get('sample_lines', '')} "
        "This persona must be clearly noticeable in wording, rhythm, warmth, and attitude. "
        "Do not keep sounding the same across different personas. "
        "If persona is friendly or playful, sound more lively and personal. "
        "If persona is professional, sound more polished and formal. "
        "If persona is mentor, sound more patient and guiding. "
        "If persona is concise, keep replies clearly shorter than other personas. "
        "Follow the persona speech habits actively, not passively. "
        "Stay within the chosen persona even in simple greetings and smalltalk. "
        "Default response style: short, clear, and action-oriented. "
        "Only provide detailed answers when user explicitly asks for details, explanation, full version, or step-by-step. "
        "Use Hinglish naturally when user writes in Hinglish. No emojis unless user asks. "
        "Use memory context actively: short-term context for immediate continuity and long-term context for user habits/preferences. "
        "Adapt to user taste, language, and workflow style from profile context. "
        "When live web context is provided, treat it as your tool output: prioritize it over memory, "
        "do not fabricate facts beyond it, and answer naturally like a human assistant. "
        "Sound calm and natural, avoid dramatic slang or repetitive openers. "
        "Never inject current affairs/news on your own in casual chat. "
        "If user did not explicitly ask for latest/news/updates, stay conversational and non-factual. "
        "For casual conversation, continue like a real human instead of ending the chat every turn. "
        "Do not keep repeating the same reassurance line or same closing phrase. "
        "If user is casually talking, respond with fresh wording based on the immediate previous exchange. "
        "When suitable, add one natural follow-up, light observation, or playful continuation. "
        "Avoid robotic lines like 'jab bhi kuch chahiye bata dena' on every smalltalk turn. "
        "Avoid copy-pasting your own recent phrasing from memory unless the user asked you to repeat something. "
        "For latest/news style queries: by default do NOT include source names, publish times, or links. "
        "Just give a clean human-like summary with a short takeaway first, then 2-4 concise points if needed. "
        "Only show source/date/link if user explicitly asks."
    )


def _get_api_key():
    # Reload env so runtime changes in .env are picked up without restart.
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    api_key = os.getenv("API_KEY")
    if api_key:
        return api_key

    try:
        values = dotenv_values(ENV_FILE, encoding="utf-8-sig")
        return values.get("API_KEY", "")
    except Exception:
        return ""


def _extract_text(payload):
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            text = "".join(parts).strip()
            if text:
                return text

    output = payload.get("output")
    if isinstance(output, list):
        texts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
        text = "".join(texts).strip()
        if text:
            return text

    return None


def _extract_error(payload):
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or str(error)
        return message
    return None


def _extract_stream_delta(payload):
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        delta = choices[0].get("delta", {})
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            text = "".join(parts)
            if text:
                return text
    return ""


def generate_wake_acknowledgement():
    api_key = _get_api_key()
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    data = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return one short wake acknowledgement line, 2 to 6 words, "
                    "natural and friendly, Hinglish allowed, no emojis."
                ),
            },
            {"role": "user", "content": "Wake acknowledgement line only."},
        ],
        "temperature": 0.9,
    }

    try:
        response = requests.post(BASE_URL, json=data, headers=headers, timeout=8)
        if response.status_code >= 400:
            return None
        payload = response.json()
        text = _extract_text(payload)
        if not text:
            return None
        line = text.strip().splitlines()[0].strip().strip("\"'")
        words = line.split()
        if not words:
            return None
        if len(words) > 6:
            line = " ".join(words[:6])
        return line
    except Exception:
        return None


def ask_ai(prompt):
    return ask_ai_with_context(prompt, extra_context="")


def _build_ai_request(prompt, extra_context=""):
    context = get_recent_context()
    profile_context = get_user_profile_context()
    long_term_context = get_long_term_context(limit=10)
    lowered_prompt = str(prompt or "").strip().lower()
    is_casual_turn = bool(
        extra_context and "conversation mode only" in str(extra_context).lower()
    )
    if not is_casual_turn:
        is_casual_turn = bool(
            any(token in lowered_prompt for token in ("hello", "hi", "hey", "kuch nhi", "kuch nahi", "nhi", "nothing"))
            and not any(token in lowered_prompt for token in ("news", "latest", "update", "price", "stock"))
        )

    user_payload = (
        f"Profile Context:\n{profile_context}\n\n"
        f"Short-Term Memory (recent chats):\n{context or 'None'}\n\n"
        f"Long-Term Memory (historical):\n{long_term_context or 'None'}\n\n"
        f"Live Context (date/time/web/news):\n{extra_context or 'None'}\n\n"
        f"Current Query: {prompt}"
    )

    return {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": _assistant_system_prompt(),
            },
            {
                "role": "user",
                "content": user_payload,
            },
        ],
        "temperature": 0.72 if is_casual_turn else 0.45,
        "max_tokens": 520,
    }


def ask_ai_with_context(prompt, extra_context=""):
    api_key = _get_api_key()
    if not api_key:
        return "Error: Missing API key. Set API_KEY in .env"

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    data = _build_ai_request(prompt, extra_context)

    try:
        response = requests.post(BASE_URL, json=data, headers=headers, timeout=45)
    except requests.RequestException as e:
        return f"Error contacting AI service: {str(e)}"

    try:
        payload = response.json()
    except ValueError:
        return f"Error: API returned non-JSON response (status {response.status_code})."

    if response.status_code >= 400:
        return f"API Error {response.status_code}: {_extract_error(payload) or 'Unknown error'}"

    text = _extract_text(payload)
    if text:
        return text

    return "Error: API response did not contain assistant text."


def stream_ai(prompt):
    return stream_ai_with_context(prompt, extra_context="")


def stream_ai_with_context(prompt, extra_context=""):
    api_key = _get_api_key()
    if not api_key:
        yield "Error: Missing API key. Set API_KEY in .env"
        return

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    data = _build_ai_request(prompt, extra_context)
    data["stream"] = True

    try:
        response = requests.post(BASE_URL, json=data, headers=headers, timeout=(20, 180), stream=True)
    except requests.RequestException as e:
        yield f"Error contacting AI service: {str(e)}"
        return

    if response.status_code >= 400:
        try:
            payload = response.json()
            message = _extract_error(payload) or "Unknown error"
        except ValueError:
            message = f"API returned non-JSON response (status {response.status_code})."
        yield f"API Error {response.status_code}: {message}"
        return

    response.encoding = "utf-8"
    emitted = False
    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = str(raw_line).strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                payload = json.loads(data_str)
            except Exception:
                continue

            error_message = _extract_error(payload)
            if error_message:
                yield f"API Error: {error_message}"
                return

            delta = _extract_stream_delta(payload)
            if delta:
                emitted = True
                yield delta
    except requests.RequestException as e:
        if not emitted:
            yield f"Error contacting AI service: {str(e)}"
            return
    finally:
        response.close()

    if not emitted:
        yield ""


def detect_intent(prompt):
    api_key = _get_api_key()
    if not api_key:
        return {"intent": "general", "target": prompt}

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    system_prompt = """
You are an AI that extracts intent from user commands.

Return ONLY JSON in this format:
{
  "intent": "...",
  "target": "..."
}

Possible intents:
- open_file
- open_app
- organize_files
- create_folder
- rename_file
- date_time
- web_search
- latest_info
- general

Rules:
- If user refers to previously opened file (example: "open that file again", "open previous file", "open last file"),
  return target exactly "__last_file__".
- Return only valid JSON, no markdown.

Examples:
User: open resume file
Output: {"intent": "open_file", "target": "resume"}

User: open chrome
Output: {"intent": "open_app", "target": "chrome"}

User: what is AI
Output: {"intent": "general", "target": "what is AI"}

User: open that file again
Output: {"intent": "open_file", "target": "__last_file__"}

User: organize downloads
Output: {"intent": "organize_files", "target": "downloads"}

User: create folder project
Output: {"intent": "create_folder", "target": "project"}

User: create a folder on desktop named as Galaxy
Output: {"intent": "create_folder", "target": "desktop,Galaxy"}

User: rename file test.txt to new.txt
Output: {"intent": "rename_file", "target": "test.txt,new.txt"}

User: what is current time
Output: {"intent": "date_time", "target": "current time"}

User: search web for python 3.13 features
Output: {"intent": "web_search", "target": "python 3.13 features"}

User: latest ai news
Output: {"intent": "latest_info", "target": "ai news"}
"""

    data = {
        "model": INTENT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }

    try:
        response = requests.post(BASE_URL, json=data, headers=headers, timeout=20)
        payload = response.json()
        content = _extract_text(payload) or ""

        if response.status_code >= 400:
            return {"intent": "general", "target": prompt}

        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return {"intent": "general", "target": prompt}

        intent = parsed.get("intent", "general")
        target = parsed.get("target", prompt)

        if intent not in {
            "open_file",
            "open_app",
            "organize_files",
            "create_folder",
            "rename_file",
            "date_time",
            "web_search",
            "latest_info",
            "general",
        }:
            return {"intent": "general", "target": prompt}

        if not isinstance(target, str) or not target.strip():
            target = prompt

        normalized_target = target.strip()
        target_lower = normalized_target.lower()
        if intent == "open_file":
            if any(
                phrase in target_lower
                for phrase in (
                    "__last_file__",
                    "that file",
                    "previous file",
                    "last file",
                    "open it again",
                    "open that again",
                )
            ):
                normalized_target = "__last_file__"

        return {"intent": intent, "target": normalized_target}
    except Exception:
        return {"intent": "general", "target": prompt}
