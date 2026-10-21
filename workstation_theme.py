BG = "#282a36"
BG_DARK = "#21222c"
BG_DARKER = "#191a21"
CURRENT = "#44475a"
FG = "#f8f8f2"
COMMENT = "#6272a4"
CYAN = "#8be9fd"
GREEN = "#50fa7b"
ORANGE = "#ffb86c"
PINK = "#ff79c6"
PURPLE = "#bd93f9"
RED = "#ff5555"
YELLOW = "#f1fa8c"

ACCENT = RED
MODE_COLORS = {"pomodoro": RED, "short": CYAN, "long": PURPLE}

MODE_CSS = "".join(
    f".card.{mode} {{ background-image: linear-gradient(160deg, alpha({color}, 0.20), alpha({color}, 0.05));"
    f" border-color: alpha({color}, 0.35); }}\n"
    f".card.{mode} .timer {{ color: {color}; }}\n"
    f".card.{mode} .mode-btn:checked {{ background: alpha({color}, 0.22); color: {color}; }}\n"
    f".card.{mode} .ctl.start, .card.{mode} .ctl.start:hover {{ background: {color}; color: {BG_DARKER}; }}\n"
    for mode, color in MODE_COLORS.items())

THEME_CSS = f"""
window, .background {{ background-color: {BG}; color: {FG}; }}
headerbar {{ background: {BG_DARK}; color: {FG}; border-bottom: 1px solid {BG_DARKER}; box-shadow: none; }}
headerbar:backdrop {{ background: {BG_DARK}; }}
stackswitcher button {{ background: transparent; color: alpha({FG}, 0.65); border: none; box-shadow: none;
                       border-radius: 6px; padding: 4px 16px; font-weight: 600; }}
stackswitcher button:hover {{ background: alpha({FG}, 0.06); color: {FG}; }}
stackswitcher button:checked {{ background: {CURRENT}; color: {FG}; }}

button {{ background: {CURRENT}; color: {FG}; border: none; box-shadow: none; text-shadow: none; border-radius: 6px; }}
button:hover {{ background: #50546a; }}
button:active, button:checked {{ background: #5a5e78; }}
button.flat {{ background: transparent; }}
button.flat:hover {{ background: alpha({FG}, 0.07); }}
button.flat:active, button.flat:checked {{ background: alpha({FG}, 0.12); }}
button.suggested-action, button.suggested-action:hover {{ background: {ACCENT}; color: {BG_DARKER}; font-weight: bold; }}
button.destructive-action {{ color: {RED}; }}

entry, spinbutton, dropdown > button {{ background: {BG_DARK}; color: {FG}; border: 1px solid {CURRENT};
                                        border-radius: 6px; box-shadow: none; }}
dropdown > button:hover {{ background: {BG_DARKER}; }}
entry:focus-within, spinbutton:focus-within {{ border-color: {PURPLE}; box-shadow: 0 0 0 1px alpha({PURPLE}, 0.5);
                                              outline: none; }}
selection, text selection {{ background-color: alpha({PURPLE}, 0.4); color: {FG}; }}
checkbutton check {{ border: 1px solid {COMMENT}; background: transparent; border-radius: 4px; box-shadow: none; }}
checkbutton check:checked {{ background: {PURPLE}; border-color: {PURPLE}; color: {BG_DARKER}; }}

popover > contents {{ background: {BG_DARK}; color: {FG}; border: 1px solid {BG_DARKER}; border-radius: 10px;
                      box-shadow: 0 8px 24px alpha(black, 0.45); }}
popover > arrow {{ background: {BG_DARK}; border: 1px solid {BG_DARKER}; }}
popover button.flat:hover, popover modelbutton:hover, popover row:hover {{ background: alpha({FG}, 0.07); }}
tooltip, tooltip.background {{ background: {BG_DARKER}; color: {FG}; border-radius: 6px; border: none; }}
calendar {{ background: transparent; color: {FG}; border-color: {CURRENT}; }}
calendar > grid > label.today {{ color: {ACCENT}; box-shadow: inset 0 -2px {ACCENT}; }}
calendar > grid > label:selected {{ background: {ACCENT}; color: {BG_DARKER}; border-radius: 6px; }}
scrollbar slider {{ background-color: alpha({FG}, 0.25); }}
paned > separator {{ background-image: image({BG_DARKER}); }}
list, listview, textview, textview text {{ background: transparent; color: {FG}; }}

.card {{ background-color: {BG_DARK}; border: 1px solid {CURRENT}; }}
.timer {{ font-weight: 800; }}
.mode-btn, .mode-btn:hover {{ color: alpha({FG}, 0.65); background: transparent; border-radius: 6px; }}
.mode-btn:hover {{ background: alpha({FG}, 0.06); }}
.ctl {{ border-radius: 8px; }}
.ctl.stop, .ctl.stop:hover {{ background: {CURRENT}; color: {FG}; }}
.ctl.reset, .ctl.reset:hover {{ background: transparent; color: alpha({FG}, 0.7); }}
.ctl.reset:hover {{ background: alpha({FG}, 0.06); }}
{MODE_CSS}
.view-title {{ color: {FG}; }}
.sidebar, .notes-sidebar {{ background: {BG_DARK}; }}
.sidebar row:hover:not(:selected), .notes-sidebar row:hover:not(:selected) {{ background: alpha({FG}, 0.05); }}
.sidebar row:selected, .notes-sidebar row:selected {{ background: alpha({ACCENT}, 0.16); color: #ff9d9d; }}
.board-column {{ background: {BG_DARK}; }}
.board-card {{ background: {BG}; border-color: {CURRENT}; }}
.board-card:hover {{ border-color: {COMMENT}; }}
.board-card:hover .task-actions {{ opacity: 1; }}
.task-form {{ background: {BG_DARK}; border-color: {CURRENT}; }}
"""
