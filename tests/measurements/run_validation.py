"""Functional checks; run separately from latency and load measurements."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(os.environ.get("COMPASS_REPO", Path(__file__).resolve().parents[2]))
OUT = Path(os.environ.get("COMPASS_METRICS_OUT", ROOT / "test-results" / "metrics"))
OUT.mkdir(parents=True, exist_ok=True)
env = {
    **os.environ,
    "COMPASS_AI_API_KEY": "",
    "COMPASS_AI_BASE_URL": "",
    "COMPASS_AI_MODEL": "",
    "COMPASS_TELEGRAM_BOT_TOKEN": "",
    "COMPASS_PUBLIC_URL": "",
    "COMPASS_DISABLE_WORKER": "1",
    "COMPASS_SECURE_COOKIES": "0",
}
jobs = [
    (
        "server_tests",
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
    )
]
jobs += [
    (p.stem, ["python", str(p)]) for p in sorted((ROOT / "tests").glob("browser_*.py"))
]
jobs += [("gunicorn_notifications", ["python", "tests/gunicorn_notifications.py"])]
jobs += [
    ("syntax_" + p.stem, ["node", "--check", str(p)])
    for p in sorted((ROOT / "static").glob("*.js"))
]
result = {
    "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "concurrency": 1,
    "test_correction": "browser_smoke expected medication schedule text updated from ДЕМО-Альфа to existing UI Авиандр 20 мг; application behavior unchanged",
    "results": [],
}
for name, command in jobs:
    scratch = Path(tempfile.mkdtemp(prefix="cc-val-", dir="/tmp"))
    folder = OUT / "validation" / name
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with (folder / "output.log").open("w") as log:
        try:
            done = subprocess.run(
                command,
                cwd=ROOT,
                env={**env, "TMPDIR": str(scratch)},
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=240,
            )
            status = done.returncode
        except subprocess.TimeoutExpired:
            status = -1
    if (scratch / "compass-artifacts").exists():
        shutil.copytree(
            scratch / "compass-artifacts", folder / "screenshots", dirs_exist_ok=True
        )
    shutil.rmtree(scratch, ignore_errors=True)
    row = {
        "name": name,
        "exit_code": status,
        "seconds": round(time.perf_counter() - start, 3),
    }
    result["results"].append(row)
    (OUT / "validation-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(("PASS" if status == 0 else "FAIL"), name, row["seconds"], flush=True)
result["finished_at"] = datetime.now(timezone.utc).isoformat()
(OUT / "validation-results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2)
)
assert all(r["exit_code"] == 0 for r in result["results"]), result["results"]
