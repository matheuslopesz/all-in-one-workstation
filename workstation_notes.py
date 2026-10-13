import os
import re
from datetime import date

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

NOTES_DIR = os.path.join(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or GLib.get_home_dir(),
                         "Workstation Notes")
ACCENT = "#7f6df2"
LINK_RE = re.compile(r"\[\[([^\]|#\n]+)([#|][^\]\n]*)?\]\]")
URL_LINK_RE = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
HEADING_RE = re.compile(r"^(#{1,6}) ")
TASK_RE = re.compile(r"^\s*[-*+] \[([ xX])\] ")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.) ")
INLINE_RULES = [
    (re.compile(r"`[^`\n]+`"), "code", 1),
    (re.compile(r"\*\*[^*\n]+\*\*"), "bold", 2),
    (re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])|(?<!\w)_[^_\n]+_(?!\w)"), "italic", 1),
    (re.compile(r"~~[^~\n]+~~"), "strike", 2),
    (re.compile(r"==[^=\n]+=="), "mark", 2),
    (URL_LINK_RE, "link", 0),
    (re.compile(r"(?<!\S)#[\w/-]+"), "hashtag", 0),
]
TAGS = {
    "h1": {"weight": 800, "scale": 1.8},
    "h2": {"weight": 800, "scale": 1.5},
    "h3": {"weight": 700, "scale": 1.3},
    "h4": {"weight": 700, "scale": 1.15},
    "h5": {"weight": 700, "scale": 1.05},
    "h6": {"weight": 700},
    "bold": {"weight": 700},
    "italic": {"style": Pango.Style.ITALIC},
    "strike": {"strikethrough": True},
    "mark": {"background": "rgba(255,208,0,0.35)"},
    "code": {"family": "monospace", "background": "rgba(127,127,127,0.15)"},
    "code_block": {"family": "monospace", "paragraph_background": "rgba(127,127,127,0.10)"},
    "link": {"foreground": ACCENT, "underline": Pango.Underline.SINGLE},
    "hashtag": {"foreground": ACCENT, "background": "rgba(127,109,242,0.12)"},
    "syntax": {"foreground": "rgba(128,128,128,0.75)"},
    "quote": {"foreground": "rgba(128,128,128,1)", "style": Pango.Style.ITALIC, "left_margin": 16},
    "bullet": {"foreground": ACCENT, "weight": 700},
    "done": {"strikethrough": True, "foreground": "rgba(128,128,128,1)"},
}
WELCOME = """# Welcome

Notes are plain **Markdown** files in this folder, so you can also open it as an Obsidian vault.

- Link notes with [[double brackets]] and *Ctrl+click* to follow (missing notes are created)
- Notes that link here show up under **Linked mentions**
- Use the calendar button for today's daily note
- Also: `code`, ==highlight==, ~~strike~~, #tags, > quotes and - [ ] tasks
"""

NOTES_CSS = f"""
.notes-sidebar {{ background: alpha(currentColor, 0.04); padding: 10px 8px; }}
.notes-sidebar list {{ background: transparent; }}
.notes-sidebar row {{ padding: 6px 10px; border-radius: 6px; }}
.notes-sidebar row:selected {{ background: alpha({ACCENT}, 0.16); color: inherit; }}
.note-name {{ font-weight: bold; }}
.note-preview {{ font-size: 12px; opacity: 0.55; }}
entry.note-title {{ background: transparent; border: none; box-shadow: none; outline: none;
                   font-size: 26px; font-weight: 800; padding: 0; }}
textview.note-body, textview.note-body text {{ background: transparent; font-size: 15px; }}
.backlink {{ color: {ACCENT}; }}
"""


def safe_title(title):
    return re.sub(r'[\\/:*?"<>|]', "-", title).strip().lstrip(".")


def preview_of(text):
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return re.sub(r"[*_`=~\[\]]", "", line)
    return ""


class NoteStore:
    def __init__(self):
        if not os.path.isdir(NOTES_DIR):
            os.makedirs(NOTES_DIR)
            self.write("Welcome", WELCOME)

    def path(self, title):
        return os.path.join(NOTES_DIR, f"{title}.md")

    def exists(self, title):
        return os.path.exists(self.path(title))

    def titles(self):
        names = [n for n in os.listdir(NOTES_DIR) if n.endswith(".md")]
        names.sort(key=lambda n: os.path.getmtime(os.path.join(NOTES_DIR, n)), reverse=True)
        return [n[:-3] for n in names]

    def read(self, title):
        try:
            with open(self.path(title), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def write(self, title, text):
        tmp = self.path(title) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self.path(title))

    def create(self, title="Untitled", text=""):
        base, title, n = title, title, 1
        while self.exists(title):
            title = f"{base} {n}"
            n += 1
        self.write(title, text)
        return title

    def rename(self, old, new):
        os.rename(self.path(old), self.path(new))
        for title in self.titles():
            text = self.read(title)
            updated = LINK_RE.sub(lambda m: f"[[{new}{m.group(2) or ''}]]" if m.group(1).strip() == old
                                  else m.group(0), text)
            if updated != text:
                self.write(title, updated)

    def trash(self, title):
        Gio.File.new_for_path(self.path(title)).trash(None)

    def backlinks(self, target):
        return [t for t in self.titles() if t != target
                and any(m.group(1).strip() == target for m in LINK_RE.finditer(self.read(t)))]


class NotesView(Gtk.Paned):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, position=240,
                         shrink_start_child=False, resize_start_child=False)
        self.store = NoteStore()
        self.current = None
        self.loading = False
        self.syncing_list = False
        self.save_id = None
        self.set_start_child(self.build_sidebar())
        self.set_end_child(self.build_editor())

        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        shortcuts.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>n"),
                                            action=Gtk.CallbackAction.new(lambda *_: self.new_note() or True)))
        self.add_controller(shortcuts)

        titles = self.store.titles()
        self.open_note(titles[0] if titles else None)

    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["notes-sidebar"],
                      width_request=200)
        top = Gtk.Box(spacing=4)
        self.search = Gtk.SearchEntry(placeholder_text="Search notes", hexpand=True)
        self.search.connect("search-changed", lambda _e: self.rebuild_list())
        top.append(self.search)
        for icon, tip, handler in (("x-office-calendar-symbolic", "Today's daily note", self.open_daily),
                                   ("document-new-symbolic", "New note (Ctrl+N)", self.new_note)):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            button.connect("clicked", lambda _b, h=handler: h())
            top.append(button)
        box.append(top)

        self.note_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.note_list.connect("row-selected", self.on_row_selected)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self.note_list)
        box.append(scroller)
        return box

    def build_editor(self):
        self.pages = Gtk.Stack()
        self.pages.add_named(Gtk.Label(label="No note selected. Press Ctrl+N to create one.",
                                       css_classes=["empty"]), "empty")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24, margin_bottom=24,
                      margin_start=40, margin_end=40)
        head = Gtk.Box(spacing=8)
        self.title_entry = Gtk.Entry(hexpand=True, css_classes=["note-title"])
        self.title_entry.connect("activate", lambda _e: (self.commit_title(), self.body.grab_focus()))
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda _c: self.commit_title())
        self.title_entry.add_controller(focus)
        head.append(self.title_entry)
        head.append(self.note_menu())
        box.append(head)

        self.buffer = Gtk.TextBuffer()
        for name, props in TAGS.items():
            self.buffer.create_tag(name, **props)
        self.buffer.connect("changed", self.on_changed)
        self.body = Gtk.TextView(buffer=self.buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 pixels_below_lines=4, css_classes=["note-body"],
                                 tooltip_text="Ctrl+click a link to open it")
        click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self.on_body_click)
        self.body.add_controller(click)
        body_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        body_scroller.set_child(self.body)
        box.append(body_scroller)

        self.backlinks = Gtk.Expander(expanded=True)
        self.backlink_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6)
        backlink_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                               max_content_height=160)
        backlink_scroller.set_child(self.backlink_list)
        self.backlinks.set_child(backlink_scroller)
        box.append(Gtk.Separator())
        box.append(self.backlinks)
        self.pages.add_named(box, "editor")
        return self.pages

    def note_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popover = Gtk.Popover(child=box)
        folder = Gtk.Button(label="Open notes folder", css_classes=["flat"])
        folder.connect("clicked", lambda _b: (popover.popdown(), Gtk.FileLauncher.new(
            Gio.File.new_for_path(NOTES_DIR)).launch(self.get_root(), None, None, None)))
        delete = Gtk.Button(label="Delete note", css_classes=["flat", "destructive-action"])
        delete.connect("clicked", lambda _b: (popover.popdown(), self.confirm_delete()))
        box.append(folder)
        box.append(delete)
        return Gtk.MenuButton(icon_name="view-more-symbolic", popover=popover, has_frame=False,
                              valign=Gtk.Align.CENTER)

    def rebuild_list(self):
        query = self.search.get_text().strip().lower()
        self.syncing_list = True
        self.note_list.remove_all()
        for title in self.store.titles():
            text = self.store.read(title)
            if query and query not in title.lower() and query not in text.lower():
                continue
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.append(Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["note-name"]))
            preview = preview_of(text)
            if preview:
                box.append(Gtk.Label(label=preview, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                     css_classes=["note-preview"]))
            row = Gtk.ListBoxRow(child=box)
            row.title = title
            self.note_list.append(row)
            if title == self.current:
                self.note_list.select_row(row)
        self.syncing_list = False

    def rebuild_backlinks(self):
        while child := self.backlink_list.get_first_child():
            self.backlink_list.remove(child)
        titles = self.store.backlinks(self.current)
        self.backlinks.set_label(f"Linked mentions ({len(titles)})")
        if not titles:
            self.backlink_list.append(Gtk.Label(label="No notes link here yet.", xalign=0, css_classes=["hint"]))
        for title in titles:
            button = Gtk.Button(label=title, halign=Gtk.Align.START, css_classes=["flat", "backlink"])
            button.connect("clicked", lambda _b, t=title: self.open_note(t))
            self.backlink_list.append(button)

    def open_note(self, title):
        self.flush()
        self.current = title
        if title is None:
            self.pages.set_visible_child_name("empty")
            self.rebuild_list()
            return
        self.loading = True
        self.title_entry.set_text(title)
        self.buffer.set_text(self.store.read(title))
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.buffer.set_modified(False)
        self.loading = False
        self.highlight()
        self.pages.set_visible_child_name("editor")
        self.rebuild_list()
        self.rebuild_backlinks()

    def open_or_create(self, title, text=""):
        title = safe_title(title)
        if title and not self.store.exists(title):
            self.store.write(title, text)
        if title:
            self.open_note(title)

    def new_note(self):
        self.open_note(self.store.create())
        self.title_entry.grab_focus()

    def open_daily(self):
        today = date.today().isoformat()
        self.open_or_create(today, f"# {today}\n\n")
        self.body.grab_focus()
        self.buffer.place_cursor(self.buffer.get_end_iter())

    def commit_title(self):
        if self.current is None:
            return
        new = safe_title(self.title_entry.get_text())
        if not new or new == self.current or self.store.exists(new):
            self.title_entry.set_text(self.current)
            return
        self.flush()
        self.store.rename(self.current, new)
        self.current = new
        self.rebuild_list()
        self.rebuild_backlinks()

    def confirm_delete(self):
        title = self.current
        dialog = Gtk.AlertDialog(message=f"Delete “{title}”?", detail="The note will be moved to the trash.",
                                 buttons=["Cancel", "Delete"], cancel_button=0, default_button=1, modal=True)

        def finish(source, result):
            try:
                if source.choose_finish(result) == 1:
                    self.cancel_save()
                    self.store.trash(title)
                    self.current = None
                    titles = self.store.titles()
                    self.open_note(titles[0] if titles else None)
            except GLib.Error:
                pass

        dialog.choose(self.get_root(), None, finish)

    def on_row_selected(self, _listbox, row):
        if row and not self.syncing_list and row.title != self.current:
            self.open_note(row.title)

    def on_changed(self, _buffer):
        if self.loading:
            return
        self.highlight()
        self.cancel_save()
        self.save_id = GLib.timeout_add(600, self.flush)

    def cancel_save(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = None

    def flush(self):
        if self.save_id is None:
            return False
        self.save_id = None
        if self.current is not None and self.buffer.get_modified():
            start, end = self.buffer.get_bounds()
            self.store.write(self.current, self.buffer.get_text(start, end, True))
            self.buffer.set_modified(False)
            self.rebuild_list()
        return False

    def highlight(self):
        start, end = self.buffer.get_bounds()
        self.buffer.remove_all_tags(start, end)
        offset = 0
        in_code = False
        for line in self.buffer.get_text(start, end, True).split("\n"):
            tag = self.tagger(offset)
            if line.startswith("```"):
                tag("code_block", 0, len(line))
                tag("syntax", 0, len(line))
                in_code = not in_code
            elif in_code:
                tag("code_block", 0, len(line))
            else:
                self.highlight_line(line, tag)
            offset += len(line) + 1

    def tagger(self, offset):
        def tag(name, a, b):
            self.buffer.apply_tag_by_name(name, self.buffer.get_iter_at_offset(offset + a),
                                          self.buffer.get_iter_at_offset(offset + b))
        return tag

    def highlight_line(self, line, tag):
        if heading := HEADING_RE.match(line):
            tag(f"h{len(heading.group(1))}", 0, len(line))
            tag("syntax", 0, heading.end())
        elif line.startswith(">"):
            tag("quote", 0, len(line))
        elif task := TASK_RE.match(line):
            tag("bullet", 0, task.end())
            if task.group(1) != " ":
                tag("done", task.end(), len(line))
        elif bullet := LIST_RE.match(line):
            tag("bullet", 0, bullet.end())
        for pattern, name, marker in INLINE_RULES:
            for m in pattern.finditer(line):
                tag(name, m.start(), m.end())
                if marker:
                    tag("syntax", m.start(), m.start() + marker)
                    tag("syntax", m.end() - marker, m.end())
        for m in LINK_RE.finditer(line):
            tag("link", m.start(), m.end())
            tag("syntax", m.start(), m.start() + 2)
            tag("syntax", m.end() - 2, m.end())

    def on_body_click(self, gesture, _n, x, y):
        if not gesture.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return
        bx, by = self.body.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, where = self.body.get_iter_at_location(bx, by)
        if not found:
            return
        line_start = where.copy()
        line_start.set_line_offset(0)
        line_end = line_start.copy()
        line_end.forward_to_line_end()
        line = self.buffer.get_text(line_start, line_end, True)
        column = where.get_line_offset()
        for m in LINK_RE.finditer(line):
            if m.start() <= column < m.end():
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.open_or_create(m.group(1).strip())
                return
        for m in URL_LINK_RE.finditer(line):
            if m.start() <= column < m.end():
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                Gtk.UriLauncher.new(m.group(1)).launch(self.get_root(), None, None, None)
                return
