"""Circular planning (Bibiana Terra's method): cycles of goals where any day can be a fresh start.

There are no streaks and no "missed" days: each day you do at least one activity toward any goal,
chosen by enthusiasm and coherence, and a cycle (a lap of the spiral) ends with a short review."""
import json
import os
import uuid
from datetime import date, timedelta

from workstation_theme import CYAN, GREEN, ORANGE, PINK, PURPLE, YELLOW

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "all-in-one-workstation")
CIRCLE_FILE = os.path.join(CONFIG_DIR, "circular.json")
DEFAULT_DAYS = 90
GOAL_COLORS = [PURPLE, PINK, CYAN, GREEN, ORANGE, YELLOW]


def new_id():
    return uuid.uuid4().hex[:12]


def cycle_start(cycle):
    return date.fromisoformat(cycle["start"])


def cycle_end(cycle):
    return cycle_start(cycle) + timedelta(days=cycle["days"] - 1)


def day_number(cycle, day=None):
    """1-based position of a day inside the cycle (can go past the length if the lap wasn't closed yet)."""
    return ((day or date.today()) - cycle_start(cycle)).days + 1


def entries_on(cycle, day):
    return cycle["log"].get(day.isoformat(), [])


def goals_on(cycle, day):
    """Distinct goal ids worked on that day, in the order they were first logged."""
    return list(dict.fromkeys(entry["goal"] for entry in entries_on(cycle, day)))


def days_in_motion(cycle):
    return sum(1 for entries in cycle["log"].values() if entries)


def goal_days(cycle, goal):
    return sum(1 for entries in cycle["log"].values() if any(e["goal"] == goal["id"] for e in entries))


def find_goal(cycle, goal_id):
    return next((goal for goal in cycle["goals"] if goal["id"] == goal_id), None)


class Circle:
    def __init__(self, path=CIRCLE_FILE):
        self.path = path
        self.cycles = []
        self.load()

    def load(self):
        try:
            with open(self.path) as f:
                self.cycles = json.load(f).get("cycles", [])
        except (OSError, ValueError):
            self.cycles = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"cycles": self.cycles}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    @property
    def current(self):
        return next((cycle for cycle in reversed(self.cycles) if not cycle["closed"]), None)

    def past(self):
        """Closed cycles, newest first."""
        return [cycle for cycle in reversed(self.cycles) if cycle["closed"]]

    def lap(self, cycle):
        return self.cycles.index(cycle) + 1

    def start_cycle(self, name, days=DEFAULT_DAYS, start=None, goals=()):
        cycle = {"id": new_id(), "name": name.strip(), "start": (start or date.today()).isoformat(), "days": days,
                 "goals": [{"id": new_id(), "title": g["title"], "color": g["color"],
                            "activities": list(g["activities"])} for g in goals],
                 "log": {}, "closed": None, "review": {}}
        self.cycles.append(cycle)
        self.save()
        return cycle

    def next_color(self, cycle):
        used = [goal["color"] for goal in cycle["goals"]]
        return min(GOAL_COLORS, key=lambda color: (used.count(color), GOAL_COLORS.index(color)))

    def put_goal(self, cycle, goal, title, color, activities):
        values = {"title": title.strip(), "color": color,
                  "activities": list(dict.fromkeys(a.strip() for a in activities if a.strip()))}
        if goal is None:
            goal = {"id": new_id(), **values}
            cycle["goals"].append(goal)
        else:
            goal.update(values)
        self.save()
        return goal

    def remove_goal(self, cycle, goal):
        cycle["goals"].remove(goal)
        for day, entries in list(cycle["log"].items()):
            cycle["log"][day] = [entry for entry in entries if entry["goal"] != goal["id"]]
            if not cycle["log"][day]:
                del cycle["log"][day]
        self.save()

    def log(self, cycle, day, goal, text):
        cycle["log"].setdefault(day.isoformat(), []).append({"goal": goal["id"], "text": text.strip()})
        self.save()

    def unlog(self, cycle, day, entry):
        entries = cycle["log"].get(day.isoformat(), [])
        entries.remove(entry)
        if not entries:
            del cycle["log"][day.isoformat()]
        self.save()

    def close_cycle(self, cycle, enthusiasm, leave_behind):
        cycle["closed"] = date.today().isoformat()
        cycle["review"] = {"enthusiasm": enthusiasm.strip(), "leave_behind": leave_behind.strip()}
        self.save()
