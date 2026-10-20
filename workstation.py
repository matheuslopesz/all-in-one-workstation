#!/usr/bin/env python3
import array
import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from datetime import date, datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from workstation_notes import NOTES_CSS, NotesView  # noqa: E402
from workstation_tasks import TASKS_CSS, TasksView  # noqa: E402
from workstation_theme import PINK, THEME_CSS  # noqa: E402

APP_ID = "dev.matheus.AllInOneWorkstation"
APP_NAME = "All-in-One Workstation"
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "all-in-one-workstation")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "all-in-one-workstation")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
PANEL_FILE = os.path.join(GLib.get_user_runtime_dir(), "all-in-one-workstation", "panel.json")

MODES = {"pomodoro": "Pomodoro", "short": "Short Break", "long": "Long Break"}
SOUNDS = ["80s Alarm", "Alarm Clock", "Wristwatch Alarm", "Elevator Ding", "Ding", "Door Bell"]
VOLUMES = [("Mute", 0), ("10%", 10), ("25%", 25), ("50%", 50), ("75%", 75), ("100%", 100)]
LONG_BREAK_EVERY = 4

DEFAULTS = {
    "times": {"pomodoro": 25, "short": 5, "long": 10},
    "title_indicator": True,
    "notifications": True,
    "auto_start": False,
    "goal": 8,
    "sound": "80s Alarm",
    "volume": 50,
    "done_today": 0,
    "done_date": "",
    "log": [],
}

CSS = """
.card { border-radius: 14px; padding: 28px 24px; transition: background-color 400ms; }
.card.pomodoro { background-color: #d9534f; }
.card.short { background-color: #4c9195; }
.card.long { background-color: #457ca3; }
.card, .card label { color: white; }
.mode-btn { background: transparent; color: white; border: none; box-shadow: none; font-weight: bold; padding: 4px 14px; }
.mode-btn:hover { background: rgba(255,255,255,0.12); }
.mode-btn:checked { background: rgba(0,0,0,0.18); }
.timer { font-size: 112px; font-weight: 800; font-feature-settings: "tnum"; }
.ctl { font-weight: bold; font-size: 15px; padding: 8px 26px; color: white; border: none; box-shadow: none; }
.ctl.start { background: #5cb85c; }
.ctl.start:hover { background: #4cae4c; }
.ctl.stop { background: #c9302c; }
.ctl.stop:hover { background: #ac2925; }
.ctl.reset { background: #6c757d; }
.ctl.reset:hover { background: #5a6268; }
.ctl:disabled { opacity: 0.45; }
.section-title { font-weight: bold; font-size: 15px; }
.log-head { font-weight: bold; opacity: 0.7; }
.hint { opacity: 0.6; font-size: 12px; }
"""


class Store:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(STATE_FILE) as f:
                saved = json.load(f)
            self.data.update(saved)
            self.data["times"] = {**DEFAULTS["times"], **saved.get("times", {})}
        except (OSError, ValueError):
            pass
        self.roll_day()

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
        self.data["done_today"] += 1
        self.save()


class Sounds:
    RATE = 44100
    MASTER_GAIN = 0.3

    def path_for(self, name, volume):
        os.makedirs(CACHE_DIR, exist_ok=True)
        slug = name.lower().replace(" ", "-")
        path = os.path.join(CACHE_DIR, f"{slug}-{volume}-g{self.MASTER_GAIN}.wav")
        if not os.path.exists(path):
            self.write_wav(path, self.render(name), volume)
        return path

    def play(self, name, volume):
        if volume <= 0:
            return
        path = self.path_for(name, volume)
        for player in (["pw-play"], ["paplay"], ["aplay", "-q"], ["canberra-gtk-play", "-f"]):
            if shutil.which(player[0]):
                subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        Gdk.Display.get_default().beep()

    def write_wav(self, path, samples, volume):
        peak = max((abs(s) for s in samples), default=1.0) or 1.0
        gain = self.MASTER_GAIN * (volume / 100) ** 2 * 32767 / peak
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
    def __init__(self):
        super().__init__(height_request=8)
        self.fraction = 0.0

    def set_fraction(self, fraction):
        self.fraction = fraction
        self.queue_draw()

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        bounds = Graphene.Rect().init(0, 0, width, height)
        clip = Gsk.RoundedRect()
        clip.init_from_rect(bounds, height / 2)
        fg = self.get_color()
        track = Gdk.RGBA()
        track.red, track.green, track.blue, track.alpha = fg.red, fg.green, fg.blue, 0.1
        fill = Gdk.RGBA()
        fill.parse(PINK)
        snapshot.push_rounded_clip(clip)
        snapshot.append_color(track, bounds)
        snapshot.append_color(fill, Graphene.Rect().init(0, 0, width * self.fraction, height))
        snapshot.pop()


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
        options = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Options")
        options.connect("clicked", lambda _b: OptionsWindow(self).present())
        header.pack_end(options)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=20,
                       margin_bottom=16, margin_start=20, margin_end=20, width_request=560,
                       halign=Gtk.Align.CENTER)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(root)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(scroller, "timer", "Timer")
        self.stack.add_titled(TasksView(self.focus_on_task), "tasks", "Tasks")
        self.notes = NotesView()
        self.stack.add_titled(self.notes, "notes", "Notes")
        self.connect("close-request", self.on_close)
        header.set_title_widget(Gtk.StackSwitcher(stack=self.stack))
        self.set_child(self.stack)

        root.append(self.build_card())
        root.append(self.build_goal())
        root.append(self.build_log())
        root.append(Gtk.Label(
            label="SPACE  Start / Stop     ALT+P  Pomodoro     ALT+S  Short Break     "
                  "ALT+L  Long Break     ALT+R  Reset",
            css_classes=["hint"], wrap=True, justify=Gtk.Justification.CENTER))

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        self.refresh()
        self.rebuild_log()

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
        return self.card

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
        self.end_at = time.monotonic() + self.remaining
        self.tick_id = GLib.timeout_add(200, self.tick)
        self.refresh()

    def stop(self):
        if not self.running:
            return
        self.remaining = max(0.0, self.end_at - time.monotonic())
        self.halt()
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
        self.store["done_today"] = 0
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
        self.goal_bar.set_fraction(min(1.0, done / goal) if goal else 0.0)
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
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS + TASKS_CSS + NOTES_CSS + THEME_CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.get_active_window() or WorkstationWindow(self)
        window.present()


if __name__ == "__main__":
    sys.exit(WorkstationApp().run(sys.argv))
