#!/usr/bin/env python3
"""
BookMyShow Watcher (Chennai, multi-source)
==========================================
Watches BookMyShow for ONE movie across your preferred Chennai theatres and
alerts you the moment booking opens anywhere.

Why multi-source: BMS surfaces a movie in several places that update at
different times — each theatre's own /cinemas/ page AND the aggregated
/movies/ page. PVR/INOX usually open on their cinema page first. This watcher
checks BOTH for every theatre, plus a Chennai-wide safety net on the movie
page, so it can never go silently blind the way a single-page watcher can.

Fail-loud design: if a page can't be read (timeout, redirect, empty), you get
a distinct WARNING notification instead of a misleading "No luck". A periodic
heartbeat confirms the watcher is alive even on quiet days.

Usage:
    python bms_watcher.py            # run the watch from config.json
    python bms_watcher.py --dry-run  # check without alerting or writing state
    python bms_watcher.py --status   # print current state and exit
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
HEARTBEAT_FILE = SCRIPT_DIR / ".bms_heartbeat"


# ─── Config ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE} not found. Run: python setup_movie.py")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─── Notifications ────────────────────────────────────────────────────────────

def _post(ntfy_topic: str, title: str, msg: str, priority: str, tags: str) -> bool:
    """Send one ntfy message. Returns True on success. Retries transient errors."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{ntfy_topic}",
                data=msg.encode("utf-8"),
                headers={"Title": title, "Priority": priority, "Tags": tags},
            )
            urllib.request.urlopen(req, timeout=20)
            return True
        except Exception as e:
            print(f"[{ts()}] ntfy send failed (attempt {attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(3)
    return False


def notify_found(theatre: str, showtimes: list[str], formats: list[str],
                 url: str, ntfy_topic: str, movie_name: str) -> None:
    """Send 4 back-to-back urgent notifications when a theatre opens."""
    format_text = ", ".join(dict.fromkeys(formats)) if formats else "Check BMS"
    showtime_text = ", ".join(dict.fromkeys(showtimes)) if showtimes else "Available now"

    messages = [
        {
            "title": f"Book Now - {movie_name}!",
            "msg": f"{theatre} just opened booking for {movie_name}!\nFormats: {format_text}\nShowtimes: {showtime_text}",
            "tags": "rotating_light",
        },
        {
            "title": f"Hurry - {theatre} slots live!",
            "msg": f"{movie_name} at {theatre} - Go go go!\nBook now:\n{url}",
            "tags": "fire",
        },
        {
            "title": f"Hurry Hurry - {theatre}!",
            "msg": f"{movie_name} at {theatre} is filling up!\nShowtimes: {showtime_text}\nBook now:\n{url}",
            "tags": "fire",
        },
        {
            "title": f"Last Reminder to Book - {movie_name}!",
            "msg": f"{theatre}\nShowtimes: {showtime_text}\nDon't miss it!\n{url}",
            "tags": "ticket",
        },
    ]
    for i, m in enumerate(messages):
        _post(ntfy_topic, m["title"], m["msg"], "urgent", m["tags"])
        if i < len(messages) - 1:
            time.sleep(2)
    print(f"[{ts()}] {len(messages)} urgent notifications sent for {theatre}!")


def notify_not_yet(theatres_waiting: list[str], ntfy_topic: str, interval: int, movie_name: str) -> None:
    waiting = ", ".join(theatres_waiting)
    _post(
        ntfy_topic,
        f"No luck - {movie_name}",
        f"[{movie_name}] No luck yet.\nWaiting for: {waiting}\nChecking every {interval} min...",
        "default",
        "hourglass",
    )
    print(f"[{ts()}] 'No luck' notification sent")


def notify_warning(ntfy_topic: str, movie_name: str, problems: list[str]) -> None:
    """Fail-loud: a page could not be read. This is NOT the same as 'not open yet'."""
    detail = "\n".join(f"- {p}" for p in problems)
    _post(
        ntfy_topic,
        f"WATCHER PROBLEM - {movie_name}",
        f"The watcher could not read {len(problems)} source(s) for {movie_name}.\n"
        f"These are NOT confirmed closed - the watcher is partially blind here:\n{detail}\n"
        f"Check the Mac / network. It will keep retrying.",
        "high",
        "warning",
    )
    print(f"[{ts()}] WARNING notification sent ({len(problems)} unreadable source(s))")


def notify_safety_net(ntfy_topic: str, movie_name: str, url: str) -> None:
    """Movie opened SOMEWHERE in Chennai even if none of your named theatres matched."""
    _post(
        ntfy_topic,
        f"Chennai booking OPEN - {movie_name}",
        f"{movie_name} booking has opened somewhere in Chennai!\n"
        f"(None of your named theatres matched yet - check manually too.)\n{url}",
        "urgent",
        "rotating_light",
    )
    print(f"[{ts()}] SAFETY-NET notification sent")


def notify_heartbeat(ntfy_topic: str, movie_name: str, n_sources: int, interval: int) -> None:
    _post(
        ntfy_topic,
        f"Watcher alive - {movie_name}",
        f"Still watching {movie_name} across {n_sources} sources, every {interval} min.\n"
        f"You'll get an urgent alert the moment a theatre opens.",
        "min",
        "heartbeat",
    )
    print(f"[{ts()}] heartbeat notification sent")


# ─── Page loading ─────────────────────────────────────────────────────────────

class PageResult:
    """Outcome of a page load. ok=True only if the page was genuinely readable."""
    def __init__(self, ok: bool, text: str = "", reason: str = ""):
        self.ok = ok
        self.text = text
        self.reason = reason


def load_page(url: str, date_str: str) -> PageResult:
    """Load a BMS page. Returns PageResult so callers can tell 'not open' from 'unreadable'."""
    try:
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
                page.wait_for_timeout(6000)

                current_url = page.url
                if date_str and date_str not in current_url:
                    browser.close()
                    return PageResult(False, "", f"redirected to {current_url} (expected {date_str})")

                for _ in range(12):
                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(600)
                page.wait_for_timeout(1500)

                text = page.inner_text("body")
            except Exception as e:
                browser.close()
                return PageResult(False, "", f"load error: {e}")

            browser.close()
    except Exception as e:
        return PageResult(False, "", f"playwright error: {e}")

    if not text or len(text) < 500:
        return PageResult(False, text, "page text suspiciously empty")
    return PageResult(True, text, "")


# ─── Parsing ──────────────────────────────────────────────────────────────────

def find_theatre(page_text: str, keyword: str, format_filter: str) -> tuple[bool, list[str], list[str]]:
    """Movie-page layout: find a THEATRE block and extract its showtimes."""
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
    return _extract(block_lines, format_filter)


def find_movie_at_cinema(page_text: str, movie_keyword: str, format_filter: str) -> tuple[bool, list[str], list[str]]:
    """Cinema-page layout: find the MOVIE block and extract its showtimes.

    The title can appear several times (real showtime block + footer carousels).
    Scan every occurrence and return the first block that actually yields showtimes.
    """
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    for idx, line in enumerate(lines):
        if movie_keyword.lower() not in line.lower():
            continue
        block_lines: list[str] = []
        for nxt in lines[idx + 1:]:
            if _looks_like_movie_header(nxt) or _is_section_header(nxt):
                break
            block_lines.append(nxt)
        found, showtimes, formats = _extract(block_lines, format_filter)
        if found:
            return (True, showtimes, formats)
    return (False, [], [])


def movie_present_anywhere(page_text: str, movie_keyword: str) -> bool:
    """Chennai-wide safety net: is the movie listed with ANY showtime on the movie page?"""
    found, showtimes, _ = find_movie_at_cinema(page_text, movie_keyword, "any")
    return found and bool(showtimes)


def _extract(block_lines: list[str], format_filter: str) -> tuple[bool, list[str], list[str]]:
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


def _is_section_header(line: str) -> bool:
    low = line.lower()
    banners = ["movies now showing", "top cinemas", "upcoming movies",
               "top cinema chains", "movies in ", "screening movies"]
    return any(b in low for b in banners)


def _looks_like_movie_header(line: str) -> bool:
    return bool(re.search(r"\((UA|A|U)\d*\+?\)", line))


def _looks_like_theatre_header(line: str, current_keyword: str) -> bool:
    markers = ["pvr", "inox", "cinemas", "cinepolis", "screen", "palazzo", "sathyam",
               "rakki", "rohini", "kamala", "ags", "vr chennai", "luxe", "escape",
               "aerohub", "miraj", "mayajaal"]
    low = line.lower()
    return any(m in low for m in markers) and current_keyword.lower() not in low


def _is_format_label(text: str) -> bool:
    indicators = ["2d", "3d", "imax", "4dx", "dolby", "english", "tamil",
                  "hindi", "telugu", "atmos", "epiq", "screenx", "pxl"]
    low = text.lower()
    return any(i in low for i in indicators)


def _is_showtime(text: str) -> bool:
    return bool(re.match(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", text.strip()))


# ─── State ─────────────────────────────────────────────────────────────────────

def _state_file(label: str, date_str: str) -> Path:
    safe = label.lower().replace(" ", "_")
    return SCRIPT_DIR / f".bms_alert_{safe}_{date_str}"


def _heartbeat_due(hours: int) -> bool:
    if hours <= 0:
        return False
    if not HEARTBEAT_FILE.exists():
        return True
    try:
        last = datetime.fromisoformat(HEARTBEAT_FILE.read_text().strip())
    except Exception:
        return True
    return datetime.now() - last >= timedelta(hours=hours)


def _mark_heartbeat() -> None:
    HEARTBEAT_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")


# ─── Core watch ────────────────────────────────────────────────────────────────

def run_watch(config: dict, dry_run: bool) -> None:
    ntfy_topic = config.get("ntfy_topic", "bms-luxe-srihari")
    interval = config.get("interval", 15)
    heartbeat_hours = config.get("heartbeat_hours", 12)
    movie = config["movie"]
    movie_name = movie.get("name", "Unknown")
    date_str = str(movie.get("date", "")) or _date_from_url(movie.get("movie_page_url", ""))
    movie_page_url = movie.get("movie_page_url", "")
    theatres = movie.get("theatres", [])

    print(f"[{ts()}] Watching '{movie_name}' ({date_str}) across {len(theatres)} theatres + Chennai safety net.")

    found_hits: list[str] = []        # theatres we alerted this run
    still_waiting: list[str] = []     # theatres confirmed readable but not open
    unreadable: list[str] = []        # sources we could NOT read (fail-loud)

    # Cache movie-page load (used both as a per-theatre source and safety net).
    movie_page: PageResult | None = None
    if movie_page_url:
        movie_page = load_page(movie_page_url, date_str)
        if not movie_page.ok:
            unreadable.append(f"movie page ({movie_page.reason})")

    for t in theatres:
        name = t["name"]
        state = _state_file(name, date_str)
        if state.exists() and not dry_run:
            print(f"  ⏭  {name}: already alerted (state file exists).")
            continue

        hit = False
        hit_url = ""
        hit_showtimes: list[str] = []
        hit_formats: list[str] = []
        readable_somewhere = False

        # Source 1: the theatre's own cinema page (opens first for PVR/INOX).
        cinema_url = t.get("cinema_url", "")
        if cinema_url:
            res = load_page(cinema_url, date_str)
            if res.ok:
                readable_somewhere = True
                ok, st, fmts = find_movie_at_cinema(res.text, movie_name, "any")
                if ok:
                    hit, hit_url, hit_showtimes, hit_formats = True, cinema_url, st, fmts
            else:
                unreadable.append(f"{name} cinema page ({res.reason})")

        # Source 2: the aggregated movie page (second place it can appear).
        if not hit and movie_page and movie_page.ok:
            readable_somewhere = True
            kw = t.get("movie_page_keyword", name)
            ok, st, fmts = find_theatre(movie_page.text, kw, "any")
            if ok:
                hit, hit_url, hit_showtimes, hit_formats = True, movie_page_url, st, fmts

        if hit:
            found_hits.append(name)
            print(f"  ✅ ✅ ✅ {name} is OPEN! Showtimes: {hit_showtimes}")
            _handle_hit(name, hit_showtimes, hit_formats, hit_url, ntfy_topic,
                        movie_name, state, dry_run)
        elif readable_somewhere:
            still_waiting.append(name)
            print(f"  ❌ {name}: not open yet.")
        else:
            print(f"  ⚠️  {name}: could not read any source (treated as UNKNOWN, not closed).")

    # Chennai-wide safety net: movie open somewhere even if no named theatre matched.
    safety_net_fired = False
    if not found_hits and movie_page and movie_page.ok:
        if movie_present_anywhere(movie_page.text, movie_name):
            safety_net_fired = True
            print(f"  🛟 Safety net: {movie_name} is open somewhere in Chennai.")
            if not dry_run:
                notify_safety_net(ntfy_topic, movie_name, movie_page_url)

    # Fail-loud: warn about unreadable sources (distinct from 'not open').
    if unreadable and not dry_run:
        notify_warning(ntfy_topic, movie_name, unreadable)
    elif unreadable:
        print(f"  [dry-run] Would send WARNING for: {unreadable}")

    # "No luck" only when everything was readable and nothing opened.
    if not found_hits and not safety_net_fired and not unreadable and still_waiting:
        if not dry_run:
            notify_not_yet(still_waiting, ntfy_topic, interval, movie_name)
        else:
            print(f"  [dry-run] Would send 'No luck' for: {still_waiting}")

    # Heartbeat so running state is always visible.
    n_sources = len(theatres) * 2 + (1 if movie_page_url else 0)
    if not dry_run and _heartbeat_due(heartbeat_hours):
        notify_heartbeat(ntfy_topic, movie_name, n_sources, interval)
        _mark_heartbeat()


def _handle_hit(label, showtimes, formats, url, ntfy_topic, movie_name, state_file, dry_run) -> None:
    if dry_run:
        print(f"    [dry-run] Would alert for {label}")
        return
    notify_found(label, showtimes, formats, url, ntfy_topic, movie_name)
    state_file.write_text(
        json.dumps({
            "alerted_at": ts(),
            "theatre": label,
            "showtimes": showtimes,
            "formats": formats,
        }),
        encoding="utf-8",
    )
    print(f"    State file written for {label}.")


def _date_from_url(url: str) -> str:
    m = re.search(r"(\d{8})", url)
    return m.group(1) if m else ""


# ─── Status ────────────────────────────────────────────────────────────────────

def print_status(config: dict) -> None:
    movie = config.get("movie", {})
    name = movie.get("name", "?")
    date_str = str(movie.get("date", "")) or _date_from_url(movie.get("movie_page_url", ""))
    print(f"Movie:    {name} ({date_str})")
    print(f"Topic:    {config.get('ntfy_topic')}")
    print(f"Interval: every {config.get('interval', 15)} min")
    print("Theatres:")
    for t in movie.get("theatres", []):
        state = _state_file(t["name"], date_str)
        status = "ALERTED ✅" if state.exists() else "watching…"
        print(f"  - {t['name']:20} {status}")
    if HEARTBEAT_FILE.exists():
        print(f"Last heartbeat: {HEARTBEAT_FILE.read_text().strip()}")


# ─── Entrypoint ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BookMyShow Watcher (Chennai, multi-source)")
    parser.add_argument("--dry-run", action="store_true", help="Check but don't alert or write state")
    parser.add_argument("--status", action="store_true", help="Print current state and exit")
    args = parser.parse_args()

    config = load_config()

    if args.status:
        print_status(config)
        return

    if "movie" not in config:
        print("config.json has no 'movie'. Run: python setup_movie.py")
        sys.exit(1)

    run_watch(config, args.dry_run)


if __name__ == "__main__":
    main()
