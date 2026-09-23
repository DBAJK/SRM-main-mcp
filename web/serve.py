"""실험 실행 웹 UI — 옵션을 고르고 눌러서 돌린다.

    .venv310\\Scripts\\python.exe web\\serve.py
    → http://127.0.0.1:8765

`run.py` 를 자식 프로세스로 띄우고 출력을 실시간으로 흘려보낸다. 표준 라이브러리만
쓴다 — 실험 환경에 의존성을 더하지 않기 위해서다.

**127.0.0.1 에만 바인딩한다.** 프로세스를 띄우는 서버이므로 외부에 열지 않는다.
인자는 화이트리스트로만 받는다 — 셸을 거치지 않고 argv 리스트로 넘긴다.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv310" / "Scripts" / "python.exe"
PORT = 8765

# run.py 의 argparse 와 맞춘다. 여기 없는 값은 아예 실행되지 않는다.
CHOICES = {
    "scenario": ["normal", "emergency", "special_event", "iot_surge", "mixed"],
    "driver": ["fixed", "orchestrator"],
    "backend": ["mock", "mcp"],
    "decider": ["rule", "llm"],
    "desc_mode": ["minimal", "advisory"],
    "memory_mode": ["warm", "cold"],
    "llm_model": ["sonnet", "haiku", "opus"],
}
NUMERIC = {"seed", "steps", "max_calls", "step_budget_usd", "llm_timeout"}
FLAGS = {"fresh", "trace", "quiet"}

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


# ── 명령 조립 ──────────────────────────────────────────────────────────
def build_argv(form: dict) -> tuple[list[str], str]:
    """폼 값 → run.py argv. 화이트리스트 밖의 값은 버린다."""
    argv = [str(PYTHON), "run.py"]

    for key, allowed in CHOICES.items():
        v = form.get(key, "")
        if v and v in allowed:
            argv += [f"--{key.replace('_', '-')}", v]

    for key in NUMERIC:
        v = str(form.get(key, "")).strip()
        if v and re.fullmatch(r"-?\d+(\.\d+)?", v):
            argv += [f"--{key.replace('_', '-')}", v]

    for key in FLAGS:
        if form.get(key):
            argv.append(f"--{key}")

    intent = str(form.get("intent", "")).strip()
    if intent:
        argv += ["--intent", intent[:400]]

    arm = str(form.get("arm", "")).strip()
    if arm and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", arm):
        argv += ["--arm", arm]

    run_id = "{}-{}-s{}".format(
        arm or "proposed",
        form.get("scenario", "normal") if form.get("scenario") in CHOICES["scenario"] else "normal",
        form.get("seed", "0") if str(form.get("seed", "0")).isdigit() else "0",
    )
    return argv, run_id


def spawn(argv: list[str], run_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}

    with _lock:
        _jobs[job_id] = {"lines": [], "done": False, "code": None,
                         "argv": argv, "run_id": run_id, "started": time.time()}

    def pump():
        try:
            p = subprocess.Popen(argv, cwd=str(ROOT), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace",
                                 bufsize=1)
        except OSError as e:
            with _lock:
                _jobs[job_id]["lines"].append(f"[실행 실패] {e}")
                _jobs[job_id]["done"] = True
                _jobs[job_id]["code"] = -1
            return

        with _lock:
            _jobs[job_id]["proc"] = p
        for line in p.stdout:
            with _lock:
                _jobs[job_id]["lines"].append(line.rstrip("\n"))
        p.wait()
        with _lock:
            _jobs[job_id]["done"] = True
            _jobs[job_id]["code"] = p.returncode

    threading.Thread(target=pump, daemon=True, name=f"job-{job_id}").start()
    return job_id


def list_runs() -> list[dict]:
    out = []
    runs = ROOT / "runs"
    if not runs.is_dir():
        return out
    for d in sorted(runs.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        out.append({
            "run_id": d.name,
            "mtime": int(d.stat().st_mtime),
            "report": (d / "report.html").is_file(),
            "decisions": (d / "decisions.json").is_file(),
            "referee": (d / "referee.jsonl").is_file(),
        })
    return out[:40]


def score(run_id: str) -> dict:
    """eval.score 를 돌려 채점 결과를 돌려준다."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", run_id):
        return {"error": "bad run_id"}
    r = subprocess.run([str(PYTHON), "-m", "eval.score", run_id],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout or "")[-600:]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": r.stdout[-600:]}


# ── HTTP ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "SliceRunner/1.0"

    def log_message(self, fmt, *args):  # 콘솔을 조용히
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    # ── GET ──
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path in ("/", "/index.html"):
            f = WEB / "index.html"
            if not f.is_file():
                return self._send(500, b"index.html not found", "text/plain")
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")

        if u.path == "/api/runs":
            return self._json(200, {"runs": list_runs()})

        if u.path == "/api/score":
            return self._json(200, score(q.get("run_id", [""])[0]))

        if u.path == "/api/job":
            job_id = q.get("id", [""])[0]
            since = int(q.get("since", ["0"])[0] or 0)
            with _lock:
                j = _jobs.get(job_id)
                if j is None:
                    return self._json(404, {"error": "unknown job"})
                return self._json(200, {
                    "lines": j["lines"][since:], "next": len(j["lines"]),
                    "done": j["done"], "code": j["code"], "run_id": j["run_id"],
                    "elapsed": int(time.time() - j["started"]),
                })

        if u.path == "/report":
            rid = q.get("run_id", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", rid):
                return self._send(400, b"bad run_id", "text/plain")
            f = ROOT / "runs" / rid / "report.html"
            if not f.is_file():
                return self._send(404, "report.html 이 없다 — 먼저 생성한다".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")

        return self._send(404, b"not found", "text/plain")

    # ── POST ──
    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
        try:
            form = json.loads(raw)
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})

        if u.path == "/api/run":
            argv, run_id = build_argv(form)
            job_id = spawn(argv, run_id)
            return self._json(200, {"job": job_id, "run_id": run_id,
                                    "cmd": " ".join(argv[1:])})

        if u.path == "/api/stop":
            with _lock:
                j = _jobs.get(form.get("job", ""))
                p = j.get("proc") if j else None
            if p and p.poll() is None:
                p.terminate()
                return self._json(200, {"stopped": True})
            return self._json(200, {"stopped": False})

        if u.path == "/api/report":
            rid = form.get("run_id", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", rid or ""):
                return self._json(400, {"error": "bad run_id"})
            r = subprocess.run([str(PYTHON), "-m", "eval.report", rid],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                               timeout=180)
            ok = (ROOT / "runs" / rid / "report.html").is_file()
            return self._json(200, {"ok": ok,
                                    "out": (r.stdout or r.stderr or "")[-600:]})

        return self._json(404, {"error": "not found"})


def main() -> int:
    if not PYTHON.is_file():
        print(f"[오류] {PYTHON} 가 없다. .venv310 을 먼저 만든다.", file=sys.stderr)
        return 1
    if not (WEB / "index.html").is_file():
        print(f"[오류] {WEB / 'index.html'} 가 없다.", file=sys.stderr)
        return 1

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  실험 실행 UI   http://127.0.0.1:{PORT}")
    print(f"  파이썬         {PYTHON}")
    print(f"  작업 디렉터리   {ROOT}")
    print("  Ctrl+C 로 종료")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
