import math
from datetime import date, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, GLib, Gsk, Gtk, Pango  # noqa: E402

from workstation_circle import (DEFAULT_DAYS, GOAL_COLORS, Circle, cycle_end, cycle_start, day_number,  # noqa: E402
                                days_in_motion, entries_on, find_goal, goal_days, goals_on)
from workstation_theme import ACCENT, FG  # noqa: E402

LENGTHS = [("30 days", 30), ("60 days", 60), ("90 days (about 3 months)", 90)]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CIRCLE_CSS = "".join(
    f".circle-dot.goal-c{i} {{ background: {color}; }}\n"
    f".goal-chip.goal-c{i} > button {{ background: alpha({color}, 0.14); color: {color};"
    f" border: 1px solid alpha({color}, 0.4); }}\n"
    f".goal-chip.goal-c{i} > button:hover, .goal-chip.goal-c{i} > button:checked"
    f" {{ background: alpha({color}, 0.28); }}\n"
    f".goal-name.goal-c{i} {{ color: {color}; }}\n"
    f".swatch.goal-c{i}, .swatch.goal-c{i}:hover, .swatch.goal-c{i}:checked {{ background: {color}; }}\n"
    for i, color in enumerate(GOAL_COLORS)) + f"""
.circle-page {{ padding: 4px 0; }}
.circle-title {{ font-size: 22px; font-weight: 800; }}
.circle-meta {{ font-size: 12px; opacity: 0.6; }}
.circle-big {{ font-size: 40px; font-weight: 800; font-feature-settings: "tnum"; }}
.circle-small {{ font-size: 12px; opacity: 0.65; }}
.circle-section {{ font-weight: bold; font-size: 15px; }}
.circle-hint {{ font-size: 12px; opacity: 0.6; }}
.circle-banner {{ background: alpha({ACCENT}, 0.12); border: 1px solid alpha({ACCENT}, 0.35); border-radius: 10px;
                  padding: 10px 14px; }}
.circle-card {{ border: 1px solid alpha(currentColor, 0.12); border-radius: 10px; padding: 12px 14px; }}
.circle-dot {{ min-width: 10px; min-height: 10px; border-radius: 5px; }}
.goal-name {{ font-weight: bold; }}
.goal-chip > button {{ border-radius: 14px; padding: 2px 12px; font-weight: 600; font-size: 13px; }}
.activity-chip {{ border-radius: 12px; padding: 1px 10px; font-size: 12px; background: alpha(currentColor, 0.07); }}
.entry-row {{ padding: 4px 2px; border-bottom: 1px solid alpha(currentColor, 0.06); }}
.swatch {{ min-width: 22px; min-height: 22px; border-radius: 11px; padding: 0; }}
.swatch:checked {{ box-shadow: 0 0 0 2px {FG}; }}
.circle-empty {{ padding: 40px 20px; }}
"""


def color_class(color):
    return f"goal-c{GOAL_COLORS.index(color) if color in GOAL_COLORS else 0}"


def rgba(color, alpha=1.0):
    value = Gdk.RGBA()
    value.parse(color)
    value.alpha = alpha
    return value


def dot(color):
    return Gtk.Box(css_classes=["circle-dot", color_class(color)], valign=Gtk.Align.CENTER)


def format_day(day):
    if day == date.today():
        return "Today"
    if day == date.today() - timedelta(days=1):
        return "Yesterday"
    return f"{WEEKDAYS[day.weekday()]} {day:%d/%m}"


class Ring(Gtk.Widget):
    """The cycle drawn as a ring: one segment per day, colored by the goals worked on. Empty days stay neutral."""

    def __init__(self, on_pick):
        super().__init__(width_request=340, height_request=340, halign=Gtk.Align.CENTER, has_tooltip=True)
        self.on_pick = on_pick
        self.cycle = None
        self.selected = date.today()
        click = Gtk.GestureClick()
        click.connect("released", self.on_click)
        self.add_controller(click)
        self.connect("query-tooltip", self.on_tooltip)

    def show(self, cycle, selected):
        self.cycle, self.selected = cycle, selected
        self.queue_draw()

    def geometry(self):
        width, height = self.get_width(), self.get_height()
        outer = min(width, height) / 2 - 10
        return width / 2, height / 2, outer, outer * 0.74

    def day_at(self, x, y):
        if not self.cycle:
            return None
        cx, cy, outer, inner = self.geometry()
        if not inner - 6 <= math.hypot(x - cx, y - cy) <= outer + 10:
            return None
        angle = (math.atan2(y - cy, x - cx) + math.pi / 2) % (2 * math.pi)
        index = int(angle / (2 * math.pi / self.cycle["days"]))
        return cycle_start(self.cycle) + timedelta(days=min(index, self.cycle["days"] - 1))

    def on_click(self, _gesture, _n, x, y):
        day = self.day_at(x, y)
        if day and day <= date.today():
            self.on_pick(day)

    def on_tooltip(self, _widget, x, y, _keyboard, tooltip):
        day = self.day_at(x, y)
        if not day:
            return False
        lines = [f"Day {day_number(self.cycle, day)} · {format_day(day)} {day:%d/%m}"]
        for entry in entries_on(self.cycle, day):
            goal = find_goal(self.cycle, entry["goal"])
            lines.append(f"• {goal['title'] if goal else '?'}{': ' + entry['text'] if entry['text'] else ''}")
        if len(lines) == 1 and day <= date.today():
            lines.append("A pause, the spiral keeps going")
        tooltip.set_text("\n".join(lines))
        return True

    def do_snapshot(self, snapshot):
        if not self.cycle:
            return
        cx, cy, outer, inner = self.geometry()
        days = self.cycle["days"]
        step = 2 * math.pi / days
        gap = min(step * 0.18, 0.02)
        fg = self.get_color()
        start = cycle_start(self.cycle)
        today = date.today()

        def segment(a0, a1, r0, r1, color):
            """Fill the annular sector between angles a0..a1 and radii r0..r1 (arcs approximated by lines)."""
            steps = max(2, math.ceil((a1 - a0) / 0.02))
            angles = [a0 + (a1 - a0) * i / steps for i in range(steps + 1)]
            builder = Gsk.PathBuilder.new()
            builder.move_to(cx + r1 * math.cos(a0), cy + r1 * math.sin(a0))
            for a in angles[1:]:
                builder.line_to(cx + r1 * math.cos(a), cy + r1 * math.sin(a))
            for a in reversed(angles):
                builder.line_to(cx + r0 * math.cos(a), cy + r0 * math.sin(a))
            builder.close()
            snapshot.append_fill(builder.to_path(), Gsk.FillRule.WINDING, color)

        for index in range(days):
            day = start + timedelta(days=index)
            a0 = -math.pi / 2 + index * step + gap / 2
            a1 = a0 + step - gap
            goals = [find_goal(self.cycle, goal_id) for goal_id in goals_on(self.cycle, day)]
            goals = [goal for goal in goals if goal]
            if goals:
                band = (outer - inner) / len(goals)
                for i, goal in enumerate(goals):
                    segment(a0, a1, inner + i * band, inner + (i + 1) * band, rgba(goal["color"]))
            else:
                alpha = 0.14 if day <= today else 0.05
                neutral = Gdk.RGBA()
                neutral.red, neutral.green, neutral.blue, neutral.alpha = fg.red, fg.green, fg.blue, alpha
                segment(a0, a1, inner, outer, neutral)
            if day == self.selected:
                segment(a0, a1, outer + 3, outer + 7, rgba(FG, 0.9))
            if day == today and day != self.selected:
                segment(a0, a1, outer + 3, outer + 5, rgba(ACCENT, 0.9))


class GoalDialog(Gtk.Window):
    def __init__(self, view, goal=None):
        super().__init__(title="Edit goal" if goal else "New goal", transient_for=view.get_root(), modal=True,
                         default_width=440, resizable=False)
        self.view, self.goal = view, goal
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        self.title_entry = Gtk.Entry(text=goal["title"] if goal else "", placeholder_text="Goal (e.g. Read more)")
        self.title_entry.connect("activate", lambda _e: self.save())
        box.append(self.title_entry)

        self.color = goal["color"] if goal else view.circle.next_color(view.cycle)
        swatches = Gtk.Box(spacing=8)
        group = None
        for color in GOAL_COLORS:
            swatch = Gtk.ToggleButton(css_classes=["swatch", color_class(color)], group=group,
                                      active=color == self.color, valign=Gtk.Align.CENTER)
            swatch.connect("toggled", lambda b, c=color: b.get_active() and setattr(self, "color", c))
            group = group or swatch
            swatches.append(swatch)
        box.append(swatches)

        box.append(Gtk.Label(label="Activity bank, one per line. Small things count: on each day you pick "
                                   "whatever brings enthusiasm.", xalign=0, wrap=True, css_classes=["circle-hint"]))
        self.activities = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=6, bottom_margin=6,
                                       left_margin=6, right_margin=6)
        self.activities.get_buffer().set_text("\n".join(goal["activities"]) if goal else "")
        box.append(Gtk.ScrolledWindow(child=self.activities, has_frame=True, min_content_height=130))

        buttons = Gtk.Box(spacing=8, margin_top=4)
        if goal:
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
        box.append(buttons)
        self.set_child(box)

    def save(self):
        title = self.title_entry.get_text().strip()
        if not title:
            self.title_entry.grab_focus()
            return
        buffer = self.activities.get_buffer()
        lines = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).splitlines()
        self.view.circle.put_goal(self.view.cycle, self.goal, title, self.color, lines)
        self.view.rebuild()
        self.close()

    def delete(self):
        self.view.confirm(f"Delete “{self.goal['title']}”?",
                          "The goal and everything logged for it in this lap will be removed.",
                          lambda: (self.view.circle.remove_goal(self.view.cycle, self.goal), self.view.rebuild(),
                                   self.close()))


class CycleDialog(Gtk.Window):
    """Starts a new lap, or renames/resizes the current one."""

    def __init__(self, view, cycle=None):
        super().__init__(title="Edit lap" if cycle else "Start a lap", transient_for=view.get_root(), modal=True,
                         default_width=400, resizable=False)
        self.view, self.cycle = view, cycle
        previous = None if cycle else next(iter(view.circle.past()), None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        lap = view.circle.lap(cycle) if cycle else len(view.circle.cycles) + 1
        self.name = Gtk.Entry(text=cycle["name"] if cycle else f"Lap {lap}", placeholder_text="Name of the lap")
        self.name.connect("activate", lambda _e: self.save())
        box.append(self.name)
        self.lengths = [days for _label, days in LENGTHS]
        current = cycle["days"] if cycle else DEFAULT_DAYS
        if current not in self.lengths:
            self.lengths.append(current)
        self.length = Gtk.DropDown.new_from_strings([label for label, _ in LENGTHS] +
                                                    [f"{d} days" for d in self.lengths[len(LENGTHS):]])
        self.length.set_selected(self.lengths.index(current))
        box.append(self.length)
        self.carry = None
        if previous and previous["goals"]:
            self.carry = Gtk.CheckButton(label=f"Bring the goals from “{previous['name']}”", active=True)
            box.append(self.carry)
        self.previous = previous
        if not cycle:
            box.append(Gtk.Label(label="One activity a day is enough, the most is what feels comfortable. "
                                       "A day without activity isn't a failure: you can come back anytime.",
                                 xalign=0, wrap=True, css_classes=["circle-hint"]))
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=4)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Save" if cycle else "Start", css_classes=["suggested-action"])
        save.connect("clicked", lambda _b: self.save())
        buttons.append(cancel)
        buttons.append(save)
        box.append(buttons)
        self.set_child(box)

    def save(self):
        name = self.name.get_text().strip()
        if not name:
            self.name.grab_focus()
            return
        days = self.lengths[self.length.get_selected()]
        if self.cycle:
            self.cycle["name"], self.cycle["days"] = name, days
            self.view.circle.save()
        else:
            goals = self.previous["goals"] if self.carry and self.carry.get_active() else ()
            self.view.circle.start_cycle(name, days, goals=goals)
            self.view.selected = date.today()
        self.view.rebuild()
        self.close()


class ReviewDialog(Gtk.Window):
    def __init__(self, view):
        super().__init__(title="Close the lap", transient_for=view.get_root(), modal=True,
                         default_width=440, resizable=False)
        self.view = view
        cycle = view.cycle
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        box.append(Gtk.Label(label=f"{cycle['name']}: {days_in_motion(cycle)} days in motion", xalign=0,
                             css_classes=["circle-section"]))
        self.fields = []
        for question in ("What brought enthusiasm?", "What do you leave behind in the next lap?"):
            box.append(Gtk.Label(label=question, xalign=0, margin_top=6))
            text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=6, bottom_margin=6,
                                left_margin=6, right_margin=6)
            box.append(Gtk.ScrolledWindow(child=text, has_frame=True, min_content_height=80))
            self.fields.append(text)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        close = Gtk.Button(label="Close lap", css_classes=["suggested-action"])
        close.connect("clicked", lambda _b: self.save())
        buttons.append(cancel)
        buttons.append(close)
        box.append(buttons)
        self.set_child(box)

    def save(self):
        texts = [b.get_text(b.get_start_iter(), b.get_end_iter(), False) for b in
                 (field.get_buffer() for field in self.fields)]
        self.view.circle.close_cycle(self.view.cycle, *texts)
        self.view.rebuild()
        self.close()


class CircleView(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True, vexpand=True)
        self.circle = Circle()
        self.selected = date.today()
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=20, margin_bottom=20,
                            margin_start=20, margin_end=20, width_request=620, halign=Gtk.Align.CENTER,
                            css_classes=["circle-page"])
        self.set_child(self.page)
        self.rebuild()
        self.connect("map", lambda _w: self.on_map())

    @property
    def cycle(self):
        return self.circle.current

    def on_map(self):
        if self.selected > date.today() or (self.cycle and self.selected < cycle_start(self.cycle)):
            self.selected = date.today()
        self.circle.load()
        self.rebuild()

    def pick_day(self, day):
        self.selected = day
        self.rebuild()

    def rebuild(self):
        while child := self.page.get_first_child():
            self.page.remove(child)
        if not self.cycle:
            self.build_empty()
        else:
            self.build_cycle()
        past = self.circle.past()
        if past:
            self.page.append(self.build_past(past))

    def build_empty(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER,
                      css_classes=["circle-empty"])
        box.append(Gtk.Label(label="🌀", css_classes=["circle-big"]))
        box.append(Gtk.Label(label="Circular planning", css_classes=["circle-title"]))
        box.append(Gtk.Label(
            label="Time as a spiral, not a straight line: there's no track to fall off. Pick a few goals for a lap "
                  "of about 3 months, and each day do at least one activity toward any of them, chosen by "
                  "enthusiasm and coherence. Skipped a day? Just come back, it still counts.",
            wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60, css_classes=["circle-hint"]))
        label = "Start the next lap" if self.circle.cycles else "Start the first lap"
        start = Gtk.Button(label=label, css_classes=["suggested-action"], halign=Gtk.Align.CENTER, margin_top=8)
        start.connect("clicked", lambda _b: CycleDialog(self).present())
        box.append(start)
        self.page.append(box)

    def build_cycle(self):
        cycle = self.cycle
        today_number = day_number(cycle)
        head = Gtk.Box(spacing=8)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        titles.append(Gtk.Label(label=cycle["name"], xalign=0, css_classes=["circle-title"],
                                ellipsize=Pango.EllipsizeMode.END))
        titles.append(Gtk.Label(
            label=f"Lap {self.circle.lap(cycle)} · {cycle_start(cycle):%d/%m} – {cycle_end(cycle):%d/%m/%Y} · "
                  f"{len(cycle['goals'])} goal{'s' if len(cycle['goals']) != 1 else ''}",
            xalign=0, css_classes=["circle-meta"]))
        head.append(titles)
        for icon, tip, handler in (("document-edit-symbolic", "Edit lap", lambda _b: CycleDialog(self, cycle).present()),
                                   ("object-select-symbolic", "Close the lap with a short review",
                                    lambda _b: ReviewDialog(self).present())):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat"], valign=Gtk.Align.CENTER)
            button.connect("clicked", handler)
            head.append(button)
        self.page.append(head)

        if today_number > cycle["days"]:
            banner = Gtk.Box(spacing=10, css_classes=["circle-banner"])
            banner.append(Gtk.Label(label=f"This lap reached its {cycle['days']} days. Close it with a short review "
                                          "and start the next one whenever you like.",
                                    wrap=True, xalign=0, hexpand=True))
            close = Gtk.Button(label="Close lap", valign=Gtk.Align.CENTER)
            close.connect("clicked", lambda _b: ReviewDialog(self).present())
            banner.append(close)
            self.page.append(banner)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                         can_target=False)
        center.append(Gtk.Label(label=f"Day {min(today_number, cycle['days'])}", css_classes=["circle-big"]))
        center.append(Gtk.Label(label=f"of {cycle['days']}", css_classes=["circle-small"]))
        motion = days_in_motion(cycle)
        center.append(Gtk.Label(label=f"{motion} day{'s' if motion != 1 else ''} in motion",
                                css_classes=["circle-small"], margin_top=6))
        ring = Ring(self.pick_day)
        ring.show(cycle, self.selected)
        overlay = Gtk.Overlay(child=ring, halign=Gtk.Align.CENTER)
        overlay.add_overlay(center)
        self.page.append(overlay)

        self.page.append(self.build_day(cycle))
        self.page.append(self.build_goals(cycle))

    def build_day(self, cycle):
        day = self.selected
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["circle-card"])
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label=f"{format_day(day)} · day {day_number(cycle, day)}", xalign=0, hexpand=True,
                              css_classes=["circle-section"]))
        if day != date.today():
            back = Gtk.Button(label="Back to today", css_classes=["flat"])
            back.connect("clicked", lambda _b: self.pick_day(date.today()))
            head.append(back)
        box.append(head)

        entries = entries_on(cycle, day)
        if not entries:
            hint = ("One activity is enough. Which one brings enthusiasm today?" if day == date.today()
                    else "Nothing logged here. Did something that day? Add it below.")
            box.append(Gtk.Label(label=hint, xalign=0, wrap=True, css_classes=["circle-hint"]))
        for entry in entries:
            goal = find_goal(cycle, entry["goal"])
            if not goal:
                continue
            row = Gtk.Box(spacing=10, css_classes=["entry-row"])
            row.append(dot(goal["color"]))
            row.append(Gtk.Label(label=goal["title"], css_classes=["goal-name", color_class(goal["color"])]))
            row.append(Gtk.Label(label=entry["text"], xalign=0, hexpand=True, wrap=True))
            remove = Gtk.Button(icon_name="edit-delete-symbolic", tooltip_text="Remove", css_classes=["flat", "circular"])
            remove.connect("clicked", lambda _b, e=entry: (self.circle.unlog(cycle, day, e), self.rebuild()))
            row.append(remove)
            box.append(row)
        if entries and day == date.today():
            box.append(Gtk.Label(label="✓ Today counts. Anything more only if it feels comfortable.", xalign=0,
                                 css_classes=["circle-hint"]))

        if not cycle["goals"]:
            box.append(Gtk.Label(label="Add a goal below to start logging.", xalign=0, css_classes=["circle-hint"]))
            return box
        chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6,
                            max_children_per_line=6, margin_top=4)
        for goal in cycle["goals"]:
            chip = Gtk.MenuButton(child=Gtk.Label(label=f"+ {goal['title']}"),
                                  css_classes=["goal-chip", color_class(goal["color"])],
                                  tooltip_text="Log an activity", popover=self.log_popover(cycle, day, goal))
            chips.append(chip)
        box.append(chips)
        return box

    def log_popover(self, cycle, day, goal):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6,
                      margin_start=6, margin_end=6, width_request=260)
        popover = Gtk.Popover(child=box)

        def log(text):
            popover.popdown()
            self.circle.log(cycle, day, goal, text)
            GLib.idle_add(lambda: (self.rebuild(), False)[1])

        for activity in goal["activities"]:
            button = Gtk.Button(label=activity, css_classes=["flat"])
            button.get_child().set_xalign(0)
            button.connect("clicked", lambda _b, a=activity: log(a))
            box.append(button)
        other = Gtk.Entry(placeholder_text="Something else… (Enter)", margin_top=4 if goal["activities"] else 0)
        other.connect("activate", lambda e: log(e.get_text()))
        box.append(other)
        popover.connect("show", lambda _p: other.grab_focus() if not goal["activities"] else None)
        return popover

    def build_goals(self, cycle):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label="Goals of this lap", xalign=0, hexpand=True, css_classes=["circle-section"]))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New goal", css_classes=["flat"])
        add.connect("clicked", lambda _b: GoalDialog(self).present())
        head.append(add)
        box.append(head)
        if not cycle["goals"]:
            box.append(Gtk.Label(label="A few goals are better than many. Each one has a bank of small activities "
                                       "to choose from on any day.", xalign=0, wrap=True, css_classes=["circle-hint"]))
        elapsed = max(1, min(day_number(cycle), cycle["days"]))
        for goal in cycle["goals"]:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["circle-card"])
            top = Gtk.Box(spacing=10)
            top.append(dot(goal["color"]))
            top.append(Gtk.Label(label=goal["title"], xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END,
                                 css_classes=["goal-name", color_class(goal["color"])]))
            count = goal_days(cycle, goal)
            top.append(Gtk.Label(label=f"{count} of {elapsed} day{'s' if elapsed != 1 else ''}",
                                 css_classes=["circle-meta"]))
            edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Edit goal", css_classes=["flat"])
            edit.connect("clicked", lambda _b, g=goal: GoalDialog(self, g).present())
            top.append(edit)
            card.append(top)
            if goal["activities"]:
                bank = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6,
                                   max_children_per_line=8)
                for activity in goal["activities"]:
                    bank.append(Gtk.Label(label=activity, css_classes=["activity-chip"]))
                card.append(bank)
            box.append(card)
        return box

    def build_past(self, past):
        expander = Gtk.Expander(label=f"Past laps ({len(past)})")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        for cycle in past:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["circle-card"])
            card.append(Gtk.Label(label=cycle["name"], xalign=0, css_classes=["goal-name"]))
            card.append(Gtk.Label(
                label=f"{cycle_start(cycle):%d/%m/%Y} – {date.fromisoformat(cycle['closed']):%d/%m/%Y} · "
                      f"{days_in_motion(cycle)} days in motion", xalign=0, css_classes=["circle-meta"]))
            goals = Gtk.Box(spacing=12)
            for goal in cycle["goals"]:
                item = Gtk.Box(spacing=6)
                item.append(dot(goal["color"]))
                item.append(Gtk.Label(label=f"{goal['title']} · {goal_days(cycle, goal)}d", css_classes=["circle-meta"]))
                goals.append(item)
            card.append(goals)
            for label, key in (("Enthusiasm", "enthusiasm"), ("Left behind", "leave_behind")):
                if cycle["review"].get(key):
                    card.append(Gtk.Label(label=f"{label}: {cycle['review'][key]}", xalign=0, wrap=True,
                                          css_classes=["circle-hint"]))
            box.append(card)
        expander.set_child(box)
        return expander

    def confirm(self, message, detail, action):
        dialog = Gtk.AlertDialog(message=message, detail=detail, buttons=["Cancel", "Delete"],
                                 cancel_button=0, default_button=0)

        def finish(source, result):
            try:
                if source.choose_finish(result) == 1:
                    action()
            except GLib.Error:
                pass

        dialog.choose(self.get_root(), None, finish)
