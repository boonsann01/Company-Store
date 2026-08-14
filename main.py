"""
Company Store Kiosk — launcher
Starts Flask in a background thread, then opens a pywebview window.
Single process: if it crashes, systemd restarts one thing.
"""
import threading
import time
import webview
import database
from admin_server import app

def start_flask():
    # 0.0.0.0 so managers can reach the admin panel from a laptop/phone on the
    # same network. The kiosk window itself still loads via 127.0.0.1 below.
    # Set STORE_ADMIN_PASSWORD before fielding — this port is open to the LAN.
    app.run(host='0.0.0.0', port=5000, debug=False,
            use_reloader=False, threaded=True)

if __name__ == '__main__':
    database.init_db()

    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    time.sleep(0.9)          # wait for Flask to bind

    webview.create_window(
        title='Company Store Kiosk',
        url='http://127.0.0.1:5000/kiosk',
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
