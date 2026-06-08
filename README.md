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
- **Suggestion box** — customers can submit product requests
- **Shutter transition** — smooth venetian-blind animation between all screens

### Admin Panel (Browser-Based)
- **📦 Inventory** — add, update, delete items and categories; post announcements to kiosk; update Venmo username anytime
- **💬 Suggestions** — view all customer-submitted feedback
- **📊 Analytics** — revenue, expenses, net profit, margin, avg order value, top-selling items chart, revenue by category, 7-day sales bar chart, low-stock alerts, full expense log
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
| **Display** | 10–15" HDMI touchscreen (1280×800+) | Official Raspberry Pi 7" DSI touchscreen |
| **Storage** | 32 GB microSD (Class 10 / A1) | 16 GB microSD |
| **Power** | Official 5V 3A USB-C PSU | Any 5V 3A supply |
| **Network** | Wi-Fi or Ethernet (for admin panel access from separate device) | Optional |

> The kiosk runs fully offline once booted. Network is only needed so managers can reach the admin panel from a laptop or phone on the same Wi-Fi.

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

---

## Raspberry Pi Deployment

### Enable fullscreen

In `main.py`, change:
```python
fullscreen=False,   # development
```
to:
```python
fullscreen=True,    # Pi production
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

### Accessing the admin panel

While the kiosk is running, open any browser on the same network and go to:

```
http://<pi-ip-address>:5000/
```

Find the Pi's IP with `hostname -I`

---

## Environment Variables

| Variable | Default (dev only) | Description |
|----------|--------------------|-------------|
| `STORE_ADMIN_USERNAME` | `b1_admin` | Admin panel login username |
| `STORE_ADMIN_PASSWORD` | — | Admin panel login password — **set before fielding** |
| `STORE_ADMIN_SECRET_KEY` | `change-this-before-fielding` | Flask session secret — generate with `secrets.token_hex(32)` |
| `VENMO_USERNAME` | `YourVenmoHere` | Venmo handle used in checkout QR codes — can also be updated live via **Admin → Inventory → Venmo Checkout Settings** |

---

## Admin Panel Overview

| Tab | What you can do |
|-----|----------------|
| **📦 Inventory** | Add / update / delete items and categories; post announcements to kiosk ticker; update Venmo username |
| **💬 Suggestions** | Read product suggestions submitted from the kiosk |
| **📊 Analytics** | Revenue, expenses, profit, top items, category revenue, 7-day chart, low-stock alerts, expense log |
| **📈 Sales** | Log restock dates; click any period to see every item sold and total revenue for that cycle |

The admin page updates **live every 8 seconds**. A green **🛒 New Sale** toast appears in the top-right corner on every checkout. A `● LIVE` indicator in the navbar turns red if the server is unreachable.

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

---

## Security Notes

- Set all three environment variables (`USERNAME`, `PASSWORD`, `SECRET_KEY`) **before** fielding on the Pi — the defaults are intentionally weak placeholders
- Use a strong, unique admin password — the panel is reachable by anyone on the same Wi-Fi
- Back up `store.db` regularly once the store goes live: `cp store.db store.db.bak`
- The kiosk window has no browser chrome or address bar — customers cannot navigate away from the kiosk

---

## License

Internal use — Bravo Company, First Regiment. Not for public distribution.
