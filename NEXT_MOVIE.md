# Runbook: Watching a New Movie

Follow this every time you want to watch a new movie. It is deliberately short.
The whole point is that the **verify step is mandatory** — that is how we avoid
the silent-miss that happened with Jailer 2.

> Context: Jailer 2 booking opened at your theatres but you got no alert. The old
> watcher looked only at the aggregated *movie* page, while PVR/INOX opened on
> their own *cinema* pages first. The watcher honestly reported "not listed" and
> the silence looked exactly like "working fine." Everything below exists to make
> that impossible to repeat.

---

## The procedure (do these in order)

### 1. Get the movie's slug + event ID (live listing)

Open the movie on bookmyshow.com in **Chennai**, select your **date**, and read
the browser URL:

```
https://in.bookmyshow.com/movies/chennai/<slug>/buytickets/<EVENT>/<date>
                                    ^^^^^^              ^^^^^^^
```

- `slug`  → e.g. `jailer-2`
- `EVENT` → e.g. `ET00521160`

⚠️ A movie can have more than one event ID (we saw a live one and a dead one for
Jailer 2). **Always copy the URL from the actual date page you intend to book on.**

### 2. Build the config with one command

```bash
cd ~/Desktop/"Book MY"
.venv/bin/python setup_movie.py \
    --name "Movie Name" \
    --slug movie-slug \
    --event ET00XXXXXX \
    --date YYYYMMDD \
    --clear-state
```

This rebuilds `config.json` for the new movie across all your preferred Chennai
theatres automatically. `--clear-state` wipes old alert/heartbeat files so it
re-arms cleanly. **Do not hand-edit URLs.**

### 3. VERIFY — mandatory, do not skip

```bash
.venv/bin/python bms_watcher.py --dry-run
.venv/bin/python bms_watcher.py --status
```

Confirm in the dry-run output:

- [ ] Every theatre line loaded (no "could not read any source" lines).
- [ ] No "WATCHER PROBLEM" / redirect / empty-page errors.
- [ ] If booking is already open, the right theatres show `✅ OPEN` with real showtimes.
- [ ] If not open yet, you see `❌ not open yet` for readable theatres (expected).

If a page fails to load repeatedly, the slug/event/date is probably wrong — go
back to step 1 and re-copy the URL. **Do not arm cron until the dry-run is clean.**

### 4. Arm the automation

```bash
# a) cron — check every 15 minutes
crontab -e
# add exactly this line:
*/15 * * * * cd /Users/srihari/Desktop/Book\ MY && .venv/bin/python bms_watcher.py >> cron.log 2>&1

# b) keep the Mac awake (cron won't run while asleep)
launchctl load ~/Library/LaunchAgents/com.srihari.caffeinate.plist
# If that file doesn't exist, recreate it (see "Caffeinate agent" below), then load it.
```

Confirm both:
```bash
crontab -l                                 # shows the watcher line
launchctl list | grep caffeinate           # middle column 0 = healthy
pmset -g assertions | grep caffeinate       # shows it preventing sleep
```

### 5. After you've booked — stop everything

```bash
crontab -r                                                            # stop checks
launchctl unload ~/Library/LaunchAgents/com.srihari.caffeinate.plist  # allow sleep
rm -f .bms_alert_* .bms_heartbeat                                     # clear state
```

---

## Why this won't fail silently again (the safeguards)

| What went wrong before | Safeguard now in place |
|------------------------|------------------------|
| Watched only the movie page; PVR/INOX opened on cinema pages first | **Multi-source**: each theatre is checked on its own cinema page AND the movie page |
| Silence looked like "all fine" | **Fail-loud**: an unreadable page sends a distinct **WATCHER PROBLEM** alert, never a false "No luck" |
| A wrong theatre keyword could blind it | **Chennai-wide safety net**: alerts if the movie opens anywhere in Chennai even if no named theatre matched |
| No way to know it was alive | **Heartbeat** ping + `--status` command |
| Showtimes didn't lazy-load | `load_page` scrolls; a near-empty page (<500 chars) is treated as unreadable → warning |
| Footer "now showing" links confused the parser | Parser only accepts a block with **real showtimes**, skipping footer carousels |
| Transient network blips dropped alerts | ntfy sends **retry 3×** |

**The guarantee:** every run ends in one of — a theatre opened, the movie opened
somewhere in Chennai, a page was unreadable (you're warned), nothing's open yet,
or a heartbeat. The watcher can never go quiet while something is happening.

The single human safeguard that ties it together is **step 3: always run the
dry-run before arming cron.** That is the pre-flight check that catches a wrong
URL or a page that won't load.

---

## Caffeinate agent (recreate if missing)

Create `~/Library/LaunchAgents/com.srihari.caffeinate.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.srihari.caffeinate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-i</string>
        <string>-m</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/Users/srihari/Desktop/Book MY/caffeinate.log</string>
    <key>StandardErrorPath</key><string>/Users/srihari/Desktop/Book MY/caffeinate.log</string>
</dict>
</plist>
```

Then `launchctl load ~/Library/LaunchAgents/com.srihari.caffeinate.plist`.
`-i` prevents idle sleep (battery + AC); `KeepAlive` restarts it if it dies.

---

## Changing your preferred theatres

Edit `defaults.preferred_theatres` in `config.json` (each entry needs `name`,
`slug`, `code`, `movie_page_keyword`), then re-run `setup_movie.py`. Find a
theatre's `code` from its BMS cinema URL:
`https://in.bookmyshow.com/cinemas/chennai/<slug>/buytickets/<CODE>/<date>`.

Current preferred theatres:

| Theatre | slug | code |
|---------|------|------|
| PVR: VR Chennai, Anna Nagar | pvr-vr-chennai-anna-nagar | PCAN |
| PVR: Aerohub, Chennai | pvr-aerohub-chennai | PABC |
| INOX: LUXE Phoenix Market City, Velachery | inox-luxe-phoenix-market-city-velachery | INPR |
| PVR: Palazzo, The Nexus Vijaya Mall | pvr-palazzo-the-nexus-vijaya-mall | PVPZ |
| PVR: Sathyam, Royapettah | pvr-sathyam-royapettah | PVSR |
