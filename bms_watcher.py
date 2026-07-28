#!/usr/bin/env python3
"""
BookMyShow Watcher (Reusable)
==============================
Reads config.json for what to watch. No need to edit this file.

Just edit config.json to add/remove movies, theatres, dates.

Usage:
    python bms_watcher.py            # run all watches from config.json
    python bms_watcher.py --dry-run  # check without alerting
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"


# ─── Load config ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load config.json."""
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE} not found. Create it first.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Notifications ────────────────────────────────────────────────────────────

def notify_found(theatre: str, showtimes: list[str], formats: list[str], url: str, ntfy_topic: str, watch_name: str) -> None:
    """Send 3 back-to-back urgent notifications when a theatre opens."""
    import urllib.request

    format_text = ", ".join(set(formats)) if formats else "Check BMS"
    showtime_text = ", ".join(showtimes) if showtimes else "Available now"

    messages = [
        {
            "title": f"BOOK NOW - {watch_name}!",
            "msg": f"{theatre} just opened booking for {watch_name}!\nFormats: {format_text}\nShowtimes: {showtime_text}",
            "tags": "rotating_light",
        },
        {
            "title": f"HURRY - {theatre} slots live!",
            "msg": f"{watch_name} at {theatre} - Go go go!\nBook now:\n{url}",
            "tags": "fire",
        },
        {
            "title": f"LAST REMINDER - {watch_name}!",
            "msg": f"{theatre}\nShowtimes: {showtime_text}\nDon't miss it!\n{url}",
            "tags": "ticket",
        },
    ]

    for i, m in enumerate(messages):
        req = urllib.request.Request(
            f"https://ntfy.sh/{ntfy_topic}",
            data=m["msg"].encode("utf-8"),
            headers={
                "Title": m["title"],
                "Priority": "urgent",
                "Tags": m["tags"],
            },
        )
        urllib.request.urlopen(req)
        if i < len(messages) - 1:
            time.sleep(2)

    print(f"[{datetime.now().isoformat()}] 3 urgent notifications sent for {theatre}!")


def notify_not_yet(theatres_waiting: list[str], ntfy_topic: str, interval: int, watch_name: str) -> None:
    """Send a 'no luck' notification."""
    import urllib.request

    waiting = ", ".join(theatres_waiting)
    req = urllib.request.Request(
        f"https://ntfy.sh/{ntfy_topic}",
        data=f"[{watch_name}] No luck yet.\nWaiting for: {waiting}\nChecking every {interval} min...".encode("utf-8"),
        headers={
            "Title": f"No luck - {watch_name} | {waiting}",
            "Priority": "high",
            "Tags": "hourglass",
        },
    )
    urllib.request.urlopen(req)
    print(f"[{datetime.now().isoformat()}] 'No luck' notification sent")


# ─── Page loading ─────────────────────────────────────────────────────────────

def load_page(url: str, date_str: str) -> str:
    """Load the BMS page and return the rendered text."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(8000)

            current_url = page.url
            if date_str and date_str not in current_url:
                print(f"[{datetime.now().isoformat()}] Page redirected to: {current_url} (expected {date_str})")
                browser.close()
                return ""

            page_text = page.inner_text("body")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Page load error: {e}", file=sys.stderr)
            browser.close()
            return ""

        browser.close()
    return page_text


# ─── Theatre parsing ──────────────────────────────────────────────────────────

def find_theatre(page_text: str, keyword: str, format_filter: str) -> tuple[bool, list[str], list[str]]:
    """Find a theatre block and extract showtimes."""
    lines = page_text.splitlines()
    in_block = False
    block_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if keyword.lower() in stripped.lower():
            in_block = True
            block_lines = []
            continue
        if in_block and _looks_like_theatre_header(stripped, keyword):
            break
        if in_block:
            block_lines.append(stripped)

    if not in_block:
        return (False, [], [])

    showtimes: list[str] = []
    formats: list[str] = []
    current_format = ""
    match_any = format_filter.lower() == "any"

    for entry in block_lines:
        if _is_format_label(entry):
            current_format = entry
            if current_format not in formats:
                formats.append(current_format)
        elif _is_showtime(entry):
            if match_any or format_filter.lower() in current_format.lower():
                showtimes.append(entry)

    if not showtimes:
        return (False, [], formats)

    return (True, showtimes, formats)


def _looks_like_theatre_header(line: str, current_keyword: str) -> bool:
    markers = ["pvr", "inox", "cinemas", "cinepolis", "screen", "palazzo", "sathyam",
               "rakki", "rohini", "kamala", "ags", "vr chennai", "luxe", "escape"]
    low = line.lower()
    return any(m in low for m in markers) and current_keyword.lower() not in low


def _is_format_label(text: str) -> bool:
    indicators = ["2d", "3d", "imax", "4dx", "dolby", "english", "tamil",
                  "hindi", "telugu", "atmos", "epiq", "screenx"]
    low = text.lower()
    return any(i in low for i in indicators)


def _is_showtime(text: str) -> bool:
    return bool(re.match(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", text.strip()))


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BookMyShow Watcher - reads config.json")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't alert or write state")
    args = parser.parse_args()

    config = load_config()
    ntfy_topic = config.get("ntfy_topic", "bms-luxe-srihari")
    interval = config.get("interval", 10)
    watches = config.get("watches", [])

    if not watches:
        print("No watches in config.json. Add some and re-run.")
        sys.exit(0)

    for watch in watches:
        watch_name = watch.get("name", "Unknown")
        url = watch["url"]
        theatres = watch["theatres"]
        format_filter = watch.get("format", "any")

        # Extract date from URL
        date_match = re.search(r"(\d{8})", url)
        date_str = date_match.group(1) if date_match else ""

        # Check which theatres still need alerting
        theatres_to_check = []
        for theatre in theatres:
            state_file = SCRIPT_DIR / f".bms_alert_{theatre.lower().replace(' ', '_')}_{date_str}"
            if not state_file.exists() or args.dry_run:
                theatres_to_check.append(theatre)

        if not theatres_to_check:
            print(f"[{datetime.now().isoformat()}] [{watch_name}] All theatres already alerted. Skipping.")
            continue

        print(f"[{datetime.now().isoformat()}] [{watch_name}] Checking...")
        print(f"  Theatres: {theatres_to_check} | Format: {format_filter}")

        page_text = load_page(url, date_str)
        if not page_text:
            print(f"  Failed to load page. Will retry next run.")
            continue

        found_any = False
        theatres_waiting = []

        for theatre in theatres_to_check:
            found, showtimes, formats = find_theatre(page_text, theatre, format_filter)
            state_file = SCRIPT_DIR / f".bms_alert_{theatre.lower().replace(' ', '_')}_{date_str}"

            if found:
                found_any = True
                print(f"  ✅ ✅ ✅ {theatre} is listed! Formats: {formats} Showtimes: {showtimes}")
                if args.dry_run:
                    print(f"    [dry-run] Would alert for {theatre}")
                else:
                    notify_found(theatre, showtimes, formats, url, ntfy_topic, watch_name)
                    state_file.write_text(
                        json.dumps({
                            "alerted_at": datetime.now().isoformat(),
                            "theatre": theatre,
                            "showtimes": showtimes,
                            "formats": formats,
                        }),
                        encoding="utf-8",
                    )
                    print(f"    State file written for {theatre}.")
            else:
                theatres_waiting.append(theatre)
                print(f"  ❌ {theatre} not listed yet.")

        if not found_any and not args.dry_run:
            notify_not_yet(theatres_waiting, ntfy_topic, interval, watch_name)


if __name__ == "__main__":
    main()
