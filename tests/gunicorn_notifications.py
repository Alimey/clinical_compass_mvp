"""Default Render-style command starts the background notification scheduler."""

import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "app.db"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "PORT": str(port),
        "COMPASS_DB": str(database),
        "COMPASS_TELEGRAM_BOT_TOKEN": "",
        "COMPASS_AI_API_KEY": "",
    }
    env.pop("COMPASS_DISABLE_WORKER", None)
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            [str(ROOT / ".venv/bin/gunicorn"), "app:create_app()"],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=output,
        )
        try:
            for _ in range(150):
                if process.poll() is not None:
                    output.seek(0)
                    raise RuntimeError(output.read().decode())
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=1
                    ).close()
                    with sqlite3.connect(database) as con:
                        if con.execute(
                            "SELECT 1 FROM service_state WHERE key='worker_heartbeat'"
                        ).fetchone():
                            break
                except (OSError, sqlite3.OperationalError):
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Notification scheduler did not start")
            print(
                "PASS: gunicorn factory command loads default config, binds PORT and runs the notification scheduler"
            )
        finally:
            process.terminate()
            process.wait(timeout=15)
