# BookMyShow Watcher (Chennai)

Automated alert system that watches BookMyShow and notifies you the moment your
preferred Chennai theatres open booking for a movie. Built to **never fail
silently** — if it can't read a page, it tells you; it never mistakes "I'm
blind" for "not open yet".

> **Setting up a new movie? Follow [NEXT_MOVIE.md](NEXT_MOVIE.md).**
> It is the required runbook — especially the mandatory dry-run verify step
> that prevents the silent-miss that happened with Jailer 2.

## Why this exists (the lesson that shaped it)

BookMyShow surfaces a movie in several places that update at **different times**:

- each theatre's own cinema page: `/cinemas/chennai/<slug>/buytickets/<CODE>/<date>`
- the aggregated movie page: `/movies/chennai/<slug>/buytickets/<EVENT>/<date>`

PVR and INOX usually open booking on their **own cinema page first**, before
they appear on the aggregated movie page. An earlier version watched only the
movie page, so when booking opened on the cinema pages it kept reporting "not
listed yet" — a silent miss. This version fixes that by watching **every source**.

## How It Works

```
┌──────────┐  every N min  ┌──────────────────┐  Playwright  ┌──────────────────────┐
│   cron   │──────────────▶│  bms_watcher.py  │─────────────▶│ BookMyShow            │
└──────────┘                └────────┬─────────┘              │  • 5 cinema pages     │
                                     │                        │  • 1 movie page       │
            For EACH theatre: check its cinema page           └──────────────────────┘
            AND the movie page. Plus a Chennai-wide net.
                                     │
                   ┌─────────────────▼──────────────────┐
                   │  Open anywhere?  → 4x urgent        │──▶ ntfy ──▶ Phone
                   │  Page unreadable? → WARNING         │──▶ ntfy ──▶ Phone
                   │  All read, none open? → "No luck"   │──▶ ntfy ──▶ Phone
                   │  Quiet day?       → heartbeat       │──▶ ntfy ──▶ Phone
                   └─────────────────────────────────────┘
```

## Four kinds of notification

| Trigger | Notification | Priority |
|---------|--------------|----------|
| A theatre opens booking (on either source) | 4 back-to-back: **Book Now → Hurry → Hurry Hurry → Last Reminder** | urgent |
| Movie opens somewhere in Chennai but none of your named theatres matched | **Chennai booking OPEN** safety net | urgent |
| A page can't be read (timeout, redirect, empty) | **WATCHER PROBLEM** — lists the unreadable source(s) | high |
| Everything readable, nothing open yet | **No luck** | default |
| Quiet period (configurable) | **Watcher alive** heartbeat | min |

The point: **silence is impossible**. Either a theatre opened, or the movie
opened somewhere, or a page was unreadable (you're warned), or everything was
read and nothing's open (you get "No luck"), or you get a periodic heartbeat.

## Files

| File | Purpose |
|------|---------|
| `bms_watcher.py` | The watcher. Reads `config.json`. Don't edit for routine use. |
| `setup_movie.py` | Build `config.json` for a new movie from your standing theatre list. |
| `config.json` | Current movie + your 5 preferred Chennai theatres (defaults). |
| `SETUP.md` | Install + operations guide. |
| `README.md` | This file. |

## Quick Start

### 1. Install (one time)

```bash
cd ~/Desktop/"Book MY"
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

### 2. Subscribe to notifications

Install the **ntfy** app and subscribe to the topic in `config.json`
(default `bms-luxe-srihari`). [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) · [iOS](https://apps.apple.com/app/ntfy/id1625396347)

### 3. Point it at a movie

```bash
python setup_movie.py \
    --name "Jailer 2" \
    --slug jailer-2 \
    --event ET00521160 \
    --date 20261015 \
    --clear-state
```

Get `--slug` and `--event` from the movie's BMS URL in Chennai:
`https://in.bookmyshow.com/movies/chennai/<slug>/buytickets/<EVENT>/<date>`

### 4. Test

```bash
python bms_watcher.py --dry-run   # checks everything, sends nothing
python bms_watcher.py --status    # shows current state
```

### 5. Automate (every 15 min)

```bash
crontab -e
```
```
*/15 * * * * cd /Users/srihari/Desktop/Book\ MY && .venv/bin/python bms_watcher.py >> cron.log 2>&1
```

### 6. Keep the Mac awake

A `caffeinate` LaunchAgent (`~/Library/LaunchAgents/com.srihari.caffeinate.plist`)
keeps the system awake and restarts itself. Verify:
```bash
launchctl list | grep caffeinate
pmset -g assertions | grep caffeinate
```

## Your preferred theatres (defaults)

Stored in `config.json` under `defaults.preferred_theatres`. `setup_movie.py`
builds every new movie's watch from this list — no manual URL assembly.

| Theatre | Cinema code |
|---------|-------------|
| PVR: VR Chennai, Anna Nagar | `PCAN` |
| PVR: Aerohub, Chennai | `PABC` |
| INOX: LUXE Phoenix Market City, Velachery | `INPR` |
| PVR: Palazzo, The Nexus Vijaya Mall | `PVPZ` |
| PVR: Sathyam, Royapettah | `PVSR` |

To add/remove a theatre, edit `defaults.preferred_theatres` (name, slug, code,
movie_page_keyword), then re-run `setup_movie.py`.

## config.json shape

```json
{
    "ntfy_topic": "bms-luxe-srihari",
    "interval": 15,
    "city": "chennai",
    "heartbeat_hours": 12,
    "movie": {
        "name": "Jailer 2",
        "date": "20261015",
        "movie_page_url": "https://in.bookmyshow.com/movies/chennai/jailer-2/buytickets/ET00521160/20261015",
        "theatres": [
            {
                "name": "VR Chennai",
                "cinema_url": "https://in.bookmyshow.com/cinemas/chennai/pvr-vr-chennai-anna-nagar/buytickets/PCAN/20261015",
                "movie_page_keyword": "VR Chennai"
            }
        ]
    },
    "defaults": { "preferred_theatres": [ ] }
}
```

- `interval` — minutes between checks (text only; actual cadence is your cron).
- `heartbeat_hours` — send an "alive" ping at most this often. `0` disables.
- Each theatre is checked on **both** its `cinema_url` and the `movie_page_url`.

## State files

After alerting for a theatre, a state file `.bms_alert_<theatre>_<date>` is
written so it won't re-alert. Re-arm with:
```bash
rm .bms_alert_*          # or use: python setup_movie.py ... --clear-state
```

## Stop after you've booked

```bash
crontab -r                                                            # stop checks
launchctl unload ~/Library/LaunchAgents/com.srihari.caffeinate.plist  # let Mac sleep
```

## Design decisions

1. **Multi-source** — watch each theatre's cinema page AND the movie page, because they open at different times.
2. **Fail-loud** — an unreadable page produces a WARNING, never a false "not open". This is the fix for the silent miss.
3. **Chennai-wide safety net** — if the movie opens anywhere in Chennai but a theatre keyword didn't match, you still get told.
4. **Heartbeat** — periodic "alive" ping so a dead watcher is noticeable.
5. **Playwright + scroll** — BMS is JS-rendered and lazy-loads showtimes; we scroll before reading.
6. **ntfy.sh** — zero-auth push notifications.

## Requirements

- Python 3.9+, Playwright + Chromium
- ntfy app on phone (free)
- macOS with cron; `caffeinate` to prevent sleep
