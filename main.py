"""Company Store Kiosk — launcher.

Starts Flask in a background thread, waits for it to accept connections, then
opens the pywebview window pointed at it. One process, so systemd has exactly
one thing to restart.
"""
import socket
import threading
import time

import webview

import database
from admin_server import app

HOST = '0.0.0.0'          # so managers can reach the admin panel from the LAN
KIOSK_HOST = '127.0.0.1'  # the window itself always loads locally
PORT = 5000
STARTUP_TIMEOUT = 20.0


def start_flask():
    # Bound to 0.0.0.0 so a manager's laptop or phone on the same network can
    # reach the admin panel. Set STORE_ADMIN_PASSWORD and
    # STORE_ADMIN_SECRET_KEY before fielding — this port is open to the LAN.
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def wait_for_server(host, port, timeout=STARTUP_TIMEOUT):
    """Block until the server accepts a connection. True if it came up.

    This replaces a fixed sleep, which was a race rather than a synchronization
    primitive: whatever constant you pick is simultaneously too long on a warm
    boot and too short on a cold one, and when it is too short the window opens
    on a socket nothing is listening to.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.25)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.05)
    return False


if __name__ == '__main__':
    database.init_db()

    threading.Thread(target=start_flask, daemon=True).start()

    if not wait_for_server(KIOSK_HOST, PORT):
        # Open the window regardless: the on-screen error is the only signal
        # anyone standing at the kiosk will get, and journalctl carries this
        # line for whoever is debugging it.
        print(f'WARNING: Flask did not accept connections within '
              f'{STARTUP_TIMEOUT:.0f}s — the kiosk window may fail to load.')

    webview.create_window(
        title='Company Store Kiosk',
        url=f'http://{KIOSK_HOST}:{PORT}/kiosk',
        width=1024,
        height=600,
        resizable=False,
        min_size=(1024, 600),
        background_color='#04060F',
        # Ships fullscreen so a fresh clone is deployment-ready and the Pi
        # never carries local edits to a tracked file. Set False temporarily
        # to run windowed while developing on a desktop.
        fullscreen=True,
    )
    webview.start(debug=False)
