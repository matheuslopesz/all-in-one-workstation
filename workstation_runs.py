import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime

STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                         "all-in-one-workstation")
RUNS_FILE = os.path.join(STATE_DIR, "runs.json")
LOGS_DIR = os.path.join(STATE_DIR, "runs")
LOCK_FILE = RUNS_FILE + ".lock"
ACTIVE = ("running", "needs_input")
STATUSES = ["queued", "running", "needs_input", "review", "done", "failed", "cancelled"]
STATUS_LABELS = {"queued": "⏳ Queued", "running": "🤖 Running", "needs_input": "✋ Needs you", "review": "👀 Review",
                 "done": "✅ Done", "failed": "⚠️ Failed", "cancelled": "🚫 Cancelled"}
RUN_MODEL = "sonnet"
RUN_MINUTES = 45
APPROVAL_MINUTES = 28


def now():
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def locked():
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read_runs():
    try:
        with open(RUNS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def write_runs(runs):
    tmp = RUNS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(runs, f, indent=2)
    os.replace(tmp, RUNS_FILE)


def update(run_id, **fields):
    with locked():
        runs = read_runs()
        run = next((r for r in runs if r["id"] == run_id), None)
        if run is None:
            return None
        run.update(fields)
        write_runs(runs)
        return run


def get(run_id):
    return next((r for r in read_runs() if r["id"] == run_id), None)


def log_path(run_id):
    return os.path.join(LOGS_DIR, f"{run_id}.jsonl")


def create(task, key, workspace, prompt):
    run = {"id": uuid.uuid4().hex[:12], "task_id": task["id"], "task_title": task["title"], "key": key,
           "status": "queued", "created": now(), "started": None, "finished": None, "workspace": workspace,
           "prompt": prompt, "cost": None, "session_id": None, "approval": None, "summary": None, "error": None,
           "pid": None}
    with locked():
        runs = read_runs()
        runs.append(run)
        write_runs(runs)
    return run


def latest_for_task(task_id):
    runs = [r for r in read_runs() if r["task_id"] == task_id]
    return runs[-1] if runs else None


def request_approval(run_id, command, reason):
    approval = {"id": uuid.uuid4().hex[:8], "command": command, "reason": reason, "asked_at": now(), "answer": None}
    update(run_id, status="needs_input", approval=approval)
    return approval["id"]


def answer_approval(run_id, approval_id, allow):
    with locked():
        runs = read_runs()
        run = next((r for r in runs if r["id"] == run_id), None)
        if run and run.get("approval") and run["approval"]["id"] == approval_id:
            run["approval"]["answer"] = "allow" if allow else "deny"
            write_runs(runs)


def approval_answer(run_id, approval_id):
    run = get(run_id)
    approval = (run or {}).get("approval") or {}
    if run is None or run["status"] == "cancelled":
        return "deny"
    return approval.get("answer") if approval.get("id") == approval_id else "deny"


def clear_approval(run_id):
    with locked():
        runs = read_runs()
        run = next((r for r in runs if r["id"] == run_id), None)
        if run and run["status"] == "needs_input":
            run["status"] = "running"
            write_runs(runs)
