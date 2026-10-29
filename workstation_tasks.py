import os
import threading
from calendar import monthrange
from datetime import date, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from workstation_agent import PLAN_MODEL, PlanError, plan_prompt, run_plan  # noqa: E402

from workstation_store import (DAY_NAMES, INBOX, JIRA_BROWSE, MONTH_NAMES, PROJECTS_DIR, TASKS_FILE,  # noqa: E402
                               TaskStore, claude_prompt, due_of, jira_key, list_repos, short_date)
from workstation_theme import ACCENT, BG_DARKER, GREEN, ORANGE, PURPLE, RED  # noqa: E402
from workstation_todoist import Todoist, TodoistSync, load_token, save_token  # noqa: E402

CALENDAR_VISIBLE = 3
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
.sidebar row:selected {{ background: alpha({ACCENT}, 0.14); color: inherit; }}
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
.due-today {{ color: {GREEN}; }}
.due-tomorrow {{ color: {ORANGE}; }}
.due-week {{ color: {PURPLE}; }}
.due-overdue {{ color: {RED}; }}
.due-later {{ opacity: 0.7; }}
.task-actions {{ opacity: 0; transition: opacity 120ms; }}
row:hover .task-actions {{ opacity: 1; }}
.task-form {{ border: 1px solid alpha(currentColor, 0.2); border-radius: 10px; padding: 10px; }}
.title-entry {{ font-weight: bold; }}
.task-form button.suggested-action {{ background: {ACCENT}; color: {BG_DARKER}; border: none; box-shadow: none; }}
.add-task {{ color: {ACCENT}; font-weight: bold; }}
.empty {{ opacity: 0.5; padding: 30px; }}
.cal-weekday {{ font-weight: bold; font-size: 12px; opacity: 0.6; padding: 4px 6px; }}
.cal-day {{ border: 1px solid alpha(currentColor, 0.08); padding: 4px; min-height: 110px; }}
.cal-day.other-month {{ background: alpha(currentColor, 0.03); }}
.cal-day.other-month .cal-num {{ opacity: 0.4; }}
.cal-day.drop-hover {{ background: alpha({ACCENT}, 0.12); }}
.cal-num {{ font-size: 12px; font-weight: bold; padding: 2px 6px; border-radius: 10px; }}
.cal-num.cal-today {{ background: {ACCENT}; color: {BG_DARKER}; }}
.cal-add {{ opacity: 0; min-height: 20px; min-width: 20px; padding: 0; }}
.cal-day:hover .cal-add {{ opacity: 1; }}
.cal-task {{ font-size: 12px; padding: 1px 4px; border-radius: 4px; background: alpha(currentColor, 0.05); }}
.cal-task:hover {{ background: alpha(currentColor, 0.1); }}
.cal-task check {{ min-width: 12px; min-height: 12px; margin: 0; border-width: 1px; }}
.cal-more {{ font-size: 12px; padding: 0 4px; min-height: 0; }}
.month-label {{ font-weight: bold; }}
.board-column {{ background: alpha(currentColor, 0.04); border-radius: 10px; padding: 8px; }}
.board-column.drop-hover {{ background: alpha({ACCENT}, 0.12); }}
.column-name {{ font-weight: bold; }}
.board-card {{ border: 1px solid alpha(currentColor, 0.12); border-radius: 8px; padding: 8px;
              background: alpha(currentColor, 0.03); }}
.board-card:hover {{ border-color: alpha(currentColor, 0.3); }}
.board-card.drop-before {{ box-shadow: 0 -5px 0 -2px {ACCENT}; }}
.board-card.drop-after {{ box-shadow: 0 5px 0 -2px {ACCENT}; }}
.subtasks-head {{ font-weight: bold; font-size: 13px; }}
label.card-subtask {{ font-size: 12px; }}
.card-subtask check {{ min-width: 14px; min-height: 14px; }}
.task-check.priority check {{ border-color: {RED}; background: alpha({RED}, 0.12); }}
.task-check.priority check:checked {{ background: {RED}; color: {BG_DARKER}; }}
.board-card.priority {{ background-image: linear-gradient(160deg, alpha({RED}, 0.20), alpha({RED}, 0.05));
                       border-color: alpha({RED}, 0.35); }}
.task-list row.priority {{ background-image: linear-gradient(160deg, alpha({RED}, 0.16), alpha({RED}, 0.03)); }}
.cal-task.priority {{ background: alpha({RED}, 0.18); }}
.task-list row.drop-before {{ box-shadow: inset 0 3px 0 0 {ACCENT}; }}
.task-list row.drop-after {{ box-shadow: inset 0 -3px 0 0 {ACCENT}; }}
.task-context {{ font-size: 13px; opacity: 0.8; }}
.notes-head {{ font-weight: bold; font-size: 13px; margin-top: 4px; }}
.task-note {{ font-size: 13px; padding: 6px 8px; border-radius: 6px; background: alpha(currentColor, 0.04); }}
.task-note.claude {{ background: alpha({PURPLE}, 0.10); }}
.task-note-meta {{ font-size: 11px; opacity: 0.6; }}
.plan-button:disabled {{ opacity: 0.7; }}
.plan-desc {{ font-size: 12px; opacity: 0.7; }}
.plan-context {{ font-size: 12px; padding: 8px; border-radius: 6px; background: alpha({PURPLE}, 0.10); }}
.sync-button {{ margin-top: 8px; font-size: 13px; }}
.priority-toggle:checked {{ background: alpha({RED}, 0.22); color: {RED}; }}
"""


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


def check_classes(task, *extra):
    return ["task-check", *extra, *(["priority"] if task["priority"] else [])]


def repo_name(path):
    if not path:
        return None
    path = path.rstrip("/")
    return os.path.relpath(path, PROJECTS_DIR) if path.startswith(PROJECTS_DIR + os.sep) else os.path.basename(path)


def title_markup(task):
    escaped = ("🤖 " if task.get("by_claude") else "") + GLib.markup_escape_text(task["title"])
    return f'<span strikethrough="true" alpha="50%">{escaped}</span>' if task["done"] else escaped


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
        elif word in ("!", "p1"):
            priority = True
        elif word.startswith("#") and len(word) > 1:
            match = next((p for p in projects if p["name"].lower().replace(" ", "") == word[1:]), None)
            if match:
                project = match["id"]
            else:
                kept.append(token)
        else:
            kept.append(token)
    return " ".join(kept), due, priority, project


class TaskForm(Gtk.Box):
    def __init__(self, store, on_submit, on_cancel, submit_label="Add task"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["task-form"])
        self.store = store
        self.on_submit = on_submit
        self.due = None

        self.title = Gtk.Entry(placeholder_text="Task name   e.g. Pay rent tomorrow ! #Home",
                               css_classes=["title-entry"])
        self.description = Gtk.Entry(placeholder_text="Description")
        for entry in (self.title, self.description):
            entry.connect("activate", lambda _e: self.submit())
        self.append(self.title)
        self.append(self.description)

        chips = Gtk.Box(spacing=6)
        self.due_button = Gtk.MenuButton(popover=self.build_due_popover())
        self.priority = Gtk.ToggleButton(label="🔥 Urgent", css_classes=["priority-toggle"])
        self.project = Gtk.DropDown()
        self.repos = [None, *list_repos()]
        self.repo = Gtk.DropDown.new_from_strings(["Repo: inherit", *map(repo_name, self.repos[1:])])
        self.repo.set_tooltip_text("Git repo for this task (sub-tasks and the project default are inherited)")
        chips.append(self.due_button)
        chips.append(self.priority)
        chips.append(self.project)
        chips.append(self.repo)
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

    def set_values(self, title="", description="", due=None, priority=False, project=INBOX, repo=None):
        self.title.set_text(title)
        self.description.set_text(description)
        self.set_due(due)
        self.priority.set_active(priority)
        self.project_ids = [p["id"] for p in self.store.projects]
        self.project.set_model(Gtk.StringList.new([p["name"] for p in self.store.projects]))
        self.project.set_selected(self.project_ids.index(project) if project in self.project_ids else 0)
        if repo and repo not in self.repos:
            self.repos.append(repo)
            self.repo.get_model().append(repo_name(repo))
        self.repo.set_selected(self.repos.index(repo))
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
            "priority": priority or self.priority.get_active(),
            "project": project or self.project_ids[self.project.get_selected()],
            "repo": self.repos[self.repo.get_selected()],
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
            form.set_values(task["title"], task["description"], due_of(task), task["priority"], task["project"],
                            task.get("repo"))
        else:
            form.set_values(due=due, project=parent["project"] if parent else project)
        form.project.set_sensitive(not parent and not (task and not view.store.is_root(task)))
        box.append(form)
        if task:
            self.context = Gtk.Label(xalign=0, wrap=True, css_classes=["task-context"])
            box.append(self.context)
            self.subtasks = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.append(self.subtasks)
            self.notes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(self.notes)
            self.rebuild_subtasks()
            view.dialogs.add(self)
            self.connect("close-request", lambda _w: view.dialogs.discard(self) or False)
        self.set_child(box)

    def refresh(self):
        if self.view.store.find_task(self.task["id"]) is not self.task:
            self.close()
            return
        self.rebuild_subtasks()

    def rebuild_context(self):
        parts = []
        repo = self.view.store.repo(self.task)
        if repo:
            inherited = "" if self.task.get("repo") else " (inherited)"
            parts.append(f"📁 {GLib.markup_escape_text(repo_name(repo))}{inherited}")
        key = jira_key(self.task)
        if key:
            parts.append(f'🔗 <a href="{JIRA_BROWSE}{key}">{key}</a>')
        self.context.set_markup("   ·   ".join(parts))
        self.context.set_visible(bool(parts))

    def rebuild_notes(self):
        while child := self.notes.get_first_child():
            self.notes.remove(child)
        self.notes.append(Gtk.Label(label="Notes", xalign=0, css_classes=["notes-head"]))
        entry = Gtk.Entry(placeholder_text="Add a note and press Enter")
        entry.connect("activate", self.on_note)
        self.notes.append(entry)
        for note in reversed(self.task.get("notes") or []):
            claude = note["author"] == "claude"
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                           css_classes=["task-note", *(["claude"] if claude else [])])
            card.append(Gtk.Label(label=f"{'🤖 Claude' if claude else '📝 You'} · {note['at'].replace('T', ' ')[:16]}",
                                  xalign=0, css_classes=["task-note-meta"]))
            card.append(Gtk.Label(label=note["text"], xalign=0, wrap=True, selectable=True))
            self.notes.append(card)

    def on_note(self, entry):
        text = entry.get_text().strip()
        if text:
            self.view.store.add_note(self.task, text)
            self.rebuild_notes()

    def rebuild_subtasks(self):
        while child := self.subtasks.get_first_child():
            self.subtasks.remove(child)
        children = self.view.store.children(self.task)
        done = sum(c["done"] for c in children)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label=f"Sub-tasks  {done}/{len(children)}" if children else "Sub-tasks",
                              xalign=0, hexpand=True, css_classes=["subtasks-head"]))
        if self.view.store.is_root(self.task) and self.view.store.repo(self.task):
            head.append(self.view.plan_button(self.task))
        head.append(self.view.claude_button(self.task))
        self.subtasks.append(head)
        for child in children:
            row = Gtk.Box(spacing=8)
            check = Gtk.CheckButton(active=child["done"], css_classes=check_classes(child))
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
        self.rebuild_context()
        self.rebuild_notes()

    def on_check(self, check, child):
        self.view.store.set_done(child, check.get_active())
        self.view.reload()
        GLib.idle_add(lambda: (self.rebuild_subtasks(), False)[1])

    def save(self, values):
        if self.task:
            self.view.dialogs.discard(self)
            self.view.store.update_task(self.task, **values)
        else:
            self.view.store.add_task(**values, section=self.section,
                                     parent=self.parent["id"] if self.parent else None)
        self.view.reload()
        if self.on_change:
            self.on_change()
        self.close()


class PlanDialog(Gtk.Window):
    def __init__(self, view, task, plan):
        super().__init__(title="Plan suggestions", transient_for=view.get_root(), modal=True, default_width=560,
                         default_height=560)
        self.view = view
        self.task = task
        self.plan = plan
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                      margin_start=14, margin_end=14)
        box.append(Gtk.Label(label=f"🤖 Suggested sub-tasks for “{task['title']}”", xalign=0, wrap=True,
                             css_classes=["subtasks-head"]))
        items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.checks = []
        for suggestion in plan["subtasks"]:
            check = Gtk.CheckButton(active=True)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.append(Gtk.Label(label=suggestion["title"], xalign=0, wrap=True))
            if suggestion["description"]:
                text.append(Gtk.Label(label=suggestion["description"], xalign=0, wrap=True, css_classes=["plan-desc"]))
            check.set_child(text)
            items.append(check)
            self.checks.append((check, suggestion))
        if plan["context"]:
            items.append(Gtk.Label(label="Context (saved as a note)", xalign=0, css_classes=["notes-head"]))
            items.append(Gtk.Label(label=plan["context"], xalign=0, wrap=True, selectable=True,
                                   css_classes=["plan-context"]))
        box.append(Gtk.ScrolledWindow(child=items, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        buttons = Gtk.Box(spacing=8)
        cost = f" · ${plan['cost']:.2f}" if isinstance(plan.get("cost"), (int, float)) else ""
        buttons.append(Gtk.Label(label=f"{PLAN_MODEL.capitalize()}, read-only{cost}", xalign=0, hexpand=True,
                                 css_classes=["task-note-meta"]))
        cancel = Gtk.Button(label="Discard")
        cancel.connect("clicked", lambda _b: self.close())
        add = Gtk.Button(label="Add selected", css_classes=["suggested-action"])
        add.connect("clicked", lambda _b: self.accept())
        buttons.append(cancel)
        buttons.append(add)
        box.append(buttons)
        self.set_child(box)

    def accept(self):
        store = self.view.store
        for check, suggestion in self.checks:
            if check.get_active():
                store.add_task(suggestion["title"], suggestion["description"], parent=self.task["id"], by_claude=True)
        if self.plan["context"]:
            store.add_note(self.task, self.plan["context"], author="claude")
        self.view.reload()
        self.view.refresh_dialogs()
        self.close()


class RepoDialog(Gtk.Window):
    def __init__(self, parent, project, on_submit):
        super().__init__(title="Project repo", transient_for=parent, modal=True, default_width=360, resizable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        box.append(Gtk.Label(label=f"Default git repo for tasks in “{project['name']}”", xalign=0, wrap=True))
        repos = [None, *list_repos()]
        if project.get("repo") and project["repo"] not in repos:
            repos.append(project["repo"])
        picker = Gtk.DropDown.new_from_strings(["No repo", *map(repo_name, repos[1:])])
        picker.set_selected(repos.index(project.get("repo")))
        box.append(picker)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        ok = Gtk.Button(label="Save", css_classes=["suggested-action"])
        ok.connect("clicked", lambda _b: (on_submit(repos[picker.get_selected()]), self.close()))
        buttons.append(cancel)
        buttons.append(ok)
        box.append(buttons)
        self.set_child(box)


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
        self.store.on_external = lambda: GLib.idle_add(self.on_store_merged)
        self.dialogs = set()
        self.planning = set()
        self.syncing = False
        self.disk_timer = 0
        self.monitor = Gio.File.new_for_path(os.path.dirname(TASKS_FILE)).monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect("changed", self.on_disk_event)
        self.view = ("project", INBOX)
        self.show_done = False
        self.cal_month = date.today().replace(day=1)
        self.set_start_child(self.build_sidebar())
        self.set_end_child(self.build_content())
        self.reload()

    def build_sidebar(self):
        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.connect("row-selected", self.on_nav_selected)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self.nav)
        self.sync_button = Gtk.Button(label="⟳  Sync with Todoist", css_classes=["flat", "sync-button"])
        self.sync_button.connect("clicked", lambda _b: self.start_sync())
        self.update_sync_tooltip()
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["sidebar"], width_request=200)
        sidebar.append(scroller)
        sidebar.append(self.sync_button)
        return sidebar

    def update_sync_tooltip(self, error=None):
        synced_at = self.store.data.get("todoist_synced_at")
        last = f"Last sync: {synced_at.replace('T', ' ')[:16]}" if synced_at else "Never synced"
        self.sync_button.set_tooltip_text(f"{error}\n{last}" if error else last)
        self.sync_button.set_label("⚠  Sync failed" if error else "⟳  Sync with Todoist")

    def start_sync(self):
        token = load_token()
        if not token:
            NameDialog(self.get_root(), "Todoist API token", "", lambda t: (save_token(t), self.start_sync()),
                       "Todoist → Settings → Integrations → Developer").present()
            return
        self.set_sensitive(False)
        self.syncing = True
        self.sync_button.set_label("Syncing…")
        threading.Thread(target=self.run_sync, args=(token,), daemon=True).start()

    def run_sync(self, token):
        try:
            TodoistSync(self.store.data, Todoist(token)).run()
            error = None
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        GLib.idle_add(self.finish_sync, error)

    def finish_sync(self, error):
        self.syncing = False
        self.store.save()
        self.set_sensitive(True)
        self.update_sync_tooltip(error)
        if error and "token" in error.lower():
            save_token("")
        self.reload()
        return False

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
        self.marked_row = None
        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("motion", self.on_list_motion)
        target.connect("leave", lambda *_: self.mark_list_row(None))
        target.connect("drop", self.on_list_drop)
        self.list.add_controller(target)
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
        self.layout_toggle = Gtk.Box(spacing=8, margin_end=24)
        self.layout_buttons = {}
        group = None
        for layout, label in (("list", "📋 List"), ("board", "🗂️ Board")):
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
                                 lambda: (self.store.delete_project(project), self.reload())),
            ("Repo…", lambda: RepoDialog(self.get_root(), project,
                                         lambda repo: self.store.set_project_repo(project, repo)).present()))

    def section_menu(self, project, section):
        return self.item_menu(
            lambda: NameDialog(self.get_root(), "Rename section", section["name"],
                               lambda name: (self.store.rename_section(section, name), self.reload()),
                               "Section name").present(),
            lambda: (self.store.delete_section(project, section), self.reload()))

    def item_menu(self, on_rename, on_delete, *extra):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popover = Gtk.Popover(child=box)
        for label, css, action in (("Rename", ["flat"], on_rename),
                                   *((label, ["flat"], action) for label, action in extra),
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
        sections = self.store.sections(project)
        if sections:
            self.store.adopt_loose_tasks(project)
        for section in sections or [None]:
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
        cards = []
        for task in tasks:
            card = self.board_card(task)
            column.append(card)
            cards.append((card, task))
        add = Gtk.Button(label="+  Add task", css_classes=["flat", "add-task"], halign=Gtk.Align.START)
        add.connect("clicked", lambda _b: TaskDialog(self, project=project["id"], section=section_id).present())
        column.append(add)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("enter", lambda *_: (column.add_css_class("drop-hover"), Gdk.DragAction.MOVE)[1])
        target.connect("motion", self.on_board_motion, cards)
        target.connect("leave", lambda *_: (column.remove_css_class("drop-hover"), self.mark_drop_slot(cards, None)))
        target.connect("drop", self.on_board_drop, section_id, cards)
        column.add_controller(target)
        return column

    def drop_slot(self, column, cards, y):
        """Index of the card the drop lands before (len(cards) means after the last one)."""
        for index, (card, _task) in enumerate(cards):
            ok, bounds = card.compute_bounds(column)
            if ok and y < bounds.get_y() + bounds.get_height() / 2:
                return index
        return len(cards)

    def mark_drop_slot(self, cards, slot):
        for index, (card, _task) in enumerate(cards):
            card.remove_css_class("drop-before")
            card.remove_css_class("drop-after")
            if index == slot:
                card.add_css_class("drop-before")
            elif slot == len(cards) and index == slot - 1:
                card.add_css_class("drop-after")

    def on_board_motion(self, target, _x, y, cards):
        self.mark_drop_slot(cards, self.drop_slot(target.get_widget(), cards, y))
        return Gdk.DragAction.MOVE

    def board_card(self, task):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       css_classes=["board-card", *(["priority"] if task["priority"] else [])])
        top = Gtk.Box(spacing=8)
        check = Gtk.CheckButton(active=task["done"], valign=Gtk.Align.START,
                                css_classes=check_classes(task))
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
        self.append_card_subtasks(card, task, 1)
        self.add_urgent_menu(card, task)

        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(task["id"]))
        drag.connect("drag-begin", lambda source, _d: source.set_icon(Gtk.WidgetPaintable.new(card), 0, 0))
        card.add_controller(drag)
        return card

    def append_card_subtasks(self, card, task, depth):
        for child in self.store.children(task):
            if child["done"] and not self.show_done:
                continue
            row = Gtk.Box(spacing=6, margin_start=depth * 18)
            check = Gtk.CheckButton(active=child["done"], valign=Gtk.Align.START,
                                    css_classes=check_classes(child, "card-subtask"))
            check.connect("toggled", self.on_check, child)
            row.append(check)
            title = Gtk.Label(xalign=0, hexpand=True, wrap=True, max_width_chars=26, css_classes=["card-subtask"])
            title.set_markup(title_markup(child))
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, c=child: TaskDialog(self, c).present())
            title.add_controller(click)
            row.append(title)
            self.add_urgent_menu(row, child)
            card.append(row)
            self.append_card_subtasks(card, child, depth + 1)

    def on_board_drop(self, target, task_id, _x, y, section_id, cards):
        column = target.get_widget()
        column.remove_css_class("drop-hover")
        task = self.store.find_task(task_id)
        if not task:
            return False
        slot = self.drop_slot(column, cards, y)
        self.mark_drop_slot(cards, None)
        before = cards[slot][1] if slot < len(cards) else None
        self.store.move_to_section(task, section_id, before)
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
        chip = Gtk.Box(spacing=4, css_classes=["cal-task", *(["priority"] if task["priority"] else [])],
                       tooltip_text=task["title"])
        check = Gtk.CheckButton(active=task["done"], css_classes=check_classes(task))
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
        self.add_urgent_menu(chip, task)

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
        key = jira_key(task)
        if key:
            link = Gtk.Label(css_classes=["task-meta", "due-later"])
            link.set_markup(f'<a href="{JIRA_BROWSE}{key}">{key}</a>')
            meta.append(link)
        if task["id"] in self.planning:
            meta.append(Gtk.Label(label="⏳ planning…", css_classes=["task-meta", "due-week"]))
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
                                css_classes=check_classes(task))
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
        if task["priority"]:
            row.add_css_class("priority")
        row.task = task
        self.add_urgent_menu(row, task)
        if self.view[0] == "project" and depth == 0 and not task["done"]:
            drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
            drag.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(task["id"]))
            drag.connect("drag-begin", lambda source, _d: source.set_icon(Gtk.WidgetPaintable.new(box), 0, 0))
            row.add_controller(drag)
        return row

    def add_urgent_menu(self, widget, task):
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self.open_urgent_menu, widget, task)
        widget.add_controller(click)

    def open_urgent_menu(self, gesture, _n_press, x, y, widget, task):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        spot = Gdk.Rectangle()
        spot.x, spot.y, spot.width, spot.height = int(x), int(y), 1, 1
        button = Gtk.Button(label="Unmark urgent" if task["priority"] else "🔥 Mark as urgent", css_classes=["flat"])
        popover = Gtk.Popover(child=button, has_arrow=False, pointing_to=spot)
        popover.set_parent(widget)
        popover.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        button.connect("clicked", lambda _b: (popover.popdown(), self.store.set_priority(task, not task["priority"]),
                                              GLib.idle_add(lambda: (self.reload(), False)[1])))
        popover.popup()

    def list_drop_spot(self, y):
        row = self.list.get_row_at_y(int(y))
        task = getattr(row, "task", None)
        if self.view[0] != "project" or not task or task["done"] or not self.store.is_root(task):
            return None
        ok, bounds = row.compute_bounds(self.list)
        return row, task, ok and y >= bounds.get_y() + bounds.get_height() / 2

    def mark_list_row(self, spot):
        if self.marked_row:
            self.marked_row.remove_css_class("drop-before")
            self.marked_row.remove_css_class("drop-after")
        self.marked_row = spot and spot[0]
        if spot:
            spot[0].add_css_class("drop-after" if spot[2] else "drop-before")

    def on_list_motion(self, _target, _x, y):
        self.mark_list_row(self.list_drop_spot(y))
        return Gdk.DragAction.MOVE

    def on_list_drop(self, _target, task_id, _x, y):
        spot = self.list_drop_spot(y)
        self.mark_list_row(None)
        task = self.store.find_task(task_id)
        if not spot or not task or spot[1] is task:
            return False
        _row, anchor, after = spot
        before = self.store.next_in_section(anchor, task) if after else anchor
        self.store.move_to_section(task, anchor.get("section"), before)
        GLib.idle_add(lambda: (self.reload(), False)[1])
        return True

    def plan_button(self, task):
        busy = task["id"] in self.planning
        button = Gtk.Button(label="⏳ Planning…" if busy else "✨ Plan", sensitive=not busy,
                            tooltip_text=f"Ask a read-only {PLAN_MODEL.capitalize()} agent to suggest sub-tasks",
                            css_classes=["flat", "plan-button"])
        button.connect("clicked", lambda _b: self.start_plan(task))
        return button

    def start_plan(self, task):
        repo = self.store.repo(task)
        self.planning.add(task["id"])
        self.reload()
        self.refresh_dialogs()
        threading.Thread(target=self.run_plan, args=(task, repo), daemon=True).start()

    def run_plan(self, task, repo):
        try:
            plan, error = run_plan(plan_prompt(self.store, task), repo), None
        except PlanError as exc:
            plan, error = None, str(exc)
        except Exception as exc:  # noqa: BLE001
            plan, error = None, f"Unexpected error: {exc}"
        GLib.idle_add(self.finish_plan, task, plan, error)

    def finish_plan(self, task, plan, error):
        self.planning.discard(task["id"])
        self.reload()
        self.refresh_dialogs()
        app = self.get_root().get_application() if self.get_root() else None
        if app:
            note = Gio.Notification.new("Plan failed" if error else "Plan ready")
            note.set_body(f"{task['title']}: {error}" if error else
                          f"{len(plan['subtasks'])} sub-tasks suggested for “{task['title']}”")
            app.send_notification(f"plan-{task['id']}", note)
        if error:
            Gtk.AlertDialog(message="The plan agent failed", detail=error, modal=True).show(self.get_root())
        else:
            PlanDialog(self, task, plan).present()
        return False

    def refresh_dialogs(self):
        for dialog in list(self.dialogs):
            dialog.refresh()

    def on_disk_event(self, _monitor, file, other, _event):
        names = {f.get_basename() for f in (file, other) if f}
        if os.path.basename(TASKS_FILE) not in names:
            return
        if self.disk_timer:
            GLib.source_remove(self.disk_timer)
        self.disk_timer = GLib.timeout_add(300, self.on_disk_changed)

    def on_disk_changed(self):
        self.disk_timer = 0
        if not self.syncing and self.store.refresh():
            self.on_store_merged()
        return False

    def on_store_merged(self):
        self.reload()
        self.refresh_dialogs()
        return False

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
