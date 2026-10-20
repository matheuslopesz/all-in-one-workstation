import json
import os
import re
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from workstation_theme import CYAN, LAVENDER, MINT, NIGHT, PINK, PURPLE, YELLOW  # noqa: E402

TASKS_FILE = os.path.join(GLib.get_user_config_dir(), "all-in-one-workstation", "tasks.json")
INBOX = "inbox"
PRIORITY_COLORS = {1: PINK, 2: YELLOW, 3: CYAN, 4: LAVENDER}
PROJECT_COLORS = ["#db4035", "#ff9933", "#fad000", "#7ecc49", "#299438",
                  "#14aaf5", "#4073ff", "#884dff", "#e05194", "#808080"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CALENDAR_VISIBLE = 3
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_WORDS = {
    "monday": 0, "mon": 0, "segunda": 0,
    "tuesday": 1, "tue": 1, "terça": 1, "terca": 1,
    "wednesday": 2, "wed": 2, "quarta": 2,
    "thursday": 3, "thu": 3, "quinta": 3,
    "friday": 4, "fri": 4, "sexta": 4,
    "saturday": 5, "sat": 5, "sábado": 5, "sabado": 5,
    "sunday": 6, "sun": 6, "domingo": 6,
}

TASKS_CSS = f"""
.view-title {{ font-size: 22px; font-weight: 800; }}
.sidebar {{ background: alpha(currentColor, 0.04); padding: 12px 8px; }}
.sidebar list {{ background: transparent; }}
.sidebar row {{ padding: 6px 10px; border-radius: 6px; }}
.sidebar row:selected {{ background: alpha({PINK}, 0.14); color: inherit; }}
.sidebar-head {{ font-weight: bold; opacity: 0.7; font-size: 13px; }}
.count {{ opacity: 0.5; font-size: 12px; }}
.task-list {{ background: transparent; }}
.task-list row {{ padding: 8px 4px; border-bottom: 1px solid alpha(currentColor, 0.08); }}
.task-list row.group-head {{ padding: 18px 4px 4px 4px; border-bottom: 1px solid alpha(currentColor, 0.18); }}
.group-head label {{ font-weight: bold; font-size: 13px; }}
.task-check check {{ border-radius: 50%; min-width: 18px; min-height: 18px; margin-top: 2px;
                    border: 2px solid #808080; background: transparent; box-shadow: none; }}
.task-desc {{ font-size: 12px; opacity: 0.6; }}
.task-meta {{ font-size: 12px; }}
.due-today {{ color: {MINT}; }}
.due-tomorrow {{ color: {YELLOW}; }}
.due-week {{ color: {PURPLE}; }}
.due-overdue {{ color: {PINK}; }}
.due-later {{ opacity: 0.7; }}
.task-actions {{ opacity: 0; transition: opacity 120ms; }}
row:hover .task-actions {{ opacity: 1; }}
.task-form {{ border: 1px solid alpha(currentColor, 0.2); border-radius: 10px; padding: 10px; }}
.title-entry {{ font-weight: bold; }}
.task-form button.suggested-action {{ background: {PINK}; color: {NIGHT}; border: none; box-shadow: none; }}
.add-task {{ color: {PINK}; font-weight: bold; }}
.empty {{ opacity: 0.5; padding: 30px; }}
.cal-weekday {{ font-weight: bold; font-size: 12px; opacity: 0.6; padding: 4px 6px; }}
.cal-day {{ border: 1px solid alpha(currentColor, 0.08); padding: 4px; min-height: 110px; }}
.cal-day.other-month {{ background: alpha(currentColor, 0.03); }}
.cal-day.other-month .cal-num {{ opacity: 0.4; }}
.cal-day.drop-hover {{ background: alpha({PINK}, 0.12); }}
.cal-num {{ font-size: 12px; font-weight: bold; padding: 2px 6px; border-radius: 10px; }}
.cal-num.cal-today {{ background: {PINK}; color: {NIGHT}; }}
.cal-add {{ opacity: 0; min-height: 20px; min-width: 20px; padding: 0; }}
.cal-day:hover .cal-add {{ opacity: 1; }}
.cal-task {{ font-size: 12px; padding: 1px 4px; border-radius: 4px; background: alpha(currentColor, 0.05); }}
.cal-task:hover {{ background: alpha(currentColor, 0.1); }}
.cal-task check {{ min-width: 12px; min-height: 12px; margin: 0; border-width: 1px; }}
.cal-more {{ font-size: 12px; padding: 0 4px; min-height: 0; }}
.month-label {{ font-weight: bold; }}
.board-column {{ background: alpha(currentColor, 0.04); border-radius: 10px; padding: 8px; }}
.board-column.drop-hover {{ background: alpha({PINK}, 0.12); }}
.column-name {{ font-weight: bold; }}
.board-card {{ border: 1px solid alpha(currentColor, 0.12); border-radius: 8px; padding: 8px;
              background: alpha(currentColor, 0.03); }}
.board-card:hover {{ border-color: alpha(currentColor, 0.3); }}
.subtasks-head {{ font-weight: bold; font-size: 13px; }}
""" + "".join(
    f".task-check.p{p} check {{ border-color: {c}; background: alpha({c}, 0.12); }}\n"
    f".task-check.p{p} check:checked {{ background: {c}; color: {NIGHT}; }}\n"
    for p, c in PRIORITY_COLORS.items()
)


def due_of(task):
    return date.fromisoformat(task["due"]) if task["due"] else None


def short_date(d):
    text = f"{d.day} {MONTH_NAMES[d.month - 1]}"
    return text if d.year == date.today().year else f"{text} {d.year}"


def due_label(d):
    delta = (d - date.today()).days
    if delta < 0:
        return ("Yesterday" if delta == -1 else short_date(d)), "due-overdue"
    if delta == 0:
        return "Today", "due-today"
    if delta == 1:
        return "Tomorrow", "due-tomorrow"
    if delta < 7:
        return DAY_NAMES[d.weekday()], "due-week"
    return short_date(d), "due-later"


def day_heading(d):
    text = f"{d.day} {MONTH_NAMES[d.month - 1]} · {DAY_NAMES[d.weekday()]}"
    delta = (d - date.today()).days
    if delta == 0:
        return f"{text} · Today"
    if delta == 1:
        return f"{text} · Tomorrow"
    return text


def title_markup(task):
    escaped = GLib.markup_escape_text(task["title"])
    return f'<span strikethrough="true" alpha="50%">{escaped}</span>' if task["done"] else escaped


def plan_steps(store, task, depth=0):
    lines = []
    for child in store.children(task):
        indent = "  " * depth
        lines.append(f"{indent}- [{'x' if child['done'] else ' '}] {child['title']}")
        if child["description"]:
            lines.append(f"{indent}  {child['description']}")
        lines += plan_steps(store, child, depth + 1)
    return lines


def claude_prompt(store, task):
    details = [f"Projeto: {store.project(task['project'])['name']}", f"Prioridade: P{task['priority']}"]
    if task["due"]:
        details.append(f"Prazo: {task['due']}")
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
        "<plano>",
        f"# {task['title']}",
        " · ".join(details),
    ]
    if task["description"]:
        parts += ["", task["description"]]
    steps = plan_steps(store, task)
    parts += ["", "## Passos", *steps] if steps else ["", "(Sem sub-tarefas: o objetivo acima é o plano todo.)"]
    parts.append("</plano>")
    return "\n".join(parts)


def parse_quick(text, projects):
    today = date.today()
    due = priority = project = None
    kept = []
    for token in text.split():
        word = token.lower()
        if word in ("today", "hoje"):
            due = today
        elif word in ("tomorrow", "amanhã", "amanha"):
            due = today + timedelta(days=1)
        elif word in WEEKDAY_WORDS:
            due = today + timedelta(days=(WEEKDAY_WORDS[word] - today.weekday() - 1) % 7 + 1)
        elif re.fullmatch(r"p[1-4]", word):
            priority = int(word[1])
        elif word.startswith("#") and len(word) > 1:
            match = next((p for p in projects if p["name"].lower().replace(" ", "") == word[1:]), None)
            if match:
                project = match["id"]
            else:
                kept.append(token)
        else:
            kept.append(token)
    return " ".join(kept), due, priority, project


class TaskStore:
    def __init__(self):
        self.data = {"projects": [{"id": INBOX, "name": "Inbox", "color": "#246fe0"}], "tasks": []}
        try:
            with open(TASKS_FILE) as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    @property
    def projects(self):
        return self.data["projects"]

    @property
    def tasks(self):
        return self.data["tasks"]

    def save(self):
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        tmp = TASKS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, TASKS_FILE)

    def project(self, project_id):
        return next((p for p in self.projects if p["id"] == project_id), self.projects[0])

    def add_task(self, title, description="", due=None, priority=4, project=INBOX, section=None, parent=None):
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
        self.tasks.append(task)
        self.save()
        return task

    def update_task(self, task, title, description, due, priority, project):
        if project != task["project"]:
            task.update(section=None, parent=None)
            for child in self.descendants(task):
                child["project"] = project
        task.update(title=title, description=description, due=due.isoformat() if due else None,
                    priority=priority, project=project)
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
        self.sections(project).remove(section)
        for t in self.tasks:
            if t.get("section") == section["id"]:
                t["section"] = None
        self.save()

    def move_to_section(self, task, section_id):
        task["section"] = section_id
        self.save()

    def set_layout(self, project, layout):
        project["layout"] = layout
        self.save()

    def section_tasks(self, project_id, section_id, show_done):
        selected = (t for t in self.tasks if t["project"] == project_id and t.get("section") == section_id
                    and self.is_root(t) and (show_done or not t["done"]))
        return sorted(selected, key=lambda t: t["done"])

    def move_task(self, task, day):
        task["due"] = day.isoformat()
        self.save()

    def find_task(self, task_id):
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def tasks_on(self, day, show_done):
        iso = day.isoformat()
        selected = (t for t in self.tasks if t["due"] == iso and (show_done or not t["done"]))
        return sorted(selected, key=lambda t: (t["done"], t["priority"]))

    def delete_task(self, task):
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
        by_due = sorted(pending, key=lambda t: (t["due"] or "9999-12-31", t["priority"]))
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


class TaskForm(Gtk.Box):
    def __init__(self, store, on_submit, on_cancel, submit_label="Add task"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["task-form"])
        self.store = store
        self.on_submit = on_submit
        self.due = None

        self.title = Gtk.Entry(placeholder_text="Task name   e.g. Pay rent tomorrow p1 #Home",
                               css_classes=["title-entry"])
        self.description = Gtk.Entry(placeholder_text="Description")
        for entry in (self.title, self.description):
            entry.connect("activate", lambda _e: self.submit())
        self.append(self.title)
        self.append(self.description)

        chips = Gtk.Box(spacing=6)
        self.due_button = Gtk.MenuButton(popover=self.build_due_popover())
        self.priority = Gtk.DropDown.new_from_strings([f"Priority {p}" for p in PRIORITY_COLORS])
        self.project = Gtk.DropDown()
        chips.append(self.due_button)
        chips.append(self.priority)
        chips.append(self.project)
        self.append(chips)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: on_cancel())
        self.submit_button = Gtk.Button(label=submit_label, css_classes=["suggested-action"])
        self.submit_button.connect("clicked", lambda _b: self.submit())
        buttons.append(cancel)
        buttons.append(self.submit_button)
        self.append(buttons)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key, on_cancel)
        self.add_controller(keys)

    def build_due_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        quick = [("Today", lambda d: d), ("Tomorrow", lambda d: d + timedelta(days=1)),
                 ("Next week", lambda d: d + timedelta(days=7 - d.weekday())), ("No date", lambda d: None)]
        for label, pick in quick:
            button = Gtk.Button(label=label, css_classes=["flat"])
            button.connect("clicked", lambda _b, f=pick: self.set_due(f(date.today())))
            box.append(button)
        self.calendar = Gtk.Calendar()
        self.calendar.connect("day-selected", self.on_day_selected)
        box.append(self.calendar)
        popover = Gtk.Popover(child=box)
        self.popover = popover
        return popover

    def on_key(self, _controller, keyval, _keycode, _state, on_cancel):
        if keyval == Gdk.KEY_Escape:
            on_cancel()
            return True
        return False

    def on_day_selected(self, calendar):
        picked = calendar.get_date()
        self.set_due(date(picked.get_year(), picked.get_month(), picked.get_day_of_month()))

    def set_due(self, value):
        self.due = value
        self.due_button.set_label(due_label(value)[0] if value else "Due date")
        self.popover.popdown()

    def set_values(self, title="", description="", due=None, priority=4, project=INBOX):
        self.title.set_text(title)
        self.description.set_text(description)
        self.set_due(due)
        self.priority.set_selected(priority - 1)
        self.project_ids = [p["id"] for p in self.store.projects]
        self.project.set_model(Gtk.StringList.new([p["name"] for p in self.store.projects]))
        self.project.set_selected(self.project_ids.index(project) if project in self.project_ids else 0)
        self.title.grab_focus()

    def submit(self):
        text = self.title.get_text().strip()
        if not text:
            return
        title, due, priority, project = parse_quick(text, self.store.projects)
        self.on_submit({
            "title": title or text,
            "description": self.description.get_text().strip(),
            "due": due or self.due,
            "priority": priority or self.priority.get_selected() + 1,
            "project": project or self.project_ids[self.project.get_selected()],
        })


class TaskDialog(Gtk.Window):
    def __init__(self, view, task=None, due=None, project=INBOX, section=None, parent=None, owner=None,
                 on_change=None):
        super().__init__(title="Edit task" if task else "Add sub-task" if parent else "Add task",
                         transient_for=owner or view.get_root(), modal=True, default_width=520, resizable=False)
        self.view = view
        self.task = task
        self.section = section
        self.parent = parent
        self.on_change = on_change
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=14, margin_bottom=14,
                      margin_start=14, margin_end=14)
        form = TaskForm(view.store, self.save, self.close, submit_label="Save" if task else "Add task")
        if task:
            form.set_values(task["title"], task["description"], due_of(task), task["priority"], task["project"])
        else:
            form.set_values(due=due, project=parent["project"] if parent else project)
        form.project.set_sensitive(not parent and not (task and not view.store.is_root(task)))
        box.append(form)
        if task:
            self.subtasks = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.append(self.subtasks)
            self.rebuild_subtasks()
        self.set_child(box)

    def rebuild_subtasks(self):
        while child := self.subtasks.get_first_child():
            self.subtasks.remove(child)
        children = self.view.store.children(self.task)
        done = sum(c["done"] for c in children)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label=f"Sub-tasks  {done}/{len(children)}" if children else "Sub-tasks",
                              xalign=0, hexpand=True, css_classes=["subtasks-head"]))
        head.append(self.view.claude_button(self.task))
        self.subtasks.append(head)
        for child in children:
            row = Gtk.Box(spacing=8)
            check = Gtk.CheckButton(active=child["done"], css_classes=["task-check", f"p{child['priority']}"])
            check.connect("toggled", self.on_check, child)
            row.append(check)
            title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
            title.set_markup(title_markup(child))
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, c=child: TaskDialog(
                self.view, c, owner=self, on_change=self.rebuild_subtasks).present())
            title.add_controller(click)
            row.append(title)
            self.subtasks.append(row)
        add = Gtk.Button(label="+  Add sub-task", css_classes=["flat", "add-task"], halign=Gtk.Align.START)
        add.connect("clicked", lambda _b: TaskDialog(self.view, parent=self.task, owner=self,
                                                     on_change=self.rebuild_subtasks).present())
        self.subtasks.append(add)

    def on_check(self, check, child):
        self.view.store.set_done(child, check.get_active())
        self.view.reload()
        GLib.idle_add(lambda: (self.rebuild_subtasks(), False)[1])

    def save(self, values):
        if self.task:
            self.view.store.update_task(self.task, **values)
        else:
            self.view.store.add_task(**values, section=self.section,
                                     parent=self.parent["id"] if self.parent else None)
        self.view.reload()
        if self.on_change:
            self.on_change()
        self.close()


class NameDialog(Gtk.Window):
    def __init__(self, parent, title, initial, on_submit, placeholder="Project name"):
        super().__init__(title=title, transient_for=parent, modal=True, default_width=360, resizable=False)
        self.on_submit = on_submit
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        self.entry = Gtk.Entry(text=initial, placeholder_text=placeholder)
        self.entry.connect("activate", lambda _e: self.submit())
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        ok = Gtk.Button(label="Save", css_classes=["suggested-action"])
        ok.connect("clicked", lambda _b: self.submit())
        buttons.append(cancel)
        buttons.append(ok)
        box.append(self.entry)
        box.append(buttons)
        self.set_child(box)

    def submit(self):
        name = self.entry.get_text().strip()
        if name:
            self.on_submit(name)
            self.close()


class TasksView(Gtk.Paned):
    def __init__(self, on_focus):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, position=240,
                         shrink_start_child=False, resize_start_child=False)
        self.on_focus = on_focus
        self.store = TaskStore()
        self.view = ("project", INBOX)
        self.show_done = False
        self.cal_month = date.today().replace(day=1)
        self.set_start_child(self.build_sidebar())
        self.set_end_child(self.build_content())
        self.reload()

    def build_sidebar(self):
        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.connect("row-selected", self.on_nav_selected)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, css_classes=["sidebar"],
                                      width_request=200)
        scroller.set_child(self.nav)
        return scroller

    def build_content(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=24, margin_bottom=24,
                      margin_start=40, margin_end=40)
        head = Gtk.Box(spacing=8)
        self.title = Gtk.Label(xalign=0, hexpand=True, css_classes=["view-title"])
        show_done = Gtk.CheckButton(label="Show completed")
        show_done.connect("toggled", self.on_show_done)
        head.append(self.title)
        head.append(self.build_calendar_nav())
        head.append(self.build_layout_toggle())
        head.append(show_done)
        box.append(head)

        self.pages = Gtk.Stack(vhomogeneous=False)
        list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.pages.add_named(list_page, "list")
        self.cal_grid = Gtk.Grid(column_homogeneous=True, margin_top=10)
        self.pages.add_named(self.cal_grid, "calendar")
        self.board = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10)
        self.pages.add_named(Gtk.ScrolledWindow(child=self.board, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                                propagate_natural_height=True), "board")
        box.append(self.pages)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["task-list"])
        self.list.connect("row-activated", self.on_row_activated)
        list_page.append(self.list)

        self.add_button = Gtk.Button(label="+  Add task", css_classes=["flat", "add-task"],
                                     halign=Gtk.Align.START, margin_top=6)
        self.add_button.connect("clicked", lambda _b: self.open_form())
        self.form = TaskForm(self.store, self.add_from_form, self.close_form)
        self.form.set_visible(False)
        self.form.set_margin_top(6)
        list_page.append(self.add_button)
        list_page.append(self.form)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        scroller.set_child(box)
        return scroller

    def build_calendar_nav(self):
        self.cal_nav = Gtk.Box(spacing=4, margin_end=12)
        self.month_label = Gtk.Label(css_classes=["month-label"], margin_end=6)
        self.cal_nav.append(self.month_label)
        for step, button in ((-1, Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous month")),
                             (0, Gtk.Button(label="Today")),
                             (1, Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next month"))):
            button.add_css_class("flat")
            button.connect("clicked", lambda _b, s=step: self.shift_month(s))
            self.cal_nav.append(button)
        return self.cal_nav

    def build_layout_toggle(self):
        self.layout_toggle = Gtk.Box(css_classes=["linked"], margin_end=12)
        self.layout_buttons = {}
        group = None
        for layout, label in (("list", "List"), ("board", "Board")):
            button = Gtk.ToggleButton(label=label, group=group)
            button.connect("toggled", self.on_layout, layout)
            group = group or button
            self.layout_buttons[layout] = button
            self.layout_toggle.append(button)
        return self.layout_toggle

    def on_layout(self, button, layout):
        project = self.store.project(self.view[1])
        if button.get_active() and project.get("layout", "list") != layout:
            self.store.set_layout(project, layout)
            self.close_form()
            self.rebuild_list()

    def reload(self):
        self.rebuild_sidebar()
        self.rebuild_list()

    def view_name(self, view):
        if view[0] == "project":
            return self.store.project(view[1])["name"]
        return {"today": "Today", "upcoming": "Upcoming", "calendar": "Calendar"}[view[0]]

    def rebuild_sidebar(self):
        if self.view[0] == "project" and self.store.project(self.view[1])["id"] != self.view[1]:
            self.view = ("project", INBOX)
        self.nav.remove_all()
        inbox = self.store.projects[0]
        for view, icon in ((("project", INBOX), "mail-inbox-symbolic"),
                           (("today", None), "x-office-calendar-symbolic"),
                           (("upcoming", None), "view-list-symbolic"),
                           (("calendar", None), "view-grid-symbolic")):
            self.nav.append(self.nav_row(view, Gtk.Image(icon_name=icon)))

        head = Gtk.Box(spacing=6, margin_top=14)
        head.append(Gtk.Label(label="My Projects", xalign=0, hexpand=True, css_classes=["sidebar-head"]))
        add = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat"], tooltip_text="Add project")
        add.connect("clicked", lambda _b: NameDialog(self.get_root(), "Add project", "", self.add_project).present())
        head.append(add)
        head_row = Gtk.ListBoxRow(child=head, selectable=False, activatable=False)
        self.nav.append(head_row)

        for project in self.store.projects:
            if project is inbox:
                continue
            dot = Gtk.Label()
            dot.set_markup(f'<span foreground="{project["color"]}">●</span>')
            self.nav.append(self.nav_row(("project", project["id"]), dot, self.project_menu(project)))

        for row in self.iter_rows(self.nav):
            if getattr(row, "view", None) == self.view:
                self.nav.select_row(row)

    def nav_row(self, view, icon, menu=None):
        box = Gtk.Box(spacing=10)
        box.append(icon)
        box.append(Gtk.Label(label=self.view_name(view), xalign=0, hexpand=True,
                             ellipsize=Pango.EllipsizeMode.END))
        count = self.store.open_count(view)
        box.append(Gtk.Label(label=str(count) if count else "", css_classes=["count"]))
        if menu:
            box.append(menu)
        row = Gtk.ListBoxRow(child=box)
        row.view = view
        return row

    def project_menu(self, project):
        return self.item_menu(
            lambda: NameDialog(self.get_root(), "Rename project", project["name"],
                               lambda name: (self.store.rename_project(project, name), self.reload())).present(),
            lambda: self.confirm(f"Delete “{project['name']}”?",
                                 "This will permanently delete the project and all its tasks.",
                                 lambda: (self.store.delete_project(project), self.reload())))

    def section_menu(self, project, section):
        return self.item_menu(
            lambda: NameDialog(self.get_root(), "Rename section", section["name"],
                               lambda name: (self.store.rename_section(section, name), self.reload()),
                               "Section name").present(),
            lambda: (self.store.delete_section(project, section), self.reload()))

    def item_menu(self, on_rename, on_delete):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popover = Gtk.Popover(child=box)
        for label, css, action in (("Rename", ["flat"], on_rename),
                                   ("Delete", ["flat", "destructive-action"], on_delete)):
            button = Gtk.Button(label=label, css_classes=css)
            button.connect("clicked", lambda _b, a=action: (popover.popdown(), a()))
            box.append(button)
        return Gtk.MenuButton(icon_name="view-more-symbolic", popover=popover, has_frame=False)

    def iter_rows(self, listbox):
        row = listbox.get_first_child()
        while row:
            yield row
            row = row.get_next_sibling()

    def rebuild_list(self):
        self.title.set_text(self.view_name(self.view))
        calendar = self.view[0] == "calendar"
        self.cal_nav.set_visible(calendar)
        self.layout_toggle.set_visible(self.view[0] == "project")
        board = False
        if self.view[0] == "project":
            layout = self.store.project(self.view[1]).get("layout", "list")
            self.layout_buttons[layout].set_active(True)
            board = layout == "board"
        self.pages.set_visible_child_name("calendar" if calendar else "board" if board else "list")
        if calendar:
            self.rebuild_calendar()
            return
        if board:
            self.rebuild_board()
            return
        self.list.remove_all()
        groups = self.store.groups(self.view, self.show_done)
        if not groups:
            self.list.append(Gtk.ListBoxRow(child=Gtk.Label(label="All clear. Enjoy your day!",
                                                            css_classes=["empty"]),
                                            activatable=False, selectable=False))
        for heading, tasks in groups:
            if heading:
                self.list.append(Gtk.ListBoxRow(child=Gtk.Label(label=heading, xalign=0), activatable=False,
                                                css_classes=["group-head"]))
            for task in tasks:
                self.append_tree(task, 0)

    def append_tree(self, task, depth):
        self.list.append(self.task_row(task, depth))
        if self.view[0] != "project":
            return
        for child in self.store.children(task):
            if self.show_done or not child["done"]:
                self.append_tree(child, depth + 1)

    def rebuild_board(self):
        project = self.store.project(self.view[1])
        while child := self.board.get_first_child():
            self.board.remove(child)
        for section in [None, *self.store.sections(project)]:
            self.board.append(self.board_column(project, section))
        add = Gtk.Button(label="+  Add section", css_classes=["flat", "add-task"], valign=Gtk.Align.START)
        add.connect("clicked", lambda _b: NameDialog(
            self.get_root(), "Add section", "",
            lambda name: (self.store.add_section(project, name), self.reload()), "Section name").present())
        self.board.append(add)

    def board_column(self, project, section):
        section_id = section and section["id"]
        tasks = self.store.section_tasks(project["id"], section_id, self.show_done)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=280, valign=Gtk.Align.START,
                         css_classes=["board-column"])
        head = Gtk.Box(spacing=6)
        head.append(Gtk.Label(label=section["name"] if section else "No section", xalign=0, max_width_chars=22,
                              ellipsize=Pango.EllipsizeMode.END, css_classes=["column-name"]))
        count = sum(1 for t in tasks if not t["done"])
        head.append(Gtk.Label(label=str(count) if count else "", xalign=0, hexpand=True, css_classes=["count"]))
        if section:
            head.append(self.section_menu(project, section))
        column.append(head)
        for task in tasks:
            column.append(self.board_card(task))
        add = Gtk.Button(label="+  Add task", css_classes=["flat", "add-task"], halign=Gtk.Align.START)
        add.connect("clicked", lambda _b: TaskDialog(self, project=project["id"], section=section_id).present())
        column.append(add)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("enter", lambda *_: (column.add_css_class("drop-hover"), Gdk.DragAction.MOVE)[1])
        target.connect("leave", lambda *_: column.remove_css_class("drop-hover"))
        target.connect("drop", self.on_board_drop, section_id)
        column.add_controller(target)
        return column

    def board_card(self, task):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["board-card"])
        top = Gtk.Box(spacing=8)
        check = Gtk.CheckButton(active=task["done"], valign=Gtk.Align.START,
                                css_classes=["task-check", f"p{task['priority']}"])
        check.connect("toggled", self.on_check, task)
        top.append(check)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        title = Gtk.Label(xalign=0, wrap=True, max_width_chars=28)
        title.set_markup(title_markup(task))
        text.append(title)
        if task["description"]:
            text.append(Gtk.Label(label=task["description"], xalign=0, wrap=True, max_width_chars=28,
                                  css_classes=["task-desc"]))
        meta = self.task_meta(task)
        if meta:
            text.append(meta)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: TaskDialog(self, task).present())
        text.add_controller(click)
        top.append(text)
        copy = self.claude_button(task)
        copy.set_valign(Gtk.Align.START)
        copy.add_css_class("task-actions")
        top.append(copy)
        card.append(top)

        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(task["id"]))
        drag.connect("drag-begin", lambda source, _d: source.set_icon(Gtk.WidgetPaintable.new(card), 0, 0))
        card.add_controller(drag)
        return card

    def on_board_drop(self, target, task_id, _x, _y, section_id):
        target.get_widget().remove_css_class("drop-hover")
        task = self.store.find_task(task_id)
        if not task:
            return False
        self.store.move_to_section(task, section_id)
        GLib.idle_add(lambda: (self.reload(), False)[1])
        return True

    def rebuild_calendar(self):
        month = self.cal_month
        self.month_label.set_text(f"{MONTH_NAMES[month.month - 1]} {month.year}")
        while child := self.cal_grid.get_first_child():
            self.cal_grid.remove(child)
        for col, name in enumerate(DAY_NAMES):
            self.cal_grid.attach(Gtk.Label(label=name[:3], xalign=0, css_classes=["cal-weekday"]), col, 0, 1, 1)
        start = month - timedelta(days=month.weekday())
        weeks = (month.weekday() + monthrange(month.year, month.month)[1] + 6) // 7
        for i in range(weeks * 7):
            self.cal_grid.attach(self.day_cell(start + timedelta(days=i)), i % 7, 1 + i // 7, 1, 1)

    def day_cell(self, day):
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["cal-day"])
        if day.month != self.cal_month.month:
            cell.add_css_class("other-month")
        head = Gtk.Box(spacing=4)
        number = Gtk.Label(label=f"{day.day} {MONTH_NAMES[day.month - 1]}" if day.day == 1 else str(day.day),
                           css_classes=["cal-num"])
        if day == date.today():
            number.add_css_class("cal-today")
        head.append(number)
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add task", hexpand=True, halign=Gtk.Align.END,
                         css_classes=["flat", "circular", "cal-add"])
        add.connect("clicked", lambda _b: TaskDialog(self, due=day).present())
        head.append(add)
        cell.append(head)

        tasks = self.store.tasks_on(day, self.show_done)
        for task in tasks[:CALENDAR_VISIBLE]:
            cell.append(self.calendar_chip(task))
        hidden = tasks[CALENDAR_VISIBLE:]
        if hidden:
            more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, width_request=220)
            for task in hidden:
                more.append(self.calendar_chip(task))
            cell.append(Gtk.MenuButton(child=Gtk.Label(label=f"{len(hidden)} more"), has_frame=False,
                                       popover=Gtk.Popover(child=more), halign=Gtk.Align.START,
                                       css_classes=["cal-more"]))

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("enter", lambda *_: (cell.add_css_class("drop-hover"), Gdk.DragAction.MOVE)[1])
        target.connect("leave", lambda *_: cell.remove_css_class("drop-hover"))
        target.connect("drop", self.on_drop, day)
        cell.add_controller(target)
        return cell

    def calendar_chip(self, task):
        chip = Gtk.Box(spacing=4, css_classes=["cal-task"], tooltip_text=task["title"])
        check = Gtk.CheckButton(active=task["done"], css_classes=["task-check", f"p{task['priority']}"])
        check.connect("toggled", self.on_check, task)
        chip.append(check)
        title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        title.set_markup(title_markup(task))
        due = due_of(task)
        if not task["done"] and due < date.today():
            title.add_css_class("due-overdue")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: TaskDialog(self, task).present())
        title.add_controller(click)
        chip.append(title)

        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(task["id"]))
        drag.connect("drag-begin", lambda source, _d: source.set_icon(Gtk.WidgetPaintable.new(chip), 0, 0))
        chip.add_controller(drag)
        return chip

    def on_drop(self, target, task_id, _x, _y, day):
        target.get_widget().remove_css_class("drop-hover")
        task = self.store.find_task(task_id)
        if not task:
            return False
        self.store.move_task(task, day)
        GLib.idle_add(lambda: (self.reload(), False)[1])
        return True

    def shift_month(self, step):
        if step == 0:
            self.cal_month = date.today().replace(day=1)
        elif step < 0:
            self.cal_month = (self.cal_month - timedelta(days=1)).replace(day=1)
        else:
            self.cal_month = (self.cal_month + timedelta(days=31)).replace(day=1)
        self.rebuild_list()

    def task_meta(self, task):
        meta = Gtk.Box(spacing=12)
        due = due_of(task)
        if due:
            label, css = due_label(due)
            meta.append(Gtk.Label(label=f"\U0001F4C5 {label}", css_classes=["task-meta", css]))
        children = self.store.children(task)
        if children:
            done = sum(c["done"] for c in children)
            meta.append(Gtk.Label(label=f"☑ {done}/{len(children)}", tooltip_text="Sub-tasks",
                                  css_classes=["task-meta", "due-later"]))
        if self.view[0] != "project":
            parent = self.store.find_task(task.get("parent"))
            if parent:
                meta.append(Gtk.Label(label=f"↳ {parent['title']}", ellipsize=Pango.EllipsizeMode.END,
                                      css_classes=["task-meta", "due-later"]))
            project = self.store.project(task["project"])
            name = Gtk.Label(xalign=1, hexpand=True, css_classes=["task-meta"])
            name.set_markup(f'{GLib.markup_escape_text(project["name"])} '
                            f'<span foreground="{project["color"]}">●</span>')
            meta.append(name)
        return meta if meta.get_first_child() else None

    def task_row(self, task, depth=0):
        box = Gtk.Box(spacing=10, margin_start=depth * 28)
        check = Gtk.CheckButton(active=task["done"], valign=Gtk.Align.START,
                                css_classes=["task-check", f"p{task['priority']}"])
        check.connect("toggled", self.on_check, task)
        box.append(check)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        title = Gtk.Label(xalign=0, wrap=True)
        title.set_markup(title_markup(task))
        text.append(title)
        if task["description"]:
            text.append(Gtk.Label(label=task["description"], xalign=0, wrap=True, css_classes=["task-desc"]))
        meta = self.task_meta(task)
        if meta:
            text.append(meta)
        box.append(text)

        actions = Gtk.Box(spacing=2, valign=Gtk.Align.START, css_classes=["task-actions"])
        for icon, tip, handler in (("media-playback-start-symbolic", "Start a pomodoro on this task",
                                    lambda _b: self.on_focus(task["title"])),
                                   ("list-add-symbolic", "Add sub-task",
                                    lambda _b: TaskDialog(self, parent=task).present()),
                                   ("document-edit-symbolic", "Edit", lambda _b: TaskDialog(self, task).present()),
                                   ("user-trash-symbolic", "Delete", lambda _b: self.confirm(
                                       "Delete task?", f"“{task['title']}” will be permanently deleted.",
                                       lambda: (self.store.delete_task(task), self.reload())))):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat", "circular"])
            button.connect("clicked", handler)
            actions.append(button)
        actions.insert_child_after(self.claude_button(task), actions.get_first_child())
        box.append(actions)

        row = Gtk.ListBoxRow(child=box)
        row.task = task
        return row

    def claude_button(self, task):
        button = Gtk.Button(label="🤖", tooltip_text="Copy as an implementation plan for Claude",
                            css_classes=["flat", "circular", "claude-copy"])
        button.connect("clicked", self.copy_for_claude, task)
        return button

    def copy_for_claude(self, button, task):
        self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(claude_prompt(self.store, task)))
        button.set_label("✓")
        button.set_tooltip_text("Copied! Paste it into Claude")
        GLib.timeout_add(1500, lambda: (button.set_label("🤖"),
                                        button.set_tooltip_text("Copy as an implementation plan for Claude"),
                                        False)[2])

    def confirm(self, message, detail, action):
        dialog = Gtk.AlertDialog(message=message, detail=detail, buttons=["Cancel", "Delete"],
                                 cancel_button=0, default_button=1, modal=True)

        def finish(source, result):
            try:
                if source.choose_finish(result) == 1:
                    action()
            except GLib.Error:
                pass

        dialog.choose(self.get_root(), None, finish)

    def on_nav_selected(self, _listbox, row):
        view = getattr(row, "view", None)
        if view and view != self.view:
            self.view = view
            self.close_form()
            self.rebuild_list()

    def on_show_done(self, check):
        self.show_done = check.get_active()
        self.rebuild_list()

    def on_row_activated(self, _listbox, row):
        task = getattr(row, "task", None)
        if task:
            TaskDialog(self, task).present()

    def on_check(self, check, task):
        self.store.set_done(task, check.get_active())
        GLib.timeout_add(300, lambda: (self.reload(), False)[1])

    def open_form(self):
        kind, project_id = self.view
        if kind == "project":
            self.form.set_values(project=project_id)
        else:
            self.form.set_values(due=date.today())
        self.add_button.set_visible(False)
        self.form.set_visible(True)
        self.form.title.grab_focus()

    def close_form(self):
        self.form.set_visible(False)
        self.add_button.set_visible(True)

    def add_from_form(self, values):
        self.store.add_task(**values)
        self.form.title.set_text("")
        self.form.description.set_text("")
        self.reload()
        self.form.title.grab_focus()

    def add_project(self, name):
        project = self.store.add_project(name)
        self.view = ("project", project["id"])
        self.reload()
