#!/usr/bin/env python3
"""
BookMyShow IMAX Watcher
========================
Checks whether INOX LUXE Phoenix Market City, Velachery has opened
IMAX booking for "The Odyssey" on Mon 20 Jul 2026.

Designed for cron: runs once (--once implied), writes a state file on
first match so repeated runs don't re-alert.

Usage:
    python bms_theatre_watch.py            # single check
    python bms_theatre_watch.py --dry-run  # print what would happen, don't alert
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# ─── Configuration ────────────────────────────────────────────────────────────

TARGET_URL = (
    "https://in.bookmyshow.com/buytickets/"
    "the-odyssey-chennai/movie-chen-ET00480917-MT/20260720"
)

THEATRE_KEYWORD = "LUXE"  # substring to locate the venue block
FORMAT_KEYWORD = "IMAX"   # only alert for IMAX showtimes
STATE_FILE = Path(__file__).parent / ".bms_alert_sent"

# ─── Alert channel (swap this section once you pick) ──────────────────────────

def notify(showtimes: list[str]) -> None:
    """
    Send 3 back-to-back push notifications to make sure you notice.
    """
    import urllib.request
    import time

    NTFY_TOPIC = "bms-luxe-srihari"

    messages = [
        {
            "title": "BOOK NOW - IMAX Opened!",
            "msg": f"INOX LUXE Velachery - The Odyssey - Mon 20 Jul\nShowtimes: {', '.join(showtimes)}",
            "tags": "rotating_light",
        },
        {
            "title": "HURRY - IMAX slots live!",
            "msg": f"Go go go! LUXE IMAX is bookable now.\n{TARGET_URL}",
            "tags": "fire",
        },
        {
            "title": "LAST REMINDER - Book IMAX now!",
            "msg": f"Showtimes: {', '.join(showtimes)}\nDon't miss it!\n{TARGET_URL}",
            "tags": "ticket",
        },
    ]

    for i, m in enumerate(messages):
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=m["msg"].encode("utf-8"),
            headers={
                "Title": m["title"],
                "Priority": "urgent",
                "Tags": m["tags"],
            },
        )
        urllib.request.urlopen(req)
        if i < len(messages) - 1:
            time.sleep(2)  # slight gap so they arrive as separate notifications

    print(f"[{datetime.now().isoformat()}] 🔔 3 urgent notifications sent!")


def notify_not_yet() -> None:
    """Send a notification that LUXE IMAX is still not available."""
    import urllib.request

    NTFY_TOPIC = "bms-luxe-srihari"

    msg = (
        f"No luck yet. Still checking every 10 min..."
    )

    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg.encode("utf-8"),
        headers={
            "Title": "No luck - IMAX not open yet",
            "Priority": "high",
            "Tags": "hourglass",
        },
    )
    urllib.request.urlopen(req)
    print(f"[{datetime.now().isoformat()}] 🔔 'Not yet' notification sent")


# ─── Core logic ──────────────────────────────────────────────────────────────

def check() -> tuple[bool, list[str], str]:
    """
    Load the BMS page, find the LUXE block, extract IMAX showtimes.

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
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=90_000)
            # Give JS extra time to render showtime cards
            page.wait_for_timeout(8000)

            # Verify we're actually on July 20's page (BMS may redirect to an earlier date)
            current_url = page.url
            if "20260720" not in current_url:
                print(f"[{datetime.now().isoformat()}] Page redirected to: {current_url} (not July 20)")
                browser.close()
                return (False, [], "")

            page_text = page.inner_text("body")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Page load error: {e}", file=sys.stderr)
            browser.close()
            return (False, [], "")

        browser.close()

    # ─── Parse: verify date context on page ─────────────────────────────
    # Check that page content mentions Mon/20 Jul, not Sun/19 Jul
    page_lower = page_text.lower()
    # If page shows "sun" prominently near date but not "mon", it's the wrong date
    if "sun, 19 jul" in page_lower or ("19 jul" in page_lower and "20 jul" not in page_lower):
        print(f"[{datetime.now().isoformat()}] Page shows July 19 content, not July 20. Skipping.")
        return (False, [], "")

    # ─── Parse: find theatre block ────────────────────────────────────────
    lines = page_text.splitlines()
    in_luxe_block = False
    luxe_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Theatre names appear as their own line
        if THEATRE_KEYWORD.lower() in stripped.lower():
            in_luxe_block = True
            luxe_lines = []
            continue
        # A new theatre block starts — stop collecting
        if in_luxe_block and _looks_like_theatre_header(stripped, lines):
            break
        if in_luxe_block:
            luxe_lines.append(stripped)

    # ─── Parse: pair format labels with showtimes ─────────────────────────
    imax_showtimes: list[str] = []
    current_format = ""

    for entry in luxe_lines:
        # Format labels look like "English - IMAX 2D", "IMAX 3D", "2D", etc.
        if _is_format_label(entry):
            current_format = entry
        elif _is_showtime(entry) and FORMAT_KEYWORD.lower() in current_format.lower():
            imax_showtimes.append(entry)

    found = len(imax_showtimes) > 0
    return (found, imax_showtimes, "\n".join(luxe_lines[:40]))


def _looks_like_theatre_header(line: str, all_lines: list[str]) -> bool:
    """Heuristic: theatre names contain keywords like 'cinemas', 'screen', 'PVR', 'INOX'."""
    markers = ["pvr", "inox", "cinemas", "cinepolis", "screen", "palazzo", "sathyam"]
    low = line.lower()
    return any(m in low for m in markers) and THEATRE_KEYWORD.lower() not in low


def _is_format_label(text: str) -> bool:
    """Format labels contain language or format keywords."""
    indicators = ["2d", "3d", "imax", "4dx", "dolby", "english", "tamil", "hindi", "telugu"]
    low = text.lower()
    return any(i in low for i in indicators)


def _is_showtime(text: str) -> bool:
    """Showtimes look like '10:30 AM', '02:15 PM', etc."""
    import re
    return bool(re.match(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", text.strip()))


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BookMyShow IMAX watcher")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't alert or write state")
    args = parser.parse_args()

    # Already alerted?
    if STATE_FILE.exists() and not args.dry_run:
        print(f"[{datetime.now().isoformat()}] Already alerted (state file exists). Exiting.")
        sys.exit(0)

    print(f"[{datetime.now().isoformat()}] Checking BMS for LUXE IMAX showtimes...")
    found, showtimes, debug_text = check()

    if found:
        print(f"[{datetime.now().isoformat()}] ✅ ✅ ✅ Opened IMAX showtimes found: {showtimes}")
        if args.dry_run:
            print("[dry-run] Would alert and write state file.")
        else:
            notify(showtimes)
            STATE_FILE.write_text(
                json.dumps({
                    "alerted_at": datetime.now().isoformat(),
                    "showtimes": showtimes,
                }),
                encoding="utf-8",
            )
            print(f"[{datetime.now().isoformat()}] State file written. Won't alert again.")
    else:
        print(f"[{datetime.now().isoformat()}] ❌  ❌  ❌ No IMAX showtimes yet for LUXE.")
        if not args.dry_run:
            notify_not_yet()
        if debug_text:
            print("── LUXE block (first 40 lines) ──")
            print(debug_text)
        else:
            print("(LUXE block not found on page at all.)")


if __name__ == "__main__":
    main()
