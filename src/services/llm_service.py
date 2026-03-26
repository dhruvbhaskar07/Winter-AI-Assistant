import requests
import os
import json
from dotenv import load_dotenv
from utils.memory import get_long_term_context, get_recent_context, get_user_profile_context

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
    return (
        f"You are {ASSISTANT_NAME}, a real conversational AI assistant (not a generic chatbot). "
        "Identity: female assistant, warm, friend-like, and practical. "
        f"Primary user is your boss: {ASSISTANT_BOSS_NAME}. "
        "Treat boss context as important and personalize accordingly. "
        "Default response style: short, clear, and action-oriented. "
        "Only provide detailed answers when user explicitly asks for details, explanation, full version, or step-by-step. "
        "Use Hinglish naturally when user writes in Hinglish. No emojis unless user asks. "
        "Use memory context actively: short-term context for immediate continuity and long-term context for user habits/preferences. "
        "Adapt to user taste, language, and workflow style from profile context."
    )


def _get_api_key():
    # Reload env so runtime changes in .env are picked up without restart.
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    return os.getenv("API_KEY")


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
    api_key = _get_api_key()
    if not api_key:
        return "Error: Missing API key. Set API_KEY in .env"

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    context = get_recent_context()
    profile_context = get_user_profile_context()
    long_term_context = get_long_term_context(limit=10)

    user_payload = (
        f"Profile Context:\n{profile_context}\n\n"
        f"Short-Term Memory (recent chats):\n{context or 'None'}\n\n"
        f"Long-Term Memory (historical):\n{long_term_context or 'None'}\n\n"
        f"Current Query: {prompt}"
    )

    data = {
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
    }

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

        if intent not in {"open_file", "open_app", "organize_files", "create_folder", "rename_file", "general"}:
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
