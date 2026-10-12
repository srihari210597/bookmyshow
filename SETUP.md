# BookMyShow Watcher — Setup & Operations (Chennai)

Get notified the moment your preferred Chennai theatres open booking. This
watcher checks every place a ticket can appear and **never fails silently**.

---

## Prerequisites

- Python 3.9+
- [ntfy app](https://ntfy.sh) on your phone (free, no account)
  - [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) · [iOS](https://apps.apple.com/app/ntfy/id1625396347)

---

## One-time install

```bash
cd ~/Desktop/"Book MY"
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

Subscribe to the ntfy topic in `config.json` (default `bms-luxe-srihari`) in
the app. To change it, edit `ntfy_topic`.

---

## Watching a new movie (the only routine step)

> **Follow the full runbook in [NEXT_MOVIE.md](NEXT_MOVIE.md).** The steps below
> are the summary; the runbook includes the mandatory verify step that prevents
> the silent-miss we hit with Jailer 2. Do not skip the dry-run.

You always watch in Chennai across your 5 standing theatres, so setting up a
new movie takes one command:

```bash
python setup_movie.py \
    --name "Movie Name" \
    --slug movie-slug \
    --event ET00XXXXXX \
    --date YYYYMMDD \
    --clear-state
```

**Finding `--slug` and `--event`:** open the movie on bookmyshow.com in
Chennai, pick the date, and read the URL:

```
https://in.bookmyshow.com/movies/chennai/<slug>/buytickets/<EVENT>/<date>
                                    ^^^^^^              ^^^^^^^
```

Example (Jailer 2, Oct 15 2026):
```bash
python setup_movie.py --name "Jailer 2" --slug jailer-2 --event ET00521160 --date 20261015 --clear-state
```

`--clear-state` wipes old alert/heartbeat files so everything re-arms cleanly.

Then verify:
```bash
python bms_watcher.py --dry-run    # full check, sends nothing
python bms_watcher.py --status     # shows which theatres are armed/alerted
```

---

## Running it automatically (cron, every 15 min)

```bash
crontab -e
```
Add:
```
*/15 * * * * cd /Users/srihari/Desktop/Book\ MY && .venv/bin/python bms_watcher.py >> cron.log 2>&1
```

If cron logs show "Operation not permitted":
System Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron`.

---

## Keeping the Mac awake (required)

Cron won't fire while the Mac sleeps. A LaunchAgent keeps `caffeinate` running
and restarts it automatically (survives reboots):

`~/Library/LaunchAgents/com.srihari.caffeinate.plist` runs `caffeinate -i -m`.

Check it:
```bash
launchctl list | grep caffeinate          # 0 in the middle column = healthy
pmset -g assertions | grep caffeinate      # should show it preventing sleep
```

Note: `caffeinate` keeps the *system* awake; the display may still sleep (fine).
Closing the lid will still sleep the Mac unless on power + external display.

---

## The five notification types

| You see | It means |
|---------|----------|
| **Book Now / Hurry / Hurry Hurry / Last Reminder** (4 urgent) | A theatre opened booking — go book |
| **Chennai booking OPEN** | Movie opened somewhere in Chennai though your named theatres didn't match — check manually |
| **WATCHER PROBLEM** | A page couldn't be read; the watcher is partially blind there (NOT confirmed closed). Check Mac/network |
| **No luck** | Everything was readable, nothing open yet |
| **Watcher alive** | Periodic heartbeat so you know it's running |

You get the 4-notification burst **once per theatre** (a state file prevents
repeats). Each of the 5 theatres fires its own burst when it opens.

---

## Config reference (`config.json`)

| Field | Meaning |
|-------|---------|
| `ntfy_topic` | ntfy topic your phone is subscribed to |
| `interval` | minutes between checks (display text; real cadence = cron) |
| `city` | always `chennai` |
| `heartbeat_hours` | max frequency of the "alive" ping; `0` disables |
| `movie` | the current watch (built by `setup_movie.py`) |
| `defaults.preferred_theatres` | your standing theatre list used to build new movies |

To change your standing theatres, edit `defaults.preferred_theatres` (each has
`name`, `slug`, `code`, `movie_page_keyword`) and re-run `setup_movie.py`.

---

## After you've booked

```bash
crontab -r                                                            # stop checks
launchctl unload ~/Library/LaunchAgents/com.srihari.caffeinate.plist  # allow sleep
rm .bms_alert_* .bms_heartbeat                                        # clear state
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No module named playwright" | `pip install playwright` inside `.venv` |
| WATCHER PROBLEM notifications | A page kept failing — check network / that the Mac is awake. It auto-retries |
| Page timeout in logs | BMS slow or date not open yet; next run retries |
| No notifications at all | Confirm ntfy app subscribed to the right topic; run `--dry-run` to test |
| "already alerted" / no re-alert | Delete `.bms_alert_*` or re-run `setup_movie.py --clear-state` |
| Watcher stopped overnight | Mac slept — check the caffeinate LaunchAgent |

---

## Project files

| File | Purpose |
|------|---------|
| `bms_watcher.py` | The watcher (don't edit for routine use) |
| `setup_movie.py` | Create a new movie watch from your defaults |
| `config.json` | Current movie + your preferred theatres |
| `README.md` | Overview + design |
| `SETUP.md` | This guide |
