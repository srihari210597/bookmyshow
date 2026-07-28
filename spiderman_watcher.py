#!/usr/bin/env python3
"""
Spider-Man: Brand New Day — LUXE Velachery Watcher
===================================================
Watches for INOX LUXE Phoenix Market City, Velachery to open booking
for Spider-Man: Brand New Day on Thu 31 Jul 2026.

Cron: runs once per invocation, alerts via ntfy.sh.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# ─── Configuration ────────────────────────────────────────────────────────────

TARGET_URL = "https://in.bookmyshow.com/movies/chennai/spider-man-brand-new-day/buytickets/ET00502600/20260730"
DATE_STR = "20260730"
THEATRE_KEYWORD = "VR Chennai"
NTFY_TOPIC = "bms-luxe-srihari"
STATE_FILE = Path(__file__).parent / ".bms_alert_spiderman_vr_20260730"

# ─── Notifications ────────────────────────────────────────────────────────────

def notify(showtimes: list[str], formats: list[str]) -> None:
    """Send 3 back-to-back urgent notifications."""
    import urllib.request

    format_text = ", ".join(set(formats)) if formats else "Check BMS"
    showtime_text = ", ".join(showtimes) if showtimes else "Available now"

    messages = [
        {
            "title": "BOOK NOW - Spider-Man at VR Chennai!",
            "msg": f"PVR VR Chennai, Anna Nagar opened Spider-Man - Jul 30!\nShowtimes: {showtime_text}",
            "tags": "rotating_light",
        },
        {
            "title": "HURRY - VR Chennai slots live!",
            "msg": f"Go go go! PVR VR Chennai is bookable now.\n{TARGET_URL}",
            "tags": "fire",
        },
        {
            "title": "LAST REMINDER - Book Spider-Man!",
            "msg": f"Showtimes: {showtime_text}\nDon't miss it!\n{TARGET_URL}",
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
            time.sleep(2)

    print(f"[{datetime.now().isoformat()}] 3 urgent notifications sent!")


def notify_not_yet() -> None:
    """Send a 'no luck' notification."""
    import urllib.request

    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data="No luck yet. VR Chennai not listed for Spider-Man Jul 30. Still checking...".encode("utf-8"),
        headers={
            "Title": "No luck - VR Chennai not open for Spider-Man",
            "Priority": "high",
            "Tags": "hourglass",
        },
    )
    urllib.request.urlopen(req)
    print(f"[{datetime.now().isoformat()}] 'No luck' notification sent")


# ─── Core logic ───────────────────────────────────────────────────────────────

def check() -> tuple[bool, list[str], list[str], str]:
    """
    Load the BMS page, check if LUXE appears at all.

    Returns:
        (found: bool, showtimes: list[str], formats: list[str], raw_text: str)
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
            page.wait_for_timeout(8000)

            # Verify we're on the right date
            current_url = page.url
            if DATE_STR not in current_url:
                print(f"[{datetime.now().isoformat()}] Page redirected to: {current_url} (not {DATE_STR})")
                browser.close()
                return (False, [], [], "")

            page_text = page.inner_text("body")
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Page load error: {e}", file=sys.stderr)
            browser.close()
            return (False, [], [], "")

        browser.close()

    # ─── Check if LUXE appears on the page ────────────────────────────────
    lines = page_text.splitlines()
    luxe_found = False
    luxe_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if THEATRE_KEYWORD.lower() in stripped.lower():
            luxe_found = True
            luxe_lines = []
            continue
        if luxe_found and _looks_like_theatre_header(stripped):
            break
        if luxe_found:
            luxe_lines.append(stripped)

    if not luxe_found:
        return (False, [], [], "")

    # ─── Extract all showtimes from VR Chennai block ────────────────────
    showtimes: list[str] = []
    formats: list[str] = []
    current_format = ""

    for entry in luxe_lines:
        if _is_format_label(entry):
            current_format = entry
            if current_format not in formats:
                formats.append(current_format)
        elif _is_showtime(entry):
            showtimes.append(entry)

    if not showtimes:
        return (False, [], formats, "\n".join(luxe_lines[:40]))

    return (True, showtimes, formats, "\n".join(luxe_lines[:40]))


def _looks_like_theatre_header(line: str) -> bool:
    markers = ["pvr", "inox", "cinemas", "cinepolis", "screen", "palazzo", "sathyam", "rakki", "rohini", "kamala", "ags", "vr chennai"]
    low = line.lower()
    return any(m in low for m in markers) and THEATRE_KEYWORD.lower() not in low


def _is_format_label(text: str) -> bool:
    indicators = ["2d", "3d", "imax", "4dx", "dolby", "english", "tamil", "hindi", "telugu", "atmos", "epiq"]
    low = text.lower()
    return any(i in low for i in indicators)


def _is_showtime(text: str) -> bool:
    return bool(re.match(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", text.strip()))


# ─── Entrypoint ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Spider-Man LUXE watcher")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't alert or write state")
    args = parser.parse_args()

    if STATE_FILE.exists() and not args.dry_run:
        print(f"[{datetime.now().isoformat()}] Already alerted (state file exists). Exiting.")
        sys.exit(0)

    print(f"[{datetime.now().isoformat()}] Checking BMS for VR Chennai - Spider-Man Jul 30...")
    found, showtimes, formats, debug_text = check()

    if found:
        print(f"[{datetime.now().isoformat()}] ✅ ✅ ✅ VR Chennai is listed! Formats: {formats} Showtimes: {showtimes}")
        if args.dry_run:
            print("[dry-run] Would alert and write state file.")
        else:
            notify(showtimes, formats)
            STATE_FILE.write_text(
                json.dumps({
                    "alerted_at": datetime.now().isoformat(),
                    "showtimes": showtimes,
                    "formats": formats,
                }),
                encoding="utf-8",
            )
            print(f"[{datetime.now().isoformat()}] State file written. Won't alert again.")
    else:
        print(f"[{datetime.now().isoformat()}] ❌ ❌ ❌ VR Chennai not listed for Spider-Man Jul 30 yet.")
        if not args.dry_run:
            notify_not_yet()
        if debug_text:
            print("── LUXE block ──")
            print(debug_text)
        else:
            print("(LUXE not found on page at all.)")


if __name__ == "__main__":
    main()
