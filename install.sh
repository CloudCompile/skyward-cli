#!/usr/bin/env bash
# Install skyward: a dedicated venv in ~/.venv-skyward plus a ~/.local/bin
# symlink, matching how the other box tools are laid out.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SKYWARD_VENV:-$HOME/.venv-skyward}"
BIN="${SKYWARD_BIN:-$HOME/.local/bin}"

python3 -m venv "$VENV"
"$VENV/bin/pip" -q install --upgrade pip
"$VENV/bin/pip" -q install -e "$HERE"

mkdir -p "$BIN"
ln -sf "$VENV/bin/skyward" "$BIN/skyward"

mkdir -p "$HOME/.config/skyward"
if [ ! -e "$HOME/.config/skyward/config" ]; then
    cat > "$HOME/.config/skyward/config" <<'EOF'
# skyward credentials — chmod 600 this file
# username=
# password=
# security_code=
EOF
    chmod 600 "$HOME/.config/skyward/config"
    echo "wrote template $HOME/.config/skyward/config"
fi

echo "installed: $BIN/skyward  ->  $VENV"
"$BIN/skyward" --help >/dev/null && echo "ok"
