from datetime import date

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

from workstation_finance import (ACCOUNTS, CATEGORIES, FINANCE_FILE, NOT_SPENDING, Finance, FinanceError,  # noqa: E402
                                 add_months, brl, month_key, month_label)
from workstation_theme import ACCENT, GREEN, RED  # noqa: E402

FINANCES_CSS = f"""
.fin-month {{ font-size: 20px; font-weight: 800; }}
.fin-hint {{ font-size: 12px; opacity: 0.6; }}
.fin-tile {{ background: alpha(currentColor, 0.05); border-radius: 10px; padding: 12px 16px; }}
.fin-tile-label {{ font-size: 12px; opacity: 0.7; }}
.fin-tile-value {{ font-size: 20px; font-weight: 800; }}
.fin-good {{ color: {GREEN}; }}
.fin-bad {{ color: {RED}; }}
.fin-list {{ background: transparent; }}
.fin-list row {{ padding: 6px 4px; border-bottom: 1px solid alpha(currentColor, 0.08); }}
.fin-head {{ font-weight: bold; font-size: 13px; color: {ACCENT}; margin-top: 12px; }}
.fin-amount {{ font-family: monospace; }}
.fin-over progressbar progress {{ background: {RED}; }}
.fin-plan {{ font-size: 14px; }}
"""


def label(text, *css, **kwargs):
    kwargs.setdefault("xalign", 0)
    return Gtk.Label(label=text, css_classes=list(css), **kwargs)


def scrolled(child):
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    scroller.set_child(child)
    return scroller


def clear(box):
    while child := box.get_first_child():
        box.remove(child)


class DebtDialog(Gtk.Window):
    def __init__(self, view):
        super().__init__(title="Add fixed debt", transient_for=view.get_root(), modal=True, default_width=340,
                         resizable=False)
        grid = Gtk.Grid(row_spacing=8, column_spacing=10, margin_top=16, margin_bottom=16, margin_start=16,
                        margin_end=16)
        self.name = Gtk.Entry(placeholder_text="Car, loan…", hexpand=True)
        self.monthly = Gtk.SpinButton.new_with_range(0, 100000, 50)
        self.monthly.set_digits(2)
        self.until = Gtk.Entry(placeholder_text="YYYY-MM", text=add_months(month_key(date.today()), 12))
        for row, (text, widget) in enumerate((("Name", self.name), ("Per month", self.monthly),
                                              ("Last month", self.until))):
            grid.attach(label(text), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save.connect("clicked", lambda _b: self.save(view))
        buttons.append(cancel)
        buttons.append(save)
        grid.attach(buttons, 0, 3, 2, 1)
        self.set_child(grid)

    def save(self, view):
        until = self.until.get_text().strip()
        if not self.name.get_text().strip() or len(until) != 7 or until[4] != "-":
            return
        view.finance.add_debt(self.name.get_text().strip(), round(self.monthly.get_value(), 2), until)
        view.rebuild()
        self.close()


class FinancesView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self.finance = Finance()
        self.month = month_key(date.today())
        self.append(self.build_bar())
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.overview, self.transactions, self.debts, self.plan = (
            Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=20, margin_end=20,
                    margin_bottom=16) for _ in range(4))
        for widget, name, title in ((self.overview, "overview", "Overview"),
                                    (self.transactions, "transactions", "Transactions"),
                                    (self.debts, "debts", "Debts"), (self.plan, "plan", "Plan")):
            self.pages.add_titled(scrolled(widget), name, title)
        switcher = Gtk.StackSwitcher(stack=self.pages, halign=Gtk.Align.CENTER, margin_top=8, margin_bottom=8)
        self.append(switcher)
        self.append(self.pages)
        self.monitor = Gio.File.new_for_path(FINANCE_FILE).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_disk_changed)
        self.reload_pending = False
        self.rebuild()

    def build_bar(self):
        bar = Gtk.Box(spacing=6, margin_top=16, margin_start=20, margin_end=20)
        prev = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat"], tooltip_text="Previous month")
        prev.connect("clicked", lambda _b: self.shift(-1))
        nxt = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat"], tooltip_text="Next month")
        nxt.connect("clicked", lambda _b: self.shift(1))
        self.title = label("", "fin-month", hexpand=True)
        self.status = label("", "fin-hint", ellipsize=Pango.EllipsizeMode.END, max_width_chars=50)
        imp = Gtk.Button(label="⬆  Import bills", css_classes=["flat"],
                         tooltip_text="Nubank card (CSV), Nubank account (CSV) or Itaú card (PDF)")
        imp.connect("clicked", lambda _b: self.pick_files())
        for widget in (prev, self.title, nxt, self.status, imp):
            bar.append(widget)
        bar.reorder_child_after(nxt, prev)
        return bar

    def shift(self, step):
        self.month = add_months(self.month, step)
        self.rebuild()

    def on_disk_changed(self, _monitor, _file, _other, event):
        if event == Gio.FileMonitorEvent.CHANGES_DONE_HINT or event == Gio.FileMonitorEvent.CREATED:
            if not self.reload_pending:
                self.reload_pending = True
                GLib.timeout_add(300, self.reload_from_disk)

    def reload_from_disk(self):
        self.reload_pending = False
        self.finance.reload()
        self.rebuild()
        return False

    def rebuild(self):
        self.title.set_text(month_label(self.month))
        self.rebuild_overview()
        self.rebuild_transactions()
        self.rebuild_debts()
        self.rebuild_plan()

    def tile(self, title, value, css=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, css_classes=["fin-tile"])
        box.append(label(title, "fin-tile-label"))
        box.append(label(value, "fin-tile-value", *([css] if css else [])))
        return box

    def rebuild_overview(self):
        clear(self.overview)
        summary = self.finance.summary(self.month)
        goal = self.finance.plan_month(self.month) or {}
        tiles = Gtk.Box(spacing=10, homogeneous=True)
        tiles.append(self.tile("Income", brl(summary["income"])))
        tiles.append(self.tile("Spending", brl(summary["spent"])))
        tiles.append(self.tile("Left over", brl(summary["left"]), "fin-good" if summary["left"] >= 0 else "fin-bad"))
        if goal.get("save") is not None:
            tiles.append(self.tile("Savings goal", brl(goal["save"])))
        self.overview.append(tiles)
        if not self.finance.month_transactions(self.month):
            self.overview.append(label("Nothing imported for this month yet. Card purchases count in the month the "
                                       "bill is due.", "fin-hint", wrap=True, margin_top=12))
            return
        budgets = goal.get("budgets", {})
        self.overview.append(label("Spending by category" + (" · real vs plan" if budgets else ""), "fin-head"))
        names = list(summary["categories"]) + [c for c in budgets if c not in summary["categories"]]
        for name in names:
            spent, budget = summary["categories"].get(name, 0.0), budgets.get(name)
            row = Gtk.Box(spacing=10)
            row.append(label(name, width_chars=18))
            bar = Gtk.ProgressBar(hexpand=True, valign=Gtk.Align.CENTER)
            top = budget or max(summary["categories"].values(), default=1) or 1
            bar.set_fraction(min(spent / top, 1.0))
            row.append(bar)
            text = f"{brl(spent)} / {brl(budget)}" if budget else brl(spent)
            row.append(label(text, "fin-amount", width_chars=24, xalign=1))
            if budget and spent > budget:
                row.add_css_class("fin-over")
            click = Gtk.GestureClick()
            click.connect("released", lambda *_, n=name: self.show_category(n))
            row.add_controller(click)
            self.overview.append(row)

    def show_category(self, name):
        self.search.set_text(name)
        self.pages.set_visible_child_name("transactions")

    def rebuild_transactions(self):
        if not hasattr(self, "search"):
            self.search = Gtk.SearchEntry(placeholder_text="Filter by description or category", margin_top=4)
            self.search.connect("search-changed", lambda _e: self.fill_transactions())
            self.tx_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["fin-list"])
        clear(self.transactions)
        self.transactions.append(self.search)
        self.transactions.append(label("Changing a category also changes every purchase from the same place, "
                                       "now and in future imports.", "fin-hint", wrap=True))
        self.transactions.append(self.tx_list)
        self.fill_transactions()

    def fill_transactions(self):
        self.tx_list.remove_all()
        needle = self.search.get_text().strip().lower()
        for t in reversed(self.finance.month_transactions(self.month)):
            if needle and needle not in t["description"].lower() and needle not in t["category"].lower():
                continue
            self.tx_list.append(self.tx_row(t))

    def tx_row(self, t):
        box = Gtk.Box(spacing=10)
        box.append(label(t["date"][8:10] + "/" + t["date"][5:7], "fin-hint"))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(label(t["description"], ellipsize=Pango.EllipsizeMode.END))
        meta = ACCOUNTS[t["account"]]
        if t.get("installment"):
            meta += " · parcela {}/{}".format(*t["installment"])
        text.append(label(meta, "fin-hint"))
        box.append(text)
        picker = Gtk.DropDown.new_from_strings(CATEGORIES)
        picker.set_selected(CATEGORIES.index(t["category"]) if t["category"] in CATEGORIES else 0)
        picker.connect("notify::selected", lambda d, _p: self.recategorize(t, CATEGORIES[d.get_selected()]))
        box.append(picker)
        css = "fin-good" if t["amount"] < 0 else ("fin-hint" if t["category"] in NOT_SPENDING else None)
        box.append(label(brl(-t["amount"]), "fin-amount", *([css] if css else []), width_chars=13, xalign=1))
        return Gtk.ListBoxRow(child=box)

    def recategorize(self, t, category):
        if category != t["category"]:
            self.finance.set_category(t, category)
            GLib.idle_add(lambda: (self.rebuild(), False)[1])

    def rebuild_debts(self):
        clear(self.debts)
        head = Gtk.Box(spacing=6)
        head.append(label("Fixed debts", "fin-head", hexpand=True))
        add = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat"], tooltip_text="Add fixed debt")
        add.connect("clicked", lambda _b: DebtDialog(self).present())
        head.append(add)
        self.debts.append(head)
        for debt in self.finance.data["debts"]:
            row = Gtk.Box(spacing=10)
            row.append(label(debt["name"], hexpand=True))
            row.append(label(f"{brl(debt['monthly'])}/month until {month_label(debt['until'])}", "fin-amount"))
            remove = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat", "circular"])
            remove.connect("clicked", lambda _b, d=debt: (self.finance.remove_debt(d), self.rebuild()))
            row.append(remove)
            self.debts.append(row)
        self.debts.append(label("Already committed per month", "fin-head"))
        self.debts.append(label("Imported card bills, the installments still to come and the fixed debts.",
                                "fin-hint", wrap=True))
        grid = Gtk.Grid(column_spacing=24, row_spacing=6, margin_top=6)
        columns = ["Month", "Nubank cartão", "Itaú cartão", "Fixed", "Total"]
        for col, text in enumerate(columns):
            grid.attach(label(text, "fin-hint", xalign=0 if col == 0 else 1), col, 0, 1, 1)
        for row, item in enumerate(self.finance.commitments(month_key(date.today())), start=1):
            values = [month_label(item["month"]), brl(item["cards"].get("nubank-card", 0)),
                      brl(item["cards"].get("itau-card", 0)), brl(sum(item["fixed"].values())), brl(item["total"])]
            for col, text in enumerate(values):
                grid.attach(label(text, *(["fin-amount"] if col else []), xalign=0 if col == 0 else 1),
                            col, row, 1, 1)
        self.debts.append(grid)

    def rebuild_plan(self):
        clear(self.plan)
        plan = self.finance.data.get("plan")
        if not plan:
            self.plan.append(label("No plan yet", "fin-head"))
            self.plan.append(label("Import your bills and statements, then ask Claude in the terminal: "
                                   "“analisa minhas finanças e monta o plano”. The plan shows up here, and the "
                                   "Overview compares each month with its goals.", "fin-hint", wrap=True))
            return
        if plan.get("updated"):
            self.plan.append(label(f"Updated {plan['updated'][:10]}", "fin-hint"))
        if plan.get("summary"):
            self.plan.append(label(plan["summary"], "fin-plan", wrap=True, selectable=True))
        if plan.get("steps"):
            self.plan.append(label("Steps", "fin-head"))
            for index, step in enumerate(plan["steps"], start=1):
                self.plan.append(label(f"{index}. {step}", "fin-plan", wrap=True))
        months = plan.get("months", [])
        if months:
            self.plan.append(label("Month by month", "fin-head"))
            grid = Gtk.Grid(column_spacing=24, row_spacing=6)
            for col, text in enumerate(["Month", "Pay off", "Save", "Notes"]):
                grid.attach(label(text, "fin-hint"), col, 0, 1, 1)
            for row, m in enumerate(months, start=1):
                pay = sum(p.get("amount", 0) for p in m.get("pay", []))
                values = [month_label(m["month"]), brl(pay), brl(m.get("save", 0)), m.get("note", "")]
                for col, text in enumerate(values):
                    grid.attach(label(text, *(["fin-amount"] if col in (1, 2) else []), wrap=col == 3),
                                col, row, 1, 1)
            self.plan.append(grid)

    def pick_files(self):
        dialog = Gtk.FileDialog(title="Import bills and statements")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        bills = Gtk.FileFilter(name="Bills (CSV, PDF)")
        bills.add_pattern("*.csv")
        bills.add_pattern("*.pdf")
        filters.append(bills)
        dialog.set_filters(filters)
        dialog.open_multiple(self.get_root(), None, self.on_files_picked)

    def on_files_picked(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        done, failed = 0, []
        for index in range(files.get_n_items()):
            path = files.get_item(index).get_path()
            try:
                scope, _count = self.finance.import_file(path)
                done += 1
                if "months" in scope:
                    self.month = scope["months"][0]
            except (OSError, UnicodeDecodeError, KeyError, ValueError, FinanceError) as error:
                failed.append(f"{GLib.path_get_basename(path)}: {error}")
        self.status.set_text(f"Imported {done} file(s)" + (f" · ⚠ {'; '.join(failed)}" if failed else ""))
        self.status.set_tooltip_text("\n".join(failed) or None)
        self.rebuild()
