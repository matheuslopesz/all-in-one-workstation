#!/usr/bin/env bash
APP_ID=dev.matheus.AllInOneWorkstation
SLUG=all-in-one-workstation
gnome-extensions disable "$SLUG@matheus.dev" 2>/dev/null || true
rm -rf "$HOME/.local/share/$SLUG" "$HOME/.cache/$SLUG" \
       "$HOME/.local/share/gnome-shell/extensions/$SLUG@matheus.dev" \
       "$HOME/.local/share/fonts/$SLUG"
rm -f "$HOME/.local/bin/$SLUG" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "$HOME/.local/share/applications/$APP_ID.desktop"
echo "Removido. (Dados ficam em ~/.config/$SLUG e as notas em Documentos/Workstation Notes)"
