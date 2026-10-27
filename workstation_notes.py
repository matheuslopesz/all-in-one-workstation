import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from workstation_theme import ACCENT, GREEN, PURPLE  # noqa: E402

NOTES_DIR = os.path.join(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or GLib.get_home_dir(),
                         "Workstation Notes")
CLAUDE_FOLDER = "Claude"
INLINE = ["bold", "italic", "underline", "strike", "mark", "code"]
BLOCKS = ["h1", "h2", "h3", "quote", "codeblock", "table"]
LISTS = ["bullet", "numbered", "check"]
BLOCK_MENU = [("p", "Text"), ("h1", "Heading 1"), ("h2", "Heading 2"), ("h3", "Heading 3"),
              ("quote", "Quote"), ("codeblock", "Code block")]
MARKERS = {"bullet": "•", "check": "☐"}
CHECKED = "☑"
TABLE_WIDTH = 72
PANGO = {"bold": ("<b>", "</b>"), "italic": ("<i>", "</i>"), "underline": ("<u>", "</u>"),
         "strike": ("<s>", "</s>"), "mark": ('<span background="#f1fa8c" bgalpha="30%">', "</span>"),
         "code": (f'<span font_family="monospace" foreground="{GREEN}">', "</span>")}
TAGS = {
    "h1": {"weight": 800, "scale": 1.8, "pixels_above_lines": 10},
    "h2": {"weight": 800, "scale": 1.45, "pixels_above_lines": 8},
    "h3": {"weight": 700, "scale": 1.2, "pixels_above_lines": 6},
    "quote": {"style": Pango.Style.ITALIC, "left_margin": 18, "foreground": "rgba(248,248,242,0.7)"},
    "codeblock": {"family": "monospace", "paragraph_background": "rgba(0,0,0,0.25)", "left_margin": 12},
    "table": {"family": "monospace", "scale": 0.9},
    "bold": {"weight": 700},
    "italic": {"style": Pango.Style.ITALIC},
    "underline": {"underline": Pango.Underline.SINGLE},
    "strike": {"strikethrough": True},
    "mark": {"background": "rgba(241,250,140,0.3)"},
    "code": {"family": "monospace", "foreground": GREEN, "background": "rgba(0,0,0,0.25)"},
    "marker": {"editable": False, "foreground": PURPLE, "weight": 700},
    "done": {"strikethrough": True, "foreground": "rgba(248,248,242,0.4)"},
}
# Markdown is only the file format: styled text is wrapped when saving and parsed back when loading.
ORDER = ["bold", "italic", "underline", "strike", "mark"]
WRAPS = {"bold": ("**", "**"), "italic": ("_", "_"), "underline": ("<u>", "</u>"), "strike": ("~~", "~~"),
         "mark": ("==", "==")}
INLINE_RE = re.compile(
    r"`([^`\n]+)`"
    r"|\*\*(.+?)\*\*"
    r"|<u>(.+?)</u>"
    r"|~~(.+?)~~"
    r"|==(.+?)=="
    r"|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"
    r"|(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])"
    r"|\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|([^\]\n]+))?\]\]"
    r"|\[([^\]\n]+)\]\(([^)\n]+)\)")
STYLED = ["bold", "underline", "strike", "mark", "italic", "italic"]
ESCAPED_RE = re.compile(r"\\([\\`*_~=\[\]<>|#+\-.!()])")
LITERAL_BLOCK_RE = re.compile(r"#{1,6} |>|[-*+] |\d+[.)] ")
WELCOME = """# Welcome

Notes work like a regular document: use the toolbar above to format text.

- Pick **Heading**, **Quote** or **Code block** in the first menu
- Make text **bold**, _italic_, <u>underlined</u>, ~~struck~~ or ==highlighted==
- [ ] Click a checkbox to tick it
- [x] Everything is saved automatically
"""

NOTES_CSS = f"""
.notes-sidebar {{ background: alpha(currentColor, 0.04); padding: 10px 8px; }}
.notes-sidebar list {{ background: transparent; }}
.notes-sidebar row {{ padding: 6px 10px; border-radius: 6px; }}
.notes-sidebar row:selected {{ background: alpha({ACCENT}, 0.16); color: inherit; }}
.note-name {{ font-weight: bold; }}
.notes-sidebar row.notes-group {{ padding: 6px 6px; }}
.notes-group label {{ font-weight: bold; }}
.notes-group .count {{ font-weight: normal; opacity: 0.5; font-size: 12px; }}
.group-arrow {{ opacity: 0.6; min-width: 14px; }}
.md-table {{ border: 1px solid alpha(currentColor, 0.18); border-radius: 6px; margin: 4px 0; }}
.md-cell {{ padding: 6px 10px; font-size: 13px; border-bottom: 1px solid alpha(currentColor, 0.1);
           border-right: 1px solid alpha(currentColor, 0.1); }}
.md-head {{ font-weight: bold; background: alpha(currentColor, 0.06); }}
.note-preview {{ font-size: 12px; opacity: 0.55; }}
entry.note-title {{ background: transparent; border: none; box-shadow: none; outline: none;
                   font-size: 26px; font-weight: 800; padding: 0; }}
textview.note-body, textview.note-body text {{ background: transparent; font-size: 15px; }}
.note-toolbar {{ padding-bottom: 8px; border-bottom: 1px solid alpha(currentColor, 0.12); }}
.note-toolbar button {{ min-width: 30px; padding: 4px 6px; font-weight: bold; }}
.note-toolbar button.active {{ background: alpha({PURPLE}, 0.25); color: {PURPLE}; }}
"""


def table_rows(lines):
    rows = [[cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))] for line in lines]
    return [r for r in rows if not all(re.fullmatch(r":?-+:?", cell) for cell in r if cell)]


def cell_markup(text):
    out = ""
    for chunk, tags in parse_inline(text):
        piece = GLib.markup_escape_text(chunk)
        for tag in tags:
            if tag.startswith("link:"):
                piece = f'<a href="{GLib.markup_escape_text(tag[5:])}">{piece}</a>'
            else:
                piece = PANGO[tag][0] + piece + PANGO[tag][1]
        out += piece
    return out


def readable_markdown(text):
    out, in_code = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        out.append("─" * 40 if not in_code and re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line) else line)
    return "\n".join(out)


def safe_title(title):
    return re.sub(r'[\\/:*?"<>|]', "-", title).strip().lstrip(".")


def split_inline(text, tags=()):
    out, pos = [], 0
    for m in INLINE_RE.finditer(text):
        out.append((text[pos:m.start()], tags))
        code, *styled = m.groups()[:7]
        page, alias, label, url = m.groups()[7:]
        if code is not None:
            out.append((code, tags + ("code",)))
        elif page:
            out.append(((alias or page).strip(), tags))
        elif label:
            out += split_inline(label, tags + (f"link:{url}",))
        else:
            i = next(i for i, group in enumerate(styled) if group is not None)
            out += split_inline(styled[i], tags + (STYLED[i],))
        pos = m.end()
    out.append((text[pos:], tags))
    return out


def parse_inline(text):
    escaped = []

    def stash(m):
        escaped.append(m.group(1))
        return chr(0xE000 + len(escaped) - 1)

    def restore(s):
        return re.sub("[\ue000-\uf8ff]", lambda m: escaped[ord(m.group()) - 0xE000], s)

    return [(restore(t), tags) for t, tags in split_inline(ESCAPED_RE.sub(stash, text)) if t]


def parse_markdown(text):
    """One (block, marker, [(text, inline tags)]) entry per line; marker is the list bullet, box or number."""
    lines = []
    in_code = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith("|"):
            lines.append(("codeblock" if in_code else "table", None, [(line, ())] if line else []))
            continue
        block, marker = "p", None
        if line.startswith("\\") and LITERAL_BLOCK_RE.match(line[1:]):
            line = line[1:]
        elif m := re.match(r"(#{1,6}) ", line):
            block = f"h{min(len(m.group(1)), 3)}"
        elif m := re.match(r"> ?", line):
            block = "quote"
        elif m := re.match(r"\s*[-*+] \[([ xX])\] ", line):
            block, marker = "check", MARKERS["check"] if m.group(1) == " " else CHECKED
        elif m := re.match(r"\s*(\d+)[.)] ", line):
            block, marker = "numbered", m.group(1) + "."
        elif m := re.match(r"\s*[-*+] ", line):
            block, marker = "bullet", MARKERS["bullet"]
        lines.append((block, marker, parse_inline(line[m.end():] if block != "p" else line)))
    return lines


def escape(text):
    # Only characters that would otherwise be read back as formatting get a backslash.
    text = re.sub(r"\\(?=[\\`*_~=\[\]<>|#+\-.!()]|$)", r"\\\\", text)
    text = re.sub(r"([`*])", r"\\\1", text)
    text = re.sub(r"(?<!\w)_|_(?!\w)", r"\\_", text)
    text = re.sub(r"\[(?=\[|[^\]\n]*\]\()", r"\\[", text)
    text = re.sub(r"<(?=/?u>)", r"\\<", text)
    return text.replace("~~", "\\~\\~").replace("==", "\\=\\=")


def wrap(name):
    return ("[", f"]({name[5:]})") if name.startswith("link:") else WRAPS[name]


def inline_markdown(segments):
    out, stack = "", []

    def close(keep):
        nonlocal out
        body = out.rstrip(" ")
        space = out[len(body):]
        for name in reversed(stack[keep:]):
            body += wrap(name)[1]
        del stack[keep:]
        out = body + space

    for text, tags in segments:
        if "code" not in tags and not text.strip():
            out += text
            continue
        wanted = [t for t in tags if t.startswith("link:")] + [t for t in ORDER if t in tags]
        keep = 0
        while keep < min(len(stack), len(wanted)) and stack[keep] == wanted[keep]:
            keep += 1
        close(keep)
        if "code" not in tags:
            lead = text[:len(text) - len(text.lstrip(" "))]
            out, text = out + lead, text[len(lead):]
        for name in wanted[keep:]:
            stack.append(name)
            out += wrap(name)[0]
        out += f"`{text}`" if "code" in tags else escape(text)
    close(0)
    return out


def line_markdown(block, marker, segments):
    body = inline_markdown(segments)
    if block == "p":
        return "\\" + body if LITERAL_BLOCK_RE.match(body) else body
    prefix = {"h1": "# ", "h2": "## ", "h3": "### ", "quote": "> ", "bullet": "- ", "numbered": f"{marker} ",
              "check": "- [x] " if marker == CHECKED else "- [ ] "}[block]
    return prefix + body


def preview_of(text):
    for block, _marker, segments in parse_markdown(text):
        line = "".join(t for t, _tags in segments).strip()
        if line and block not in ("h1", "h2", "h3"):
            return line
    return ""


class NoteStore:
    def __init__(self):
        if not os.path.isdir(NOTES_DIR):
            os.makedirs(NOTES_DIR)
            self.write("Welcome", WELCOME)
        os.makedirs(os.path.join(NOTES_DIR, CLAUDE_FOLDER), exist_ok=True)

    def path(self, title):
        return os.path.join(NOTES_DIR, f"{title}.md")

    def exists(self, title):
        return os.path.exists(self.path(title))

    def titles(self):
        names = [n for n in os.listdir(NOTES_DIR) if n.endswith(".md")]
        for folder in self.claude_folders():
            rel = os.path.relpath(folder, NOTES_DIR)
            names += [f"{rel}/{n}" for n in os.listdir(folder) if n.endswith(".md")]
        names.sort(key=lambda n: os.path.getmtime(os.path.join(NOTES_DIR, n)), reverse=True)
        return [n[:-3] for n in names]

    def claude_folders(self):
        return [root for root, _dirs, _files in os.walk(os.path.join(NOTES_DIR, CLAUDE_FOLDER))]

    def is_claude(self, title):
        return title is not None and title.startswith(f"{CLAUDE_FOLDER}/")

    def theme(self, title):
        parts = title.split("/")
        return "/".join(parts[1:-1]) if self.is_claude(title) else None

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

    def trash(self, title):
        if os.path.islink(self.path(title)):
            os.remove(self.path(title))
        else:
            Gio.File.new_for_path(self.path(title)).trash(None)


class NotesView(Gtk.Paned):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, position=240,
                         shrink_start_child=False, resize_start_child=False)
        self.store = NoteStore()
        self.current = None
        self.loaded_text = None
        self.expanded = set()
        self.disk_id = None
        self.loading = False
        self.applying = False
        self.syncing = False
        self.syncing_list = False
        self.save_id = None
        self.insert_offset = 0
        self.inserting = False
        self.pending = None
        self.pending_block = None
        self.set_start_child(self.build_sidebar())
        self.set_end_child(self.build_editor())

        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        shortcuts.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>n"),
                                            action=Gtk.CallbackAction.new(lambda *_: self.new_note() or True)))
        self.add_controller(shortcuts)

        titles = self.store.titles()
        self.open_note(titles[0] if titles else None)
        self.monitors = {}
        self.watch_folders()

    def watch_folders(self):
        for folder in [NOTES_DIR, *self.store.claude_folders()]:
            if folder not in self.monitors:
                monitor = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
                monitor.connect("changed", self.on_disk_event)
                self.monitors[folder] = monitor

    def on_disk_event(self, *_args):
        if self.disk_id:
            GLib.source_remove(self.disk_id)
        self.disk_id = GLib.timeout_add(300, self.on_disk_changed)

    def on_disk_changed(self):
        self.disk_id = None
        self.watch_folders()
        if self.save_id is not None or self.buffer.get_modified():
            self.rebuild_list()
            return False
        if self.current is not None and not self.store.exists(self.current):
            titles = self.store.titles()
            self.open_note(titles[0] if titles else None)
        elif self.current is not None and self.store.read(self.current) != self.loaded_text:
            self.open_note(self.current)
        else:
            self.rebuild_list()
        return False

    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["notes-sidebar"],
                      width_request=200)
        top = Gtk.Box(spacing=4)
        self.search = Gtk.SearchEntry(placeholder_text="Search notes", hexpand=True)
        self.search.connect("search-changed", lambda _e: self.rebuild_list())
        top.append(self.search)
        new = Gtk.Button(icon_name="document-new-symbolic", tooltip_text="New note (Ctrl+N)", css_classes=["flat"])
        new.connect("clicked", lambda _b: self.new_note())
        top.append(new)
        box.append(top)

        self.note_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.note_list.connect("row-selected", self.on_row_selected)
        self.note_list.connect("row-activated", self.on_row_activated)
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
        self.claude_banner = Gtk.Label(label="🤖 Written by Claude · read-only", xalign=0,
                                       css_classes=["note-preview"])
        box.append(self.claude_banner)
        self.toolbar = self.build_toolbar()
        box.append(self.toolbar)

        self.buffer = Gtk.TextBuffer()
        for name, props in TAGS.items():
            self.buffer.create_tag(name, **props)
        self.buffer.connect("changed", self.on_changed)
        self.buffer.connect("insert-text", self.on_insert_before)
        self.buffer.connect_after("insert-text", self.on_insert_after)
        self.buffer.connect("mark-set", self.on_mark_set)
        self.body = Gtk.TextView(buffer=self.buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 pixels_below_lines=4, css_classes=["note-body"],
                                 tooltip_text="Ctrl+click a link to open it")
        click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self.on_body_click)
        self.body.add_controller(click)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.body.add_controller(keys)
        body_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        body_scroller.set_child(self.body)
        box.append(body_scroller)
        self.pages.add_named(box, "editor")
        return self.pages

    def build_toolbar(self):
        bar = Gtk.Box(spacing=4, css_classes=["note-toolbar"])
        self.block_menu = Gtk.DropDown.new_from_strings([label for _block, label in BLOCK_MENU])
        self.block_menu.set_focus_on_click(False)
        self.block_menu.connect("notify::selected", self.on_block_menu)
        bar.append(self.block_menu)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=4, margin_end=4))

        self.format_buttons = {}
        for name, icon, label, tip in (("bold", "format-text-bold-symbolic", None, "Bold (Ctrl+B)"),
                                       ("italic", "format-text-italic-symbolic", None, "Italic (Ctrl+I)"),
                                       ("underline", "format-text-underline-symbolic", None, "Underline (Ctrl+U)"),
                                       ("strike", "format-text-strikethrough-symbolic", None, "Strikethrough"),
                                       ("mark", None, "H", "Highlight"),
                                       ("code", None, "</>", "Inline code"),
                                       (None, None, None, None),
                                       ("bullet", "view-list-bullet-symbolic", None, "Bulleted list"),
                                       ("numbered", "view-list-ordered-symbolic", None, "Numbered list"),
                                       ("check", "checkbox-checked-symbolic", None, "Checklist")):
            if name is None:
                bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=4, margin_end=4))
                continue
            button = Gtk.Button(tooltip_text=tip, focus_on_click=False, css_classes=["flat"])
            if icon:
                button.set_icon_name(icon)
            else:
                button.set_label(label)
            if name in LISTS:
                button.connect("clicked", lambda _b, n=name: self.toggle_list(n))
            else:
                button.connect("clicked", lambda _b, n=name: self.toggle_inline(n))
            self.format_buttons[name] = button
            bar.append(button)
        return bar

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
        titles = self.store.titles()
        groups = {}
        for title in titles:
            groups.setdefault(self.store.theme(title), []).append(title)
        for theme in sorted(groups, key=lambda t: (t is not None, t or "")):
            matching = [t for t in groups[theme]
                        if not query or query in t.lower() or query in self.store.read(t).lower()]
            if not matching:
                continue
            open_ = bool(query) or theme in self.expanded
            self.append_group_row(theme, len(matching), open_)
            if open_:
                for title in matching:
                    self.append_note_row(title)
        self.syncing_list = False

    def append_group_row(self, theme, count, open_):
        box = Gtk.Box(spacing=6)
        box.append(Gtk.Label(label="▾" if open_ else "▸", css_classes=["group-arrow"]))
        name = "📝 My notes" if theme is None else f"🤖 {theme or 'Claude'}"
        box.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
        box.append(Gtk.Label(label=str(count), css_classes=["count"]))
        row = Gtk.ListBoxRow(child=box, selectable=False, css_classes=["notes-group"])
        row.group = theme
        self.note_list.append(row)

    def on_row_activated(self, _listbox, row):
        if not hasattr(row, "group"):
            return
        self.expanded.symmetric_difference_update({row.group})
        self.rebuild_list()

    def append_note_row(self, title):
        text = self.store.read(title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_start=20)
        box.append(Gtk.Label(label=title.rsplit("/", 1)[-1], xalign=0, ellipsize=Pango.EllipsizeMode.END,
                             css_classes=["note-name"]))
        preview = preview_of(text)
        if preview:
            box.append(Gtk.Label(label=preview, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                 css_classes=["note-preview"]))
        row = Gtk.ListBoxRow(child=box)
        row.title = title
        self.note_list.append(row)
        if title == self.current:
            self.note_list.select_row(row)

    def open_note(self, title):
        self.flush()
        self.current = title
        if title is None:
            self.pages.set_visible_child_name("empty")
            self.rebuild_list()
            return
        claude = self.store.is_claude(title)
        self.title_entry.set_text(title.rsplit("/", 1)[-1])
        self.title_entry.set_editable(not claude)
        self.body.set_editable(not claude)
        self.body.set_cursor_visible(not claude)
        self.toolbar.set_visible(not claude)
        self.claude_banner.set_visible(claude)
        self.loaded_text = self.store.read(title)
        self.load(readable_markdown(self.loaded_text) if claude else self.loaded_text, rich_tables=claude)
        self.pages.set_visible_child_name("editor")
        self.rebuild_list()

    def new_note(self):
        self.expanded.add(None)
        self.open_note(self.store.create())
        self.title_entry.grab_focus()

    def commit_title(self):
        if self.current is None or self.store.is_claude(self.current):
            return
        new = safe_title(self.title_entry.get_text())
        if not new or new == self.current or self.store.exists(new):
            self.title_entry.set_text(self.current)
            return
        self.flush()
        self.store.rename(self.current, new)
        self.current = new
        self.rebuild_list()

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

    # Loading and saving

    def load(self, text, rich_tables=False):
        self.loading = True
        self.buffer.set_text("")
        lines = parse_markdown(text)
        n = 0
        while n < len(lines):
            block, marker, segments = lines[n]
            line_tags = [block] if block in BLOCKS else []
            if rich_tables and block == "table":
                end = n
                while end + 1 < len(lines) and lines[end + 1][0] == "table":
                    end += 1
                self.insert_table(["".join(t for t, _tags in lines[k][2]) for k in range(n, end + 1)])
                line_tags, n = [], end
            else:
                if marker:
                    self.insert(marker + " ", "marker")
                for chunk, tags in segments:
                    for name in tags:
                        self.ensure_link_tag(name)
                    self.insert(chunk, *line_tags, *tags, *(["done"] if marker == CHECKED else []))
            if n < len(lines) - 1:
                self.insert("\n", *line_tags)
            n += 1
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.buffer.set_modified(False)
        self.pending = self.pending_block = None
        self.loading = False
        self.sync_toolbar()

    def insert_table(self, lines):
        rows = table_rows(lines)
        cols = max(map(len, rows))
        natural = [max((len(r[i]) for r in rows if i < len(r)), default=0) for i in range(cols)]
        total = sum(natural) or 1
        widths = [max(4, min(n, TABLE_WIDTH * n // total)) for n in natural]
        grid = Gtk.Grid(css_classes=["md-table"])
        for y, row in enumerate(rows):
            for x in range(cols):
                label = Gtk.Label(xalign=0, yalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True,
                                  width_chars=widths[x], max_width_chars=widths[x],
                                  css_classes=["md-cell", *(["md-head"] if y == 0 else [])])
                label.set_markup(cell_markup(row[x] if x < len(row) else ""))
                grid.attach(label, x, y, 1, 1)
        self.body.add_child_at_anchor(grid, self.buffer.create_child_anchor(self.buffer.get_end_iter()))

    def insert(self, text, *tags):
        self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), text, *tags)

    def ensure_link_tag(self, name):
        if name.startswith("link:") and not self.tag(name):
            self.buffer.create_tag(name, foreground=ACCENT, underline=Pango.Underline.SINGLE)

    def to_markdown(self):
        out, in_code = [], False
        for n in range(self.buffer.get_line_count()):
            block = self.line_block(n)
            if (block == "codeblock") != in_code:
                out.append("```")
                in_code = not in_code
            start, end = self.line_bounds(n)
            if block in ("codeblock", "table"):
                out.append(self.buffer.get_text(start, end, True))
            else:
                out.append(line_markdown(block, self.marker_text(n), self.line_segments(n)))
        if in_code:
            out.append("```")
        return "\n".join(out)

    def on_changed(self, _buffer):
        if not self.loading:
            self.schedule_save()

    def schedule_save(self):
        self.buffer.set_modified(True)
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
        if self.current is not None and self.buffer.get_modified() and not self.store.is_claude(self.current):
            self.loaded_text = self.to_markdown()
            self.store.write(self.current, self.loaded_text)
            self.buffer.set_modified(False)
            self.rebuild_list()
        return False

    # Reading lines

    def tag(self, name):
        return self.buffer.get_tag_table().lookup(name)

    def cursor(self):
        return self.buffer.get_iter_at_mark(self.buffer.get_insert())

    def line_bounds(self, n):
        start = self.buffer.get_iter_at_line(n)[1]
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return start, end

    def body_start(self, n):
        start = self.line_bounds(n)[0]
        if start.has_tag(self.tag("marker")):
            start.forward_to_tag_toggle(self.tag("marker"))
        return start

    def marker_text(self, n):
        start = self.line_bounds(n)[0]
        return self.buffer.get_text(start, self.body_start(n), True).strip() or None

    def line_block(self, n):
        start = self.line_bounds(n)[0]
        if start.has_tag(self.tag("marker")):
            first = start.get_char()
            return "bullet" if first == MARKERS["bullet"] else "numbered" if first.isdigit() else "check"
        return next((b for b in BLOCKS if start.has_tag(self.tag(b))), "p")

    def line_segments(self, n):
        start, end = self.body_start(n), self.line_bounds(n)[1]
        segments = []
        while start.compare(end) < 0:
            stop = start.copy()
            stop.forward_to_tag_toggle(None)
            if stop.compare(end) > 0 or stop.equal(start):
                stop = end.copy()
            links = [t.props.name for t in start.get_tags() if (t.props.name or "").startswith("link:")]
            segments.append((self.buffer.get_text(start, stop, True),
                             tuple(t for t in INLINE if start.has_tag(self.tag(t))) + tuple(links)))
            start = stop
        return segments

    def selected_lines(self):
        bounds = self.buffer.get_selection_bounds()
        start, end = bounds if bounds else (self.cursor(), self.cursor())
        return range(start.get_line(), end.get_line() + 1)

    def range_has(self, name, start, end):
        tag = self.tag(name)
        it = start.copy()
        while it.compare(end) < 0:
            if it.get_char() != "\n" and not it.has_tag(tag) and not it.has_tag(self.tag("marker")):
                return False
            it.forward_char()
        return True

    def typing_tags(self):
        return self.typing_tags_at(self.cursor())

    def typing_tags_at(self, start):
        if self.pending is not None:
            return self.pending
        if start.starts_line():
            return []
        before = start.copy()
        before.backward_char()
        return [t for t in INLINE if before.has_tag(self.tag(t))]

    # Editing

    def set_block(self, n, block):
        self.applying = True
        start = self.line_bounds(n)[0]
        self.buffer.delete(start, self.body_start(n))
        start, end = self.line_bounds(n)
        stop = end.copy()
        stop.forward_char()
        for name in BLOCKS + ["done"]:
            self.buffer.remove_tag_by_name(name, start, stop)
        if block in LISTS:
            self.buffer.insert_with_tags_by_name(start, f"{MARKERS.get(block) or self.next_number(n)} ", "marker")
        elif block in BLOCKS:
            if start.equal(stop):
                self.pending_block = block
            else:
                self.buffer.apply_tag_by_name(block, start, stop)
        self.renumber()
        self.applying = False
        self.schedule_save()

    def next_number(self, n):
        if n > 0 and self.line_block(n - 1) == "numbered":
            return f"{int(self.marker_text(n - 1)[:-1]) + 1}."
        return "1."

    def renumber(self):
        expected = None
        for n in range(self.buffer.get_line_count()):
            if self.line_block(n) != "numbered":
                expected = None
                continue
            current = int(self.marker_text(n)[:-1])
            expected = current if expected is None else expected
            if current != expected:
                start = self.line_bounds(n)[0]
                self.buffer.delete(start, self.body_start(n))
                self.buffer.insert_with_tags_by_name(self.line_bounds(n)[0], f"{expected}. ", "marker")
            expected += 1

    def toggle_check(self, n):
        self.applying = True
        start = self.line_bounds(n)[0]
        checked = start.get_char() == CHECKED
        after = start.copy()
        after.forward_char()
        self.buffer.delete(start, after)
        self.buffer.insert_with_tags_by_name(self.line_bounds(n)[0], MARKERS["check"] if checked else CHECKED,
                                             "marker")
        (self.buffer.remove_tag_by_name if checked else self.buffer.apply_tag_by_name)(
            "done", self.body_start(n), self.line_bounds(n)[1])
        self.applying = False

    def toggle_inline(self, name):
        bounds = self.buffer.get_selection_bounds()
        if bounds:
            start, end = bounds
            if self.range_has(name, start, end):
                self.buffer.remove_tag_by_name(name, start, end)
            else:
                self.buffer.apply_tag_by_name(name, start, end)
            self.schedule_save()
        else:
            self.pending = sorted(set(self.typing_tags()) ^ {name})
        self.body.grab_focus()
        self.sync_toolbar()

    def toggle_list(self, block):
        lines = self.selected_lines()
        target = "p" if all(self.line_block(n) == block for n in lines) else block
        for n in lines:
            self.set_block(n, target)
        self.body.grab_focus()
        self.sync_toolbar()

    def on_block_menu(self, dropdown, _param):
        if self.syncing:
            return
        for n in self.selected_lines():
            self.set_block(n, BLOCK_MENU[dropdown.get_selected()][0])
        self.body.grab_focus()
        self.sync_toolbar()

    def sync_toolbar(self):
        self.syncing = True
        block = self.pending_block or self.line_block(self.cursor().get_line())
        blocks = [b for b, _label in BLOCK_MENU]
        self.block_menu.set_selected(blocks.index(block) if block in blocks else 0)
        bounds = self.buffer.get_selection_bounds()
        active = [t for t in INLINE if self.range_has(t, *bounds)] if bounds else self.typing_tags()
        for name, button in self.format_buttons.items():
            on = name in active if name in INLINE else name == block
            (button.add_css_class if on else button.remove_css_class)("active")
        self.syncing = False

    def on_insert_before(self, _buffer, location, _text, _length):
        if not self.loading and not self.applying:
            self.insert_offset = location.get_offset()
            self.inserting = True

    def on_insert_after(self, buffer, location, _text, _length):
        if self.loading or self.applying:
            return
        self.inserting = False
        self.applying = True
        start = buffer.get_iter_at_offset(self.insert_offset)
        end = location.copy()
        probe = end.copy() if start.starts_line() else start.copy()
        if not start.starts_line():
            probe.backward_char()
        blocks = [b for b in BLOCKS if probe.has_tag(self.tag(b))]
        if self.pending_block:
            blocks, self.pending_block = [self.pending_block], None
        inline = self.typing_tags_at(start)
        self.pending = None
        for name in blocks + inline:
            buffer.apply_tag_by_name(name, start, end)
        for n in range(start.get_line(), end.get_line() + 1):
            if self.marker_text(n) == CHECKED:
                buffer.apply_tag_by_name("done", self.body_start(n), self.line_bounds(n)[1])
        self.applying = False
        self.sync_toolbar()

    def on_mark_set(self, buffer, location, mark):
        if mark.get_name() != "insert" or self.loading or self.inserting or self.applying:
            return
        self.pending = None
        self.pending_block = None
        body = self.body_start(location.get_line())
        if location.compare(body) < 0 and not buffer.get_has_selection():
            buffer.place_cursor(body)
            return
        self.sync_toolbar()

    def on_key(self, _controller, keyval, _keycode, state):
        if not self.body.get_editable():
            return False
        if state & Gdk.ModifierType.CONTROL_MASK:
            name = {Gdk.KEY_b: "bold", Gdk.KEY_i: "italic", Gdk.KEY_u: "underline"}.get(Gdk.keyval_to_lower(keyval))
            if name:
                self.toggle_inline(name)
                return True
            return False
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            return self.on_enter()
        if keyval == Gdk.KEY_BackSpace and not self.buffer.get_has_selection():
            return self.on_backspace()
        return False

    def on_enter(self):
        n = self.cursor().get_line()
        block = self.line_block(n)
        if block in LISTS + ["quote"] and self.body_start(n).equal(self.line_bounds(n)[1]):
            self.set_block(n, "p")
            self.sync_toolbar()
            return True
        if block not in LISTS + ["h1", "h2", "h3"]:
            return False
        self.buffer.begin_user_action()
        self.buffer.delete_selection(True, True)
        self.buffer.insert_interactive_at_cursor("\n", -1, True)
        self.set_block(n + 1, block if block in LISTS else "p")
        self.buffer.end_user_action()
        self.sync_toolbar()
        return True

    def on_backspace(self):
        it = self.cursor()
        n = it.get_line()
        block = self.line_block(n)
        if (block in LISTS and it.equal(self.body_start(n))) or (block in BLOCKS and it.starts_line()):
            self.set_block(n, "p")
            self.sync_toolbar()
            return True
        return False

    def on_body_click(self, gesture, _n, x, y):
        bx, by = self.body.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, where = self.body.get_iter_at_location(bx, by)
        if not found:
            return
        readonly = not self.body.get_editable()
        if (not readonly and where.get_line_offset() == 0 and where.get_char() in (MARKERS["check"], CHECKED)
                and where.has_tag(self.tag("marker"))):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.toggle_check(where.get_line())
        elif readonly or gesture.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            link = next((t.props.name[5:] for t in where.get_tags() if (t.props.name or "").startswith("link:")), None)
            if link:
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                Gtk.UriLauncher.new(link).launch(self.get_root(), None, None, None)
