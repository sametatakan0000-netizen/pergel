#!/bin/bash
# Register Pergel as the default browser (xdg)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# Install .desktop file
mkdir -p ~/.local/share/applications
cp "$DIR/pergel.desktop" ~/.local/share/applications/

# Update desktop database
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

# Set as default browser
xdg-settings set default-web-browser pergel.desktop 2>/dev/null || true
xdg-mime default pergel.desktop x-scheme-handler/http 2>/dev/null || true
xdg-mime default pergel.desktop x-scheme-handler/https 2>/dev/null || true
xdg-mime default pergel.desktop text/html 2>/dev/null || true

echo "Pergel registered as default browser."
