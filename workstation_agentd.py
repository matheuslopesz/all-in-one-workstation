#!/usr/bin/env python3
"""Background worker (systemd user service): runs queued agent jobs one at a time, in their worktrees."""
import json
import os
import signal
import subprocess
import sys
import threading
import time

import workstation_runs as runs
from workstation_agent import find_claude
from workstation_store import TaskStore

LIB = os.path.dirname(os.path.realpath(__file__))
HOOK = os.path.join(LIB, "workstation_hook.py")
POLL_SECONDS = 2
MAX_PARALLEL = 1
TOOLS = "Read,Grep,Glob,Edit,Write,MultiEdit,NotebookEdit,Bash,TodoWrite"
current = {"proc": None, "run": None}


def hook_settings():
    hook = {"type": "command", "command": f"python3 {HOOK}", "timeout": (runs.APPROVAL_MINUTES + 2) * 60,
            "onFailure": "block"}
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}})


def build_command(claude, run):
    paths = [w["path"] for w in run["workspace"]]
    command = [claude, "-p", "--model", runs.RUN_MODEL, "--output-format", "stream-json", "--verbose",
               "--permission-mode", "acceptEdits", "--allowedTools", TOOLS,
               "--disallowedTools", "WebSearch,WebFetch", "--settings", hook_settings()]
    for extra in paths[1:]:
        command += ["--add-dir", extra]
    return command, paths[0]


def pump(stream, log, result):
    for line in stream:
        log.write(line)
        log.flush()
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            result.update(event)


def stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def note_on_task(run, text):
    try:
        store = TaskStore()
        task = store.find_task(run["task_id"])
        if task:
            store.add_note(task, text, author="claude")
    except Exception:  # noqa: BLE001
        pass


def execute(run):
    claude = find_claude()
    missing = [w["path"] for w in run["workspace"] if not os.path.isdir(w["path"])]
    if not claude or missing:
        runs.update(run["id"], status="failed", finished=runs.now(),
                    error="claude CLI not found" if not claude else f"worktree missing: {missing[0]}")
        return
    command, cwd = build_command(claude, run)
    env = {**os.environ, "WORKSTATION_RUN_ID": run["id"]}
    with open(runs.log_path(run["id"]), "a") as log:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True)
        current.update(proc=proc, run=run["id"])
        proc.stdin.write(run["prompt"])
        proc.stdin.close()
        runs.update(run["id"], status="running", started=runs.now(), pid=proc.pid)
        result = {}
        reader = threading.Thread(target=pump, args=(proc.stdout, log, result), daemon=True)
        reader.start()
        budget = runs.RUN_MINUTES * 60
        outcome = None
        while proc.poll() is None:
            time.sleep(POLL_SECONDS)
            state = runs.get(run["id"]) or {}
            if state.get("status") == "cancelled":
                outcome = "cancelled"
                stop(proc)
            elif state.get("status") == "running":
                budget -= POLL_SECONDS
                if budget <= 0:
                    outcome = "timeout"
                    stop(proc)
        reader.join(timeout=10)
        current.update(proc=None, run=None)
    finish(run, outcome, result, proc.returncode)


def finish(run, outcome, result, code):
    summary = (result.get("result") or "").strip()
    fields = {"finished": runs.now(), "pid": None, "cost": result.get("total_cost_usd"),
              "session_id": result.get("session_id"), "summary": summary[:6000] or None, "approval": None}
    if outcome == "cancelled":
        fields["status"] = "cancelled"
    elif outcome == "timeout":
        fields.update(status="failed", error=f"stopped after {runs.RUN_MINUTES} minutes")
    elif result.get("is_error") or not result:
        fields.update(status="failed", error=summary[:500] or f"claude exited with code {code}")
    else:
        fields["status"] = "review"
    runs.update(run["id"], **fields)
    label = runs.STATUS_LABELS[fields["status"]]
    cost = f" · ${fields['cost']:.2f}" if isinstance(fields["cost"], (int, float)) else ""
    note_on_task(run, f"Run {run['id']} → {label}{cost}\n{(summary or fields.get('error') or '')[:800]}")


def recover():
    for run in runs.read_runs():
        if run["status"] in runs.ACTIVE:
            runs.update(run["id"], status="failed", finished=runs.now(), pid=None,
                        error="agentd restarted while this run was active")


def on_signal(_signum, _frame):
    if current["proc"]:
        stop(current["proc"])
        runs.update(current["run"], status="failed", finished=runs.now(), pid=None, error="agentd was stopped")
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    recover()
    while True:
        all_runs = runs.read_runs()
        active = [r for r in all_runs if r["status"] in runs.ACTIVE]
        queued = [r for r in all_runs if r["status"] == "queued"]
        if queued and len(active) < MAX_PARALLEL:
            try:
                execute(queued[0])
            except Exception as error:  # noqa: BLE001
                runs.update(queued[0]["id"], status="failed", finished=runs.now(), error=f"agentd error: {error}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
