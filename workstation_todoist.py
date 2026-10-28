import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

API_URL = "https://api.todoist.com/api/v1"
TOKEN_FILE = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                          "all-in-one-workstation", "todoist_token")
INBOX = "inbox"
URGENT = 4
FIELDS = ("title", "description", "priority", "due", "done", "place")
COLORS = {
    "#b8256f": "berry_red", "#db4035": "red", "#ff9933": "orange", "#fad000": "yellow",
    "#afb83b": "olive_green", "#7ecc49": "lime_green", "#299438": "green", "#6accbc": "mint_green",
    "#158fad": "teal", "#14aaf5": "sky_blue", "#96c3eb": "light_blue", "#4073ff": "blue",
    "#884dff": "grape", "#af38eb": "violet", "#eb96eb": "lavender", "#e05194": "magenta",
    "#ff8d85": "salmon", "#808080": "charcoal", "#b8b8b8": "grey", "#ccac93": "taupe",
}
HEX_COLORS = {name: hex_ for hex_, name in COLORS.items()}


class TodoistError(Exception):
    pass


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_token(token):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token.strip())


class Todoist:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, data=None, params=None):
        url = f"{API_URL}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                text = response.read()
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise TodoistError("Invalid Todoist token") from error
            raise TodoistError(f"Todoist answered {error.code} on {method} /{path}") from error
        except urllib.error.URLError as error:
            raise TodoistError(f"Could not reach Todoist: {error.reason}") from error
        return json.loads(text) if text else None

    def all(self, path):
        found, cursor = [], None
        while True:
            page = self.request("GET", path, params={"limit": 200, **({"cursor": cursor} if cursor else {})})
            found += page["results"]
            cursor = page.get("next_cursor")
            if not cursor:
                return found

    def delete(self, kind, todoist_id):
        try:
            self.request("DELETE", f"{kind}/{todoist_id}")
        except TodoistError as error:
            if "404" not in str(error):
                raise


def snapshot(task):
    return {"title": task["title"], "description": task["description"], "priority": task["priority"],
            "due": task["due"], "done": task["done"], "place": [task["project"], task.get("section"), task.get("parent")]}


class TodoistSync:
    def __init__(self, data, client):
        self.data = data
        self.client = client
        self.counts = {"pulled": 0, "pushed": 0}

    def run(self):
        deleted = self.data.setdefault("todoist_deleted", [])
        gone = {entry["id"] for entry in deleted}
        projects = [p for p in self.client.all("projects") if not p.get("is_archived") and p["id"] not in gone]
        sections = [s for s in self.client.all("sections") if s["id"] not in gone]
        tasks = [t for t in self.client.all("tasks") if t["id"] not in gone]
        self.sync_projects(projects)
        self.sync_sections(sections)
        self.sync_tasks(tasks)
        while deleted:
            entry = deleted[0]
            self.client.delete(entry["kind"], entry["id"])
            deleted.pop(0)
        self.data["todoist_synced_at"] = datetime.now().isoformat(timespec="seconds")
        return self.counts

    def synced_projects(self):
        return [p for p in self.data["projects"] if p.get("todoist_id")]

    def sync_projects(self, remote):
        by_id = {p["id"]: p for p in remote}
        inbox = next((p for p in remote if p.get("is_inbox_project") or p.get("inbox_project")), None)
        linked = {p.get("todoist_id") for p in self.data["projects"]}
        for local in self.data["projects"]:
            if local.get("todoist_off"):
                continue
            todoist_id = local.get("todoist_id")
            if todoist_id and todoist_id not in by_id:
                local.pop("todoist_id")
                local["todoist_off"] = True
                continue
            if not todoist_id:
                match = inbox if local["id"] == INBOX else next(
                    (p for p in remote if p["id"] not in linked and p is not inbox
                     and p["name"].lower() == local["name"].lower()), None)
                if not match:
                    match = self.client.request("POST", "projects", {
                        "name": local["name"], "color": COLORS.get(local["color"], "charcoal")})
                    self.counts["pushed"] += 1
                local.update(todoist_id=match["id"], synced_name=match["name"])
                linked.add(match["id"])
                by_id[match["id"]] = match
            if local["id"] != INBOX:
                local["name"] = self.merge_name(local, by_id[local["todoist_id"]], "projects")
        for project in remote:
            if project["id"] not in linked:
                self.data["projects"].append({
                    "id": uuid.uuid4().hex, "name": project["name"],
                    "color": HEX_COLORS.get(project.get("color"), "#808080"), "sections": [],
                    "todoist_id": project["id"], "synced_name": project["name"]})
                self.counts["pulled"] += 1

    def merge_name(self, local, remote, kind):
        base = local.get("synced_name")
        if local["name"] != base and remote["name"] == base:
            self.client.request("POST", f"{kind}/{remote['id']}", {"name": local["name"]})
            self.counts["pushed"] += 1
            name = local["name"]
        else:
            name = remote["name"]
        local["synced_name"] = name
        return name

    def sync_sections(self, remote):
        by_id = {s["id"]: s for s in remote}
        for project in self.synced_projects():
            sections = project.setdefault("sections", [])
            mine = [s for s in remote if s["project_id"] == project["todoist_id"]]
            linked = {s.get("todoist_id") for s in sections}
            for local in list(sections):
                todoist_id = local.get("todoist_id")
                if todoist_id and todoist_id not in by_id:
                    sections.remove(local)
                    for task in self.data["tasks"]:
                        if task.get("section") == local["id"]:
                            task["section"] = None
                    continue
                if not todoist_id:
                    match = next((s for s in mine if s["id"] not in linked
                                  and s["name"].lower() == local["name"].lower()), None)
                    if not match:
                        match = self.client.request("POST", "sections", {
                            "name": local["name"], "project_id": project["todoist_id"]})
                        self.counts["pushed"] += 1
                    local.update(todoist_id=match["id"], synced_name=match["name"])
                    linked.add(match["id"])
                    by_id[match["id"]] = match
                local["name"] = self.merge_name(local, by_id[local["todoist_id"]], "sections")
            for section in mine:
                if section["id"] not in linked:
                    sections.append({"id": uuid.uuid4().hex, "name": section["name"],
                                     "todoist_id": section["id"], "synced_name": section["name"]})
                    self.counts["pulled"] += 1

    def sync_tasks(self, remote):
        projects = {p["todoist_id"]: p["id"] for p in self.synced_projects()}
        self.project_ids = {local: todoist for todoist, local in projects.items()}
        self.section_ids = {s["id"]: s["todoist_id"] for p in self.synced_projects()
                            for s in p["sections"] if s.get("todoist_id")}
        local_sections = {todoist: local for local, todoist in self.section_ids.items()}
        by_id = {t["id"]: t for t in remote if t["project_id"] in projects}
        tasks = self.data["tasks"]
        local_ids = {t["todoist_id"]: t["id"] for t in tasks if t.get("todoist_id")}

        for task in tasks:
            todoist_id = task.get("todoist_id")
            if not todoist_id or task["project"] not in self.project_ids:
                continue
            if todoist_id not in by_id:
                if not task["done"]:
                    task.update(done=True, done_at=datetime.now().isoformat(timespec="seconds"))
                    self.counts["pulled"] += 1
                task.pop("todoist_id")
                task.pop("synced", None)
                continue
            self.merge_task(task, self.from_remote(by_id.pop(todoist_id), projects, local_sections, local_ids))

        fresh = [t for t in tasks if not t.get("todoist_id") and not t["done"] and t["project"] in self.project_ids]
        for task in sorted(fresh, key=lambda t: self.depth(t)):
            match = next((r for r in by_id.values() if r["content"] == task["title"]
                          and r["project_id"] == self.project_ids[task["project"]]), None)
            if match:
                by_id.pop(match["id"])
                task["todoist_id"] = match["id"]
                local_ids[match["id"]] = task["id"]
                task["synced"] = snapshot(task)
                self.merge_task(task, self.from_remote(match, projects, local_sections, local_ids))
                continue
            fields = {**self.remote_fields(task), **self.remote_place(task)}
            fields.pop("due_string", None)
            created = self.client.request("POST", "tasks", fields)
            task["todoist_id"] = created["id"]
            local_ids[created["id"]] = task["id"]
            task["synced"] = snapshot(task)
            self.counts["pushed"] += 1

        pulled = []
        for item in by_id.values():
            task = {"id": uuid.uuid4().hex, "todoist_id": item["id"], "done_at": None,
                    "created": datetime.now().isoformat(timespec="seconds")}
            local_ids[item["id"]] = task["id"]
            pulled.append((task, item))
        for task, item in pulled:
            fields = self.from_remote(item, projects, local_sections, local_ids)
            self.apply(task, fields)
            task["synced"] = snapshot(task)
            tasks.append(task)
            self.counts["pulled"] += 1

    def depth(self, task):
        depth, parent = 0, task.get("parent")
        while parent:
            depth += 1
            parent = next((t.get("parent") for t in self.data["tasks"] if t["id"] == parent), None)
        return depth

    def from_remote(self, item, projects, local_sections, local_ids):
        due = item.get("due")
        return {"title": item["content"], "description": item.get("description") or "",
                "priority": item.get("priority") == URGENT, "due": due["date"][:10] if due else None,
                "done": bool(item.get("checked") or item.get("completed_at")),
                "place": [projects[item["project_id"]], local_sections.get(item.get("section_id")),
                          local_ids.get(item.get("parent_id"))]}

    def apply(self, task, fields):
        project, section, parent = fields["place"]
        task.update(title=fields["title"], description=fields["description"], priority=fields["priority"],
                    due=fields["due"], project=project, section=section, parent=parent)
        if task.get("done") != fields["done"]:
            task.update(done=fields["done"], done_at=datetime.now().isoformat(timespec="seconds")
                        if fields["done"] else None)

    def merge_task(self, task, remote):
        local, base = snapshot(task), task.get("synced") or snapshot(task)
        result, push = {}, []
        for field in FIELDS:
            if local[field] != remote[field] and local[field] != base[field] and remote[field] == base[field]:
                result[field] = local[field]
                push.append(field)
            else:
                result[field] = remote[field]
        if result != local:
            self.apply(task, result)
            self.counts["pulled"] += 1
        todoist_id = task["todoist_id"]
        update = {k: v for k, v in self.remote_fields(task).items()
                  if {"content": "title", "due_date": "due", "due_string": "due"}.get(k, k) in push}
        if update:
            self.client.request("POST", f"tasks/{todoist_id}", update)
        if "place" in push:
            self.client.request("POST", f"tasks/{todoist_id}/move", self.remote_place(task, single=True))
        if "done" in push:
            self.client.request("POST", f"tasks/{todoist_id}/{'close' if task['done'] else 'reopen'}")
        if push:
            self.counts["pushed"] += 1
        task["synced"] = snapshot(task)

    def remote_fields(self, task):
        fields = {"content": task["title"], "description": task["description"],
                  "priority": URGENT if task["priority"] else 1}
        if task["due"]:
            fields["due_date"] = task["due"]
        else:
            fields["due_string"] = "no date"
        return fields

    def remote_place(self, task, single=False):
        parent = next((t.get("todoist_id") for t in self.data["tasks"] if t["id"] == task.get("parent")), None)
        place = {"project_id": self.project_ids[task["project"]],
                 "section_id": self.section_ids.get(task.get("section")), "parent_id": parent}
        if single:
            key = "parent_id" if parent else "section_id" if place["section_id"] else "project_id"
            return {key: place[key]}
        return {k: v for k, v in place.items() if v}
