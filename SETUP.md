# BookMyShow Watcher — Setup Guide

Get notified the moment your favourite theatre opens booking on BookMyShow.

Works on **macOS** and **Windows**. Pick your section below.

---

## Prerequisites (Both Platforms)

- Python 3.9 or higher
- Internet connection
- [ntfy app](https://ntfy.sh) on your phone (free, no account needed)
  - [Android (Play Store)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
  - [iOS (App Store)](https://apps.apple.com/app/ntfy/id1625396347)

---

## macOS Setup

### Step 1 — Clone the repo

```bash
cd ~/Desktop
git clone https://github.com/srihari210597/bookmyshow.git
cd bookmyshow
```

### Step 2 — Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

### Step 3 — Subscribe to ntfy topic on your phone

1. Open the ntfy app
2. Tap **+** → subscribe to topic: `bms-luxe-srihari` (or pick your own name)
3. If you pick a custom name, update it in `config.json`

### Step 4 — Configure your watches

Edit `config.json`:

```json
{
    "ntfy_topic": "bms-luxe-srihari",
    "interval": 10,
    "watches": [
        {
            "name": "Spider-Man Jul 30",
            "url": "https://in.bookmyshow.com/movies/chennai/spider-man-brand-new-day/buytickets/ET00502600/20260730",
            "theatres": ["VR Chennai", "Sathyam"],
            "format": "any"
        }
    ]
}
```

**Fields:**

| Field | What to put |
|-------|-------------|
| `name` | Any label for your reference |
| `url` | BMS showtime URL for the movie + date |
| `theatres` | List of theatre keywords to watch |
| `format` | `"any"`, `"IMAX"`, `"4DX"`, `"Dolby"`, etc. |

### Step 5 — Test it

```bash
python bms_watcher.py --dry-run
```

You should see output like:
```
[2026-07-28] [Spider-Man Jul 30] Checking...
  Theatres: ['VR Chennai', 'Sathyam'] | Format: any
  ❌ VR Chennai not listed yet.
  ❌ Sathyam not listed yet.
```

### Step 6 — Set up cron (auto-check every 10 minutes)

```bash
crontab -e
```

Add this line:

```
*/10 * * * * cd ~/Desktop/bookmyshow && .venv/bin/python bms_watcher.py >> cron.log 2>&1
```

### Step 7 — Prevent Mac from sleeping (important!)

Cron won't run while your Mac sleeps.

**Option A — Keep awake (simplest):**
```bash
caffeinate -s &
```

**Option B — Keep lid open, screen locked:**
Press `Ctrl+Cmd+Q` to lock. Cron runs fine with screen locked and lid open.

### Step 8 — Grant cron permissions (if needed)

If cron logs show "Operation not permitted":

1. System Settings → Privacy & Security → Full Disk Access
2. Click + → press Cmd+Shift+G → type `/usr/sbin/cron` → Add

### Step 9 — Stop the watcher (after you've booked)

```bash
crontab -r          # removes cron job
killall caffeinate  # let Mac sleep again
```

### Step 10 — Re-arm for next movie

```bash
rm .bms_alert_*     # delete state files
# Edit config.json with new movie details
# Re-add cron entry (Step 6)
```

---

## Windows Setup

### Step 1 — Clone the repo

```powershell
cd ~\Desktop
git clone https://github.com/srihari210597/bookmyshow.git
cd bookmyshow
```

### Step 2 — Create virtual environment and install dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install playwright
playwright install chromium
```

### Step 3 — Subscribe to ntfy topic on your phone

1. Open the ntfy app
2. Tap **+** → subscribe to topic: `bms-luxe-srihari` (or pick your own name)
3. If you pick a custom name, update it in `config.json`

### Step 4 — Configure your watches

Edit `config.json` (same format as macOS — see Step 4 above).

### Step 5 — Test it

```powershell
python bms_watcher.py --dry-run
```

### Step 6 — Set up Task Scheduler (auto-check every 10 minutes)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name: `BMS Watcher`
4. Trigger: **Daily**, start today, recur every 1 day
5. Action: **Start a program**
   - Program: `C:\Users\<YourName>\Desktop\bookmyshow\.venv\Scripts\python.exe`
   - Arguments: `bms_watcher.py`
   - Start in: `C:\Users\<YourName>\Desktop\bookmyshow`
6. Click Finish

Then edit the task for 10-minute repeats:
1. Find your task in Task Scheduler Library
2. Right-click → Properties → Triggers tab → Edit
3. Check **Repeat task every:** `10 minutes` for a duration of `Indefinitely`
4. OK → OK

### Step 7 — Prevent sleep (important!)

**Option A — Power settings:**
1. Settings → System → Power & Sleep
2. Set "Sleep" to **Never** (when plugged in)

**Option B — Keep it plugged in and set to not sleep on lid close:**
1. Control Panel → Power Options → Choose what closing the lid does
2. Set "When I close the lid" to **Do nothing** (plugged in)

### Step 8 — Stop the watcher (after you've booked)

1. Open Task Scheduler → find `BMS Watcher` → right-click → Delete

### Step 9 — Re-arm for next movie

```powershell
del .bms_alert_*
# Edit config.json with new movie details
# Re-create the Task Scheduler entry
```

---

## How to Find the BMS URL

1. Go to [bookmyshow.com](https://in.bookmyshow.com)
2. Search for your movie → select your city
3. Click "Book tickets" → select the **date** you want
4. Copy the URL from your browser. It looks like:
   ```
   https://in.bookmyshow.com/movies/chennai/movie-name/buytickets/ETXXXXXXXX/YYYYMMDD
   ```
5. Paste it into config.json (remove any `?query=params` from the end)

---

## How Notifications Work

| Scenario | What you get |
|----------|-------------|
| Theatre opens | 3 urgent back-to-back notifications with showtimes + booking link |
| Not open yet | 1 "No luck" notification every 10 minutes |
| Already alerted | Nothing (state file prevents re-alerting) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No module named playwright" | Run `pip install playwright` inside .venv |
| Page timeout | Normal — BMS can be slow. Next run will retry |
| Notifications not arriving | Check ntfy app is subscribed to the right topic |
| False positive | BMS redirected to wrong date — already handled in code |
| Watcher stops overnight | Mac slept or Windows went to sleep — fix power settings |
| "Operation not permitted" (macOS) | Grant Full Disk Access to cron |
| State file blocks alerts | Delete `.bms_alert_*` files to re-arm |

---

## Project Files

| File | Purpose |
|------|---------|
| `bms_watcher.py` | Main script (don't edit this) |
| `config.json` | Your watches — edit this for new movies |
| `SETUP.md` | This guide |
| `README.md` | Project overview |
| `runbook.html` | Original HTML runbook |
