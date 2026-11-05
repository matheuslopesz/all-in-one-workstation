import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from workstation_theme import ACCENT  # noqa: E402
from workstation_vault import MIN_MASTER, Vault, VaultError, generate_password, new_entry, read_lastpass_csv  # noqa: E402

CLIPBOARD_SECONDS = 30
AUTO_LOCK_SECONDS = 5 * 60

PASSWORDS_CSS = f"""
.vault-gate {{ padding: 40px; }}
.vault-title {{ font-size: 22px; font-weight: 800; }}
.vault-hint {{ font-size: 12px; opacity: 0.6; }}
.vault-error {{ font-size: 12px; color: #ff5555; }}
.vault-list {{ background: transparent; }}
.vault-list row {{ padding: 8px 4px; border-bottom: 1px solid alpha(currentColor, 0.08); }}
.vault-list row.group-head {{ padding: 18px 4px 4px 4px; border-bottom: 1px solid alpha(currentColor, 0.18); }}
.vault-name {{ font-weight: bold; }}
.vault-meta {{ font-size: 12px; opacity: 0.6; }}
.vault-folder {{ font-weight: bold; font-size: 13px; color: {ACCENT}; }}
"""


def password_entry(placeholder):
    return Gtk.PasswordEntry(placeholder_text=placeholder, show_peek_icon=True, hexpand=True)


class EntryDialog(Gtk.Window):
    def __init__(self, view, entry=None):
        super().__init__(title="Edit login" if entry else "Add login", transient_for=view.get_root(), modal=True,
                         default_width=460, resizable=False)
        self.view, self.entry = view, entry
        values = entry or new_entry()
        grid = Gtk.Grid(row_spacing=8, column_spacing=10, margin_top=16, margin_bottom=16,
                        margin_start=16, margin_end=16)
        self.fields = {}
        for row, (key, label) in enumerate((("name", "Name"), ("url", "URL"), ("username", "Username"),
                                            ("password", "Password"), ("folder", "Folder"), ("totp", "TOTP secret"))):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            if key == "password":
                widget = password_entry("Password")
                widget.set_text(values["password"])
                box = Gtk.Box(spacing=4)
                box.append(widget)
                generate = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Generate a strong password")
                generate.connect("clicked", lambda _b, w=widget: (w.set_text(generate_password()),
                                                                 w.set_show_peek_icon(True)))
                box.append(generate)
                grid.attach(box, 1, row, 1, 1)
            else:
                widget = Gtk.Entry(text=values[key], hexpand=True)
                grid.attach(widget, 1, row, 1, 1)
            self.fields[key] = widget
        grid.attach(Gtk.Label(label="Notes", xalign=0, valign=Gtk.Align.START), 0, 6, 1, 1)
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=90)
        self.notes.get_buffer().set_text(values["notes"])
        scroller = Gtk.ScrolledWindow(child=self.notes, has_frame=True, min_content_height=90)
        grid.attach(scroller, 1, 6, 1, 1)

        buttons = Gtk.Box(spacing=8, margin_top=8)
        if entry:
            delete = Gtk.Button(label="Delete", css_classes=["destructive-action"])
            delete.connect("clicked", lambda _b: self.delete())
            buttons.append(delete)
        buttons.append(Gtk.Box(hexpand=True))
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save.connect("clicked", lambda _b: self.save())
        buttons.append(cancel)
        buttons.append(save)
        grid.attach(buttons, 0, 7, 2, 1)
        self.set_child(grid)

    def save(self):
        values = {key: widget.get_text() for key, widget in self.fields.items()}
        buffer = self.notes.get_buffer()
        values["notes"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if not values["name"].strip():
            self.fields["name"].grab_focus()
            return
        entry = self.entry or new_entry()
        entry.update(values)
        self.view.vault.put(entry)
        self.view.rebuild_list()
        self.close()

    def delete(self):
        self.view.confirm(f"Delete “{self.entry['name']}”?", "The login will be permanently deleted.",
                          lambda: (self.view.vault.delete(self.entry), self.view.rebuild_list(), self.close()))


class MasterDialog(Gtk.Window):
    def __init__(self, view):
        super().__init__(title="Change master password", transient_for=view.get_root(), modal=True,
                         default_width=380, resizable=False)
        self.view = view
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        self.current = password_entry("Current master password")
        self.new = password_entry(f"New master password (at least {MIN_MASTER} characters)")
        self.again = password_entry("Repeat the new master password")
        self.error = Gtk.Label(xalign=0, wrap=True, css_classes=["vault-error"], visible=False)
        for widget in (self.current, self.new, self.again, self.error):
            box.append(widget)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        ok = Gtk.Button(label="Change", css_classes=["suggested-action"])
        ok.connect("clicked", lambda _b: self.submit())
        buttons.append(cancel)
        buttons.append(ok)
        box.append(buttons)
        self.set_child(box)

    def submit(self):
        if self.new.get_text() != self.again.get_text():
            return self.show_error("The new passwords don't match")
        try:
            self.view.vault.change_master(self.current.get_text(), self.new.get_text())
        except VaultError as error:
            return self.show_error(str(error))
        self.close()

    def show_error(self, text):
        self.error.set_text(text)
        self.error.set_visible(True)


class PasswordsView(Gtk.Stack):
    def __init__(self):
        super().__init__(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.vault = Vault()
        self.lock_timer = None
        self.add_named(self.build_gate(), "gate")
        self.add_named(self.build_open(), "open")
        self.show_gate()
        for controller in (Gtk.EventControllerKey(), Gtk.GestureClick()):
            controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            controller.connect("key-pressed" if isinstance(controller, Gtk.EventControllerKey) else "pressed",
                               lambda *_: (self.touch(), False)[1])
            self.add_controller(controller)

    def build_gate(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER,
                      valign=Gtk.Align.CENTER, width_request=360, css_classes=["vault-gate"])
        self.gate_title = Gtk.Label(css_classes=["vault-title"])
        self.gate_hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, css_classes=["vault-hint"])
        self.master = password_entry("Master password")
        self.master.connect("activate", lambda _e: self.submit_gate())
        self.master_again = password_entry("Repeat the master password")
        self.master_again.connect("activate", lambda _e: self.submit_gate())
        self.gate_error = Gtk.Label(wrap=True, css_classes=["vault-error"], visible=False)
        self.gate_button = Gtk.Button(css_classes=["suggested-action"])
        self.gate_button.connect("clicked", lambda _b: self.submit_gate())
        for widget in (Gtk.Label(label="🔑", css_classes=["vault-title"]), self.gate_title, self.gate_hint,
                       self.master, self.master_again, self.gate_error, self.gate_button):
            box.append(widget)
        return box

    def build_open(self):
        self.search = Gtk.SearchEntry(placeholder_text="Search logins", hexpand=True)
        self.search.connect("search-changed", lambda _e: self.rebuild_list())
        bar = Gtk.Box(spacing=6, margin_top=16, margin_start=20, margin_end=20)
        bar.append(self.search)
        for icon, tip, handler in (("list-add-symbolic", "Add login", lambda _b: EntryDialog(self).present()),
                                   ("document-open-symbolic", "Import a LastPass CSV export",
                                    lambda _b: self.pick_csv()),
                                   ("dialog-password-symbolic", "Change master password",
                                    lambda _b: MasterDialog(self).present()),
                                   ("system-lock-screen-symbolic", "Lock now", lambda _b: self.lock())):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"])
            button.connect("clicked", handler)
            bar.append(button)
        self.status = Gtk.Label(xalign=0, margin_start=20, margin_top=6, css_classes=["vault-hint"])
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["vault-list"])
        self.list.connect("row-activated", lambda _l, row: getattr(row, "entry", None)
                          and EntryDialog(self, row.entry).present())
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, margin_start=20,
                                      margin_end=20, margin_bottom=16)
        scroller.set_child(self.list)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for widget in (bar, self.status, scroller):
            box.append(widget)
        return box

    def show_gate(self):
        creating = not self.vault.exists()
        self.gate_title.set_text("Create your vault" if creating else "Vault locked")
        self.gate_hint.set_text(
            f"Pick a master password with at least {MIN_MASTER} characters. It can't be recovered: "
            "if you forget it, the passwords are lost." if creating else "Type the master password to unlock.")
        self.gate_button.set_label("Create vault" if creating else "Unlock")
        self.master_again.set_visible(creating)
        self.master.set_text("")
        self.master_again.set_text("")
        self.gate_error.set_visible(False)
        self.set_visible_child_name("gate")
        GLib.idle_add(lambda: (self.master.grab_focus(), False)[1])

    def submit_gate(self):
        master = self.master.get_text()
        try:
            if self.vault.exists():
                self.vault.unlock(master)
            elif master != self.master_again.get_text():
                raise VaultError("The passwords don't match")
            else:
                self.vault.create(master)
        except VaultError as error:
            self.gate_error.set_text(str(error))
            self.gate_error.set_visible(True)
            return
        self.master.set_text("")
        self.master_again.set_text("")
        self.search.set_text("")
        self.rebuild_list()
        self.set_visible_child_name("open")
        self.touch()

    def lock(self):
        self.vault.lock()
        self.list.remove_all()
        if self.lock_timer:
            GLib.source_remove(self.lock_timer)
            self.lock_timer = None
        self.show_gate()

    def touch(self):
        if not self.vault.unlocked:
            return
        if self.lock_timer:
            GLib.source_remove(self.lock_timer)
        self.lock_timer = GLib.timeout_add_seconds(AUTO_LOCK_SECONDS, self.auto_lock)

    def auto_lock(self):
        self.lock_timer = None
        self.lock()
        return False

    def rebuild_list(self):
        self.list.remove_all()
        entries = self.vault.search(self.search.get_text())
        self.status.set_text(f"{len(entries)} of {len(self.vault.entries)} logins · locks after "
                             f"{AUTO_LOCK_SECONDS // 60} min idle · copied passwords clear in {CLIPBOARD_SECONDS}s")
        folder = None
        for entry in entries:
            if entry["folder"] != folder:
                folder = entry["folder"]
                head = Gtk.ListBoxRow(child=Gtk.Label(label=folder or "No folder", xalign=0,
                                                      css_classes=["vault-folder"]),
                                      selectable=False, activatable=False, css_classes=["group-head"])
                self.list.append(head)
            self.list.append(self.entry_row(entry))

    def entry_row(self, entry):
        box = Gtk.Box(spacing=10)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        text.append(Gtk.Label(label=entry["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END,
                              css_classes=["vault-name"]))
        meta = " · ".join(v for v in (entry["username"], entry["url"]) if v)
        if meta:
            text.append(Gtk.Label(label=meta, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                  css_classes=["vault-meta"]))
        box.append(text)
        actions = [("avatar-default-symbolic", "Copy username", entry["username"],
                    lambda _b: self.copy(entry["username"], secret=False)),
                   ("edit-copy-symbolic", "Copy password", entry["password"],
                    lambda _b: self.copy(entry["password"], secret=True)),
                   ("web-browser-symbolic", "Open site", entry["url"].startswith(("http://", "https://")),
                    lambda _b: Gio.AppInfo.launch_default_for_uri(entry["url"], None))]
        for icon, tip, enabled, handler in actions:
            button = Gtk.Button(icon_name=icon, tooltip_text=tip, sensitive=bool(enabled),
                                css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
            button.connect("clicked", handler)
            box.append(button)
        row = Gtk.ListBoxRow(child=box)
        row.entry = entry
        return row

    def copy(self, text, secret):
        clipboard = self.get_clipboard()
        clipboard.set(text)
        self.status.set_text("Password copied, clears in 30s" if secret else "Username copied")
        if secret:
            GLib.timeout_add_seconds(CLIPBOARD_SECONDS, self.clear_clipboard)

    def clear_clipboard(self):
        clipboard = self.get_clipboard()
        if clipboard.is_local():  # don't wipe something the user copied from another app since
            clipboard.set("")
        return False

    def pick_csv(self):
        dialog = Gtk.FileDialog(title="Import LastPass CSV export")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        csv_filter = Gtk.FileFilter(name="CSV files")
        csv_filter.add_pattern("*.csv")
        filters.append(csv_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self.on_csv_picked)

    def on_csv_picked(self, dialog, result):
        try:
            path = dialog.open_finish(result).get_path()
        except GLib.Error:
            return
        try:
            entries = read_lastpass_csv(path)
            added = self.vault.import_entries(entries)
        except (OSError, UnicodeDecodeError, VaultError) as error:
            self.status.set_text(f"⚠ Import failed: {error}")
            return
        self.rebuild_list()
        self.status.set_text(f"Imported {added} of {len(entries)} logins ({len(entries) - added} already here)")
        self.confirm("Delete the CSV file?",
                     f"{os.path.basename(path)} has all your passwords in plain text. "
                     "Now that they're in the vault, it's safer to delete it.",
                     lambda: os.remove(path), action_label="Delete file")

    def confirm(self, message, detail, action, action_label="Delete"):
        dialog = Gtk.AlertDialog(message=message, detail=detail, buttons=["Cancel", action_label],
                                 cancel_button=0, default_button=0)

        def finish(source, result):
            try:
                if source.choose_finish(result) == 1:
                    action()
            except GLib.Error:
                pass

        dialog.choose(self.get_root(), None, finish)
