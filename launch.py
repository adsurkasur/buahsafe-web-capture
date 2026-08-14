from __future__ import annotations

import threading
import webbrowser
import socket

from app import app


def open_dashboard() -> None:
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    # Jika dashboard sudah berjalan, cukup buka instance yang ada. Ini mencegah
    # dua proses Flask berebut port web atau port serial ESP32.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", 5000)) == 0:
            open_dashboard()
            raise SystemExit(0)

    threading.Timer(1.0, open_dashboard).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
