#!/usr/bin/env python3
"""PreToolUse hook for agent runs: blocks what is reserved for Matheus and pauses staging writes for approval."""
import json
import os
import re
import sys
import time

import workstation_runs as runs

KUBECTL_WRITE = (r"\bkubectl\s+(?:-{1,2}[\w-]+(?:[ =][^-\s]\S*)?\s+)*"
                 r"(apply|delete|edit|patch|replace|scale|rollout|drain|cordon|uncordon|create|set|label|annotate|cp)\b")
BLOCKED = [
    (r"\bgit\s+push\b", "git push is reserved for Matheus; commit locally and stop"),
    (r"\bgh\s+pr\s+(create|merge|close|edit|ready|review)\b", "opening or merging PRs is reserved for Matheus"),
    (r"\bgh\s+(release|workflow\s+run|repo\s+(create|delete|edit))\b", "GitHub writes are reserved for Matheus"),
    (r"\bgh\s+api\b.*(-X|--method)\s*(POST|PUT|PATCH|DELETE)", "GitHub API writes are reserved for Matheus"),
    (KUBECTL_WRITE, "changing Kubernetes resources is blocked for agents"),
    (r"\batlantis\s+apply\b", "atlantis apply is reserved for Matheus"),
    (r"\bterraform\s+(apply|destroy|import|state\s+(rm|mv|push))\b", "terraform writes are reserved for Matheus"),
    (r"\bhelm\s+(install|upgrade|uninstall|delete|rollback)\b", "helm writes are reserved for Matheus"),
    (r"(^|[;&|(]\s*)sudo\b", "sudo is blocked for agents"),
    (r"\brm\s+-\w*r\w*\s+(/|~|\$HOME)(\s|/?$)", "removing your home or the root folder is blocked"),
    (r"\b(kubectl|gcloud|curl|rails|psql|mysql|redis-cli)\b.*(\bprod\b|\bproduction\b|\bprd\b)", "production is off limits"),
    (r"https?://(?![^\s/]*staging)[^\s/]*rdops\.systems", "only staging hosts are allowed"),
]
WRITE_VERBS = (r"\.(create|update|save|destroy|delete|insert|upsert|update_all|delete_all|destroy_all|update_column"
               r"|update_columns|increment|decrement|toggle|touch)\w*\b|\bperform_\w+|\.publish\b|\.deliver\w*\b|\.\w+!")
APPROVAL = [
    (lambda c: re.search(r"\b(bin/)?rails\s+(runner|r)\b", c) and re.search(WRITE_VERBS, c),
     "rails runner that writes data"),
    (lambda c: re.search(r"\bcurl\b", c) and re.search(r"staging\.rdops\.systems", c) and re.search(
        r"(-X|--request)\s*(POST|PUT|PATCH|DELETE)|\s(-d|--data[\w-]*|--json|-F|--form)\s", c),
     "write request to staging"),
    (lambda c: re.search(r"\bgh\s+pr\s+comment\b.*atlantis\s+plan", c), "atlantis plan comment on a PR"),
    (lambda c: re.search(r"\bgcloud\b.*\b(create|delete|update|deploy|set|patch|import|add-iam-policy-binding)\b", c),
     "gcloud write"),
]


def classify(command):
    for pattern, reason in BLOCKED:
        if re.search(pattern, command, re.IGNORECASE):
            return "deny", reason
    for test, reason in APPROVAL:
        if test(command):
            return "approve", reason
    return None, None


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def wait_for_answer(run_id, approval_id):
    deadline = time.time() + runs.APPROVAL_MINUTES * 60
    while time.time() < deadline:
        answer = runs.approval_answer(run_id, approval_id)
        if answer:
            return answer
        time.sleep(2)
    return None


def main():
    event = json.load(sys.stdin)
    run_id = os.environ.get("WORKSTATION_RUN_ID")
    command = (event.get("tool_input") or {}).get("command", "")
    if event.get("tool_name") != "Bash" or not run_id or not command:
        return
    verdict, reason = classify(command)
    if verdict == "deny":
        decide("deny", f"Blocked by the workstation: {reason}.")
    elif verdict == "approve":
        approval_id = runs.request_approval(run_id, command, reason)
        answer = wait_for_answer(run_id, approval_id)
        runs.clear_approval(run_id)
        if answer == "allow":
            decide("allow", f"Matheus approved this {reason}.")
        else:
            decide("deny", f"Matheus {'denied' if answer else 'did not answer'} this {reason}; "
                           "do not retry it, note it with the task CLI and continue or finish.")


if __name__ == "__main__":
    main()
