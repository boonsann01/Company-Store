# 🏪 Company Store Kiosk

A self-contained touchscreen point-of-sale kiosk for a military unit company store, built with Python (Flask + pywebview). Runs entirely on-device — no internet required at checkout. Soldiers tap through a full-screen menu, review their order, and pay via Venmo QR code. Store managers access a live admin panel from any browser on the same network.

---

## Features

### Kiosk (Customer-Facing)
- **Idle screensaver** — animated glass-bubble ring display after 30 seconds of inactivity
- **Start screen** — tap to wake and begin ordering
- **Menu & cart** — browse items by animated sliding category pills; add/remove with tap; live quantity badges
- **Order confirm** — full itemized summary with large readable cart pills before checkout
- **Venmo QR checkout** — generates a real-time QR code pre-filled with the exact total and item breakdown (e.g. `2x White Monster, 3x Quest Bar`); "Done" button locks for 5 seconds then auto-returns to start after 1 minute of inactivity
- **Shutter transition** — smooth venetian-blind animation between all screens
- **Auto item icons** — every product card picks a matching emoji from its name (ramen, ice cream, energy drinks, snack cakes, jerky…) with per-category fallbacks — no image files to manage
- **Scrolling menu** — the item grid scrolls when a category holds more products than fit on screen; cards always render at full size instead of compressing
- **🔴 Live menu sync** — the kiosk polls every 20 seconds, so stock changes, new items, deletions, and new announcements pushed from the admin panel appear on their own — no refresh, no restart, no touching the kiosk

### Admin Panel (Browser-Based)
- **📦 Inventory** — add, update, delete items and categories; post announcements to kiosk; update Venmo username anytime. Each item records its own restock capacity the first time it is stocked
- **💬 Suggestions** — view all customer-submitted feedback
- **📊 Analytics** — revenue, expenses, net profit, margin, avg order value, top-selling items chart, revenue by category, 7-day sales bar chart, low-stock alerts, full expense log
- **📉 Relative stock bars** — every stock bar is scaled to that item's *own* restock capacity, so a full shelf reads 100% green whether the item restocks at 8 units or 40. Low-stock alerts fire at 25% of capacity instead of a fixed count (items with no recorded capacity fall back to a flat 5 units)
- **📈 Sales** — log restock dates and view exact units sold + revenue per restock cycle
- **🔴 Live updates** — admin page polls every 8 seconds; a green toast notification appears for every new sale and all data updates in real time without a page refresh

---

## Architecture

```
┌──────────────────────────────────────────────┐
│                  main.py                     │
│  Starts Flask in daemon thread → pywebview   │
│  Single process — systemd restarts one thing │
└──────────┬───────────────────────────────────┘
           │
    ┌──────▼──────┐        ┌──────────────────────┐
    │ Flask :5000 │        │   store.db (SQLite)   │
    │admin_server │◄──────►│ inventory             │
    │    .py      │        │ transactions          │
    └──────┬──────┘        │ transaction_items     │
           │               │ announcements         │
    ┌──────▼──────┐        │ suggestions           │
    │  pywebview  │        │ categories            │
    │  Chromium   │        │ expenses              │
    │  /kiosk     │        │ settings              │
    │  (SPA)      │        │ restocks              │
    └─────────────┘        └──────────────────────┘
```

| Layer | Technology |
|-------|-----------|
| Window | pywebview ≥ 5.0 (Chromium/WebKit embedded) |
| Backend | Flask 3.x (daemon thread, no reloader) |
| Database | SQLite 3 via Python stdlib |
| Frontend | Vanilla JS SPA — no framework, no build step |
| QR Codes | `qrcode` library → base64 PNG via API |
| Styling | CSS custom properties, backdrop-filter glass morphism |

---

## Repository Structure

```
Company-Store/
├── main.py                # Entry point — launches Flask + pywebview window
├── admin_server.py        # All Flask routes: kiosk API + full admin panel
├── database.py            # Every SQLite read/write function
├── reset_analytics.py     # One-time script — wipes test sales/expenses before going live
├── requirements.txt       # Python dependencies
├── .gitignore
└── templates/
    ├── kiosk.html         # Full-screen customer-facing kiosk SPA
    └── admin.html         # Admin panel (Bootstrap 5, live-updating)
```

> `store.db` is **not** in the repository — it is created automatically on first run and will contain real transaction data once the store goes live.

---

## Hardware Requirements (Raspberry Pi)

| Component | Recommended | Minimum |
|-----------|-------------|---------|
| **Board** | Raspberry Pi 4 (4 GB RAM) | Raspberry Pi 4 (2 GB RAM) |
| **OS** | Raspberry Pi OS Bookworm 64-bit | Raspberry Pi OS Bullseye 64-bit |
| **Display** | Official Raspberry Pi 7" DSI touchscreen (1024×600) | Any 1024×600 HDMI touchscreen |
| **Storage** | 32 GB microSD (Class 10 / A1) | 16 GB microSD |
| **Power** | Official 5V 3A USB-C PSU | Any 5V 3A supply |
| **Network** | Wi-Fi or Ethernet (for admin panel access from separate device) | Optional |

> The kiosk runs fully offline once booted. Network is only needed so managers can reach the admin panel from a laptop or phone on the same Wi-Fi.

> **Display resolution** — the entire kiosk UI is tuned for **1024×600**, the native resolution of the official Raspberry Pi 7" touchscreen. The pywebview window in `main.py` is fixed at that size. Larger panels still work (the layout is flex/grid based), but 1024×600 is what the type scale, card sizes, and spacing were designed against.

---

## Software Requirements

### Python
Python **3.11** or newer — check with `python3 --version`

### System Packages (Raspberry Pi OS)

pywebview uses GTK + WebKit2GTK on Linux. Install these **before** running `pip install`:

```bash
sudo apt update && sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1 \
    libwebkit2gtk-4.1-dev \
    libgtk-3-dev \
    libgirepository1.0-dev \
    pkg-config \
    at-spi2-core
```

> **Bullseye fallback** — if `webkit2gtk-4.1` is not available on your OS version, substitute `gir1.2-webkit2-4.0` and `libwebkit2gtk-4.0-dev`.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/boonsann01/Company-Store.git
cd Company-Store
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt --break-system-packages
```

> A virtual environment is optional for a dedicated kiosk device. If you prefer one:
> `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

### 3. Set environment variables

> ⚠️ **Required before running on the Pi.** The defaults are for local development only and must not be used in production.

```bash
export STORE_ADMIN_USERNAME="your_admin_username"
export STORE_ADMIN_PASSWORD="your_strong_password"
export STORE_ADMIN_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export VENMO_USERNAME="YourVenmoHandle"
```

### 4. Run

```bash
python3 main.py
```

`store.db` is created automatically on first launch with sample inventory pre-loaded.

### 5. Clear prototype data before going live

After you finish testing and enter the real opening inventory, wipe every test sale and expense so prototype numbers never mix into real store analytics:

```bash
python3 reset_analytics.py
```

The script prints how many transactions, line items, and expenses it is about to delete and waits for you to type `YES` before touching anything. Inventory, categories, announcements, restock history, suggestions, and settings are all left untouched, and transaction IDs restart at 1.

---

## Raspberry Pi Deployment

### Full deployment from GitHub (fresh Pi)

Start-to-finish on a clean Raspberry Pi OS Bookworm install. Run everything in a terminal on the Pi, or over SSH.

**1 — Install system packages**

pywebview needs GTK + WebKit2GTK. These must go in **before** `pip install`:

```bash
sudo apt update && sudo apt install -y git python3-pip python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libwebkit2gtk-4.1-dev libgtk-3-dev libgirepository1.0-dev pkg-config at-spi2-core
```

**2 — Clone the repository**

```bash
cd ~ && git clone https://github.com/boonsann01/Company-Store.git && cd Company-Store
```

**3 — Install Python dependencies**

```bash
pip install -r requirements.txt --break-system-packages
```

**4 — Generate a session secret**

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Copy the output — it becomes `STORE_ADMIN_SECRET_KEY` in step 7.

> ### ⚠️ Both secrets are mandatory before this touches a network
>
> `STORE_ADMIN_PASSWORD` **and** `STORE_ADMIN_SECRET_KEY` must both be set in the systemd unit. The in-code fallbacks for both are public in this repository.
>
> The secret key is the one people underestimate: Flask session cookies are **signed, not encrypted**. If the key is left at its default, anyone on the same Wi-Fi can forge a cookie marking themselves logged in and skip the login form entirely — a strong password does not help. Set both, or the admin panel is effectively open.

**5 — Confirm fullscreen (nothing to change)**

`main.py` already ships `fullscreen=True`, so the clone is deployment-ready as-is. See [Fullscreen](#fullscreen) if you ever need to run windowed while developing.

**6 — First run, and getting your inventory onto the Pi**

```bash
python3 main.py
```

This creates `store.db` with sample inventory. `store.db` is deliberately **not** tracked by git, so your real stock does not arrive with the clone. Two options:

- **Re-enter it** through the admin panel once the Pi is on the network, or
- **Copy your existing database over** — from PowerShell on the Windows machine that has it:

```powershell
scp "C:\Users\nathan.boonsanguan\Documents\company_store_kiosk_copy\store.db" pi@raspberrypi.local:~/Company-Store/store.db
```

Stop the kiosk before overwriting `store.db`, and remember `python3 reset_analytics.py` if that database still holds prototype sales.

**7 — Install the systemd service**

Follow [Autostart with systemd](#autostart-with-systemd) below, filling in the password and the secret key from step 4.

**8 — Verify**

```bash
sudo systemctl status kiosk.service
```

The kiosk should be up fullscreen on the touchscreen. Confirm remote access from a laptop using the section below, then reboot once to prove it comes back on its own.

### Fullscreen

`main.py` ships with `fullscreen=True`, so a fresh clone is deployment-ready with no edits. This also keeps the Pi free of local modifications to tracked files, which means `git pull` stays conflict-free on every future update.

> The window is sized to `1024×600` with `resizable=False`, matching the 7" panel exactly. Fullscreen additionally removes the title bar, so customers cannot close, move, or navigate away from the kiosk.

To run windowed while developing on a desktop, temporarily set `fullscreen=False` in `main.py`. Revert before committing — or discard the change with:

```bash
git checkout -- main.py
```

### Disable screen blanking / sleep

Add to `/etc/xdg/lxsession/LXDE-pi/autostart`:
```
@xset s off
@xset -dpms
@xset s noblank
```

### Touchscreen calibration

For USB or HDMI touchscreens that need calibration:
```bash
sudo apt install -y xinput-calibrator
xinput_calibrator
```

Apply the output values in `/etc/X11/xorg.conf.d/99-calibration.conf`.

The **official Raspberry Pi 7" DSI display** includes touch drivers out of the box — no calibration needed.

To rotate the display if needed, add to `/boot/firmware/config.txt`:
```
display_rotate=1    # 90° clockwise
display_rotate=2    # 180°
display_rotate=3    # 270° clockwise
```

### Autostart with systemd

Create `/etc/systemd/system/kiosk.service`:

```ini
[Unit]
Description=Company Store Kiosk
After=graphical-session.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Company-Store
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/pi/.Xauthority"
Environment="STORE_ADMIN_USERNAME=your_admin_username"
Environment="STORE_ADMIN_PASSWORD=your_strong_password"
Environment="STORE_ADMIN_SECRET_KEY=your_secret_key_here"
Environment="VENMO_USERNAME=YourVenmoHandle"
ExecStart=/usr/bin/python3 /home/pi/Company-Store/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=graphical-session.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kiosk.service
sudo systemctl start kiosk.service
```

View logs:
```bash
journalctl -u kiosk.service -f
```

### Accessing the admin panel from a Windows laptop

The Flask server binds to `0.0.0.0:5000`, so it accepts connections from any device on the same network. The kiosk window itself still loads over `127.0.0.1`, so this changes nothing about how the kiosk behaves.

**1 — Find the Pi's address.** On the Pi:

```bash
hostname -I
```

**2 — Open it in any browser on the laptop.** Both machines must be on the same Wi-Fi:

```
http://192.168.1.42:5000
```

Substitute the address from step 1. You'll land on the login page — sign in with the `STORE_ADMIN_USERNAME` / `STORE_ADMIN_PASSWORD` set in the systemd unit.

**3 — Use the hostname instead (recommended).** Windows 10 and 11 resolve mDNS natively, and Raspberry Pi OS advertises itself over Avahi:

```
http://raspberrypi.local:5000
```

This keeps working when the Pi's IP changes on a new DHCP lease. Substitute your Pi's hostname if you renamed it during imaging.

**4 — Pin the address (optional).** For a permanent kiosk, add a DHCP reservation in the router so the Pi always receives the same IP, then bookmark it on each laptop.

#### Multiple managers

Several people can be signed in at once. Each browser holds its own independent session cookie, so logging in on one laptop never signs anyone else out — they all use the same credentials.

Three managers with the dashboard open, plus the kiosk, is roughly **0.5 requests/second**, which is negligible for a Pi 4. Every dashboard refreshes on its own every 8 seconds, so managers see each other's changes almost immediately.

> One caveat: inventory updates are **last-write-wins**. If two managers edit the same item within a few seconds of each other, the second save silently overwrites the first with no warning. The 8-second refresh makes this unlikely, but the app will not stop it.

#### If the laptop can't connect

| Symptom | Cause and fix |
|---------|---------------|
| `ping raspberrypi.local` fails, but the Pi has internet | **Client isolation** — many institutional, enterprise, and guest networks block device-to-device traffic. No code change fixes this. Use a phone hotspot, a dedicated travel router, or a direct Ethernet cable between laptop and Pi |
| Connection times out | Confirm both devices are on the *same* SSID (not one on a `-Guest` or 5 GHz-only network), and that the service is up: `sudo systemctl status kiosk.service` |
| Connection refused | The service isn't running, or an older build is deployed that still binds `127.0.0.1`. Check `git log --oneline -1` on the Pi and pull if it predates the `0.0.0.0` change |
| Works by IP, not by `.local` | mDNS is blocked or Avahi isn't running: `sudo systemctl status avahi-daemon`. Fall back to the IP with a DHCP reservation |
| Reachable but login fails | `STORE_ADMIN_USERNAME` / `STORE_ADMIN_PASSWORD` in the systemd unit differ from what you're typing. `sudo systemctl show kiosk.service -p Environment` prints what the service actually loaded |

---

## Upgrading an Existing Install

Pull the latest code and restart — schema changes apply themselves:

```bash
cd ~/Company-Store
git pull
sudo systemctl restart kiosk.service
```

`database.init_db()` runs an idempotent migration on every launch. The `inventory` table gained a `max_stock` column that powers the relative stock bars; on the first run after upgrading, every existing item has `max_stock` backfilled to its current stock — so whatever is on the shelf at that moment becomes that item's 100% baseline. Restock to a higher number later and the baseline rises with it automatically.

> Your `store.db` is **not** tracked by git, so `git pull` never overwrites live sales data.

---

## Environment Variables

| Variable | Default (dev only) | Description |
|----------|--------------------|-------------|
| `STORE_ADMIN_USERNAME` | `b1_admin` | Admin panel login username |
| `STORE_ADMIN_PASSWORD` | *(a working password is hardcoded in `admin_server.py` and is public in this repo)* | Admin panel login password — **must be overridden before fielding** |
| `STORE_ADMIN_SECRET_KEY` | `change-this-before-fielding` | Flask session secret — generate with `secrets.token_hex(32)`. **Must be overridden**: cookies are signed with this, so a known key lets anyone forge a logged-in session |
| `VENMO_USERNAME` | `YourVenmoHere` | Venmo handle used in checkout QR codes — can also be updated live via **Admin → Inventory → Venmo Checkout Settings** |

---

## Admin Panel Overview

| Tab | What you can do |
|-----|----------------|
| **📦 Inventory** | Add / update / delete items and categories; post announcements to kiosk ticker; update Venmo username |
| **💬 Suggestions** | Read suggestions collected while the kiosk's suggestion box was live (the box was removed; existing entries are retained) |
| **📊 Analytics** | Revenue, expenses, profit, top items, category revenue, 7-day chart, low-stock alerts, expense log |
| **📈 Sales** | Log restock dates; click any period to see every item sold and total revenue for that cycle |

The admin page updates **live every 8 seconds**. A green **🛒 New Sale** toast appears in the top-right corner on every checkout. A `● LIVE` indicator in the navbar turns red if the server is unreachable.

The **kiosk** pulls the same data every **20 seconds** from `/api/kiosk_poll`. Anything you change in the admin panel — restocking an item, adding a product, deleting one, or posting an announcement — shows up on the kiosk screen within 20 seconds on its own. You never need to walk over and restart it.

---

## Tests

```bash
python tests/run_all.py
```

No dependencies beyond what the kiosk already installs. The suites redirect the
database to a temporary file, so running them never touches `store.db`.

| Suite | Covers |
|-------|--------|
| `tests/test_database.py` | Inventory name uniqueness, server-side sale pricing, whole-number quantities, empty-cart and oversell refusal, concurrent-sale stock accounting, low-stock rule |
| `tests/test_routes.py` | Auth gating, kiosk API, checkout endpoint, error handling, admin panel routes |

Every case corresponds to a defect that actually reached the working tree. If
you change `log_transaction` or the checkout flow, run these first.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No module named 'gi'` | Run the `sudo apt install` system packages block above |
| pywebview window is blank | Ensure `webkit2gtk` is installed and `DISPLAY=:0` is set in the systemd service |
| Touch input not working | Run `xinput list` to verify the device is detected; use `xinput_calibrator` if needed |
| Admin shows `● OFFLINE` badge | Flask server restarted — page reconnects automatically within 8 s |
| Kiosk doesn't auto-start on boot | Check `journalctl -u kiosk.service` — verify `DISPLAY=:0` and `XAUTHORITY` in the unit file |
| `store.db` not found | Run `python3 main.py` once — `database.init_db()` creates it automatically |
| Admin page stuck on old data after restart | Hard-refresh the browser (`Ctrl+Shift+R`) — session cookie may have expired |
| Stock bar shows yellow/red at full capacity | That item's `max_stock` is lower than what is on the shelf. Update the item once in **Admin → Inventory** — `max_stock` rises to match the new stock and the bar reads 100% green |
| Kiosk not showing a new item or announcement | Wait up to 20 s for the next poll. If it still doesn't appear, confirm the kiosk can reach `/api/kiosk_poll` and check `journalctl -u kiosk.service` |

---

## Security Notes

- Set all three environment variables (`USERNAME`, `PASSWORD`, `SECRET_KEY`) **before** fielding on the Pi. These are not placeholders — `admin_server.py` ships a real, working admin password and a fixed session key, both readable by anyone who opens this repository
- **`STORE_ADMIN_SECRET_KEY` matters more than the password.** Flask signs session cookies with it rather than encrypting them. Leave it at the default and an attacker on the same Wi-Fi can mint a cookie that says they're logged in, never touching the login form. Overriding the password alone does not close this
- Use a strong, unique admin password — port 5000 is reachable by anyone on the same Wi-Fi
- Treat any credential previously committed to this repo as compromised — rotate it rather than reusing it elsewhere
- Back up `store.db` regularly once the store goes live: `cp store.db store.db.bak`
- The kiosk window has no browser chrome or address bar — customers cannot navigate away from the kiosk

---

## License

Internal use — Bravo Company, First Regiment. Not for public distribution.
