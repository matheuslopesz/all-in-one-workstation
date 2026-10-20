PINK = "#ff71ce"
CYAN = "#01cdfe"
MINT = "#05ffa1"
PURPLE = "#b967ff"
YELLOW = "#fffb96"
LAVENDER = "#9d8cc4"
INK = "#f4e9ff"
NIGHT = "#1b0f33"
DUSK = "#2a1050"

THEME_CSS = f"""
window, .background {{ background-color: {NIGHT}; color: {INK}; }}
window.background {{ background-image: linear-gradient(180deg, {NIGHT} 0%, {DUSK} 65%, #3d0f4f 100%); }}
headerbar {{ background: linear-gradient(90deg, alpha({PINK}, 0.22), alpha({PURPLE}, 0.22), alpha({CYAN}, 0.22)),
                         #160a2b;
             color: {INK}; border-bottom: 2px solid {PINK}; box-shadow: 0 2px 14px alpha({PINK}, 0.45); }}
headerbar windowtitle, headerbar .title {{ color: {INK}; }}
stackswitcher button {{ font-weight: bold; letter-spacing: 2px; }}
stackswitcher button:checked {{ background: linear-gradient(90deg, {PINK}, {PURPLE}); color: {NIGHT};
                               border-color: transparent; }}

button {{ background: alpha({PURPLE}, 0.14); border: 1px solid alpha({PURPLE}, 0.45); color: {INK};
          box-shadow: none; text-shadow: none; }}
button:hover {{ background: alpha({PINK}, 0.22); border-color: {PINK}; }}
button:checked {{ background: alpha({CYAN}, 0.22); border-color: {CYAN}; color: {INK}; }}
button.flat {{ background: transparent; border-color: transparent; }}
button.flat:hover {{ background: alpha({PINK}, 0.16); }}
button.suggested-action {{ background: linear-gradient(90deg, {PINK}, {PURPLE}); color: {NIGHT};
                          font-weight: bold; border: none; }}
button.destructive-action {{ color: {PINK}; }}

entry, dropdown > button, spinbutton {{ background: alpha(black, 0.28); color: {INK};
                                        border: 1px solid alpha({CYAN}, 0.35); box-shadow: none; }}
entry:focus-within {{ border-color: {CYAN}; box-shadow: 0 0 8px alpha({CYAN}, 0.6); outline: none; }}
selection, text selection {{ background-color: alpha({PINK}, 0.45); color: white; }}

popover > contents, popover > arrow {{ background-color: #241243; border: 1px solid alpha({PINK}, 0.7);
                                       color: {INK}; }}
calendar {{ background: transparent; color: {INK}; border-color: alpha({PURPLE}, 0.4); }}
calendar > grid > label.today {{ color: {PINK}; box-shadow: inset 0 -2px {PINK}; }}
calendar > grid > label:selected {{ background: {PINK}; color: {NIGHT}; }}
checkbutton check {{ border-color: {PURPLE}; background: alpha(black, 0.2); }}
checkbutton check:checked {{ background: {PINK}; border-color: {PINK}; color: {NIGHT}; }}
scrollbar slider {{ background-color: alpha({PINK}, 0.55); }}
paned > separator {{ background-image: image(alpha({PINK}, 0.45)); }}
list, listview, textview, textview text {{ background: transparent; color: {INK}; }}
tooltip, tooltip.background {{ background: #241243; color: {INK}; border: 1px solid {CYAN}; }}

.card {{ background-size: 100% 100%, 100% 100%; box-shadow: 0 0 26px alpha({PINK}, 0.35);
         border: 1px solid alpha(white, 0.25); }}
.card.pomodoro {{ background-image: linear-gradient(180deg, transparent 62%, alpha(white, 0.12) 100%),
                                    linear-gradient(160deg, {PINK}, {PURPLE} 70%, #6b2fd6); }}
.card.short {{ background-image: linear-gradient(180deg, transparent 62%, alpha(white, 0.12) 100%),
                                 linear-gradient(160deg, {CYAN}, #4f7cff 60%, {PURPLE}); }}
.card.long {{ background-image: linear-gradient(180deg, transparent 62%, alpha(white, 0.12) 100%),
                                linear-gradient(160deg, {PURPLE}, #5a2bb5 60%, #24104d); }}
.timer {{ font-family: monospace; letter-spacing: 6px;
          text-shadow: 4px 4px 0 alpha({NIGHT}, 0.45), 0 0 22px alpha(white, 0.55); }}
.mode-btn {{ letter-spacing: 1px; border: none; }}
.mode-btn:checked {{ background: alpha({NIGHT}, 0.35); color: white; }}
.ctl {{ border-radius: 999px; letter-spacing: 2px; }}
.ctl.start {{ background: {MINT}; color: {NIGHT}; box-shadow: 0 0 12px alpha({MINT}, 0.6); }}
.ctl.start:hover {{ background: #4dffbf; }}
.ctl.stop {{ background: {PINK}; color: {NIGHT}; box-shadow: 0 0 12px alpha({PINK}, 0.6); }}
.ctl.stop:hover {{ background: #ff95da; }}
.ctl.reset {{ background: alpha({NIGHT}, 0.55); color: white; }}
.ctl.reset:hover {{ background: alpha({NIGHT}, 0.75); }}

.section-title, .subtasks-head, .sidebar-head, .log-head {{ color: {CYAN}; letter-spacing: 1px; }}
.view-title {{ color: {PINK}; letter-spacing: 2px; text-shadow: 3px 3px 0 alpha({CYAN}, 0.45); }}
.group-head label, .column-name {{ color: {CYAN}; }}
.sidebar, .notes-sidebar {{ background: alpha(black, 0.22); }}
.board-column {{ background: alpha(black, 0.22); border: 1px solid alpha({PURPLE}, 0.35); }}
.board-card {{ background: alpha({PURPLE}, 0.10); border-color: alpha({PURPLE}, 0.4); }}
.board-card:hover {{ border-color: {PINK}; box-shadow: 0 0 10px alpha({PINK}, 0.35); }}
.board-card:hover .task-actions {{ opacity: 1; }}
.task-form {{ border-color: alpha({PINK}, 0.5); background: alpha(black, 0.15); }}
.cal-day {{ border-color: alpha({PURPLE}, 0.25); }}
"""
