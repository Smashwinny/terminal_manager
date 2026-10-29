"""Resolve the installed CLI and its own Node, without sourcing shell startup."""
import os
from pathlib import Path
import shutil
import subprocess


def command() -> list[str]:
    executable = shutil.which('codex')
    local = Path.home() / '.local/bin/codex'
    if not executable and os.access(local, os.X_OK):
        executable = str(local)
    if not executable:
        raise ValueError('未找到 Codex CLI')
    path = Path(executable).resolve()
    try:
        with path.open('rb') as stream:
            header = stream.read(128)
    except OSError as exc:
        raise ValueError(f'无法读取 Codex 启动程序：{exc}') from exc
    if header.startswith(b'#!') and b'node' in header.split(b'\n')[0]:
        # npm global layout: <prefix>/lib/node_modules/@openai/codex/bin/codex.js
        node = next((p / 'bin/node' for p in path.parents if (p / 'lib/node_modules') in path.parents and os.access(p / 'bin/node', os.X_OK)), None)
        if node is None:
            found = shutil.which('node')
            node = Path(found) if found else None
        if node is None:
            raise ValueError('Codex 使用 Node 启动，但找不到对应的 Node 运行环境')
        return [str(node), str(path)]
    return [str(path)]


def preflight() -> list[str]:
    argv = command()
    try:
        result = subprocess.run([*argv, '--version'], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'Codex 启动环境预检失败：{exc}') from exc
    if result.returncode:
        raise ValueError('Codex 启动环境预检失败：' + (result.stderr or result.stdout)[-1200:].strip())
    return argv
