from datetime import date

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from workstation_finance import ACCOUNTS, FINANCE_FILE, Finance, brl, month_key, month_label  # noqa: E402
from workstation_theme import ACCENT, GREEN, RED  # noqa: E402

HORIZON = 36

FINANCES_CSS = f"""
.fin-page {{ padding: 20px; }}
.fin-title {{ font-size: 22px; font-weight: 800; }}
.fin-hint {{ font-size: 12px; opacity: 0.6; }}
.fin-tile {{ background: alpha(currentColor, 0.05); border-radius: 10px; padding: 12px 16px; }}
.fin-tile-label {{ font-size: 12px; opacity: 0.7; }}
.fin-tile-value {{ font-size: 22px; font-weight: 800; }}
.fin-good {{ color: {GREEN}; }}
.fin-bad {{ color: {RED}; }}
.fin-head {{ font-weight: bold; font-size: 13px; color: {ACCENT}; margin-top: 18px; }}
.fin-amount {{ font-family: monospace; }}
.fin-text {{ font-size: 14px; }}
"""


def label(text, *css, **kwargs):
    kwargs.setdefault("xalign", 0)
    return Gtk.Label(label=text, css_classes=list(css), **kwargs)


class FinancesView(Gtk.ScrolledWindow):
    """Read-only picture of the finances; Claude keeps the data up to date from the terminal."""

    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True, vexpand=True)
        self.finance = Finance()
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=620,
                            halign=Gtk.Align.CENTER, css_classes=["fin-page"])
        self.set_child(self.page)
        self.monitor = Gio.File.new_for_path(FINANCE_FILE).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_disk_changed)
        self.reload_pending = False
        self.rebuild()

    def on_disk_changed(self, _monitor, _file, _other, event):
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED) and not self.reload_pending:
            self.reload_pending = True
            GLib.timeout_add(300, self.reload_from_disk)

    def reload_from_disk(self):
        self.reload_pending = False
        self.finance.reload()
        self.rebuild()
        return False

    def updated_at(self):
        stamps = [i["at"] for i in self.finance.data["imports"]]
        plan = self.finance.data.get("plan") or {}
        if plan.get("updated"):
            stamps.append(plan["updated"])
        return max(stamps)[:10] if stamps else None

    def last_closed_month(self):
        """Latest month up to now with account movement, so income and spending are both known."""
        today = month_key(date.today())
        months = [m for m in self.finance.months() if m <= today and self.finance.summary(m)["income"] > 0]
        return months[-1] if months else None

    def tile(self, title, value, detail="", css=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, css_classes=["fin-tile"])
        box.append(label(title, "fin-tile-label"))
        box.append(label(value, "fin-tile-value", *([css] if css else [])))
        if detail:
            box.append(label(detail, "fin-hint", wrap=True))
        return box

    def rebuild(self):
        while child := self.page.get_first_child():
            self.page.remove(child)
        head = Gtk.Box(spacing=8)
        head.append(label("💰 Finances", "fin-title", hexpand=True))
        updated = self.updated_at()
        head.append(label(f"updated {updated[8:10]}/{updated[5:7]}" if updated else "", "fin-hint",
                          valign=Gtk.Align.END))
        self.page.append(head)
        if not self.finance.transactions and not self.finance.data["debts"]:
            self.page.append(label("Nothing here yet. Send your bills to Claude in the terminal and this page fills "
                                   "itself.", "fin-hint", wrap=True, margin_top=12))
            return

        today = month_key(date.today())
        ahead = self.finance.commitments(today, HORIZON)
        total_debt = sum(row["total"] for row in ahead)
        month = self.last_closed_month()
        summary = self.finance.summary(month) if month else None
        goal = (self.finance.plan_month(today) or {}).get("save")

        tiles = Gtk.Box(spacing=10, homogeneous=True, margin_top=10)
        tiles.append(self.tile("Total debt", brl(total_debt), "everything already committed from this month on"))
        tiles.append(self.tile("Due this month", brl(ahead[0]["total"]), month_label(today)))
        if summary:
            left = summary["left"]
            tiles.append(self.tile("Left over", brl(left), month_label(month)
                                   + (f" · goal {brl(goal)}" if goal is not None else ""),
                                   "fin-good" if left >= 0 else "fin-bad"))
        self.page.append(tiles)

        self.page.append(label("Debts", "fin-head"))
        for name, remaining, detail in self.debt_lines(ahead):
            self.page.append(self.bar_row(name, remaining, total_debt, detail))

        if summary and summary["categories"]:
            self.page.append(label(f"Where the money went · {month_label(month)}", "fin-head"))
            biggest = max(summary["categories"].values())
            for name, spent in list(summary["categories"].items())[:8]:
                self.page.append(self.bar_row(name, spent, biggest))

        self.page.append(label("Plan", "fin-head"))
        self.append_plan(today)

    def debt_lines(self, ahead):
        lines = []
        for account in ("nubank-card", "itau-card"):
            months = [row["month"] for row in ahead if row["cards"].get(account)]
            remaining = sum(row["cards"].get(account, 0) for row in ahead)
            if remaining:
                lines.append((ACCOUNTS[account], remaining, f"bills and installments until {month_label(months[-1])}"))
        for debt in self.finance.data["debts"]:
            count = sum(1 for row in ahead if debt["name"] in row["fixed"])
            if count:
                lines.append((debt["name"], debt["monthly"] * count,
                              f"{brl(debt['monthly'])}/month · {count} left, until {month_label(debt['until'])}"))
        return sorted(lines, key=lambda line: -line[1])

    def bar_row(self, name, value, top, detail=""):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=4)
        line = Gtk.Box(spacing=10)
        line.append(label(name, hexpand=True))
        line.append(label(brl(value), "fin-amount"))
        row.append(line)
        bar = Gtk.ProgressBar(fraction=min(value / top, 1.0) if top else 0)
        row.append(bar)
        if detail:
            row.append(label(detail, "fin-hint"))
        return row

    def append_plan(self, today):
        plan = self.finance.data.get("plan")
        if not plan:
            self.page.append(label("No plan yet. Ask Claude: “analisa minhas finanças e monta o plano”.",
                                   "fin-hint", wrap=True))
            return
        months = plan.get("months", [])
        index = next((i for i, m in enumerate(months) if m.get("month") == today), None)
        if index is not None:
            current = months[index]
            pay = sum(p.get("amount", 0) for p in current.get("pay", []))
            self.page.append(label(f"Month {index + 1} of {len(months)} · this month: pay off {brl(pay)}, "
                                   f"save {brl(current.get('save', 0))}", "fin-text", wrap=True))
            if current.get("note"):
                self.page.append(label(current["note"], "fin-hint", wrap=True))
        if plan.get("summary"):
            self.page.append(label(plan["summary"], "fin-text", wrap=True, selectable=True, margin_top=6))
        for number, step in enumerate(plan.get("steps", []), start=1):
            self.page.append(label(f"{number}. {step}", "fin-text", wrap=True))
