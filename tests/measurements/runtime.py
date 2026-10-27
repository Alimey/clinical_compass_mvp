"""Local test servers; Windows uses Waitress, Linux/macOS use Gunicorn."""

import os
from pathlib import Path
import platform
import signal
import subprocess
import sys


def python_path(root):
    candidate = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    return str(candidate if candidate.exists() else Path(sys.executable))


def server_kind():
    kind = os.environ.get(
        "COMPASS_TEST_SERVER", "waitress" if os.name == "nt" else "gunicorn"
    )
    if kind not in {"waitress", "gunicorn"}:
        raise ValueError("COMPASS_TEST_SERVER must be waitress or gunicorn")
    if kind == "gunicorn" and os.name == "nt":
        raise ValueError("Gunicorn does not run on Windows; use Waitress")
    return kind


def server_command(root, port):
    if server_kind() == "waitress":
        return [
            python_path(root),
            "-X",
            "utf8",
            "-m",
            "waitress",
            "--listen=127.0.0.1:" + str(port),
            "--threads=4",
            "--call",
            "app:create_app",
        ]
    return [
        python_path(root),
        "-X",
        "utf8",
        "-m",
        "gunicorn",
        "--bind",
        f"127.0.0.1:{port}",
        "--workers",
        "1",
        "--threads",
        "4",
        "app:create_app()",
    ]


def server_label():
    return (
        "Waitress" if server_kind() == "waitress" else "Gunicorn"
    ) + "; 1 process / 4 threads"


def stop_server(process, *, force=False):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Waitress runs inside this Python process and has no worker children.
        process.kill() if force else process.terminate()
    else:
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def revision(root):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "working-copy-without-git"


def system_info():
    def read_optional(path):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "cpu_max": read_optional("/sys/fs/cgroup/cpu.max"),
        "memory_max": read_optional("/sys/fs/cgroup/memory.max"),
    }
