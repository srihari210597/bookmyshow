#!/usr/bin/env python3
"""
Setup a new movie to watch (Chennai).
=====================================
Builds the `movie` block in config.json from your standing preferred-theatre
list, so you never have to hand-assemble URLs again.

Because you always watch in Chennai with your 5 fixed theatres, you only need
to supply three things: the movie name, the movie's BMS slug + event ID, and
the date.

Usage:
    python setup_movie.py \
        --name "Jailer 2" \
        --slug jailer-2 \
        --event ET00521160 \
        --date 20261015

Where to get slug + event id:
    Open the movie on bookmyshow.com (Chennai) and look at the URL:
      https://in.bookmyshow.com/movies/chennai/<slug>/buytickets/<EVENT>/<date>
    e.g. slug=jailer-2, EVENT=ET00521160

After running, verify with:
    python bms_watcher.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

CITY = "chennai"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE} not found.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def cinema_url(slug: str, code: str, date: str) -> str:
    return f"https://in.bookmyshow.com/cinemas/{CITY}/{slug}/buytickets/{code}/{date}"


def movie_page_url(movie_slug: str, event: str, date: str) -> str:
    return f"https://in.bookmyshow.com/movies/{CITY}/{movie_slug}/buytickets/{event}/{date}"


def build_movie(config: dict, name: str, movie_slug: str, event: str, date: str) -> dict:
    prefs = config.get("defaults", {}).get("preferred_theatres", [])
    if not prefs:
        print("ERROR: config.json defaults.preferred_theatres is empty. Add your theatres there first.")
        sys.exit(1)

    theatres = []
    for p in prefs:
        theatres.append({
            "name": p["name"],
            "cinema_url": cinema_url(p["slug"], p["code"], date),
            "movie_page_keyword": p.get("movie_page_keyword", p["name"]),
        })

    return {
        "name": name,
        "date": date,
        "movie_page_url": movie_page_url(movie_slug, event, date),
        "theatres": theatres,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Set up a new movie to watch (Chennai)")
    ap.add_argument("--name", required=True, help='Display name, e.g. "Jailer 2"')
    ap.add_argument("--slug", required=True, help="Movie URL slug, e.g. jailer-2")
    ap.add_argument("--event", required=True, help="BMS event id, e.g. ET00521160")
    ap.add_argument("--date", required=True, help="Date YYYYMMDD, e.g. 20261015")
    ap.add_argument("--clear-state", action="store_true",
                    help="Delete old .bms_alert_* state + heartbeat so alerts re-arm")
    args = ap.parse_args()

    if len(args.date) != 8 or not args.date.isdigit():
        print("ERROR: --date must be YYYYMMDD (8 digits).")
        sys.exit(1)

    config = load_config()
    config["city"] = CITY
    config["movie"] = build_movie(config, args.name, args.slug, args.event, args.date)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
        f.write("\n")

    if args.clear_state:
        removed = 0
        for sf in SCRIPT_DIR.glob(".bms_alert_*"):
            sf.unlink()
            removed += 1
        hb = SCRIPT_DIR / ".bms_heartbeat"
        if hb.exists():
            hb.unlink()
        print(f"Cleared {removed} old state file(s) + heartbeat.")

    print(f"\nconfig.json updated for '{args.name}' ({args.date}).")
    print("Theatres armed:")
    for t in config["movie"]["theatres"]:
        print(f"  - {t['name']:20} {t['cinema_url']}")
    print(f"\nMovie page (safety net): {config['movie']['movie_page_url']}")
    print("\nNext: python bms_watcher.py --dry-run")


if __name__ == "__main__":
    main()
