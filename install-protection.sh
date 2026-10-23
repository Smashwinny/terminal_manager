#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v tmux >/dev/null 2>&1; then
    tmux -V
    exit 0
fi
cache="$PWD/tmp/protection-download"
destination="$HOME/.local/share/terminal-manager/tools"
mkdir -p "$cache" "$destination"
cd "$cache"
# apt validates downloads against the configured Ubuntu/Debian archive index.
apt-get download tmux libutempter0
for package in ./*.deb; do
    dpkg-deb -x "$package" "$destination"
done
env LD_LIBRARY_PATH="$destination/usr/lib/x86_64-linux-gnu" "$destination/usr/bin/tmux" -V
