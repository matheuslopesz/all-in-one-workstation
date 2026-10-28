import json
import os
import subprocess
from datetime import date

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

import workstation_runs as runs  # noqa: E402
from workstation_repos import RepoError, changes, display, remove_worktree  # noqa: E402
from workstation_theme import ACCENT, GREEN, ORANGE, PURPLE, RED  # noqa: E402

SERVICE = "all-in-one-workstation-agentd.service"
ORDER = ["needs_input", "running", "queued", "review", "failed", "done", "cancelled"]
OPEN_STATUSES = ("queued", "running", "needs_input")
AGENTS_CSS = f"""
.agents-sidebar {{ background: alpha(currentColor, 0.04); padding: 12px 8px; }}
.agents-sidebar list {{ background: transparent; }}
.agents-sidebar row {{ padding: 6px 8px; border-radius: 6px; }}
.run-title {{ font-weight: bold; }}
.run-meta {{ font-size: 12px; opacity: 0.65; }}
.run-status {{ font-weight: bold; }}
.run-status.needs_input {{ color: {ORANGE}; }}
.run-status.running {{ color: {PURPLE}; }}
.run-status.review {{ color: {ACCENT}; }}
.run-status.done {{ color: {GREEN}; }}
.run-status.failed {{ color: {RED}; }}
.approval {{ border: 1px solid alpha({ORANGE}, 0.6); border-radius: 8px; padding: 10px;
            background: alpha({ORANGE}, 0.10); }}
.approval-command {{ font-family: monospace; font-size: 12px; }}
textview.run-log, textview.run-log text {{ font-family: monospace; font-size: 12px; background: alpha(black, 0.2); }}
.daemon-off {{ color: {RED}; font-size: 12px; }}
.daemon-on {{ color: {GREEN}; font-size: 12px; }}
"""


def short_time(stamp):
    return stamp.replace("T", " ")[5:16] if stamp else ""


def tool_line(block):
    data = block.get("input") or {}
    detail = data.get("command") or data.get("file_path") or data.get("pattern") or data.get("path") or ""
    return f"🔧 {block.get('name')}: {' '.join(str(detail).split())[:300]}"


def event_lines(event):
    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        return [f"▶ session started · {event.get('model', '')}"]
    if kind == "assistant":
        lines = []
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                lines.append("💬 " + block["text"].strip())
            elif block.get("type") == "tool_use":
                lines.append(tool_line(block))
        return lines
    if kind == "user":
        lines = []
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                content = block.get("content")
                text = content if isinstance(content, str) else " ".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
                prefix = "   ⚠ " if block.get("is_error") else "   ↳ "
                lines.append(prefix + " ".join(text.split())[:240])
        return lines
    if kind == "result":
        cost = event.get("total_cost_usd")
        return [f"🏁 finished in {round((event.get('duration_ms') or 0) / 1000)}s"
                + (f" · ${cost:.2f}" if isinstance(cost, (int, float)) else "")]
    return []


class ChangesWindow(Gtk.Window):
    def __init__(self, parent, run):
        super().__init__(title=f"Changes · {run['task_title']}", transient_for=parent, default_width=900,
                         default_height=700)
        text = "\n\n".join(changes(entry) for entry in run["workspace"]) or "(no workspace)"
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE, css_classes=["run-log"])
        view.get_buffer().set_text(text)
        self.set_child(Gtk.ScrolledWindow(child=view))


class AgentsView(Gtk.Paned):
    def __init__(self, tasks_view):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, position=300,
                         shrink_start_child=False, resize_start_child=False)
        self.tasks_view = tasks_view
        self.selected = None
        self.snapshot = None
        self.statuses = {}
        self.log_offset = 0
        self.daemon_active = None
        self.set_start_child(self.build_sidebar())
        self.set_end_child(self.build_detail())
        self.tick()
        GLib.timeout_add_seconds(2, self.tick)
        self.check_daemon()
        GLib.timeout_add_seconds(10, self.check_daemon)

    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["agents-sidebar"])
        head = Gtk.Box(spacing=6)
        head.append(Gtk.Label(label="Agent runs", xalign=0, hexpand=True, css_classes=["run-title"]))
        self.daemon_label = Gtk.Label(label="", css_classes=["daemon-off"])
        head.append(self.daemon_label)
        self.daemon_button = Gtk.Button(label="Start", css_classes=["flat"], visible=False,
                                        tooltip_text=f"systemctl --user start {SERVICE}")
        self.daemon_button.connect("clicked", lambda _b: self.start_daemon())
        head.append(self.daemon_button)
        box.append(head)
        self.run_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.run_list.connect("row-selected", self.on_selected)
        box.append(Gtk.ScrolledWindow(child=self.run_list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.totals = Gtk.Label(xalign=0, css_classes=["run-meta"])
        box.append(self.totals)
        return box

    def build_detail(self):
        self.pages = Gtk.Stack()
        self.pages.add_named(Gtk.Label(label="No run selected.\nStart one with ▶ Run in a task.",
                                       justify=Gtk.Justification.CENTER, css_classes=["empty"]), "empty")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=20, margin_bottom=20,
                      margin_start=28, margin_end=28)
        self.title = Gtk.Label(xalign=0, wrap=True, css_classes=["view-title"])
        box.append(self.title)
        self.status = Gtk.Label(xalign=0, css_classes=["run-status"])
        box.append(self.status)
        self.meta = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["run-meta"])
        box.append(self.meta)
        self.approval = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["approval"])
        box.append(self.approval)
        self.actions = Gtk.Box(spacing=6)
        box.append(self.actions)
        self.summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(self.summary)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                css_classes=["run-log"])
        self.log_scroller = Gtk.ScrolledWindow(child=self.log, vexpand=True)
        box.append(self.log_scroller)
        self.pages.add_named(box, "run")
        return self.pages

    def tick(self):
        all_runs = runs.read_runs()
        snapshot = json.dumps(all_runs, sort_keys=True)
        if snapshot != self.snapshot:
            self.snapshot = snapshot
            self.notify_changes(all_runs)
            self.rebuild_list(all_runs)
            self.show_run(next((r for r in all_runs if r["id"] == self.selected), None), reset_log=False)
            self.tasks_view.reload()
        self.append_log()
        return True

    def notify_changes(self, all_runs):
        app = self.get_root().get_application() if self.get_root() else None
        for run in all_runs:
            before = self.statuses.get(run["id"])
            self.statuses[run["id"]] = run["status"]
            if app is None or before is None or before == run["status"]:
                continue
            if run["status"] == "needs_input":
                message = ("Agent needs your approval", f"{run['task_title']}: {(run.get('approval') or {}).get('reason', '')}")
            elif run["status"] in ("review", "failed"):
                message = (f"Agent run {runs.STATUS_LABELS[run['status']]}", run["task_title"])
            else:
                continue
            note = Gio.Notification.new(message[0])
            note.set_body(message[1])
            app.send_notification(f"run-{run['id']}", note)

    def rebuild_list(self, all_runs):
        self.run_list.remove_all()
        for status in ORDER:
            group = [r for r in reversed(all_runs) if r["status"] == status]
            if not group:
                continue
            head = Gtk.ListBoxRow(selectable=False, activatable=False,
                                  child=Gtk.Label(label=f"{runs.STATUS_LABELS[status]}  {len(group)}", xalign=0,
                                                  css_classes=["run-status", status]))
            self.run_list.append(head)
            for run in group:
                self.run_list.append(self.run_row(run))
        today = date.today().isoformat()
        spent = sum(r["cost"] or 0 for r in all_runs if (r.get("finished") or "").startswith(today))
        count = sum(1 for r in all_runs if (r.get("created") or "").startswith(today))
        self.totals.set_text(f"Today: {count} runs · ${spent:.2f} · Sonnet, one at a time")

    def run_row(self, run):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(Gtk.Label(label=run["task_title"], xalign=0, ellipsize=Pango.EllipsizeMode.END,
                             css_classes=["run-title"]))
        cost = f" · ${run['cost']:.2f}" if isinstance(run.get("cost"), (int, float)) else ""
        repos = ", ".join(display(w["identity"]) for w in run["workspace"])
        box.append(Gtk.Label(label=f"{short_time(run['created'])} · {repos}{cost}", xalign=0,
                             ellipsize=Pango.EllipsizeMode.END, css_classes=["run-meta"]))
        row = Gtk.ListBoxRow(child=box)
        row.run_id = run["id"]
        if run["id"] == self.selected:
            GLib.idle_add(lambda: (self.run_list.select_row(row), False)[1])
        return row

    def on_selected(self, _listbox, row):
        if row is None or getattr(row, "run_id", None) == self.selected:
            return
        self.selected = row.run_id
        self.show_run(runs.get(self.selected), reset_log=True)

    def select_run(self, run_id):
        self.selected = run_id
        self.snapshot = None
        self.tick()
        self.show_run(runs.get(run_id), reset_log=True)

    def show_run(self, run, reset_log):
        if run is None:
            self.pages.set_visible_child_name("empty")
            return
        self.pages.set_visible_child_name("run")
        self.title.set_text(run["task_title"])
        self.status.set_text(runs.STATUS_LABELS[run["status"]])
        self.status.set_css_classes(["run-status", run["status"]])
        lines = [f"🌳 {display(w['identity'])} · {w['branch']} · {w['path']}" for w in run["workspace"]]
        timing = f"created {short_time(run['created'])}"
        if run.get("started"):
            timing += f" · started {short_time(run['started'])}"
        if run.get("finished"):
            timing += f" · finished {short_time(run['finished'])}"
        if isinstance(run.get("cost"), (int, float)):
            timing += f" · ${run['cost']:.2f}"
        self.meta.set_text("\n".join([*lines, timing, *([f"⚠ {run['error']}"] if run.get("error") else [])]))
        self.rebuild_approval(run)
        self.rebuild_actions(run)
        self.summary.set_text(run.get("summary") or "")
        self.summary.set_visible(bool(run.get("summary")))
        if reset_log:
            self.log.get_buffer().set_text("")
            self.log_offset = 0
            self.append_log()

    def rebuild_approval(self, run):
        while child := self.approval.get_first_child():
            self.approval.remove(child)
        approval = run.get("approval")
        waiting = run["status"] == "needs_input" and approval and not approval.get("answer")
        self.approval.set_visible(bool(waiting))
        if not waiting:
            return
        self.approval.append(Gtk.Label(label=f"✋ The agent wants to run a {approval['reason']}:", xalign=0,
                                       css_classes=["run-title"]))
        self.approval.append(Gtk.Label(label=approval["command"], xalign=0, wrap=True, selectable=True,
                                       wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=["approval-command"]))
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        for label, allow, css in (("Deny", False, ["destructive-action"]), ("Approve", True, ["suggested-action"])):
            button = Gtk.Button(label=label, css_classes=css)
            button.connect("clicked", lambda _b, a=allow: (runs.answer_approval(run["id"], approval["id"], a),
                                                            self.tick()))
            buttons.append(button)
        self.approval.append(buttons)

    def rebuild_actions(self, run):
        while child := self.actions.get_first_child():
            self.actions.remove(child)
        entries = []
        if run["status"] in OPEN_STATUSES:
            entries.append(("Cancel", lambda: self.cancel(run)))
        entries.append(("Show changes", lambda: ChangesWindow(self.get_root(), run).present()))
        if run["workspace"]:
            entries.append(("Open folder", lambda: Gtk.FileLauncher.new(Gio.File.new_for_path(
                os.path.dirname(run["workspace"][0]["path"]))).launch(self.get_root(), None, None, None)))
        if run["status"] in ("review", "failed", "cancelled"):
            entries.append(("Mark done", lambda: runs.update(run["id"], status="done")))
            entries.append(("Done + remove worktrees", lambda: self.finish_and_clean(run)))
        for label, action in entries:
            button = Gtk.Button(label=label, css_classes=["flat"])
            button.connect("clicked", lambda _b, a=action: (a(), self.tick()))
            self.actions.append(button)

    def cancel(self, run):
        if run["status"] == "queued":
            runs.update(run["id"], status="cancelled", finished=runs.now())
        else:
            runs.update(run["id"], status="cancelled")

    def finish_and_clean(self, run):
        errors = []
        for entry in run["workspace"]:
            try:
                remove_worktree(entry)
            except RepoError as error:
                errors.append(f"{display(entry['identity'])}: {error}")
        runs.update(run["id"], status="done")
        store = self.tasks_view.store
        task = store.find_task(run["task_id"])
        if task and not errors:
            task.pop("workspace", None)
            store.save()
        if errors:
            Gtk.AlertDialog(message="Some worktrees were kept", detail="\n".join(errors) +
                            "\n\nThey have uncommitted changes or are in use; remove them by hand if you are sure.",
                            modal=True).show(self.get_root())

    def append_log(self):
        if not self.selected:
            return
        path = runs.log_path(self.selected)
        try:
            with open(path) as f:
                f.seek(self.log_offset)
                chunk = f.read()
                self.log_offset = f.tell()
        except OSError:
            return
        lines = []
        for raw in chunk.splitlines():
            try:
                lines += event_lines(json.loads(raw))
            except ValueError:
                if raw.strip():
                    lines.append(raw.strip()[:300])
        if lines:
            buffer = self.log.get_buffer()
            buffer.insert(buffer.get_end_iter(), "\n".join(lines) + "\n")
            adjustment = self.log_scroller.get_vadjustment()
            GLib.idle_add(lambda: (adjustment.set_value(adjustment.get_upper()), False)[1])

    def check_daemon(self):
        try:
            state = subprocess.run(["systemctl", "--user", "is-active", SERVICE], capture_output=True, text=True,
                                   timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            state = "unknown"
        active = state == "active"
        if active != self.daemon_active:
            self.daemon_active = active
            self.daemon_label.set_text("● agentd on" if active else "● agentd off")
            self.daemon_label.set_css_classes(["daemon-on" if active else "daemon-off"])
            self.daemon_button.set_visible(not active)
        return True

    def start_daemon(self):
        subprocess.run(["systemctl", "--user", "start", SERVICE], capture_output=True, timeout=15)
        self.daemon_active = None
        self.check_daemon()
