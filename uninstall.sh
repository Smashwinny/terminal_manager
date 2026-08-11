#!/usr/bin/env bash
set -euo pipefail

python3 -m pip uninstall -y terminal-manager
desktop_file="${HOME}/.local/share/applications/terminal-manager.desktop"
if [ -f "$desktop_file" ]; then
    rm "$desktop_file"
fi

printf 'Terminal Manager 已卸载。Shell 状态记录仍保留在 ~/.local/state/terminal-manager。\n'
printf '如需删除这些非关键状态记录，可手动删除该目录。\n'

