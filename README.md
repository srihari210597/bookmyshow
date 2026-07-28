# BookMyShow Watcher

Automated alert system that watches BookMyShow and notifies you the moment a specific theatre opens booking for your chosen movie, date, and format.

## How It Works

```
┌──────────┐   every N min   ┌──────────────────┐   Playwright   ┌─────────────┐
│   cron   │────────────────▶│  bms_watcher.py  │──────────────▶│  BookMyShow  │
└──────────┘                  └────────┬─────────┘                └─────────────┘
                                       │
                          Parse theatre block + format filter
                                       │
                              ┌─────────▼──────────┐
                              │   Match found?     │
                              │   YES → 3x urgent  │──▶ ntfy.sh ──▶ Phone
                              │   NO  → "No luck"  │──▶ ntfy.sh ──▶ Phone
                              └────────────────────┘
```

1. **cron** triggers the script at a fixed interval (e.g., every 10 minutes)
2. **Playwright** launches headless Chromium and loads the BMS showtimes page (JS-rendered, can't use plain HTTP)
3. Script **parses** the rendered page text to find the target theatre block
4. **Format filter** matches showtimes under the correct format label (IMAX, 4DX, Dolby, etc.)
5. **Date verification** ensures BMS didn't redirect to a different date's page
6. **ntfy.sh** sends push notifications to your phone — no login or API key needed

## Files

| File | Purpose |
|------|---------|
| `bms_watcher.py` | Reusable watcher — pass any movie/theatre/format/date as arguments |
| `odyssey_watcher.py` | Original watcher hardcoded for The Odyssey / LUXE / IMAX / 20 Jul 2026 |
| `runbook.html` | Step-by-step setup guide with troubleshooting |
| `README.md` | This file |

## Quick Start

### 1. Install dependencies

```bash
cd ~/Desktop/"Book MY"
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

### 2. Set up ntfy (notifications)

1. Install the **ntfy** app on your phone — [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347)
2. Subscribe to a topic (e.g., `bms-luxe-srihari`)
3. Use the same topic name with `--ntfy-topic`

### 3. Run a test

```bash
python bms_watcher.py \
    --url "https://in.bookmyshow.com/buytickets/the-odyssey-chennai/movie-chen-ET00480917-MT/20260720" \
    --theatre LUXE \
    --format IMAX \
    --dry-run
```

### 4. Set up cron

```bash
crontab -e
```

Add:
```
*/10 * * * * /Users/srihari/Desktop/Book\ MY/.venv/bin/python /Users/srihari/Desktop/Book\ MY/bms_watcher.py --url "https://in.bookmyshow.com/buytickets/the-odyssey-chennai/movie-chen-ET00480917-MT/20260720" --theatre LUXE --format IMAX >> /Users/srihari/Desktop/Book\ MY/cron.log 2>&1
```

### 5. Prevent Mac from sleeping

```bash
caffeinate -s &
```

## Usage

```
python bms_watcher.py [OPTIONS]
```

### Required Arguments

| Argument | Description |
|----------|-------------|
| `--url` | Full BMS showtime URL (OR use `--movie` + `--date`) |
| `--movie` | Movie path from BMS URL (used with `--date`) |
| `--date` | Date in YYYYMMDD format |
| `--theatre` | Theatre name to match (e.g., `LUXE`, `PVR`, `Palazzo`) |

### Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--format` | `IMAX` | Format to filter (`IMAX`, `4DX`, `Dolby`, or `any`) |
| `--ntfy-topic` | `bms-luxe-srihari` | ntfy.sh topic for notifications |
| `--interval` | `10` | Check interval in minutes (for notification text only) |
| `--dry-run` | — | Check without alerting or writing state |

## Examples

```bash
# The Odyssey - LUXE IMAX - July 20
python bms_watcher.py \
    --url "https://in.bookmyshow.com/buytickets/the-odyssey-chennai/movie-chen-ET00480917-MT/20260720" \
    --theatre LUXE --format IMAX

# Future movie at PVR in 4DX
python bms_watcher.py \
    --url "https://in.bookmyshow.com/buytickets/some-movie-chennai/movie-chen-ET00XXXXXX-MT/20260801" \
    --theatre PVR --format 4DX

# Any format at Palazzo
python bms_watcher.py \
    --url "https://in.bookmyshow.com/buytickets/..." \
    --theatre Palazzo --format any

# Custom notification topic
python bms_watcher.py \
    --url "..." --theatre LUXE --format IMAX \
    --ntfy-topic my-movie-alerts

# Watch multiple movies simultaneously (separate cron entries)
*/10 * * * * .venv/bin/python bms_watcher.py --url "URL1" --theatre LUXE --format IMAX --ntfy-topic alerts >> cron.log 2>&1
*/10 * * * * .venv/bin/python bms_watcher.py --url "URL2" --theatre PVR --format 4DX --ntfy-topic alerts >> cron.log 2>&1
```

## How to Find the BMS URL

1. Go to [bookmyshow.com](https://in.bookmyshow.com)
2. Search for your movie
3. Click on the movie → select your city
4. Click "Book tickets" → select the date you want to watch
5. The URL in your browser is what you need. It looks like:
   ```
   https://in.bookmyshow.com/buytickets/MOVIE-NAME-CITY/movie-CITY-ETXXXXXXXX-MT/YYYYMMDD
   ```

## Notifications

### When booking opens (3 urgent notifications):
1. 🚨 **BOOK NOW - IMAX Opened!** — with showtimes
2. 🔥 **HURRY - IMAX slots live!** — with booking link
3. 🎫 **LAST REMINDER - Book IMAX now!** — showtimes + link

### When not yet available:
- ⏳ **No luck - IMAX not open yet** — "No luck yet. Still checking every 10 min..."

## State Files

The watcher creates a state file (`.bms_alert_THEATRE_DATE`) after the first successful alert to prevent repeated notifications. Each theatre+date combo gets its own state file.

To re-arm the watcher:
```bash
rm .bms_alert_luxe_20260720
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Page timeout | BMS slow or date page doesn't exist yet | Normal — next cron run will retry |
| False positive alert | BMS redirected to a different date | Fixed with URL + date verification |
| No cron output | macOS blocking cron | Grant Full Disk Access to `/usr/sbin/cron` |
| Notifications stop overnight | Mac slept | Use `caffeinate -s &` or keep lid open |
| "Already alerted" in log | State file exists | Delete `.bms_alert_*` file to re-arm |
| Permission error in cron log | Sandbox blocking .venv | Use full absolute paths in crontab |

## Design Decisions

1. **Playwright over requests** — BMS showtimes are JS-rendered; plain HTTP gets an empty shell
2. **Format filtering** — the URL doesn't include format filters (that's client-side state), so we parse all formats and match the one you want
3. **Date verification** — BMS may redirect to the nearest available date if your target date isn't open yet, causing false positives
4. **Single-shot + state file** — cron needs one-check-and-exit; the state file prevents alert spam
5. **ntfy.sh** — zero-auth push notifications; no Gmail App Passwords or API keys needed

## Requirements

- Python 3.9+
- Playwright (`pip install playwright`)
- Chromium (`playwright install chromium`)
- ntfy app on phone (free)
- macOS with cron access
