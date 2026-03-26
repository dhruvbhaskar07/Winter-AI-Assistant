import json
import os
import sqlite3
from datetime import datetime


SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
MEMORY_DB = os.path.join(DATA_DIR, "memory_history.db")
MAX_HISTORY_ITEMS = 10
MAX_CONTEXT_ITEMS = 6
MAX_FIELD_CHARS = 500
ARCHIVE_BATCH_SIZE = 10
LONG_TERM_CONTEXT_ITEMS = 10


def _default_user_profile():
    return {
        "language_scores": {"english": 0, "hindi": 0, "hinglish": 0},
        "style_scores": {"short": 0, "detailed": 0},
        "friend_tone_score": 0,
        "workflow_counts": {
            "open": 0,
            "create": 0,
            "rename": 0,
            "organize": 0,
            "general": 0,
        },
    }


def _default_user_preferences():
    return {
        "preferred_language": "auto",
        "preferred_tone": "auto",
        "preferred_response_length": "auto",
    }


def _safe_profile(raw):
    profile = _default_user_profile()
    if not isinstance(raw, dict):
        return profile

    for section in ("language_scores", "style_scores", "workflow_counts"):
        source = raw.get(section, {})
        if isinstance(source, dict):
            for key in profile[section]:
                value = source.get(key)
                if isinstance(value, int):
                    profile[section][key] = max(0, value)

    friend_score = raw.get("friend_tone_score")
    if isinstance(friend_score, int):
        profile["friend_tone_score"] = max(0, friend_score)

    return profile


def _safe_preferences(raw):
    preferences = _default_user_preferences()
    if not isinstance(raw, dict):
        return preferences

    language = str(raw.get("preferred_language", "auto")).strip().lower()
    tone = str(raw.get("preferred_tone", "auto")).strip().lower()
    response_length = str(raw.get("preferred_response_length", "auto")).strip().lower()

    if language in {"auto", "english", "hindi", "hinglish"}:
        preferences["preferred_language"] = language
    if tone in {"auto", "friend-like", "professional-friendly"}:
        preferences["preferred_tone"] = tone
    if response_length in {"auto", "short", "detailed"}:
        preferences["preferred_response_length"] = response_length

    return preferences


def _infer_last_file_from_history(history):
    for item in reversed(history):
        response = item.get("response", "")
        if isinstance(response, str) and response.startswith("Opened: "):
            return response.replace("Opened: ", "", 1).strip()
    return None


def _detect_language_bucket(text):
    value = str(text or "").strip().lower()
    if not value:
        return "english"

    if any("\u0900" <= ch <= "\u097f" for ch in value):
        return "hindi"

    hindi_roman = {
        "hai",
        "nahi",
        "nhi",
        "kya",
        "mujhe",
        "tum",
        "kr",
        "kar",
        "bolo",
        "bata",
        "acha",
        "thik",
    }
    english_markers = {"what", "how", "please", "can", "tell", "explain", "open", "create"}

    tokens = set(value.split())
    has_hindi_roman = bool(tokens & hindi_roman)
    has_english = bool(tokens & english_markers)

    if has_hindi_roman and has_english:
        return "hinglish"
    if has_hindi_roman:
        return "hinglish"
    return "english"


def _detect_style_bucket(text):
    value = str(text or "").strip().lower()
    if not value:
        return "short"
    if any(phrase in value for phrase in ("detail", "explain", "step by step", "full", "deep")):
        return "detailed"
    if len(value.split()) <= 8:
        return "short"
    return "short"


def _detect_workflow_bucket(text):
    value = str(text or "").strip().lower()
    if any(word in value for word in ("open", "launch", "start")):
        return "open"
    if any(word in value for word in ("create", "make", "bna", "banao")):
        return "create"
    if "rename" in value:
        return "rename"
    if "organize" in value or "sort" in value or "clean" in value:
        return "organize"
    return "general"


def _update_user_profile(profile, user_text):
    lang_key = _detect_language_bucket(user_text)
    style_key = _detect_style_bucket(user_text)
    flow_key = _detect_workflow_bucket(user_text)

    profile["language_scores"][lang_key] += 1
    profile["style_scores"][style_key] += 1
    profile["workflow_counts"][flow_key] += 1

    lowered = str(user_text or "").lower()
    if any(word in lowered for word in ("friend", "yaar", "buddy", "bro", "sis", "dost")):
        profile["friend_tone_score"] += 1


def ensure_memory_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(MEMORY_FILE):
        return

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "history": [],
                "pending_archive": [],
                "last_file": None,
                "user_profile": _default_user_profile(),
                "user_preferences": _default_user_preferences(),
            },
            f,
            indent=4,
        )


def ensure_memory_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user_text TEXT NOT NULL,
                ai_text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'app'
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_start TEXT NOT NULL,
                ts_end TEXT NOT NULL,
                exchange_count INTEGER NOT NULL,
                summary_text TEXT NOT NULL,
                profile_snapshot TEXT,
                source TEXT NOT NULL DEFAULT 'app'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _load_json_with_fallbacks():
    with open(MEMORY_FILE, "rb") as f:
        raw = f.read()

    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            data = json.loads(text)
            return data, encoding
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue

    raise ValueError("Unable to decode memory file")


def load_memory():
    ensure_memory_file()

    if not os.path.exists(MEMORY_FILE):
        return {
            "history": [],
            "pending_archive": [],
            "last_file": None,
            "user_profile": _default_user_profile(),
            "user_preferences": _default_user_preferences(),
        }

    try:
        data, source_encoding = _load_json_with_fallbacks()
        if isinstance(data, dict):
            history = data.get("history")
            if not isinstance(history, list):
                history = []

            pending_archive = data.get("pending_archive")
            if not isinstance(pending_archive, list):
                pending_archive = []

            last_file = data.get("last_file")
            if last_file is not None and not isinstance(last_file, str):
                last_file = None
            if not last_file:
                last_file = _infer_last_file_from_history(history)

            user_profile = _safe_profile(data.get("user_profile"))
            user_preferences = _safe_preferences(data.get("user_preferences"))

            normalized = {
                "history": history,
                "pending_archive": pending_archive,
                "last_file": last_file,
                "user_profile": user_profile,
                "user_preferences": user_preferences,
            }
            if normalized != data or source_encoding not in ("utf-8", "utf-8-sig"):
                save_memory(normalized)
            return normalized
    except (ValueError, OSError):
        pass

    return {
        "history": [],
        "pending_archive": [],
        "last_file": None,
        "user_profile": _default_user_profile(),
        "user_preferences": _default_user_preferences(),
    }


def save_memory(memory):
    ensure_memory_file()
    temp_file = f"{MEMORY_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=4)
    os.replace(temp_file, MEMORY_FILE)


def _build_batch_summary(entries, profile, preferences):
    first_ts = str(entries[0].get("ts", ""))
    last_ts = str(entries[-1].get("ts", ""))
    exchange_count = len(entries)

    lang_pref = max(profile["language_scores"], key=profile["language_scores"].get)
    style_pref = max(profile["style_scores"], key=profile["style_scores"].get)
    flow_pref = max(profile["workflow_counts"], key=profile["workflow_counts"].get)

    highlights = []
    for item in entries[-3:]:
        user_line = str(item.get("user", "")).strip()[:80]
        ai_line = str(item.get("response", "")).strip()[:80]
        if user_line or ai_line:
            highlights.append(f"U:{user_line} | A:{ai_line}")

    summary = (
        f"Batch summary ({exchange_count} chats). "
        f"Language trend={lang_pref}, response style={style_pref}, workflow focus={flow_pref}, "
        f"tone={'friend-like' if profile.get('friend_tone_score', 0) >= 2 else 'professional-friendly'}. "
        f"Preference lock: language={preferences.get('preferred_language')}, "
        f"tone={preferences.get('preferred_tone')}, length={preferences.get('preferred_response_length')}. "
        f"Recent highlights: {' || '.join(highlights) if highlights else 'N/A'}"
    )

    return {
        "ts_start": first_ts,
        "ts_end": last_ts,
        "exchange_count": exchange_count,
        "summary_text": summary,
    }


def _archive_pending_to_db(memory, force=False):
    pending = memory.get("pending_archive", [])
    if not pending:
        return

    if not force and len(pending) < ARCHIVE_BATCH_SIZE:
        return

    ensure_memory_db()
    conn = sqlite3.connect(MEMORY_DB)
    try:
        cursor = conn.cursor()

        while pending and (force or len(pending) >= ARCHIVE_BATCH_SIZE):
            batch_size = ARCHIVE_BATCH_SIZE if len(pending) >= ARCHIVE_BATCH_SIZE else len(pending)
            batch = pending[:batch_size]
            summary_payload = _build_batch_summary(
                batch,
                _safe_profile(memory.get("user_profile")),
                _safe_preferences(memory.get("user_preferences")),
            )

            cursor.execute(
                """
                INSERT INTO memory_summaries (ts_start, ts_end, exchange_count, summary_text, profile_snapshot, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_payload["ts_start"],
                    summary_payload["ts_end"],
                    summary_payload["exchange_count"],
                    summary_payload["summary_text"],
                    json.dumps(memory.get("user_profile", {}), ensure_ascii=False),
                    "app",
                ),
            )

            pending = pending[batch_size:]

        conn.commit()
    finally:
        conn.close()

    memory["pending_archive"] = pending


def add_to_memory(user_input, response):
    ensure_memory_db()
    memory = load_memory()

    user_text = str(user_input or "").strip()[:MAX_FIELD_CHARS]
    response_text = str(response or "").strip()[:MAX_FIELD_CHARS]
    if not user_text and not response_text:
        return

    entry = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "user": user_text,
        "response": response_text,
    }

    memory["history"].append(entry)
    memory.setdefault("pending_archive", []).append(entry)
    memory["history"] = memory["history"][-MAX_HISTORY_ITEMS:]

    memory["user_profile"] = _safe_profile(memory.get("user_profile"))
    _update_user_profile(memory["user_profile"], user_text)

    if response_text.startswith("Opened: "):
        memory["last_file"] = response_text.replace("Opened: ", "", 1).strip()

    _archive_pending_to_db(memory, force=False)
    save_memory(memory)


def set_last_file(file_path):
    memory = load_memory()
    memory["last_file"] = file_path
    save_memory(memory)


def get_last_file():
    memory = load_memory()
    return memory.get("last_file")


def get_recent_context():
    memory = load_memory()
    history = memory.get("history", [])[-MAX_CONTEXT_ITEMS:]

    context = ""
    for item in history:
        context += f"User: {item.get('user', '')}\nAI: {item.get('response', '')}\n"

    return context


def get_user_profile_context():
    memory = load_memory()
    profile = _safe_profile(memory.get("user_profile"))
    preferences = _safe_preferences(memory.get("user_preferences"))

    language_scores = profile["language_scores"]
    style_scores = profile["style_scores"]
    workflow_counts = profile["workflow_counts"]

    inferred_language = max(language_scores, key=language_scores.get)
    inferred_style = max(style_scores, key=style_scores.get)
    inferred_workflow = max(workflow_counts, key=workflow_counts.get)
    inferred_tone = "friend-like" if profile.get("friend_tone_score", 0) >= 2 else "professional-friendly"

    final_language = preferences["preferred_language"] if preferences["preferred_language"] != "auto" else inferred_language
    final_style = (
        preferences["preferred_response_length"]
        if preferences["preferred_response_length"] != "auto"
        else inferred_style
    )
    final_tone = preferences["preferred_tone"] if preferences["preferred_tone"] != "auto" else inferred_tone

    return (
        f"User profile: language={final_language}, response_style={final_style}, "
        f"tone_preference={final_tone}, workflow_focus={inferred_workflow}."
    )


def get_user_preferences():
    memory = load_memory()
    return _safe_preferences(memory.get("user_preferences"))


def set_user_preferences(preferences):
    memory = load_memory()
    current = _safe_preferences(memory.get("user_preferences"))

    if isinstance(preferences, dict):
        merged = {
            "preferred_language": str(preferences.get("preferred_language", current["preferred_language"])).strip().lower(),
            "preferred_tone": str(preferences.get("preferred_tone", current["preferred_tone"])).strip().lower(),
            "preferred_response_length": str(
                preferences.get("preferred_response_length", current["preferred_response_length"])
            )
            .strip()
            .lower(),
        }
        memory["user_preferences"] = _safe_preferences(merged)
        save_memory(memory)


def reset_user_profile_learning():
    memory = load_memory()
    memory["user_profile"] = _default_user_profile()
    memory["user_preferences"] = _default_user_preferences()
    save_memory(memory)


def get_long_term_context(limit=LONG_TERM_CONTEXT_ITEMS):
    ensure_memory_db()
    max_items = max(1, int(limit))
    summary_rows = []

    conn = sqlite3.connect(MEMORY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ts_start, ts_end, summary_text FROM memory_summaries ORDER BY id DESC LIMIT ?",
            (max_items,),
        )
        summary_rows = cursor.fetchall()
    finally:
        conn.close()

    summary_rows = list(reversed(summary_rows))

    lines = []
    for ts_start, ts_end, summary_text in summary_rows:
        lines.append(f"[{ts_start} -> {ts_end}] Summary: {summary_text}")

    # Include latest short memory so current-day context is always visible.
    memory = load_memory()
    for item in memory.get("history", [])[-3:]:
        ts = str(item.get("ts", ""))
        lines.append(f"[{ts}] Recent User: {item.get('user', '')}")
        lines.append(f"[{ts}] Recent AI: {item.get('response', '')}")

    return "\n".join(lines)


def get_memory_insights():
    memory = load_memory()
    profile = _safe_profile(memory.get("user_profile"))
    preferences = _safe_preferences(memory.get("user_preferences"))

    summary_count = 0
    total_archived_chats = 0
    conn = sqlite3.connect(MEMORY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(exchange_count), 0) FROM memory_summaries")
        row = cursor.fetchone() or (0, 0)
        summary_count = int(row[0] or 0)
        total_archived_chats = int(row[1] or 0)
    finally:
        conn.close()

    top_language = max(profile["language_scores"], key=profile["language_scores"].get)
    top_style = max(profile["style_scores"], key=profile["style_scores"].get)
    top_workflow = max(profile["workflow_counts"], key=profile["workflow_counts"].get)

    return {
        "short_term_count": len(memory.get("history", [])),
        "pending_for_summary": len(memory.get("pending_archive", [])),
        "summary_count": summary_count,
        "total_archived_chats": total_archived_chats,
        "top_language": top_language,
        "top_style": top_style,
        "top_workflow": top_workflow,
        "friend_tone_score": profile.get("friend_tone_score", 0),
        "preferences": preferences,
    }


def flush_memory_to_db(force=False):
    ensure_memory_db()
    memory = load_memory()
    _archive_pending_to_db(memory, force=bool(force))
    save_memory(memory)


def _all_memory_rows_for_export():
    ensure_memory_db()
    rows = []

    conn = sqlite3.connect(MEMORY_DB)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ts_start, ts_end, exchange_count, summary_text FROM memory_summaries ORDER BY id ASC")
        for ts_start, ts_end, count, summary_text in cursor.fetchall():
            rows.append((str(ts_start), f"Summary ({count} chats)", str(summary_text)))
            rows.append((str(ts_end), "", ""))
    finally:
        conn.close()

    memory = load_memory()
    for item in memory.get("history", []):
        ts = str(item.get("ts", ""))
        rows.append((ts, f"Recent User: {item.get('user', '')}", f"Recent AI: {item.get('response', '')}"))

    return rows


def export_memory_history(export_format="pdf", output_path=None):
    fmt = str(export_format or "pdf").strip().lower()
    rows = _all_memory_rows_for_export()

    if not output_path:
        if fmt == "pdf":
            output_path = os.path.join(PROJECT_ROOT, "conversation_history.pdf")
        else:
            output_path = os.path.join(PROJECT_ROOT, "conversation_history.doc")

    lines = []
    for ts, left, right in rows:
        if left:
            lines.append(f"[{ts}] {left}")
        if right:
            lines.append(f"[{ts}] {right}")
        lines.append("")

    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception:
            return "Error: PDF export requires reportlab. Install it first."

        pdf = canvas.Canvas(output_path, pagesize=A4)
        _, height = A4
        y = height - 40
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, "Winter AI Memory Export")
        y -= 24

        for line in lines:
            safe_line = str(line)[:180]
            if y < 40:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - 40
            pdf.drawString(40, y, safe_line)
            y -= 14

        pdf.save()
        return f"Exported conversation history to PDF: {output_path}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Winter AI Memory Export\n\n")
        f.write("\n".join(lines))
    return f"Exported conversation history to DOC: {output_path}"


ensure_memory_file()
ensure_memory_db()
