"""Optional "PC anos 2000" look: Windows 98 chrome, pixel font, CRT timer, BIOS boot screen."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

PINK = "#ff71ce"
CYAN = "#01cdfe"
MINT = "#05ffa1"
PURPLE = "#b967ff"
YELLOW = "#fffb96"
LAVENDER = "#9d8cc4"
INK = "#f4e9ff"
NIGHT = "#1b0f33"
DUSK = "#2a1050"

SILVER = "#c8c0dc"
SILVER_HI = "#ece6f8"
SILVER_LO = "#8b80a8"
BLACK = "#0a0418"
RETRO_FONT = "VT323"

PHOSPHOR = {"pomodoro": PINK, "short": CYAN, "long": PURPLE}


def bevel(hi, lo, inner_hi, inner_lo):
    return (f"border: 2px solid; border-color: {hi} {lo} {lo} {hi}; "
            f"box-shadow: inset -1px -1px {inner_lo}, inset 1px 1px {inner_hi};")


RAISED = bevel("#ffffff", BLACK, SILVER_HI, SILVER_LO)
PRESSED = bevel(BLACK, "#ffffff", SILVER_LO, SILVER_HI)
SUNKEN = f"border: 2px solid; border-color: {SILVER_LO} #ffffff #ffffff {SILVER_LO}; box-shadow: inset 1px 1px {BLACK};"
DARK_RAISED = f"border: 2px solid; border-color: #5d4396 {BLACK} {BLACK} #5d4396;"


def colored_button(selector, face, hi, lo):
    return (f"{selector}, {selector}:hover {{ background: {face}; color: {BLACK}; "
            f"{bevel(hi, BLACK, hi, lo)} }}\n"
            f"{selector}:active {{ {bevel(BLACK, hi, lo, hi)} }}\n")


CRT_CSS = "".join(
    f".card.{mode} .timer {{ color: {color}; text-shadow: 0 0 10px alpha({color}, 0.9), 0 0 34px alpha({color}, 0.55); }}\n"
    f".card.{mode} .mode-btn {{ color: alpha({color}, 0.75); }}\n"
    f".card.{mode} .mode-btn:checked {{ background: {color}; color: {BLACK}; box-shadow: 0 0 12px alpha({color}, 0.6); }}\n"
    f".log-dot.{mode} {{ background: {color}; border-radius: 0; }}\n"
    f".log-kind.{mode} {{ color: {color}; }}\n"
    for mode, color in PHOSPHOR.items())

RETRO_CSS = f"""
* {{ border-radius: 0; }}
window, .background {{ background-color: {NIGHT}; color: {INK}; }}
window.background {{ background-image: none; }}
window.csd {{ box-shadow: 0 0 0 1px {BLACK}, 6px 6px 0 alpha(black, 0.35); }}

headerbar {{ min-height: 30px; padding: 2px 4px; color: white; box-shadow: none; border: none;
             border-bottom: 2px solid {SILVER};
             background: linear-gradient(90deg, #3b0f8a, {PURPLE} 38%, {PINK} 72%, {CYAN}); }}
headerbar:backdrop {{ background: linear-gradient(90deg, #4a4060, #7d7397); }}
.titlebar-label {{ font-family: "{RETRO_FONT}"; font-size: 22px; color: white;
                   text-shadow: 2px 2px 0 alpha({BLACK}, 0.55); }}
headerbar windowcontrols button, headerbar button.titlebar-btn {{
    min-width: 22px; min-height: 20px; padding: 0; margin: 0 1px; background: {SILVER}; color: {BLACK}; {RAISED} }}
headerbar windowcontrols button:active, headerbar button.titlebar-btn:active {{ {PRESSED} }}
headerbar windowcontrols button > image {{ background: none; box-shadow: none; padding: 0; }}

.chrome {{ background: {SILVER}; color: {BLACK}; }}
.tabstrip {{ padding: 6px 8px 0 8px; }}
.tabstrip stackswitcher > button {{ margin: 4px 2px 0 0; padding: 0 18px; min-height: 26px; font-size: 21px;
                                   border-bottom-width: 0; }}
.tabstrip stackswitcher > button:checked {{ margin-top: 0; min-height: 30px; padding: 0 18px; background: {SILVER};
                                           {RAISED} border-bottom-width: 0; box-shadow: inset 0 3px {PINK}; }}
.well {{ background: {NIGHT}; color: {INK}; margin: 0 6px; {SUNKEN} }}
.statusbar {{ padding: 4px 6px; font-family: "{RETRO_FONT}"; font-size: 18px; }}
.statusbar .panel {{ padding: 0 10px; border: 1px solid; border-color: {SILVER_LO} #ffffff #ffffff {SILVER_LO}; }}

button {{ font-family: "{RETRO_FONT}"; font-size: 19px; background: {SILVER}; color: {BLACK}; padding: 2px 12px;
          min-height: 22px; text-shadow: none; -gtk-icon-shadow: none; transition: none; {RAISED} }}
button:hover {{ background: #d8d1ea; }}
button:active, button:checked {{ background: #b6acd0; {PRESSED} }}
button:disabled {{ color: {SILVER_LO}; text-shadow: 1px 1px #ffffff; }}
button:focus-visible {{ outline: 1px dotted {BLACK}; outline-offset: -5px; }}
button.flat {{ background: transparent; color: {INK}; border-color: transparent; box-shadow: none; }}
button.flat:hover {{ background: alpha({PURPLE}, 0.18); border-color: alpha(white, 0.55) {BLACK} {BLACK} alpha(white, 0.55); }}
button.flat:active, button.flat:checked {{ background: alpha({PURPLE}, 0.28);
                                          border-color: {BLACK} alpha(white, 0.55) alpha(white, 0.55) {BLACK}; }}
button.flat:disabled {{ color: alpha({INK}, 0.35); text-shadow: none; }}
{colored_button("button.suggested-action", PINK, "#ffd1f0", "#c94aa0")}
button.destructive-action {{ color: #a0005f; }}
button.flat.destructive-action {{ color: {PINK}; }}
spinbutton > button {{ padding: 0 6px; min-height: 0; }}
dropdown > button {{ padding: 2px 8px; }}

entry, spinbutton {{ background: #0f0722; color: {INK}; min-height: 26px; {SUNKEN} }}
entry:focus-within, spinbutton:focus-within {{ box-shadow: inset 1px 1px {BLACK}, 0 0 0 1px {CYAN}; outline: none; }}
selection, text selection {{ background-color: alpha({PINK}, 0.55); color: white; }}

checkbutton check, .task-check check, .cal-task check {{ border-radius: 0; background: #0f0722; color: {MINT};
    {SUNKEN} min-width: 14px; min-height: 14px; }}
.task-check check {{ min-width: 16px; min-height: 16px; }}
checkbutton check:checked {{ background: #0f0722; color: {MINT}; }}

popover > contents {{ background: #241243; color: {INK}; padding: 4px; border: 2px solid;
                      border-color: {SILVER} {BLACK} {BLACK} {SILVER}; box-shadow: 4px 4px 0 alpha(black, 0.45); }}
popover > arrow {{ background: #241243; border: 2px solid {SILVER}; }}
popover button.flat:hover, popover modelbutton:hover, popover row:hover, popover row:selected {{
    background: linear-gradient(90deg, #6b2fd6, {PINK}); color: white; border-color: transparent; }}
tooltip, tooltip.background {{ background: {YELLOW}; color: {BLACK}; border: 1px solid {BLACK}; box-shadow: none; }}
tooltip label {{ color: {BLACK}; font-family: "{RETRO_FONT}"; font-size: 18px; }}

calendar {{ background: transparent; color: {INK}; border-color: alpha({PURPLE}, 0.4); }}
calendar > grid > label.today {{ color: {PINK}; box-shadow: inset 0 -2px {PINK}; }}
calendar > grid > label:selected {{ background: {PINK}; color: {NIGHT}; }}
scrollbar {{ background: transparent; }}
scrollbar slider {{ background-color: {SILVER}; border: 1px solid {BLACK}; min-width: 6px; min-height: 6px; }}
paned > separator {{ background-image: image({SILVER_LO}); }}
list, listview, textview, textview text {{ background: transparent; color: {INK}; }}

.card {{ border-radius: 26px; padding: 22px 24px; border: 12px solid {SILVER}; transition: none;
         background-color: #0d0520; background-image: radial-gradient(ellipse at center, #2a1050, #0d0520 70%, #050210);
         box-shadow: inset 0 0 36px black, 0 0 0 2px {BLACK}, 6px 6px 0 alpha(black, 0.4); }}
.card button label {{ color: inherit; }}
.timer {{ font-family: "{RETRO_FONT}"; font-size: 168px; font-weight: normal; letter-spacing: 6px; }}
.mode-btn, .mode-btn:hover {{ font-size: 22px; padding: 0 12px; background: transparent; border: none; box-shadow: none; }}
{CRT_CSS}
.ctl {{ font-size: 24px; padding: 2px 26px; letter-spacing: 2px; font-weight: normal; }}
{colored_button(".ctl.start", MINT, "#c9ffe9", "#02a96a")}
{colored_button(".ctl.stop", PINK, "#ffd1f0", "#c94aa0")}
.ctl.reset, .ctl.reset:hover {{ background: {SILVER}; color: {BLACK}; }}
.ctl:disabled {{ opacity: 0.4; }}

.view-title {{ font-family: "{RETRO_FONT}"; font-size: 36px; font-weight: normal; color: {PINK};
               letter-spacing: 2px; text-shadow: 3px 3px 0 alpha({CYAN}, 0.45); }}
.section-title, .subtasks-head, .sidebar-head, .log-head, .group-head label, .column-name, .month-label, .cal-weekday {{
    font-family: "{RETRO_FONT}"; font-weight: normal; color: {CYAN}; }}
.section-title, .month-label {{ font-size: 23px; }}
.subtasks-head, .sidebar-head, .log-head, .group-head label, .column-name, .cal-weekday {{ font-size: 20px; }}
entry.note-title {{ font-family: "{RETRO_FONT}"; font-size: 38px; font-weight: normal; color: {PINK}; }}
.hint {{ font-family: "{RETRO_FONT}"; font-size: 17px; }}

.sidebar, .notes-sidebar {{ background: #160a2e; }}
.sidebar row, .notes-sidebar row, .cal-num, .cal-task {{ border-radius: 0; }}
.sidebar row:selected, .notes-sidebar row:selected {{ background: linear-gradient(90deg, #6b2fd6, {PURPLE}); color: white; }}
.board-column, .board-card, .task-form, .cal-add, .cal-more {{ border-radius: 0; }}
.board-column {{ background: #1f0f40; {DARK_RAISED} }}
.board-card {{ background: #2a1556; {DARK_RAISED} }}
.board-card:hover {{ border-color: {PINK} {BLACK} {BLACK} {PINK}; }}
.board-card:hover .task-actions {{ opacity: 1; }}
.task-form {{ background: #160a2e; {DARK_RAISED} }}
.cal-day {{ border-color: alpha({PURPLE}, 0.25); }}
.log-day {{ border-bottom: 1px dashed alpha({PURPLE}, 0.5); }}
.log-day, .log-kind, .log-time, .log-dur {{ font-family: "{RETRO_FONT}"; font-size: 19px; }}
.log-row {{ border-radius: 0; }}
.log-day-meta {{ font-family: "{RETRO_FONT}"; font-size: 16px; }}
entry.log-desc {{ background: transparent; box-shadow: none; border-color: transparent; }}
entry.log-desc:focus-within {{ background: #0f0722; box-shadow: inset 1px 1px {BLACK}, 0 0 0 1px {CYAN}; }}
entry.log-desc.saved {{ box-shadow: inset 1px 1px {BLACK}, 0 0 0 1px #39ff14; }}

.boot {{ background: {BLACK}; padding: 28px 34px; }}
.boot label {{ font-family: "{RETRO_FONT}"; font-size: 22px; color: #d8d0e8; }}
.boot .boot-title {{ color: {PINK}; }}
.boot .boot-ok {{ color: {MINT}; }}
.boot .boot-skip {{ color: {LAVENDER}; }}
"""


class Scanlines(Gtk.Widget):
    BEZEL, RADIUS = 12, 14

    def __init__(self):
        super().__init__(can_target=False)

    def do_snapshot(self, snapshot):
        inset = self.BEZEL
        width, height = self.get_width() - 2 * inset, self.get_height() - 2 * inset
        if width <= 0 or height <= 0:
            return
        clip = Gsk.RoundedRect()
        clip.init_from_rect(Graphene.Rect().init(inset, inset, width, height), self.RADIUS)
        snapshot.push_rounded_clip(clip)
        line = Gdk.RGBA()
        line.parse("rgba(0,0,0,0.3)")
        for y in range(0, int(height), 3):
            snapshot.append_color(line, Graphene.Rect().init(inset, inset + y, width, 1))
        snapshot.pop()


class BootScreen(Gtk.Box):
    STEP_MS = 90
    HOLD_MS = 450

    def __init__(self, icon_name, checks, on_done):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["boot"])
        self.on_done = on_done
        self.done = False

        top = Gtk.Box(spacing=16)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        head.append(self.line("WORKSTATION BIOS v4.20  Release 10/20/98", "boot-title"))
        head.append(self.line("Copyright (C) 1984-1999, Vaporsoft Technologies, Inc."))
        top.append(head)
        top.append(Gtk.Image(icon_name=icon_name, pixel_size=80, valign=Gtk.Align.START))
        self.append(top)
        self.lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=22, vexpand=True)
        self.append(self.lines)
        self.append(self.line("Press any key to skip", "boot-skip"))

        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_a: self.finish())
        self.add_controller(click)
        self.steps = self.script(checks)
        self.timer = GLib.timeout_add(self.STEP_MS, self.step)

    def line(self, text, css=None):
        return Gtk.Label(label=text, xalign=0, css_classes=[css] if css else [])

    def say(self, text, value=None):
        label = self.line(text)
        if value is not None:
            label.set_markup(f"{GLib.markup_escape_text(text)} "
                             f"<span foreground='{MINT}'>{GLib.markup_escape_text(value)}</span>")
        self.lines.append(label)
        return label

    def script(self, checks):
        self.say("AESTHETIC(tm) Pentium(R) III 450MHz Processor")
        yield
        memory = self.say("Memory Test :      0K")
        for kb in range(16384, 65537, 16384):
            memory.set_text(f"Memory Test : {kb:6d}K")
            yield
        memory.set_markup(f"Memory Test :  65536K <span foreground='{MINT}'>OK</span>")
        self.say("")
        yield
        for name, value in checks:
            self.say(f"{name:.<32}", value)
            yield
        self.say("")
        self.say("Starting All-in-One Workstation 98 ...")

    def step(self):
        try:
            next(self.steps)
            return True
        except StopIteration:
            self.timer = GLib.timeout_add(self.HOLD_MS, self.on_hold_over)
            return False

    def on_hold_over(self):
        self.timer = None
        self.finish()
        return False

    def finish(self):
        if self.done:
            return
        self.done = True
        if self.timer:
            GLib.source_remove(self.timer)
        self.on_done()
