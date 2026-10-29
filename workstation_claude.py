import os
import shlex

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Vte", "3.91")
    from gi.repository import Vte  # noqa: E402
except (ValueError, ImportError):
    Vte = None

from workstation_repos import PROJECTS_DIR, identities, local_path  # noqa: E402
from workstation_theme import BG, COMMENT, CYAN, FG, GREEN, PINK, PURPLE, RED, YELLOW  # noqa: E402

INSTALL_HINT = "sudo apt install gir1.2-vte-3.91"
CLAUDE_COMMAND = "claude"
PALETTE = ["#21222c", RED, GREEN, YELLOW, PURPLE, PINK, CYAN, FG,
           COMMENT, "#ff6e6e", "#69ff94", "#ffffa5", "#d6acff", "#ff92df", "#a4ffff", "#ffffff"]
CLAUDE_CSS = """
.claude-toolbar { padding: 6px 8px; }
.claude-tab-label { font-size: 13px; }
"""


def rgba(color):
    value = Gdk.RGBA()
    value.parse(color)
    return value


class ClaudeView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.font_scale = 1.0
        if Vte is None:
            self.append(self.missing_vte())
            return
        bar = Gtk.Box(spacing=8, css_classes=["claude-toolbar"])
        self.folders = [PROJECTS_DIR, *filter(None, map(local_path, identities()))]
        self.folder = Gtk.DropDown.new_from_strings(["projetos", *map(os.path.basename, self.folders[1:])])
        self.folder.set_tooltip_text("Folder for the next session")
        bar.append(self.folder)
        new = Gtk.Button(label="＋ New session", css_classes=["flat"])
        new.connect("clicked", lambda _b: self.open_session(self.folders[self.folder.get_selected()]))
        bar.append(new)
        resume = Gtk.Button(label="↻ Continue last", css_classes=["flat"],
                            tooltip_text="claude --continue in the selected folder")
        resume.connect("clicked", lambda _b: self.open_session(self.folders[self.folder.get_selected()],
                                                                ["--continue"]))
        bar.append(resume)
        bar.append(Gtk.Label(label="Ctrl+Shift+C / Ctrl+Shift+V to copy and paste", hexpand=True, xalign=1,
                             css_classes=["run-meta"]))
        self.append(bar)
        self.notebook = Gtk.Notebook(scrollable=True, vexpand=True, hexpand=True)
        self.append(self.notebook)
        self.open_session(PROJECTS_DIR)

    def missing_vte(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.CENTER, vexpand=True,
                      halign=Gtk.Align.CENTER)
        box.append(Gtk.Label(label="The Claude tab needs the GTK 4 terminal widget (VTE).", css_classes=["run-title"]))
        box.append(Gtk.Label(label="Install it once, then restart the app:"))
        command = Gtk.Label(label=INSTALL_HINT, selectable=True, css_classes=["approval-command"])
        box.append(command)
        copy = Gtk.Button(label="Copy command", halign=Gtk.Align.CENTER)
        copy.connect("clicked", lambda _b: self.get_clipboard().set(INSTALL_HINT))
        box.append(copy)
        return box

    def open_session(self, folder, args=()):
        if Vte is None:
            return None
        terminal = Vte.Terminal(vexpand=True, hexpand=True, scrollback_lines=20000)
        terminal.set_colors(rgba(FG), rgba(BG), [rgba(c) for c in PALETTE])
        terminal.set_font(Pango.FontDescription.from_string("Monospace 11"))
        terminal.set_font_scale(self.font_scale)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key, terminal)
        terminal.add_controller(keys)
        shell = os.environ.get("SHELL", "/bin/bash")
        claude = shlex.join([CLAUDE_COMMAND, *args])
        terminal.spawn_async(Vte.PtyFlags.DEFAULT, folder, [shell, "-l", "-c", f"{claude}; exec {shell} -l"],
                             None, GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
        label = Gtk.Box(spacing=4)
        label.append(Gtk.Label(label=f"🤖 {os.path.basename(folder.rstrip('/'))}", css_classes=["claude-tab-label"]))
        close = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat", "circular"])
        label.append(close)
        page = self.notebook.append_page(terminal, label)
        self.notebook.set_tab_reorderable(terminal, True)
        close.connect("clicked", lambda _b: self.notebook.remove_page(self.notebook.page_num(terminal)))
        terminal.connect("child-exited", lambda *_: self.notebook.remove_page(self.notebook.page_num(terminal)))
        self.notebook.set_current_page(page)
        terminal.grab_focus()
        return terminal

    def on_key(self, _controller, keyval, _keycode, state, terminal):
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if state & ctrl_shift == ctrl_shift:
            if keyval in (Gdk.KEY_C, Gdk.KEY_c):
                terminal.copy_clipboard_format(Vte.Format.TEXT)
                return True
            if keyval in (Gdk.KEY_V, Gdk.KEY_v):
                terminal.paste_clipboard()
                return True
        return False

    def set_font_scale(self, scale):
        self.font_scale = scale
        if Vte is None:
            return
        for n in range(self.notebook.get_n_pages()):
            self.notebook.get_nth_page(n).set_font_scale(scale)

    def send_task(self, folder, prompt, title):
        terminal = self.open_session(folder, [prompt])
        if terminal:
            label = self.notebook.get_tab_label(terminal).get_first_child()
            label.set_text(f"🤖 {title[:24]}")
        return terminal is not None
