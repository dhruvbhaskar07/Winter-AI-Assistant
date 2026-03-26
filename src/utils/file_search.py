import os
import time
import heapq
import re


# Keep the search responsive for interactive CLI usage.
MAX_RESULTS = 120
SEARCH_TIMEOUT_SECONDS = 3.0
CACHE_TTL_SECONDS = 30
MAX_SCAN_DEPTH = 5

# Skip very large/system folders that slow traversal and rarely contain user targets.
SKIP_DIRS = {
    "$recycle.bin",
    ".git",
    ".venv",
    "__pycache__",
    "appdata",
    "anaconda3",
    "env",
    "node_modules",
    "program files",
    "program files (x86)",
    "programdata",
    "venv",
    "windows",
}

_CACHE = {}
STOP_WORDS = {"open", "file", "my", "the", "a", "an", "please"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}


def score_file(file_name, target):
    file_name_lower = file_name.lower()
    target_lower = target.lower()

    score = 0

    if target_lower == file_name_lower:
        score += 100

    if file_name_lower.startswith(target_lower):
        score += 50

    if target_lower in file_name_lower:
        score += 30

    return score


def _normalize_query(query):
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    filtered = [t for t in tokens if t not in STOP_WORDS]
    if not filtered and tokens:
        filtered = tokens
    return " ".join(filtered).strip(), filtered


def _add_ranked_result(heap, score, path):
    if len(heap) < MAX_RESULTS:
        heapq.heappush(heap, (score, path))
        return

    if score > heap[0][0]:
        heapq.heapreplace(heap, (score, path))


def _iter_search_paths():
    user_home = os.path.expanduser("~")
    one_drive = os.path.join(user_home, "OneDrive")

    candidates = [
        os.getcwd(),
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Downloads"),
        os.path.join(one_drive, "Desktop"),
        os.path.join(one_drive, "Documents"),
        os.path.join(one_drive, "Downloads"),
        user_home,
    ]

    seen = set()
    for path in candidates:
        normalized = os.path.normcase(os.path.normpath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        yield path


def _matches_query(name_lower, query_lower, tokens):
    if query_lower and query_lower in name_lower:
        return True
    if tokens and all(token in name_lower for token in tokens):
        return True
    return False


def _score_hit(file_name, query, tokens, modified_time):
    score = score_file(file_name, query)
    name_lower = file_name.lower()

    for token in tokens:
        if token in name_lower:
            score += 12

    extension = os.path.splitext(file_name)[1].lower()
    if extension in DOCUMENT_EXTENSIONS:
        score += 8
        if any(token in {"resume", "cv"} for token in tokens):
            score += 70

    score += modified_time / 1e10
    return score


def _scan_dir(root_path, query_lower, query_original, tokens, deadline, heap):
    stack = [(root_path, 0)]

    while stack and time.monotonic() < deadline:
        current, depth = stack.pop()

        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if time.monotonic() >= deadline:
                        return

                    name_lower = entry.name.lower()

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if name_lower in SKIP_DIRS:
                                continue
                            if os.path.exists(os.path.join(entry.path, "pyvenv.cfg")):
                                continue
                            if depth < MAX_SCAN_DEPTH:
                                stack.append((entry.path, depth + 1))
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue

                    if not _matches_query(name_lower, query_lower, tokens):
                        continue

                    try:
                        modified_time = entry.stat().st_mtime
                    except OSError:
                        modified_time = 0

                    final_score = _score_hit(entry.name, query_original, tokens, modified_time)
                    _add_ranked_result(heap, final_score, entry.path)
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
            continue


def search_file(filename):
    query = filename.strip()
    if not query:
        return []

    normalized_query, tokens = _normalize_query(query)
    active_query = normalized_query or query.lower()
    query_lower = active_query.lower()
    now = time.monotonic()
    cached = _CACHE.get(query_lower)
    if cached and now - cached[0] <= CACHE_TTL_SECONDS:
        return cached[1]

    deadline = now + SEARCH_TIMEOUT_SECONDS
    heap = []

    for path in _iter_search_paths():
        if time.monotonic() >= deadline:
            break
        if not os.path.exists(path):
            continue
        _scan_dir(path, query_lower, active_query, tokens, deadline, heap)

    ranked = sorted(heap, reverse=True, key=lambda x: x[0])
    results = []
    seen = set()
    for _, path in ranked:
        key = os.path.normcase(os.path.normpath(path))
        if key in seen:
            continue
        seen.add(key)
        results.append(path)
    _CACHE[query_lower] = (time.monotonic(), results)
    return results
