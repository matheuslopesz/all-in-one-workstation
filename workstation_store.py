import copy
import fcntl
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import date, datetime

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "all-in-one-workstation")
TASKS_FILE = os.path.join(CONFIG_DIR, "tasks.json")
LOCK_FILE = TASKS_FILE + ".lock"
PROJECTS_DIR = os.path.expanduser("~/Área de trabalho/projetos")
JIRA_BROWSE = "https://rdstation.atlassian.net/browse/"
JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
INBOX = "inbox"
PROJECT_COLORS = ["#db4035", "#ff9933", "#fad000", "#7ecc49", "#299438",
                  "#14aaf5", "#4073ff", "#884dff", "#e05194", "#808080"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CLI = "all-in-one-workstation task"
MISSING = object()


def due_of(task):
    return date.fromisoformat(task["due"]) if task["due"] else None


def short_date(d):
    text = f"{d.day} {MONTH_NAMES[d.month - 1]}"
    return text if d.year == date.today().year else f"{text} {d.year}"


def day_heading(d):
    text = f"{d.day} {MONTH_NAMES[d.month - 1]} · {DAY_NAMES[d.weekday()]}"
    delta = (d - date.today()).days
    if delta == 0:
        return f"{text} · Today"
    if delta == 1:
        return f"{text} · Tomorrow"
    return text


def short_id(task):
    return task["id"][:8]


def jira_key(task):
    match = JIRA_KEY.search(task["title"]) or JIRA_KEY.search(task["description"] or "")
    return match.group(0) if match else None


def is_repo(path):
    return os.path.exists(os.path.join(path, ".git"))


def child_dirs(path):
    try:
        names = sorted(os.listdir(path), key=str.lower)
    except OSError:
        return []
    return [os.path.join(path, n) for n in names
            if not n.startswith(".") and n != "node_modules" and os.path.isdir(os.path.join(path, n))]


def list_repos():
    repos = []
    for path in child_dirs(PROJECTS_DIR):
        if is_repo(path):
            repos.append(path)
        else:
            repos.extend(child for child in child_dirs(path) if is_repo(child))
    return repos


def read_tasks_file():
    try:
        with open(TASKS_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    for task in data.get("tasks", []):
        if not isinstance(task["priority"], bool):
            task["priority"] = task["priority"] == 1
    return data


def write_tasks_file(data):
    tmp = TASKS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, TASKS_FILE)


@contextmanager
def locked():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def merge_record(ours, base, theirs):
    for key in set(ours) | set(theirs):
        mine, old = ours.get(key, MISSING), base.get(key, MISSING)
        if key == "notes" and mine is not MISSING and key in theirs:
            seen = theirs[key] + ([] if old is MISSING else old)
            ours[key] = [*theirs[key], *(n for n in mine if n not in seen)]
            continue
        value = theirs.get(key, MISSING) if mine == old else mine
        if value is MISSING:
            ours.pop(key, None)
        else:
            ours[key] = value


def merge_list(ours, base, theirs):
    base_by = {item["id"]: item for item in base}
    theirs_by = {item["id"]: item for item in theirs}
    kept = []
    for item in ours:
        if item["id"] in base_by:
            if item["id"] not in theirs_by:
                continue
            merge_record(item, base_by[item["id"]], theirs_by[item["id"]])
        kept.append(item)
    known = {item["id"] for item in ours}
    kept += [copy.deepcopy(item) for item in theirs if item["id"] not in base_by and item["id"] not in known]
    ours[:] = kept


def merge_data(ours, base, theirs):
    for key in set(ours) | set(theirs):
        if key in ("tasks", "projects"):
            merge_list(ours.setdefault(key, []), base.get(key, []), theirs.get(key, []))
        elif ours.get(key, MISSING) == base.get(key, MISSING) and key in theirs:
            ours[key] = copy.deepcopy(theirs[key])


def plan_steps(store, task, depth=0):
    lines = []
    for child in store.children(task):
        indent = "  " * depth
        lines.append(f"{indent}- [{'x' if child['done'] else ' '}] {child['title']} (id: {short_id(child)})")
        if child["description"]:
            lines.append(f"{indent}  {child['description']}")
        lines += plan_steps(store, child, depth + 1)
    return lines


def task_context(store, task):
    details = [f"Projeto: {store.project(task['project'])['name']}"]
    if task["priority"]:
        details.append("Prioridade: alta")
    if task["due"]:
        details.append(f"Prazo: {task['due']}")
    repo = store.repo(task)
    if repo:
        details.append(f"Repo: {repo}")
    key = jira_key(task)
    if key:
        details.append(f"Jira: {JIRA_BROWSE}{key}")
    return details


def claude_prompt(store, task):
    task_id = short_id(task)
    parts = [
        "Abaixo está um plano de implementação que montei no meu gerenciador de tarefas. "
        "A tarefa principal é o objetivo e as sub-tarefas são os passos, na ordem em que devem ser feitos "
        "(sub-tarefas indentadas detalham o passo acima delas). Passos marcados com [x] já estão feitos.",
        "",
        "Como quero que você trabalhe:",
        "1. Leia o plano inteiro e explore o código relevante antes de mudar qualquer coisa.",
        "2. Se algo estiver ambíguo ou parecer errado, me pergunte antes de começar.",
        "3. Execute os passos pendentes em ordem, um de cada vez, verificando cada um antes de seguir.",
        "4. No fim, me diga o que foi feito em cada passo e o que ficou pendente.",
        "",
        "Como dar notícias (rode no terminal; o progresso aparece no meu app na hora):",
        f"- Ao terminar um passo: `{CLI} done <id>`",
        f"- Para registrar uma decisão ou um bloqueio: `{CLI} note {task_id} \"texto\"`",
        f"- Se faltar um passo no plano: `{CLI} add <id-do-pai> \"título\"`",
        f"- Para rever o plano: `{CLI} show {task_id}`",
        "- A tarefa principal eu concluo; você só marca os passos.",
        "",
        "<plano>",
        f"# {task['title']} (id: {task_id})",
        " · ".join(task_context(store, task)),
    ]
    if task["description"]:
        parts += ["", task["description"]]
    steps = plan_steps(store, task)
    parts += ["", "## Passos", *steps] if steps else ["", "(Sem sub-tarefas: o objetivo acima é o plano todo.)"]
    parts.append("</plano>")
    return "\n".join(parts)


class TaskStore:
    def __init__(self):
        self.data = {"projects": [{"id": INBOX, "name": "Inbox", "color": "#246fe0"}], "tasks": []}
        self.data.update(read_tasks_file() or {})
        self.base = copy.deepcopy(self.data)
        self.on_external = None

    @property
    def projects(self):
        return self.data["projects"]

    @property
    def tasks(self):
        return self.data["tasks"]

    def save(self):
        with locked():
            disk = read_tasks_file()
            merged = disk is not None and disk != self.base
            if merged:
                merge_data(self.data, self.base, disk)
            write_tasks_file(self.data)
            self.base = copy.deepcopy(self.data)
        if merged and self.on_external:
            self.on_external()

    def refresh(self):
        with locked():
            disk = read_tasks_file()
            if disk is None or disk == self.base:
                return False
            merge_data(self.data, self.base, disk)
            if self.data != disk:
                write_tasks_file(self.data)
            self.base = copy.deepcopy(self.data)
        return True

    def project(self, project_id):
        return next((p for p in self.projects if p["id"] == project_id), self.projects[0])

    def repo(self, task):
        for t in [task, *self.ancestors(task)]:
            if t.get("repo"):
                return t["repo"]
        return self.project(task["project"]).get("repo")

    def add_task(self, title, description="", due=None, priority=False, project=INBOX, section=None, parent=None,
                 repo=None, by_claude=False):
        parent_task = self.find_task(parent)
        if parent_task:
            project, section = parent_task["project"], None
        task = {
            "id": uuid.uuid4().hex,
            "title": title,
            "description": description,
            "due": due.isoformat() if due else None,
            "priority": priority,
            "project": project,
            "section": section,
            "parent": parent_task["id"] if parent_task else None,
            "done": False,
            "done_at": None,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        if repo:
            task["repo"] = repo
        if by_claude:
            task["by_claude"] = True
        self.tasks.append(task)
        self.save()
        return task

    def update_task(self, task, title, description, due, priority, project, repo=None):
        if project != task["project"]:
            task.update(section=None, parent=None)
            for child in self.descendants(task):
                child["project"] = project
        task.update(title=title, description=description, due=due.isoformat() if due else None,
                    priority=priority, project=project)
        if repo:
            task["repo"] = repo
        else:
            task.pop("repo", None)
        self.save()

    def add_note(self, task, text, author="me"):
        task.setdefault("notes", []).append(
            {"at": datetime.now().isoformat(timespec="seconds"), "author": author, "text": text})
        self.save()

    def set_project_repo(self, project, repo):
        if repo:
            project["repo"] = repo
        else:
            project.pop("repo", None)
        self.save()

    def set_priority(self, task, priority):
        task["priority"] = priority
        self.save()

    def set_done(self, task, done):
        # Completing a task completes its sub-tasks; reopening a sub-task reopens its parents.
        stamp = datetime.now().isoformat(timespec="seconds") if done else None
        for t in [task, *(self.descendants(task) if done else self.ancestors(task))]:
            if t is task or t["done"] != done:
                t.update(done=done, done_at=stamp)
        self.save()

    def children(self, task):
        return sorted((t for t in self.tasks if t.get("parent") == task["id"]), key=lambda t: t["done"])

    def descendants(self, task):
        found = []
        for child in self.children(task):
            found += [child, *self.descendants(child)]
        return found

    def ancestors(self, task):
        found = []
        while task := self.find_task(task.get("parent")):
            found.append(task)
        return found

    def is_root(self, task):
        return self.find_task(task.get("parent")) is None

    def sections(self, project):
        return project.setdefault("sections", [])

    def add_section(self, project, name):
        self.sections(project).append({"id": uuid.uuid4().hex, "name": name})
        self.save()

    def rename_section(self, section, name):
        section["name"] = name
        self.save()

    def delete_section(self, project, section):
        self.forget_remote("sections", section)
        self.sections(project).remove(section)
        for t in self.tasks:
            if t.get("section") == section["id"]:
                t["section"] = None
        self.save()

    def adopt_loose_tasks(self, project):
        sections = self.sections(project)
        known = {s["id"] for s in sections}
        loose = [t for t in self.tasks if t["project"] == project["id"] and t.get("section") not in known
                 and self.is_root(t)]
        for task in loose:
            task["section"] = sections[0]["id"]
        if loose:
            self.save()

    def move_to_section(self, task, section_id, before=None):
        """Move a task into a section; it lands just before `before`, or at the end of the section."""
        task["section"] = section_id
        if before is not task:
            self.tasks.remove(task)
            self.tasks.insert(self.tasks.index(before) if before else len(self.tasks), task)
        self.save()

    def set_layout(self, project, layout):
        project["layout"] = layout
        self.save()

    def next_in_section(self, task, skip):
        siblings = [t for t in self.tasks if t is not skip and t["project"] == task["project"]
                    and t.get("section") == task.get("section") and self.is_root(t)]
        index = siblings.index(task) + 1
        return siblings[index] if index < len(siblings) else None

    def section_tasks(self, project_id, section_id, show_done):
        selected = (t for t in self.tasks if t["project"] == project_id and t.get("section") == section_id
                    and self.is_root(t) and (show_done or not t["done"]))
        return sorted(selected, key=lambda t: t["done"])

    def move_task(self, task, day):
        task["due"] = day.isoformat()
        self.save()

    def find_task(self, task_id):
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def find_by_prefix(self, prefix):
        found = [t for t in self.tasks if t["id"].startswith(prefix)] if len(prefix) >= 4 else []
        return found[0] if len(found) == 1 else None

    def tasks_on(self, day, show_done):
        iso = day.isoformat()
        selected = (t for t in self.tasks if t["due"] == iso and (show_done or not t["done"]))
        return sorted(selected, key=lambda t: t["done"])

    def forget_remote(self, kind, item):
        if item.get("todoist_id"):
            self.data.setdefault("todoist_deleted", []).append({"kind": kind, "id": item["todoist_id"]})

    def delete_task(self, task):
        for t in [task, *self.descendants(task)]:
            self.forget_remote("tasks", t)
        doomed = {t["id"] for t in [task, *self.descendants(task)]}
        self.data["tasks"] = [t for t in self.tasks if t["id"] not in doomed]
        self.save()

    def add_project(self, name):
        color = PROJECT_COLORS[(len(self.projects) - 1) % len(PROJECT_COLORS)]
        project = {"id": uuid.uuid4().hex, "name": name, "color": color}
        self.projects.append(project)
        self.save()
        return project

    def rename_project(self, project, name):
        project["name"] = name
        self.save()

    def delete_project(self, project):
        self.forget_remote("projects", project)
        self.projects.remove(project)
        self.data["tasks"] = [t for t in self.tasks if t["project"] != project["id"]]
        self.save()

    def matches(self, view, task):
        kind, project_id = view
        due = due_of(task)
        if kind == "project":
            return task["project"] == project_id
        if kind == "today":
            return due is not None and due <= date.today()
        return due is not None

    def open_count(self, view):
        return sum(1 for t in self.tasks if not t["done"] and self.matches(view, t))

    def groups(self, view, show_done):
        today = date.today()
        selected = [t for t in self.tasks if self.matches(view, t) and (view[0] != "project" or self.is_root(t))]
        pending = [t for t in selected if not t["done"]]
        by_due = sorted(pending, key=lambda t: (not t["priority"], t["due"] or "9999-12-31"))
        groups = []
        if view[0] == "project":
            for section in [None, *self.sections(self.project(view[1]))]:
                groups.append((section and section["name"],
                               self.section_tasks(view[1], section and section["id"], False)))
        else:
            overdue = [t for t in by_due if due_of(t) < today]
            if overdue:
                groups.append(("Overdue", overdue))
            if view[0] == "today":
                groups.append((day_heading(today) if overdue else None,
                               [t for t in by_due if due_of(t) == today]))
            else:
                for t in by_due:
                    d = due_of(t)
                    if d < today:
                        continue
                    if not groups or groups[-1][0] != day_heading(d):
                        groups.append((day_heading(d), []))
                    groups[-1][1].append(t)
        if show_done:
            done = sorted((t for t in selected if t["done"]), key=lambda t: t["done_at"] or "", reverse=True)
            if done:
                groups.append(("Completed", done))
        return [(heading, tasks) for heading, tasks in groups if tasks]


def describe(store, task):
    lines = [f"# {task['title']} (id: {short_id(task)})", " · ".join(task_context(store, task))]
    if task["done"]:
        lines.append("Status: concluída")
    if task["description"]:
        lines += ["", task["description"]]
    steps = plan_steps(store, task)
    lines += ["", "## Sub-tarefas", *(steps or ["(nenhuma)"])]
    notes = task.get("notes") or []
    if notes:
        lines += ["", "## Notas"]
        lines += [f"- {n['at'].replace('T', ' ')[:16]} {'🤖' if n['author'] == 'claude' else '📝'} {n['text']}"
                  for n in reversed(notes)]
    return "\n".join(lines)


def cli(args):
    usage = (f"usage: {CLI} show <id> | done <sub-task-id> | note <id> \"text\" | add <parent-id> \"title\"\n"
             "ids are the first 8 characters shown by `show` or in the copied plan")
    command = args[0] if args else ""
    if (command, len(args)) not in (("show", 2), ("done", 2), ("note", 3), ("add", 3)):
        print(usage, file=sys.stderr)
        return 2
    store = TaskStore()
    task = store.find_by_prefix(args[1])
    if not task:
        print(f"no task matches id {args[1]!r}", file=sys.stderr)
        return 1
    if command == "show":
        print(describe(store, task))
    elif command == "done":
        if store.is_root(task):
            print("only sub-tasks can be completed from the CLI; the main task is up to you", file=sys.stderr)
            return 1
        store.set_done(task, True)
        print(f"done: {task['title']}")
    elif command == "note":
        store.add_note(task, args[2], author="claude")
        print(f"note added to: {task['title']}")
    else:
        child = store.add_task(args[2], parent=task["id"], by_claude=True)
        print(f"added {short_id(child)}: {child['title']}")
    return 0
