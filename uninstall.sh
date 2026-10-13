#!/usr/bin/env bash
APP_ID=dev.matheus.TomatoTimer
rm -rf "$HOME/.local/share/tomato-timer"
rm -f "$HOME/.local/bin/tomato-timer" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "$HOME/.local/share/applications/$APP_ID.desktop"
gnome-extensions disable tomato-timer@matheus.dev 2>/dev/null || true
rm -rf "$HOME/.local/share/gnome-shell/extensions/tomato-timer@matheus.dev" "$HOME/.cache/tomato-timer"
echo "Removido. (Dados ficam em ~/.config/tomato-timer e as notas em Documentos/Tomato Notes)"
