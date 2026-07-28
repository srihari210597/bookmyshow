#!/usr/bin/env python3
"""
BookMyShow Theatre Watcher (Reusable)
======================================
Watches for a specific theatre + format to open booking on a given date.

Usage:
    # Using full URL:
    python bms_watcher.py --url "https://in.bookmyshow.com/buytickets/the-odyssey-chennai/movie-chen-ET00480917-MT/20260720" \
                          --theatre LUXE --format IMAX

    # Using movie name + date (constructs URL automatically):
    python bms_watcher.py --movie "the-odyssey-chennai/movie-chen-ET00480917-MT" \
                          --date 20260720 --theatre LUXE --format IMAX

    # Watch any format (not just IMAX):
    python bms_watcher.py --url "..." --theatre LUXE --format any

    # Dry run:
    python bms_watcher.py --url "..." --theatre LUXE --format IMAX --dry-run

    # Custom ntfy topic:
    python bms_watcher.py --url "..." --theatre LUXE --format IMAX --ntfy-topic my-alerts

Options:
    --url         Full BMS showtime URL
    --movie       Movie path from BMS URL (alternative to --url)
    --date        Date in YYYYMMDD format (used with --movie)
    --theatre     Theatre name to watch for (e.g., LUXE, PVR, Palazzo)
    --format      Format to filter (e.g., IMAX, 4DX, Dolby, or "any" for all)
    --ntfy-topic  ntfy.sh topic name (default: bms-luxe-srihari)
    --interval    How often cron runs, just for the notification message (default: 10)
    --dry-run     Check but don't alert or write state
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


# ─── Notifications ────────────────────────────────────────────────────────────

def notify(showtimes: list[str], theatre: str, fmt: str, url: str, ntfy_topic: str) -> None:
    """Send 3 back-to-back urgent notifications."""
    import urllib.request

    messages = [
        {
            "title": f"BOOK NOW - {fmt} Opened!",
            "msg": f"{theatre} - {fmt} booking is LIVE!\nShowtimes: {', '.join(showtimes)}",
            "tags": "rotating_light",
        },
        {
            "title": f"HURRY - {fmt} slots live!",
            "msg": f"Go go go! {theatre} {fmt} is bookable now.\n{url}",
            "tags": "fire",
        },
        {
            "title": f"LAST REMINDER - Book {fmt} now!",
            "msg": f"Showtimes: {', '.join(showtimes)}\nDon't miss it!\n{url}",
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

    print(f"[{datetime.now().isoformat()}] 3 urgent notifications sent!")


def notify_not_yet(theatre: str, fmt: str, ntfy_topic: str, interval: int) -> None:
    """Send a 'no luck' notification."""
    import urllib.request

    req = urllib.request.Request(
        f"https://ntfy.sh/{ntfy_topic}",
        data=f"No luck yet. Still checking every {interval} min...".encode("utf-8"),
        headers={
            "Title": f"No luck - {theatre} {fmt} not open yet",
            "Priority": "high",
            "Tags": "hourglass",
        },
    )
    urllib.request.urlopen(req)
    print(f"[{datetime.now().isoformat()}] 'No luck' notification sent")


# ─── Core logic ───────────────────────────────────────────────────────────────

def check(url: str, date_str: str, theatre: str, fmt: str) -> tuple[bool, list[str], str]:
    """
    Load the BMS page, find the theatre block, extract showtimes for the format.

    Returns:
        (found: bool, showtimes: list[str], raw_text: str)
    """
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

            # Verify URL wasn't redirected to a different date
            current_url = page.url
            if date_str not in current_url:
                print(f"[{datetime.now().isoformat()}] Page redirected to: {current_url} (not {date_str})")
                browser.close()
                return (False, [], "")

            page_text = page.inner_text("body")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Page load error: {e}", file=sys.stderr)
            browser.close()
            return (False, [], "")

        browser.close()

    # ─── Parse: find theatre block ────────────────────────────────────────
    lines = page_text.splitlines()
    in_theatre_block = False
    theatre_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if theatre.lower() in stripped.lower():
            in_theatre_block = True
            theatre_lines = []
            continue
        if in_theatre_block and _looks_like_theatre_header(stripped, theatre):
            break
        if in_theatre_block:
            theatre_lines.append(stripped)

    # ─── Parse: pair format labels with showtimes ─────────────────────────
    matched_showtimes: list[str] = []
    current_format = ""
    match_any = fmt.lower() == "any"

    for entry in theatre_lines:
        if _is_format_label(entry):
            current_format = entry
        elif _is_showtime(entry):
            if match_any or fmt.lower() in current_format.lower():
                matched_showtimes.append(entry)

    found = len(matched_showtimes) > 0
    return (found, matched_showtimes, "\n".join(theatre_lines[:40]))


def _looks_like_theatre_header(line: str, current_theatre: str) -> bool:
    """Heuristic: theatre names contain keywords like 'cinemas', 'screen', 'PVR', 'INOX'."""
    markers = ["pvr", "inox", "cinemas", "cinepolis", "screen", "palazzo", "sathyam", "luxe", "rohini", "kamala"]
    low = line.lower()
    return any(m in low for m in markers) and current_theatre.lower() not in low


def _is_format_label(text: str) -> bool:
    """Format labels contain language or format keywords."""
    indicators = ["2d", "3d", "imax", "4dx", "dolby", "english", "tamil", "hindi", "telugu", "atmos"]
    low = text.lower()
    return any(i in low for i in indicators)


def _is_showtime(text: str) -> bool:
    """Showtimes look like '10:30 AM', '02:15 PM', etc."""
    return bool(re.match(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", text.strip()))


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BookMyShow Watcher - get notified when a theatre opens booking"
    )
    parser.add_argument("--url", help="Full BMS showtime URL")
    parser.add_argument("--movie", help="Movie path from BMS URL (used with --date)")
    parser.add_argument("--date", help="Date in YYYYMMDD format (e.g., 20260720)")
    parser.add_argument("--theatre", required=True, help="Theatre name to watch (e.g., LUXE, PVR)")
    parser.add_argument("--format", default="IMAX", help="Format to filter (IMAX, 4DX, Dolby, or 'any')")
    parser.add_argument("--ntfy-topic", default="bms-luxe-srihari", help="ntfy.sh topic")
    parser.add_argument("--interval", type=int, default=10, help="Check interval in minutes (for notification text)")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't alert or write state")
    args = parser.parse_args()

    # Build URL
    if args.url:
        target_url = args.url
    elif args.movie and args.date:
        target_url = f"https://in.bookmyshow.com/buytickets/{args.movie}/{args.date}"
    else:
        parser.error("Provide either --url OR both --movie and --date")

    # Extract date from URL for redirect checking
    date_match = re.search(r"(\d{8})$", target_url.rstrip("/"))
    date_str = date_match.group(1) if date_match else ""

    # State file unique per theatre+date combo
    state_file = SCRIPT_DIR / f".bms_alert_{args.theatre.lower()}_{date_str}"

    # Already alerted?
    if state_file.exists() and not args.dry_run:
        print(f"[{datetime.now().isoformat()}] Already alerted (state file exists). Exiting.")
        sys.exit(0)

    print(f"[{datetime.now().isoformat()}] Checking BMS for {args.theatre} {args.format} showtimes...")
    print(f"  URL: {target_url}")

    found, showtimes, debug_text = check(target_url, date_str, args.theatre, args.format)

    if found:
        print(f"[{datetime.now().isoformat()}] ✅ ✅ ✅ {args.format} showtimes found: {showtimes}")
        if args.dry_run:
            print("[dry-run] Would alert and write state file.")
        else:
            notify(showtimes, args.theatre, args.format, target_url, args.ntfy_topic)
            state_file.write_text(
                json.dumps({
                    "alerted_at": datetime.now().isoformat(),
                    "showtimes": showtimes,
                    "theatre": args.theatre,
                    "format": args.format,
                }),
                encoding="utf-8",
            )
            print(f"[{datetime.now().isoformat()}] State file written. Won't alert again.")
    else:
        print(f"[{datetime.now().isoformat()}] ❌ ❌ ❌ No {args.format} showtimes yet for {args.theatre}.")
        if not args.dry_run:
            notify_not_yet(args.theatre, args.format, args.ntfy_topic, args.interval)
        if debug_text:
            print("── Theatre block (first 40 lines) ──")
            print(debug_text)
        else:
            print("(Theatre block not found on page at all.)")


if __name__ == "__main__":
    main()
