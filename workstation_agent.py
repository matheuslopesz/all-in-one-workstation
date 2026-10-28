import json
import os
import shutil
import subprocess

from workstation_store import claude_prompt, jira_key

JIRA_SCRIPT = os.path.expanduser("~/.claude/skills/jira-daily-report/scripts/jira.sh")
CLAUDE_FALLBACKS = ["~/.local/bin/claude", "~/.claude/local/claude", "~/.npm-global/bin/claude"]
PLAN_MODEL = "sonnet"
PLAN_TIMEOUT = 900
PLAN_INSTRUCTIONS = """Você é um agente de planejamento SOMENTE LEITURA. Não altere nada: só leia o código com Read, Grep e Glob.

Sua tarefa: estudar o repositório atual e propor a quebra da tarefa abaixo em sub-tarefas pequenas e concretas,
na ordem em que devem ser feitas. Considere as sub-tarefas que já existem (não repita as que já estão no plano)
e o ticket do Jira, quando houver.

Responda APENAS com um objeto JSON, sem texto antes ou depois, neste formato:
{"subtasks": [{"title": "verbo no infinitivo + o quê, até 80 caracteres", "description": "1 ou 2 frases: onde mexer e como saber que terminou"}],
 "context": "arquivos e trechos relevantes que você encontrou, riscos e dúvidas, em até 8 linhas"}

Entre 3 e 8 sub-tarefas. Escreva em português."""


class PlanError(Exception):
    pass


def find_claude():
    found = shutil.which("claude")
    if found:
        return found
    return next((os.path.expanduser(p) for p in CLAUDE_FALLBACKS if os.access(os.path.expanduser(p), os.X_OK)), None)


def jira_text(key):
    if not key or not os.access(JIRA_SCRIPT, os.X_OK):
        return ""
    try:
        result = subprocess.run([JIRA_SCRIPT, "describe", key], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def plan_prompt(store, task):
    parts = [PLAN_INSTRUCTIONS, "", claude_prompt(store, task)]
    ticket = jira_text(jira_key(task))
    if ticket:
        parts += ["", "<jira>", ticket, "</jira>"]
    return "\n".join(parts)


def parse_plan(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise PlanError("The agent did not answer with a plan")
    try:
        plan = json.loads(text[start:end + 1])
    except ValueError as error:
        raise PlanError("The agent's plan was not valid JSON") from error
    subtasks = [{"title": str(s.get("title", "")).strip()[:200], "description": str(s.get("description", "")).strip()}
                for s in plan.get("subtasks", []) if isinstance(s, dict) and str(s.get("title", "")).strip()]
    if not subtasks:
        raise PlanError("The agent did not suggest any sub-task")
    return subtasks, str(plan.get("context", "")).strip()


def run_plan(prompt, repo):
    claude = find_claude()
    if not claude:
        raise PlanError("Claude Code CLI not found (claude)")
    if not os.path.isdir(repo):
        raise PlanError(f"Repo folder not found: {repo}")
    command = [claude, "-p", "--model", PLAN_MODEL, "--output-format", "json",
               "--allowedTools", "Read,Grep,Glob", "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch"]
    try:
        result = subprocess.run(command, input=prompt, cwd=repo, capture_output=True, text=True, timeout=PLAN_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise PlanError(f"The agent took more than {PLAN_TIMEOUT // 60} minutes") from error
    try:
        output = json.loads(result.stdout)
    except ValueError as error:
        raise PlanError((result.stderr or result.stdout or "claude exited without output").strip()[:300]) from error
    if output.get("is_error"):
        raise PlanError(str(output.get("result") or output.get("subtype") or "claude reported an error")[:300])
    subtasks, context = parse_plan(output.get("result", ""))
    return {"subtasks": subtasks, "context": context, "cost": output.get("total_cost_usd")}
