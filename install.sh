#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
APP_ID=dev.matheus.AllInOneWorkstation
SLUG=all-in-one-workstation
EXT_UUID=$SLUG@matheus.dev
LIB="$HOME/.local/share/$SLUG"

migrate_from_tomato_timer() {
  local docs
  docs=$(xdg-user-dir DOCUMENTS 2>/dev/null || echo "$HOME")
  if [ -d "$HOME/.config/tomato-timer" ] && [ ! -e "$HOME/.config/$SLUG" ]; then
    mv "$HOME/.config/tomato-timer" "$HOME/.config/$SLUG"
  fi
  if [ -d "$docs/Tomato Notes" ] && [ ! -e "$docs/Workstation Notes" ]; then
    mv "$docs/Tomato Notes" "$docs/Workstation Notes"
  fi
  gnome-extensions disable tomato-timer@matheus.dev 2>/dev/null || true
  rm -rf "$HOME/.local/share/tomato-timer" "$HOME/.cache/tomato-timer" \
         "$HOME/.local/share/gnome-shell/extensions/tomato-timer@matheus.dev"
  rm -f "$HOME/.local/bin/tomato-timer" \
        "$HOME/.local/share/icons/hicolor/scalable/apps/dev.matheus.TomatoTimer.svg" \
        "$HOME/.local/share/applications/dev.matheus.TomatoTimer.desktop"
}

enable_extension() {
  gnome-extensions enable "$EXT_UUID" 2>/dev/null && return
  python3 - "$EXT_UUID" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
current = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                         capture_output=True, text=True).stdout.strip().removeprefix("@as ")
enabled = [e for e in (ast.literal_eval(current) if current else []) if e != "tomato-timer@matheus.dev"]
if uuid not in enabled:
    enabled.append(uuid)
subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(enabled)], check=True)
PY
  echo "Extensão da barra superior habilitada: faça logout/login pra ela aparecer."
}

migrate_from_tomato_timer

install -Dm755 workstation.py "$LIB/workstation.py"
install -Dm644 workstation_tasks.py "$LIB/workstation_tasks.py"
install -Dm644 workstation_notes.py "$LIB/workstation_notes.py"
install -Dm644 workstation_theme.py "$LIB/workstation_theme.py"
mkdir -p "$HOME/.local/bin"
ln -sf "$LIB/workstation.py" "$HOME/.local/bin/$SLUG"
install -Dm644 workstation.svg "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 /dev/stdin "$HOME/.local/share/applications/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=All-in-One Workstation
Comment=Pomodoro timer, tasks and notes
Exec=$HOME/.local/bin/$SLUG
Icon=$APP_ID
Terminal=false
Categories=Utility;Office;
Keywords=pomodoro;timer;focus;tasks;todo;notes;workstation;
StartupWMClass=$APP_ID
DESKTOP

install -Dm644 panel-extension/metadata.json "$HOME/.local/share/gnome-shell/extensions/$EXT_UUID/metadata.json"
install -Dm644 panel-extension/extension.js "$HOME/.local/share/gnome-shell/extensions/$EXT_UUID/extension.js"
enable_extension

rm -f "$HOME/.cache/$SLUG/"*.wav
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "Instalado. Procure por 'All-in-One Workstation' no menu de apps ou rode: $SLUG"
