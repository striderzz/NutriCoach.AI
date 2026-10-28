"""
NutriCoach.AI desktop launcher: serves the Flask app on a free local port and
opens it in a chromeless Edge/Chrome app window. Closing the window quits.
"""
import shutil
import socket
import subprocess
import threading
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from app import app

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_browser():
    return next((p for p in BROWSERS if Path(p).exists()), None) or shutil.which("msedge")


def main():
    port = free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"

    browser = find_browser()
    if browser:
        # A dedicated profile makes the app window its own process, so wait() returns on close
        profile = Path.home() / ".nutricoach" / "window-profile"
        subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={profile}",
                          "--window-size=1440,920", "--no-first-run"]).wait()
    else:
        webbrowser.open(url)
        threading.Event().wait()
    server.shutdown()


if __name__ == "__main__":
    main()
