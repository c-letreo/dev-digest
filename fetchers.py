"""
Fetching logic: RSS feeds, YouTube Data API, YouTube transcripts.
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError

YT_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="


def fetch_url(url: str, timeout: int = 10) -> str:
    req = Request(url, headers={"User-Agent": "dev-digest/1.0 (RSS reader)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_date(date_str: str) -> datetime | None:
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return None


def is_recent(date_str: str, max_age_days: int) -> bool:
    if not date_str:
        return True
    dt = parse_date(date_str)
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= timedelta(days=max_age_days)


def strip_html(html: str) -> str:
    if not html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:3000]


# ── RSS ───────────────────────────────────────────────────────────────────────

def fetch_rss_items(feed_url: str, max_items: int, max_age_days: int) -> list[dict]:
    try:
        raw = fetch_url(feed_url)
    except URLError as e:
        print(f"  ⚠  Could not fetch {feed_url}: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  ⚠  Could not parse XML from {feed_url}: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    items = []

    # Atom feeds
    for entry in root.findall(".//atom:entry", ns)[:max_items * 2]:
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        date_el = entry.find("atom:updated", ns) or entry.find("atom:published", ns)
        summary_el = entry.find("atom:summary", ns) or entry.find("atom:content", ns)

        title = title_el.text if title_el is not None else "No title"
        url = link_el.get("href", "") if link_el is not None else ""
        date = date_el.text if date_el is not None else ""
        content = summary_el.text if summary_el is not None else ""

        if url and is_recent(date, max_age_days):
            items.append({"title": title, "url": url, "content": strip_html(content), "date": date})
        if len(items) >= max_items:
            break

    # RSS 2.0 feeds
    if not items:
        for item in root.findall(".//item")[:max_items * 2]:
            title_el = item.find("title")
            link_el = item.find("link")
            date_el = item.find("pubDate") or item.find("dc:date", ns)
            desc_el = item.find("description") or item.find("content:encoded", ns)

            title = title_el.text if title_el is not None else "No title"
            url = link_el.text if link_el is not None else ""
            date = date_el.text if date_el is not None else ""
            content = desc_el.text if desc_el is not None else ""

            if url and is_recent(date, max_age_days):
                items.append({"title": title, "url": url, "content": strip_html(content), "date": date})
            if len(items) >= max_items:
                break

    return items


# ── YouTube ───────────────────────────────────────────────────────────────────

def fetch_youtube_items_api(api_key: str, channel_id: str, max_items: int, max_age_days: int) -> list[dict]:
    """Fetch recent videos using YouTube Data API v3 (reliable, free quota)."""
    base = "https://www.googleapis.com/youtube/v3"

    # Resolve handle/ID → uploads playlist ID
    if channel_id.startswith("UC"):
        params = urlencode({"part": "contentDetails", "id": channel_id, "key": api_key})
    else:
        handle = channel_id.lstrip("@")
        params = urlencode({"part": "contentDetails", "forHandle": handle, "key": api_key})

    try:
        data = json.loads(fetch_url(f"{base}/channels?{params}"))
    except Exception as e:
        print(f"  ⚠  YouTube API channels request failed: {e}")
        return []

    api_items = data.get("items", [])
    if not api_items:
        print(f"  ⚠  YouTube API: channel not found for '{channel_id}'")
        return []

    uploads_playlist = api_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    params = urlencode({
        "part": "snippet",
        "playlistId": uploads_playlist,
        "maxResults": min(max_items * 2, 50),
        "key": api_key,
    })

    try:
        data = json.loads(fetch_url(f"{base}/playlistItems?{params}"))
    except Exception as e:
        print(f"  ⚠  YouTube API playlistItems request failed: {e}")
        return []

    items = []
    for entry in data.get("items", []):
        snippet = entry.get("snippet", {})
        title = snippet.get("title", "No title")
        video_id = snippet.get("resourceId", {}).get("videoId", "")
        date = snippet.get("publishedAt", "")
        description = snippet.get("description", "")
        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""

        if url and is_recent(date, max_age_days):
            items.append({"title": title, "url": url, "video_id": video_id, "content": description[:2000], "date": date})
        if len(items) >= max_items:
            break

    return items[:max_items]


def fetch_youtube_items_rss(channel_id: str, max_items: int, max_age_days: int) -> list[dict]:
    """Fallback: fetch recent videos via YouTube RSS feed."""
    if not channel_id.startswith("UC"):
        slug = channel_id.lstrip("@")
        for url in [
            f"https://www.youtube.com/@{slug}",
            f"https://www.youtube.com/c/{slug}",
            f"https://www.youtube.com/user/{slug}",
        ]:
            try:
                page = fetch_url(url, timeout=10)
                match = re.search(r'"externalId":"(UC[^"]+)"', page)
                if match:
                    channel_id = match.group(1)
                    print(f"   ↳ resolved to channel ID: {channel_id}")
                    break
            except Exception:
                continue

    feed_url = YT_RSS_BASE + channel_id
    try:
        raw = fetch_url(feed_url)
    except URLError as e:
        print(f"  ⚠  Could not fetch YouTube RSS for {channel_id}: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  ⚠  Could not parse YouTube feed: {e}")
        return []

    items = []
    for entry in root.findall("atom:entry", ns)[:max_items * 2]:
        title_el = entry.find("atom:title", ns)
        vid_el = entry.find("yt:videoId", ns)
        date_el = entry.find("atom:published", ns)
        desc_el = entry.find(".//media:description", ns)

        title = title_el.text if title_el is not None else "No title"
        video_id = vid_el.text if vid_el is not None else ""
        date = date_el.text if date_el is not None else ""
        description = desc_el.text if desc_el is not None else ""
        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""

        if url and is_recent(date, max_age_days):
            items.append({"title": title, "url": url, "video_id": video_id, "content": description[:2000], "date": date})
        if len(items) >= max_items:
            break

    return items[:max_items]


def fetch_youtube_items(channel_id: str, max_items: int, max_age_days: int, api_key: str = None) -> list[dict]:
    """Fetch recent videos, preferring the YouTube Data API and falling back to RSS."""
    if api_key:
        return fetch_youtube_items_api(api_key, channel_id, max_items, max_age_days)
    return fetch_youtube_items_rss(channel_id, max_items, max_age_days)


def fetch_youtube_transcript(video_id: str) -> str:
    """Fetch a YouTube transcript. Falls back gracefully if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        entries = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        return " ".join(e["text"] for e in entries)[:4000]
    except Exception:
        return ""
