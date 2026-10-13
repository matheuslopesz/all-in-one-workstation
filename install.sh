#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
APP_ID=dev.matheus.TomatoTimer
install -Dm755 tomato_timer.py "$HOME/.local/share/tomato-timer/tomato_timer.py"
install -Dm644 tomato_tasks.py "$HOME/.local/share/tomato-timer/tomato_tasks.py"
install -Dm644 tomato_notes.py "$HOME/.local/share/tomato-timer/tomato_notes.py"
mkdir -p "$HOME/.local/bin"
ln -sf "$HOME/.local/share/tomato-timer/tomato_timer.py" "$HOME/.local/bin/tomato-timer"
install -Dm644 tomato-timer.svg "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 /dev/stdin "$HOME/.local/share/applications/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Tomato Timer
Comment=Pomodoro timer
Exec=$HOME/.local/bin/tomato-timer
Icon=$APP_ID
Terminal=false
Categories=Utility;Office;
Keywords=pomodoro;timer;focus;
StartupWMClass=$APP_ID
DESKTOP
EXT_UUID=tomato-timer@matheus.dev
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
install -Dm644 panel-extension/metadata.json "$EXT_DIR/metadata.json"
install -Dm644 panel-extension/extension.js "$EXT_DIR/extension.js"
if ! gnome-extensions enable "$EXT_UUID" 2>/dev/null; then
  python3 - "$EXT_UUID" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
current = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                         capture_output=True, text=True).stdout.strip().removeprefix("@as ")
enabled = ast.literal_eval(current) if current else []
if uuid not in enabled:
    subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(enabled + [uuid])], check=True)
PY
  echo "Extensão da barra superior habilitada: faça logout/login pra ela aparecer."
fi
rm -f "$HOME/.cache/tomato-timer/"*.wav
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "Instalado. Procure por 'Tomato Timer' no menu de apps ou rode: tomato-timer"
