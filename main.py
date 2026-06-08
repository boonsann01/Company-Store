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
    app.run(host='127.0.0.1', port=5000, debug=False,
            use_reloader=False, threaded=True)

if __name__ == '__main__':
    database.init_db()

    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    time.sleep(0.9)          # wait for Flask to bind

    webview.create_window(
        title='Company Store Kiosk',
        url='http://127.0.0.1:5000/kiosk',
        width=1280,
        height=800,
        resizable=False,
        min_size=(1280, 800),
        background_color='#04060F',
        # Set fullscreen=True when deploying on the Pi
        fullscreen=False,
    )
    webview.start(debug=False)
