#!/usr/bin/env python3
"""
dev-digest: A CLI tool to generate a local HTML digest of blog + YouTube summaries.
Usage: python digest.py [--config sources.yaml] [--force]
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from string import Template

import anthropic
import yaml

from fetchers import fetch_rss_items, fetch_youtube_items, fetch_youtube_transcript
from summarize import summarize, format_summary_html

SEEN_CACHE = ".seen_items.json"
TEMPLATE_FILE = Path(__file__).parent / "template.html"


# ── Config & cache ────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def load_seen(cache_path: str) -> set:
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return set(json.load(f))
    return set()

def save_seen(cache_path: str, seen: set):
    with open(cache_path, "w") as f:
        json.dump(list(seen), f)

def item_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


# ── HTML rendering ────────────────────────────────────────────────────────────

def format_date(date_str: str) -> str:
    from fetchers import parse_date
    dt = parse_date(date_str)
    return dt.strftime("%b %d, %Y") if dt else ""

def build_card(item: dict) -> str:
    tag_class = "tag-blog" if item["type"] == "blog" else "tag-youtube"
    fmt_date = format_date(item.get("date", ""))
    date_badge = f'<span class="date-badge">{fmt_date}</span>' if fmt_date else ""
    yt_thumb = ""
    if item["type"] == "youtube" and item.get("video_id"):
        yt_thumb = f'<div class="thumb-wrap"><img class="thumb" src="https://img.youtube.com/vi/{item["video_id"]}/mqdefault.jpg" alt="thumbnail" loading="lazy"></div>'
    summary_html = format_summary_html(item["summary"])
    link_label = "▶ Watch on YouTube" if item["type"] == "youtube" else "→ Read article"

    return f"""
    <article class="card">
        {yt_thumb}
        <div class="card-body">
            <div class="card-meta">
                <span class="tag {tag_class}">{item['source_name']}</span>
            </div>
            <h2 class="card-title">
                <a href="{item['url']}" target="_blank" rel="noopener">{item['title']}</a>
                {date_badge}
            </h2>
            <div class="summary">{summary_html}</div>
            <a class="read-link" href="{item['url']}" target="_blank" rel="noopener">{link_label} ↗</a>
        </div>
    </article>"""

def generate_html(digest_items: list[dict], generated_at: str) -> str:
    if digest_items:
        cards_html = "\n".join(build_card(item) for item in digest_items)
    else:
        cards_html = '<div class="empty">No new items found. Everything is up to date.</div>'

    total = len(digest_items)
    blogs = sum(1 for i in digest_items if i["type"] == "blog")

    return Template(TEMPLATE_FILE.read_text()).substitute(
        generated_at=generated_at,
        blogs_count=blogs,
        videos_count=total - blogs,
        total_count=total,
        cards_html=cards_html,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate a local HTML dev digest.")
    parser.add_argument("--config", default="sources.yaml", help="Path to sources.yaml")
    parser.add_argument("--output", default=None, help="Override output HTML path")
    parser.add_argument("--force", action="store_true", help="Re-summarize already-seen items")
    parser.add_argument("--no-cache", action="store_true", help="Don't update the seen cache (dry run)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"✗ Config file not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    settings = config.get("settings", {})
    max_items = settings.get("max_items_per_source", 3)
    max_age = settings.get("max_age_days", 2)
    summary_sentences = settings.get("summary_sentences", 3)
    output_file = args.output or f"digest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_dir = config_path.parent / "output"
    output_dir.mkdir(exist_ok=True)

    cache_path = config_path.parent / SEEN_CACHE
    seen = load_seen(cache_path) if not args.force else set()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("✗ ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=anthropic_key)

    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if google_api_key:
        print("ℹ  GOOGLE_API_KEY found — using YouTube Data API + Gemini for summaries.")
    else:
        print("ℹ  No GOOGLE_API_KEY — falling back to YouTube RSS feed + transcript summaries.")

    digest_items = []
    new_seen = set()

    # ── Blogs ─────────────────────────────────────────────────────────────────
    for blog in config.get("blogs", []):
        name = blog["name"]
        print(f"\n📰 {name}")
        items = fetch_rss_items(blog["rss"], blog.get("max_items", max_items), max_age)
        if not items:
            print("   No recent items.")
            continue

        for item in items:
            iid = item_id(item["url"])
            new_seen.add(iid)
            if iid in seen:
                print(f"   ⏭  (seen) {item['title'][:60]}")
                continue
            print(f"   ✦ {item['title'][:65]}")
            summary = summarize(client, item["title"], item["content"], summary_sentences, "blog article")
            time.sleep(0.3)
            digest_items.append({
                "type": "blog",
                "source_name": name,
                "title": item["title"],
                "url": item["url"],
                "date": item["date"],
                "summary": summary,
            })

    # ── YouTube ───────────────────────────────────────────────────────────────
    for channel in config.get("youtube_channels", []):
        name = channel["name"]
        channel_id = channel["channel_id"]
        print(f"\n▶  {name}")
        items = fetch_youtube_items(channel_id, channel.get("max_items", max_items), max_age, api_key=google_api_key)
        if not items:
            print("   No recent videos.")
            continue

        for item in items:
            iid = item_id(item["url"])
            new_seen.add(iid)
            if iid in seen:
                print(f"   ⏭  (seen) {item['title'][:60]}")
                continue
            print(f"   ✦ {item['title'][:65]}")

            transcript = fetch_youtube_transcript(item["video_id"])
            content = transcript if transcript else item.get("content", "")
            if transcript:
                content_type = "YouTube video transcript"
            elif len(content.strip()) >= 50:
                content_type = "YouTube video description"
            else:
                content = item["title"]
                content_type = "YouTube video title"

            summary = summarize(client, item["title"], content, summary_sentences, content_type)
            time.sleep(0.3)
            digest_items.append({
                "type": "youtube",
                "source_name": name,
                "title": item["title"],
                "url": item["url"],
                "video_id": item.get("video_id", ""),
                "date": item["date"],
                "summary": summary,
            })

    # ── Write output ──────────────────────────────────────────────────────────
    generated_at = datetime.now().strftime("%A, %B %d %Y — %H:%M")
    html = generate_html(digest_items, generated_at)
    output_path = output_dir / output_file
    output_path.write_text(html, encoding="utf-8")

    if not args.no_cache:
        save_seen(cache_path, seen | new_seen)

    print(f"\n✅ Digest written → {output_path.resolve()}")
    print(f"   {len(digest_items)} new items summarized.")

    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(output_path)])
    elif system == "Linux":
        subprocess.run(["xdg-open", str(output_path)])
    elif system == "Windows":
        os.startfile(str(output_path))


if __name__ == "__main__":
    main()
