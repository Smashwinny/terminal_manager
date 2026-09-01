#!/usr/bin/env bash
set -euo pipefail

for command_name in python3 wmctrl xdotool; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf '缺少依赖：%s\n' "$command_name" >&2
        printf 'Ubuntu/Debian 可执行：sudo apt install python3-tk wmctrl xdotool\n' >&2
        exit 1
    fi
done

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    printf '缺少 Python Tk。Ubuntu/Debian 可执行：sudo apt install python3-tk\n' >&2
    exit 1
fi

# The project supports the setuptools shipped by Ubuntu 22.04, so installation
# does not need to download an isolated build environment.
python3 -m pip install --user --upgrade --no-build-isolation .

user_bin="${HOME}/.local/bin"
desktop_dir="${HOME}/.local/share/applications"
icon_dir_64="${HOME}/.local/share/icons/hicolor/64x64/apps"
icon_dir_512="${HOME}/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$desktop_dir"
mkdir -p "$icon_dir_64"
mkdir -p "$icon_dir_512"
launcher="$(mktemp)"
trap 'rm -f "$launcher"' EXIT
sed "s|@TERMINAL_MANAGER_EXEC@|${user_bin}/terminal-manager|g" \
    packaging/terminal-manager.desktop >"$launcher"
install -m 0644 "$launcher" "$desktop_dir/terminal-manager.desktop"
install -m 0644 terminal_manager/assets/terminal-manager-64.png "$icon_dir_64/terminal-manager.png"
install -m 0644 terminal_manager/assets/terminal-manager.png "$icon_dir_512/terminal-manager.png"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '\n安装完成。\n'
printf '启动命令：%s/terminal-manager\n' "$user_bin"
printf '登记窗口：在管理页面选择终端后，点击“登记窗口”。\n'
printf '也可以在应用菜单中搜索 Terminal Manager。\n'
