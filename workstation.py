#!/usr/bin/env python3
import array
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import wave
from datetime import date, datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, GObject, Graphene, Gsk, Gtk  # noqa: E402

from workstation_notes import NOTES_CSS, NotesView  # noqa: E402
from workstation_tasks import TASKS_CSS, TasksView  # noqa: E402
from workstation_retro import BLACK, PINK, RETRO_CSS, SILVER_LO, BootScreen, Scanlines  # noqa: E402
from workstation_theme import ACCENT, THEME_CSS  # noqa: E402

APP_ID = "dev.matheus.AllInOneWorkstation"
APP_NAME = "All-in-One Workstation"
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "all-in-one-workstation")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "all-in-one-workstation")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
PANEL_FILE = os.path.join(GLib.get_user_runtime_dir(), "all-in-one-workstation", "panel.json")

MODES = {"pomodoro": "Pomodoro", "short": "Short Break", "long": "Long Break"}
SOUNDS = ["80s Alarm", "Alarm Clock", "Wristwatch Alarm", "Elevator Ding", "Ding", "Door Bell"]
THEMES = {"dracula": ("Dracula", THEME_CSS), "retro": ("PC anos 2000", RETRO_CSS)}
VOLUMES = [("Mute", 0), ("10%", 10), ("25%", 25), ("50%", 50), ("75%", 75), ("100%", 100)]
LONG_BREAK_EVERY = 4

DEFAULTS = {
    "times": {"pomodoro": 25, "short": 5, "long": 10},
    "title_indicator": True,
    "notifications": True,
    "auto_start": False,
    "theme": "dracula",
    "boot_screen": True,
    "retro_sounds": True,
    "goal": 8,
    "sound": "80s Alarm",
    "volume": 50,
    "done_today": 0,
    "done_date": "",
    "log": [],
    "history": {},
}
CHART_WEEKS = 8

CSS = """
.card { border-radius: 14px; padding: 28px 24px; }
.mode-btn { font-weight: bold; padding: 4px 14px; }
.timer { font-size: 112px; font-weight: 800; font-feature-settings: "tnum"; }
.ctl { font-weight: bold; font-size: 15px; padding: 8px 26px; }
.ctl:disabled { opacity: 0.45; }
.section-title { font-weight: bold; font-size: 15px; }
.log-head { font-weight: bold; opacity: 0.7; }
.hint { opacity: 0.6; font-size: 12px; }
.week-count { font-size: 12px; font-weight: bold; font-feature-settings: "tnum"; }
.week-label { font-size: 11px; opacity: 0.6; }
.week-label.current { opacity: 1; font-weight: bold; }
"""


class Store:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(STATE_FILE) as f:
                saved = json.load(f)
            self.data.update(saved)
            self.data["times"] = {**DEFAULTS["times"], **saved.get("times", {})}
            if "history" not in saved:
                self.data["history"] = self.history_from_log()
        except (OSError, ValueError):
            pass
        self.roll_day()

    def history_from_log(self):
        """Rebuild daily pomodoro counts from the time log for states saved before history existed."""
        history = {}
        full = self.data["times"]["pomodoro"] * 60 - 5
        for entry in self.data["log"]:
            if entry["session"] != MODES["pomodoro"] or not entry.get("date") or not entry["end"]:
                continue
            start, end = (datetime.strptime(entry[k], "%H:%M:%S") for k in ("start", "end"))
            if (end - start).total_seconds() % 86400 >= full:
                history[entry["date"]] = history.get(entry["date"], 0) + 1
        if self.data["done_date"] == date.today().isoformat():
            history[self.data["done_date"]] = max(history.get(self.data["done_date"], 0), self.data["done_today"])
        return history

    def set_done_today(self, count):
        self.roll_day()
        self.data["done_today"] = count
        self.data["history"][self.data["done_date"]] = count
        self.save()

    def weekly_counts(self, weeks):
        """Completed pomodoros per week (Monday first), oldest first, ending with the current week."""
        monday = date.today() - timedelta(days=date.today().weekday())
        starts = [monday - timedelta(weeks=i) for i in reversed(range(weeks))]
        counts = dict.fromkeys(starts, 0)
        for day, count in self.data["history"].items():
            d = date.fromisoformat(day)
            start = d - timedelta(days=d.weekday())
            if start in counts:
                counts[start] += count
        return list(counts.items())

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, STATE_FILE)

    def roll_day(self):
        today = date.today().isoformat()
        if self.data["done_date"] != today:
            self.data["done_date"] = today
            self.data["done_today"] = 0

    def add_done(self):
        self.roll_day()
        self.set_done_today(self.data["done_today"] + 1)


class Sounds:
    RATE = 44100
    MASTER_GAIN = 0.3
    RETRO_LEVELS = {"Click": 0.35, "Beep High": 0.25, "Beep Low": 0.25, "POST Beep": 0.3}

    def __init__(self):
        self.media = {}

    def path_for(self, name, volume, level=1.0):
        os.makedirs(CACHE_DIR, exist_ok=True)
        slug = name.lower().replace(" ", "-")
        suffix = f"-l{level}" if level != 1.0 else ""
        path = os.path.join(CACHE_DIR, f"{slug}-{volume}-g{self.MASTER_GAIN}{suffix}.wav")
        if not os.path.exists(path):
            self.write_wav(path, self.render(name), volume, level)
        return path

    def blip(self, name, volume):
        if volume <= 0:
            return
        path = self.path_for(name, volume, self.RETRO_LEVELS[name])
        media = self.media.get(path)
        if media is None:
            media = self.media[path] = Gtk.MediaFile.new_for_filename(path)
        elif media.get_ended() or media.get_playing():
            media.seek(0)
        media.play()

    def play(self, name, volume):
        if volume <= 0:
            return
        path = self.path_for(name, volume)
        for player in (["pw-play"], ["paplay"], ["aplay", "-q"], ["canberra-gtk-play", "-f"]):
            if shutil.which(player[0]):
                subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        Gdk.Display.get_default().beep()

    def write_wav(self, path, samples, volume, level=1.0):
        peak = max((abs(s) for s in samples), default=1.0) or 1.0
        gain = self.MASTER_GAIN * level * (volume / 100) ** 2 * 32767 / peak
        pcm = array.array("h", (int(s * gain) for s in samples))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.RATE)
            w.writeframes(pcm.tobytes())

    def render(self, name):
        if name == "80s Alarm":
            burst = (self.tone(2000, 0.08, square=True) + self.silence(0.06)) * 4
            return (burst + self.silence(0.45)) * 3
        if name == "Alarm Clock":
            ring = []
            for i in range(28):
                ring += self.bell(1750 if i % 2 else 1650, 0.045, decay=18)
            return (ring + self.silence(0.4)) * 2
        if name == "Wristwatch Alarm":
            beeps = (self.tone(4000, 0.07) + self.silence(0.07)) * 4
            return (beeps + self.silence(0.6)) * 3
        if name == "Elevator Ding":
            return self.bell(1046.5, 2.6, decay=1.4)
        if name == "Ding":
            return self.bell(1568, 1.4, decay=3.5)
        if name == "Door Bell":
            return self.bell(659.3, 0.75, decay=2.2) + self.bell(523.3, 2.0, decay=1.6)
        if name == "Click":
            return self.click()
        if name == "Beep High":
            return self.tone(1046.5, 0.07, square=True)
        if name == "Beep Low":
            return self.tone(523.3, 0.07, square=True)
        if name == "POST Beep":
            return self.tone(1000, 0.22, square=True)
        return self.bell(1046.5, 1.5)

    def silence(self, dur):
        return [0.0] * int(self.RATE * dur)

    def tone(self, freq, dur, square=False):
        n = int(self.RATE * dur)
        edge = int(self.RATE * 0.004)
        out = []
        for i in range(n):
            v = math.sin(2 * math.pi * freq * i / self.RATE)
            if square:
                v = 0.6 if v >= 0 else -0.6
            out.append(v * min(1.0, i / edge, (n - i) / edge))
        return out

    def click(self):
        rng = random.Random(98)
        out = []
        for i in range(int(self.RATE * 0.025)):
            t = i / self.RATE
            out.append(rng.uniform(-1, 1) * math.exp(-t / 0.0025)
                       + 0.8 * math.sin(2 * math.pi * 2600 * t) * math.exp(-t / 0.004)
                       + 0.6 * math.sin(2 * math.pi * 140 * t) * math.exp(-t / 0.008))
        return out

    def bell(self, freq, dur, decay=3.0):
        n = int(self.RATE * dur)
        partials = ((1.0, 1.0), (2.0, 0.45), (3.01, 0.22), (4.17, 0.12), (5.43, 0.06))
        attack = int(self.RATE * 0.002)
        out = [0.0] * n
        for mult, amp in partials:
            w = 2 * math.pi * freq * mult / self.RATE
            k = decay * (0.6 + 0.4 * mult) / self.RATE
            for i in range(n):
                out[i] += amp * math.sin(w * i) * math.exp(-k * i)
        for i in range(min(attack, n)):
            out[i] *= i / attack
        tail = int(self.RATE * 0.01)
        for i in range(max(0, n - tail), n):
            out[i] *= (n - i) / tail
        return out


class GoalBar(Gtk.Widget):
    BLOCK, GAP, PAD = 10, 2, 3

    def __init__(self):
        super().__init__(height_request=8)
        self.fraction = 0.0
        self.retro = False

    def set_fraction(self, fraction):
        self.fraction = fraction
        self.queue_draw()

    def set_retro(self, retro):
        self.retro = retro
        self.set_size_request(-1, 20 if retro else 8)
        self.queue_draw()

    def do_snapshot(self, snapshot):
        if self.retro:
            self.snapshot_blocks(snapshot)
            return
        width, height = self.get_width(), self.get_height()
        bounds = Graphene.Rect().init(0, 0, width, height)
        clip = Gsk.RoundedRect()
        clip.init_from_rect(bounds, height / 2)
        fg = self.get_color()
        track = Gdk.RGBA()
        track.red, track.green, track.blue, track.alpha = fg.red, fg.green, fg.blue, 0.1
        fill = Gdk.RGBA()
        fill.parse(ACCENT)
        snapshot.push_rounded_clip(clip)
        snapshot.append_color(track, bounds)
        snapshot.append_color(fill, Graphene.Rect().init(0, 0, width * self.fraction, height))
        snapshot.pop()

    def snapshot_blocks(self, snapshot):
        width, height = self.get_width(), self.get_height()

        def rect(color, x, y, w, h):
            rgba = Gdk.RGBA()
            rgba.parse(color)
            snapshot.append_color(rgba, Graphene.Rect().init(x, y, w, h))

        rect("#ffffff", 0, 0, width, height)
        rect(SILVER_LO, 0, 0, width - 1, height - 1)
        rect(BLACK, 1, 1, width - 2, height - 2)
        step = self.BLOCK + self.GAP
        blocks = round((width - 2 * self.PAD + self.GAP) // step * self.fraction)
        for i in range(blocks):
            rect(PINK, self.PAD + i * step, self.PAD, self.BLOCK, height - 2 * self.PAD)


class WeekBar(Gtk.Widget):
    def __init__(self):
        super().__init__(vexpand=True, width_request=26)
        self.fraction = 0.0
        self.retro = False

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        bar = max(2.0, height * self.fraction) if self.fraction else 0.0
        rgba = Gdk.RGBA()
        rgba.parse(PINK if self.retro else ACCENT)
        if self.retro:
            snapshot.append_color(rgba, Graphene.Rect().init(0, height - bar, width, bar))
            return
        rounded = Gsk.RoundedRect()
        top = Graphene.Size().init(min(4, bar), min(4, bar))
        rounded.init(Graphene.Rect().init(0, height - bar, width, bar), top, top,
                     Graphene.Size().init(0, 0), Graphene.Size().init(0, 0))
        snapshot.push_rounded_clip(rounded)
        snapshot.append_color(rgba, rounded.bounds)
        snapshot.pop()


class WeekChart(Gtk.Box):
    """Bar chart of completed pomodoros per week."""

    def __init__(self):
        super().__init__(spacing=10, homogeneous=True, height_request=150)
        self.columns = []
        for _ in range(CHART_WEEKS):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            count = Gtk.Label(css_classes=["week-count"])
            bar = WeekBar()
            bar.set_halign(Gtk.Align.CENTER)
            label = Gtk.Label(css_classes=["week-label"])
            for widget in (count, bar, label):
                column.append(widget)
            self.append(column)
            self.columns.append((column, count, bar, label))

    def set_retro(self, retro):
        for *_rest, bar, _label in self.columns:
            bar.retro = retro
            bar.queue_draw()

    def update(self, weeks):
        peak = max((count for _start, count in weeks), default=0)
        for (column, count_label, bar, label), (start, count) in zip(self.columns, weeks):
            current = start == weeks[-1][0]
            count_label.set_text(str(count) if count else "")
            bar.fraction = count / peak if peak else 0.0
            bar.queue_draw()
            label.set_text("This week" if current else start.strftime("%d/%m"))
            if current:
                label.add_css_class("current")
            else:
                label.remove_css_class("current")
            end = start + timedelta(days=6)
            column.set_tooltip_text(f"{start:%d/%m} – {end:%d/%m}: {count} pomodoro{'s' if count != 1 else ''}")


class OptionsWindow(Gtk.Window):
    def __init__(self, main):
        super().__init__(title="Options", transient_for=main, modal=True, resizable=False)
        self.main = main
        self.store = main.store

        grid = Gtk.Grid(row_spacing=10, column_spacing=16, margin_top=20, margin_bottom=20,
                        margin_start=24, margin_end=24)
        self.set_child(grid)
        row = 0

        def title(text):
            nonlocal row
            label = Gtk.Label(label=text, xalign=0, css_classes=["section-title"],
                              margin_top=0 if row == 0 else 10)
            grid.attach(label, 0, row, 2, 1)
            row += 1

        def toggle(text, key):
            nonlocal row
            check = Gtk.CheckButton(label=text, active=self.store[key])
            check.connect("toggled", lambda b: self.set_value(key, b.get_active()))
            grid.attach(check, 0, row, 2, 1)
            row += 1

        def labeled(text, widget):
            nonlocal row
            grid.attach(Gtk.Label(label=text, xalign=0, hexpand=True), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            row += 1

        title("Appearance")
        theme_keys = list(THEMES)
        theme = Gtk.DropDown.new_from_strings([label for label, _css in THEMES.values()])
        theme.set_selected(theme_keys.index(self.store["theme"]) if self.store["theme"] in THEMES else 0)
        theme.connect("notify::selected", lambda d, _p: self.pick_theme(theme_keys[d.get_selected()]))
        labeled("Theme", theme)
        toggle("PC anos 2000: boot screen on startup?", "boot_screen")
        toggle("PC anos 2000: retro click sounds?", "retro_sounds")

        title("User preferences")
        toggle("Timer indication in title?", "title_indicator")
        toggle("Desktop notifications?", "notifications")
        toggle("Auto start pomodoros and breaks?", "auto_start")
        goal = Gtk.SpinButton.new_with_range(1, 50, 1)
        goal.set_value(self.store["goal"])
        goal.connect("value-changed", lambda s: self.set_value("goal", s.get_value_as_int()))
        labeled("Pomodoro goal for the day", goal)

        title("Select Sound")
        sound = Gtk.DropDown.new_from_strings(SOUNDS)
        sound.set_selected(SOUNDS.index(self.store["sound"]) if self.store["sound"] in SOUNDS else 0)
        sound.connect("notify::selected", lambda d, _p: self.pick_sound(SOUNDS[d.get_selected()]))
        test = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Test sound")
        test.connect("clicked", lambda _b: self.main.sounds.play(self.store["sound"], self.store["volume"]))
        sound_box = Gtk.Box(spacing=6)
        sound_box.append(sound)
        sound_box.append(test)
        labeled("Sound", sound_box)

        title("Select Volume")
        labels = [label for label, _ in VOLUMES]
        values = [value for _, value in VOLUMES]
        volume = Gtk.DropDown.new_from_strings(labels)
        volume.set_selected(values.index(self.store["volume"]) if self.store["volume"] in values else values.index(50))
        volume.connect("notify::selected", lambda d, _p: self.pick_volume(values[d.get_selected()]))
        labeled("Volume", volume)

        title("Set Custom Times (in minutes)")
        self.time_spins = {}
        for key, label in MODES.items():
            spin = Gtk.SpinButton.new_with_range(1, 240, 1)
            spin.set_value(self.store["times"][key])
            spin.connect("value-changed", lambda s, k=key: self.set_time(k, s.get_value_as_int()))
            self.time_spins[key] = spin
            labeled(label, spin)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=14)
        defaults = Gtk.Button(label="Reset to defaults")
        defaults.connect("clicked", self.reset_defaults)
        close = Gtk.Button(label="Close", css_classes=["suggested-action"])
        close.connect("clicked", lambda _b: self.close())
        buttons.append(defaults)
        buttons.append(close)
        grid.attach(buttons, 0, row, 2, 1)

    def set_value(self, key, value):
        self.store[key] = value
        self.main.refresh()

    def pick_theme(self, key):
        self.store["theme"] = key
        self.main.apply_theme()

    def pick_sound(self, name):
        self.store["sound"] = name
        self.main.sounds.play(name, self.store["volume"])

    def pick_volume(self, value):
        self.store["volume"] = value
        self.main.sounds.play(self.store["sound"], value)

    def set_time(self, key, minutes):
        self.store.data["times"][key] = minutes
        self.store.save()
        self.main.on_times_changed()

    def reset_defaults(self, _button):
        for key, spin in self.time_spins.items():
            spin.set_value(DEFAULTS["times"][key])


class WorkstationWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.store = Store()
        self.sounds = Sounds()
        self.mode = "pomodoro"
        self.running = False
        self.remaining = self.duration()
        self.end_at = 0.0
        self.tick_id = None
        self.open_entry = None
        self.panel_state = None
        self.set_default_size(960, 760)

        header = Gtk.HeaderBar()
        self.retro_icon = Gtk.Image(icon_name=APP_ID, pixel_size=18)
        self.retro_title = Gtk.Label(css_classes=["titlebar-label"])
        self.bind_property("title", self.retro_title, "label", GObject.BindingFlags.SYNC_CREATE)
        header.pack_start(self.retro_icon)
        header.pack_start(self.retro_title)
        options = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options",
                             css_classes=["flat", "titlebar-btn"])
        options.connect("clicked", lambda _b: OptionsWindow(self).present())
        header.pack_end(options)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=20,
                       margin_bottom=16, margin_start=20, margin_end=20, width_request=560,
                       halign=Gtk.Align.CENTER)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(root)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.stack.add_titled(scroller, "timer", "Timer")
        self.tasks = TasksView(self.focus_on_task)
        self.stack.add_titled(self.tasks, "tasks", "Tasks")
        self.notes = NotesView()
        self.stack.add_titled(self.notes, "notes", "Notes")
        self.connect("close-request", self.on_close)

        self.header_tabs = Gtk.StackSwitcher(stack=self.stack)
        header.set_title_widget(self.header_tabs)
        self.tabstrip = Gtk.Box(css_classes=["tabstrip"])
        self.tabstrip.append(Gtk.StackSwitcher(stack=self.stack))
        well = Gtk.Box(css_classes=["well"])
        well.append(self.stack)
        self.statusbar = self.build_statusbar()
        desktop = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["chrome"])
        desktop.append(self.tabstrip)
        desktop.append(well)
        desktop.append(self.statusbar)
        self.overlay = Gtk.Overlay(child=desktop)
        self.set_child(self.overlay)

        root.append(self.build_card())
        root.append(self.build_goal())
        root.append(self.build_chart())
        root.append(self.build_log())
        root.append(Gtk.Label(
            label="SPACE  Start / Stop     ALT+P  Pomodoro     ALT+S  Short Break     "
                  "ALT+L  Long Break     ALT+R  Reset     ALT+1/2/3  Tabs",
            css_classes=["hint"], wrap=True, justify=Gtk.Justification.CENTER))

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        presses = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        presses.connect("pressed", self.on_any_press)
        self.add_controller(presses)
        GObject.type_class_ref(Gtk.Button)
        GObject.add_emission_hook(Gtk.Button, "clicked", self.on_any_click)

        self.refresh()
        self.rebuild_log()
        self.apply_theme()
        self.boot = None
        if self.is_retro() and self.store["boot_screen"]:
            self.start_boot()

    def is_retro(self):
        return self.store["theme"] == "retro"

    def apply_theme(self):
        retro = self.is_retro()
        self.get_application().load_theme(self.store["theme"])
        for widget in (self.retro_icon, self.retro_title, self.tabstrip, self.statusbar, self.scanlines):
            widget.set_visible(retro)
        self.header_tabs.set_visible(not retro)
        self.goal_bar.set_retro(retro)
        self.week_chart.set_retro(retro)

    def build_statusbar(self):
        bar = Gtk.Box(spacing=4, css_classes=["statusbar"])
        self.status_label = Gtk.Label(xalign=0, hexpand=True, css_classes=["panel"])
        self.status_goal = Gtk.Label(css_classes=["panel"])
        self.status_clock = Gtk.Label(css_classes=["panel"])
        for label in (self.status_label, self.status_goal, self.status_clock):
            bar.append(label)
        self.tick_clock()
        GLib.timeout_add_seconds(5, self.tick_clock)
        return bar

    def tick_clock(self):
        self.status_clock.set_text(datetime.now().strftime("%H:%M"))
        return True

    def start_boot(self):
        open_tasks = sum(1 for t in self.tasks.store.tasks if not t["done"])
        checks = [("Detecting Pomodoro timer", f"{self.store['times']['pomodoro']} MIN"),
                  ("Loading tasks", f"{open_tasks} OPEN"),
                  ("Mounting notes", f"{len(self.notes.store.titles())} FILES")]
        revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                transition_duration=350, reveal_child=True)
        self.boot = BootScreen(APP_ID, checks, lambda: self.end_boot(revealer))
        revealer.set_child(self.boot)
        self.overlay.add_overlay(revealer)
        self.retro("POST Beep")

    def end_boot(self, revealer):
        self.boot = None
        revealer.connect("notify::child-revealed", lambda r, _p: self.overlay.remove_overlay(r))
        revealer.set_reveal_child(False)

    def retro(self, name):
        if self.is_retro() and self.store["retro_sounds"]:
            self.sounds.blip(name, self.store["volume"])

    def on_any_click(self, *_args):
        self.retro("Click")
        return True

    def on_any_press(self, gesture, _n_press, x, y):
        widget = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget and not isinstance(widget, (Gtk.Button, Gtk.CheckButton, Gtk.ListBoxRow)):
            widget = widget.get_parent()
        if isinstance(widget, (Gtk.CheckButton, Gtk.ListBoxRow)):
            self.retro("Click")
        gesture.set_state(Gtk.EventSequenceState.DENIED)

    def build_card(self):
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["card"])

        modes = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
        self.mode_buttons = {}
        group = None
        for key, label in MODES.items():
            button = Gtk.ToggleButton(label=label, css_classes=["mode-btn"], focus_on_click=False)
            if group:
                button.set_group(group)
            group = group or button
            button.connect("toggled", self.on_mode_toggled, key)
            self.mode_buttons[key] = button
            modes.append(button)
        self.mode_buttons[self.mode].set_active(True)
        self.card.append(modes)

        self.time_label = Gtk.Label(css_classes=["timer"])
        self.card.append(self.time_label)

        controls = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        self.start_button = Gtk.Button(label="Start", css_classes=["ctl", "start"], focus_on_click=False)
        self.stop_button = Gtk.Button(label="Stop", css_classes=["ctl", "stop"], focus_on_click=False)
        reset_button = Gtk.Button(label="Reset", css_classes=["ctl", "reset"], focus_on_click=False)
        self.start_button.connect("clicked", lambda _b: self.start())
        self.stop_button.connect("clicked", lambda _b: self.stop())
        reset_button.connect("clicked", lambda _b: self.reset())
        for button in (self.start_button, self.stop_button, reset_button):
            controls.append(button)
        self.card.append(controls)
        screen = Gtk.Overlay(child=self.card)
        self.scanlines = Scanlines()
        screen.add_overlay(self.scanlines)
        return screen

    def build_goal(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        top = Gtk.Box(spacing=8)
        self.goal_label = Gtk.Label(xalign=0, hexpand=True, css_classes=["section-title"])
        clear = Gtk.Button(label="Clear pomodoro's done today", css_classes=["flat"])
        clear.connect("clicked", self.clear_done)
        top.append(self.goal_label)
        top.append(clear)
        self.goal_bar = GoalBar()
        box.append(top)
        box.append(self.goal_bar)
        return box

    def build_chart(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(Gtk.Label(label="Pomodoros per week", xalign=0, css_classes=["section-title"]))
        self.week_chart = WeekChart()
        box.append(self.week_chart)
        return box

    def build_log(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        top = Gtk.Box(spacing=8)
        top.append(Gtk.Label(label="Time Log", xalign=0, hexpand=True, css_classes=["section-title"]))
        clear = Gtk.Button(label="Clear timer log", css_classes=["flat"])
        clear.connect("clicked", self.clear_log)
        top.append(clear)
        box.append(top)
        self.log_grid = Gtk.Grid(row_spacing=6, column_spacing=14)
        box.append(self.log_grid)
        return box

    def duration(self, mode=None):
        return self.store["times"][mode or self.mode] * 60

    def on_mode_toggled(self, button, key):
        if button.get_active() and key != self.mode:
            self.switch_mode(key)

    def switch_mode(self, key):
        self.halt()
        self.close_entry()
        self.mode = key
        self.remaining = self.duration()
        self.mode_buttons[key].set_active(True)
        self.refresh()

    def start(self):
        if self.running:
            return
        if self.remaining <= 0:
            self.remaining = self.duration()
        if self.open_entry is None:
            self.begin_entry()
        self.running = True
        self.retro("Beep High")
        self.end_at = time.monotonic() + self.remaining
        self.tick_id = GLib.timeout_add(200, self.tick)
        self.refresh()

    def stop(self):
        if not self.running:
            return
        self.remaining = max(0.0, self.end_at - time.monotonic())
        self.halt()
        self.retro("Beep Low")
        self.refresh()

    def halt(self):
        self.running = False
        if self.tick_id:
            GLib.source_remove(self.tick_id)
            self.tick_id = None

    def reset(self):
        self.halt()
        self.close_entry()
        self.remaining = self.duration()
        self.refresh()

    def tick(self):
        self.remaining = max(0.0, self.end_at - time.monotonic())
        if self.remaining <= 0:
            self.tick_id = None
            self.complete()
            return False
        self.refresh()
        return True

    def complete(self):
        self.running = False
        self.remaining = 0
        finished = self.mode
        self.close_entry()
        if finished == "pomodoro":
            self.store.add_done()
        self.sounds.play(self.store["sound"], self.store["volume"])
        self.notify_end(finished)
        self.refresh()
        if self.store["auto_start"]:
            self.switch_mode(self.next_mode(finished))
            self.start()

    def next_mode(self, finished):
        if finished != "pomodoro":
            return "pomodoro"
        return "long" if self.store["done_today"] % LONG_BREAK_EVERY == 0 else "short"

    def notify_end(self, finished):
        if not self.store["notifications"] or not shutil.which("notify-send"):
            return
        if finished == "pomodoro":
            body = "Pomodoro complete! Time for a break."
        else:
            body = f"{MODES[finished]} is over! Back to work."
        subprocess.Popen(["notify-send", "-a", APP_NAME, "-i", APP_ID, "-u", "critical", APP_NAME, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_times_changed(self):
        if not self.running and self.open_entry is None:
            self.remaining = self.duration()
        self.refresh()

    def begin_entry(self):
        self.open_entry = {
            "session": MODES[self.mode],
            "date": date.today().isoformat(),
            "start": datetime.now().strftime("%H:%M:%S"),
            "end": "",
            "description": "",
        }
        self.store["log"].append(self.open_entry)
        self.store.save()
        self.rebuild_log()

    def close_entry(self):
        if self.open_entry is None:
            return
        self.open_entry["end"] = datetime.now().strftime("%H:%M:%S")
        self.open_entry = None
        self.store.save()
        self.rebuild_log()

    def clear_done(self, _button):
        self.store.set_done_today(0)
        self.refresh()

    def clear_log(self, _button):
        self.open_entry = None
        self.store["log"] = []
        self.rebuild_log()

    def rebuild_log(self):
        while child := self.log_grid.get_first_child():
            self.log_grid.remove(child)
        for col, text in enumerate(("Session", "Start time", "End time", "Description")):
            self.log_grid.attach(Gtk.Label(label=text, xalign=0, css_classes=["log-head"]), col, 0, 1, 1)
        if not self.store["log"]:
            self.log_grid.attach(Gtk.Label(label="No sessions yet.", xalign=0, css_classes=["hint"]), 0, 1, 4, 1)
            return
        for row, entry in enumerate(reversed(self.store["log"]), start=1):
            self.log_grid.attach(Gtk.Label(label=entry["session"], xalign=0), 0, row, 1, 1)
            self.log_grid.attach(Gtk.Label(label=entry["start"], xalign=0), 1, row, 1, 1)
            self.log_grid.attach(Gtk.Label(label=entry["end"] or "…", xalign=0), 2, row, 1, 1)
            description = Gtk.Entry(text=entry["description"], placeholder_text="What did you work on?",
                                    hexpand=True)
            description.connect("changed", self.on_description_changed, entry)
            self.log_grid.attach(description, 3, row, 1, 1)

    def on_description_changed(self, field, entry):
        entry["description"] = field.get_text()
        self.store.save()

    def refresh(self):
        seconds = math.ceil(self.remaining)
        clock = f"{seconds // 60:02d}:{seconds % 60:02d}"
        self.time_label.set_text(clock)
        if self.running:
            self.status_label.set_text(f"Running: {MODES[self.mode]}")
        elif self.remaining <= 0:
            self.status_label.set_text("Time's up!")
        elif self.remaining < self.duration():
            self.status_label.set_text(f"Paused: {MODES[self.mode]}")
        else:
            self.status_label.set_text("Ready")
        if self.store["title_indicator"] and (self.running or 0 < self.remaining < self.duration()):
            self.set_title(f"({clock}) {APP_NAME}")
        elif self.store["title_indicator"] and self.remaining <= 0:
            self.set_title(f"Time's up! {APP_NAME}")
        else:
            self.set_title(APP_NAME)
        for key in MODES:
            self.card.remove_css_class(key)
        self.card.add_css_class(self.mode)
        self.start_button.set_sensitive(not self.running)
        self.stop_button.set_sensitive(self.running)

        self.store.roll_day()
        done, goal = self.store["done_today"], self.store["goal"]
        self.goal_label.set_text(f"Pomodoro goal tracker: {done} / {goal}")
        self.status_goal.set_text(f"Pomodoros {done}/{goal}")
        self.goal_bar.set_fraction(min(1.0, done / goal) if goal else 0.0)
        self.week_chart.update(self.store.weekly_counts(CHART_WEEKS))
        self.publish_panel()

    def publish_panel(self):
        state = {"pid": os.getpid(), "mode": self.mode, "running": self.running}
        if self.running:
            state["end_at"] = round(time.time() + self.end_at - time.monotonic())
        else:
            state["remaining"] = math.ceil(self.remaining)
        if state == self.panel_state:
            return
        self.panel_state = state
        os.makedirs(os.path.dirname(PANEL_FILE), exist_ok=True)
        tmp = PANEL_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, PANEL_FILE)

    def on_close(self, _window):
        try:
            os.remove(PANEL_FILE)
        except OSError:
            pass
        return self.notes.flush()

    def focus_on_task(self, title):
        self.stack.set_visible_child_name("timer")
        self.switch_mode("pomodoro")
        self.start()
        self.open_entry["description"] = title
        self.store.save()
        self.rebuild_log()

    def on_key(self, _controller, keyval, _keycode, state):
        if self.boot:
            self.boot.finish()
            return True
        tabs = {Gdk.KEY_1: "timer", Gdk.KEY_2: "tasks", Gdk.KEY_3: "notes"}
        if state & Gdk.ModifierType.ALT_MASK and keyval in tabs:
            self.stack.set_visible_child_name(tabs[keyval])
            return True
        if self.stack.get_visible_child_name() != "timer":
            return False
        if state & Gdk.ModifierType.ALT_MASK:
            actions = {
                Gdk.KEY_p: lambda: self.switch_mode("pomodoro"),
                Gdk.KEY_s: lambda: self.switch_mode("short"),
                Gdk.KEY_l: lambda: self.switch_mode("long"),
                Gdk.KEY_r: self.reset,
            }
            action = actions.get(Gdk.keyval_to_lower(keyval))
            if action:
                action()
                return True
        if keyval == Gdk.KEY_space and not isinstance(self.get_focus(), Gtk.Editable):
            self.stop() if self.running else self.start()
            return True
        return False


class WorkstationApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = True
        Gtk.Window.set_default_icon_name(APP_ID)
        self.provider = Gtk.CssProvider()
        self.load_theme("dracula")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def load_theme(self, name):
        _label, theme_css = THEMES.get(name, THEMES["dracula"])
        self.provider.load_from_string(CSS + TASKS_CSS + NOTES_CSS + theme_css)

    def do_activate(self):
        window = self.get_active_window() or WorkstationWindow(self)
        window.present()


if __name__ == "__main__":
    sys.exit(WorkstationApp().run(sys.argv))
