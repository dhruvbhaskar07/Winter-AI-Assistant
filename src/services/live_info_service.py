import datetime as _dt
import html
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from urllib.parse import quote_plus, unquote

import requests
import xml.etree.ElementTree as ET


def get_local_datetime_info():
    now = _dt.datetime.now().astimezone()
    tz_name = now.tzname() or "Local"
    offset = now.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return (
        f"Current local date and time: {now.strftime('%A, %d %B %Y, %I:%M:%S %p')} "
        f"({tz_name}, UTC{offset})."
    )


def _clean_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or "").strip()))


def _normalize_region(region):
    code = str(region or "").strip().lower()
    if code in {"in", "india"}:
        return "in"
    if code in {"us", "usa"}:
        return "us"
    if code in {"gb", "uk"}:
        return "gb"
    if code in {"au", "ca"}:
        return code
    return "in"


def _normalize_language(language):
    code = str(language or "").strip().lower()
    if code in {"hi", "hindi"}:
        return "hi"
    return "en"


def _edition_params(region_code, language_code):
    if region_code == "in":
        hl = "hi" if language_code == "hi" else "en-IN"
        return hl, "IN", f"IN:{'hi' if language_code == 'hi' else 'en'}"
    if region_code == "gb":
        return "en-GB", "GB", "GB:en"
    if region_code == "au":
        return "en-AU", "AU", "AU:en"
    if region_code == "ca":
        return "en-CA", "CA", "CA:en"
    return "en-US", "US", "US:en"


def _dedupe_items(items, max_items):
    seen = set()
    out = []
    for item in items:
        title = _clean_text(item.get("title", ""))
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized = {
            "title": title,
            "snippet": _clean_text(item.get("snippet", "")),
            "url": str(item.get("url", "")).strip(),
        }
        out.append(normalized)
        if len(out) >= max(1, int(max_items)):
            break
    return out


def _subtract_items(primary_items, blocked_items):
    blocked = {str(item.get("title", "")).strip().lower() for item in blocked_items}
    return [item for item in primary_items if str(item.get("title", "")).strip().lower() not in blocked]


def _is_http_url(url):
    value = str(url or "").strip().lower()
    return value.startswith("http://") or value.startswith("https://")


def _scrape_page_preview(url, timeout=5):
    target = str(url or "").strip()
    if not _is_http_url(target):
        return None

    try:
        response = requests.get(
            target,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=max(3, int(timeout)),
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = str(response.headers.get("Content-Type", "")).lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return None
        body = response.text
    except Exception:
        return None

    stripped = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<style[^>]*>.*?</style>", " ", stripped, flags=re.IGNORECASE | re.DOTALL)
    stripped = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", stripped, flags=re.IGNORECASE | re.DOTALL)

    title_match = re.search(r"<title[^>]*>(.*?)</title>", stripped, flags=re.IGNORECASE | re.DOTALL)
    page_title = _clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1))) if title_match else ""

    paragraph_matches = re.findall(r"<p[^>]*>(.*?)</p>", stripped, flags=re.IGNORECASE | re.DOTALL)
    best_para = ""
    for para in paragraph_matches:
        cleaned = _clean_text(re.sub(r"<[^>]+>", " ", para))
        if len(cleaned) < 80:
            continue
        if any(skip in cleaned.lower() for skip in ("cookie", "subscribe", "sign up", "all rights reserved")):
            continue
        best_para = cleaned
        break

    if not page_title and not best_para:
        return None

    return {
        "title": page_title or target,
        "snippet": best_para[:340],
        "url": target,
    }


def _collect_scraped_signals(candidate_items, max_signals=2):
    unique_urls = []
    seen = set()
    for item in candidate_items:
        url = str(item.get("url", "")).strip()
        if not _is_http_url(url):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_urls.append(url)
        if len(unique_urls) >= max(3, int(max_signals) * 2):
            break

    if not unique_urls:
        return []

    signals = []
    executor = ThreadPoolExecutor(max_workers=min(4, len(unique_urls)))
    futures = {executor.submit(_scrape_page_preview, url, 5): url for url in unique_urls}

    try:
        for future in as_completed(futures, timeout=8):
            try:
                preview = future.result()
            except Exception:
                preview = None
            if preview is None:
                continue
            signals.append(preview)
            if len(signals) >= max(1, int(max_signals)):
                break
    except FuturesTimeout:
        pass
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    return signals


def _fetch_duckduckgo_instant(query, limit=8, timeout=8):
    q = str(query or "").strip()
    if not q:
        return {"items": [], "error": "Missing query"}

    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_html": 1, "no_redirect": 1},
            timeout=max(3, int(timeout)),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return {"items": [], "error": f"DDG instant failed: {exc}"}

    items = []
    abstract = _clean_text(data.get("AbstractText", ""))
    if abstract:
        items.append({"title": abstract, "snippet": "", "url": data.get("AbstractURL", "")})

    related = data.get("RelatedTopics", [])
    for entry in related:
        if isinstance(entry, dict) and "Text" in entry:
            items.append(
                {
                    "title": _clean_text(entry.get("Text", "")),
                    "snippet": "",
                    "url": entry.get("FirstURL", ""),
                }
            )
        elif isinstance(entry, dict) and "Topics" in entry:
            for sub in entry.get("Topics", []):
                if not isinstance(sub, dict):
                    continue
                items.append(
                    {
                        "title": _clean_text(sub.get("Text", "")),
                        "snippet": "",
                        "url": sub.get("FirstURL", ""),
                    }
                )

    return {"items": _dedupe_items(items, limit), "error": ""}


def _extract_ddg_redirect_url(raw_url):
    text = str(raw_url or "")
    match = re.search(r"[?&]uddg=([^&]+)", text)
    if match:
        return unquote(match.group(1))
    return text


def _fetch_duckduckgo_html(query, limit=8, timeout=8):
    q = str(query or "").strip()
    if not q:
        return {"items": [], "error": "Missing query"}

    try:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=max(3, int(timeout)),
        )
        response.raise_for_status()
        body = response.text
    except Exception as exc:
        return {"items": [], "error": f"DDG HTML failed: {exc}"}

    links = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )

    items = []
    for idx, (href, raw_title) in enumerate(links):
        title = _clean_text(re.sub(r"<[^>]+>", " ", raw_title))
        snippet = _clean_text(re.sub(r"<[^>]+>", " ", snippets[idx] if idx < len(snippets) else ""))
        url = _extract_ddg_redirect_url(href)
        items.append({"title": title, "snippet": snippet, "url": url})

    return {"items": _dedupe_items(items, limit), "error": ""}


def _fetch_google_news_rss(
    query,
    limit=8,
    region_code="us",
    language_code="en",
    latest_first=False,
    timeout=8,
):
    q = str(query or "").strip()
    if not q:
        return {"items": [], "error": "Missing query"}

    query_text = f"{q} when:1d" if bool(latest_first) else q
    hl, gl, ceid = _edition_params(region_code, language_code)
    url = (
        "https://news.google.com/rss/search"
        f"?q={quote_plus(query_text)}"
        f"&hl={quote_plus(hl)}&gl={quote_plus(gl)}&ceid={quote_plus(ceid)}"
    )

    try:
        response = requests.get(url, timeout=max(3, int(timeout)))
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as exc:
        return {"items": [], "error": f"Google News RSS failed: {exc}"}

    channel = root.find("channel")
    if channel is None:
        return {"items": [], "error": "No channel in Google News RSS"}

    items = []
    for node in channel.findall("item"):
        if len(items) >= max(1, int(limit)):
            break
        title = _clean_text(node.findtext("title") or "")
        link = str(node.findtext("link") or "").strip()
        if not title:
            continue
        items.append({"title": title, "snippet": "", "url": link})

    return {"items": _dedupe_items(items, limit), "error": ""}


def build_live_context(
    query,
    live_web_access=True,
    max_results=5,
    region="in",
    language="en",
):
    q = str(query or "").strip()
    region_code = _normalize_region(region)
    language_code = _normalize_language(language)

    lines = [
        get_local_datetime_info(),
        "Live web mode: fast natural search (region + latest priority).",
        "",
    ]

    if not bool(live_web_access):
        lines.append("Live web access is OFF in settings.")
        return "\n".join(lines)

    per_source = max(2, int(max_results))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            "region_latest": executor.submit(
                _fetch_google_news_rss,
                q,
                limit=per_source,
                region_code=region_code,
                language_code=language_code,
                latest_first=True,
                timeout=8,
            ),
            "global_latest": executor.submit(
                _fetch_google_news_rss,
                q,
                limit=per_source,
                region_code="us",
                language_code="en",
                latest_first=True,
                timeout=8,
            ),
            "ddg_instant": executor.submit(_fetch_duckduckgo_instant, q, per_source, 8),
            "ddg_html": executor.submit(_fetch_duckduckgo_html, q, per_source, 8),
        }

        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=10)
            except Exception as exc:
                results[name] = {"items": [], "error": f"Fetch failed: {exc}"}

    region_latest = results.get("region_latest", {"items": [], "error": ""})
    global_latest = results.get("global_latest", {"items": [], "error": ""})
    ddg_instant = results.get("ddg_instant", {"items": [], "error": ""})
    ddg_html = results.get("ddg_html", {"items": [], "error": ""})

    region_latest_items = region_latest.get("items", [])
    global_latest_items = _subtract_items(global_latest.get("items", []), region_latest_items)

    scrape_candidates = region_latest_items + global_latest_items + ddg_html.get("items", [])
    scraped_signals = _collect_scraped_signals(scrape_candidates, max_signals=2)

    lines.append(f"Query: {q}")
    lines.append(f"Priority region: {region_code.upper()} | Priority language: {language_code}")

    lines.append("- Priority latest headlines:")
    if region_latest.get("error"):
        lines.append(f"  Region latest error: {region_latest['error']}")
    elif not region_latest_items:
        lines.append("  No latest regional headline found.")
    else:
        for idx, item in enumerate(region_latest_items, start=1):
            lines.append(f"  {idx}. {item['title']}")

    lines.append("- Global latest headlines:")
    if global_latest.get("error"):
        lines.append(f"  Global latest error: {global_latest['error']}")
    elif not global_latest_items:
        lines.append("  No global latest headline found.")
    else:
        for idx, item in enumerate(global_latest_items, start=1):
            lines.append(f"  {idx}. {item['title']}")

    lines.append("- Web search results:")
    if ddg_html.get("error"):
        lines.append(f"  DDG web error: {ddg_html['error']}")
    elif not ddg_html.get("items"):
        lines.append("  No web results found.")
    else:
        for idx, item in enumerate(ddg_html.get("items", []), start=1):
            if item.get("snippet"):
                lines.append(f"  {idx}. {item['title']} | {item['snippet']}")
            else:
                lines.append(f"  {idx}. {item['title']}")

    lines.append("- Quick context hits:")
    if ddg_instant.get("error"):
        lines.append(f"  DDG instant error: {ddg_instant['error']}")
    elif not ddg_instant.get("items"):
        lines.append("  No quick context hit found.")
    else:
        for idx, item in enumerate(ddg_instant.get("items", []), start=1):
            lines.append(f"  {idx}. {item['title']}")

    lines.append("- Web-scraped page signals:")
    if not scraped_signals:
        lines.append("  No stable page preview scraped.")
    else:
        for idx, signal in enumerate(scraped_signals, start=1):
            if signal.get("snippet"):
                lines.append(f"  {idx}. {signal['title']} | {signal['snippet']}")
            else:
                lines.append(f"  {idx}. {signal['title']}")

    lines.extend(
        [
            "",
            "Response rules for assistant:",
            "- Use these results as grounding context.",
            "- Start with latest updates and preferred region context.",
            "- Prefer scraped signals when they add concrete detail.",
            "- Keep response natural, human-like, and concise.",
            "- Show links/sources only if user explicitly asks.",
        ]
    )

    return "\n".join(lines)
