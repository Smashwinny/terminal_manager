# Terminal Manager（终端总控）

在一个总览窗口中管理**已经打开的 Linux 终端窗口和 Shell**。点击条目即可切换并高亮对应终端，同时查看名称、工作目录、前台命令及可解释的运行状态。

Terminal Manager 不接管 PTY、不迁移 Shell，也不会终止现有任务。它是现有终端之上的轻量控制面板。

## 当前能力

- 自动发现 GNOME Terminal、Konsole、Tilix、Terminator、Kitty、Alacritty、WezTerm、XTerm、Wave 等 X11 终端窗口；
- 双击或按 Enter 聚焦、抬升对应终端窗口；
- 给每个已注册 Shell 设置清晰的用途名称；
- 显示 Shell PID、TTY、工作目录、前台进程和最近更新时间；
- 区分空闲、运行中、暂停、结束和未知状态；
- 未注册窗口也会立即出现，可以先使用窗口切换功能；
- 用户级安装，不替换默认终端，不要求关闭已有终端。

## 状态语义

界面有意区分事实和推断：

| 状态 | 含义 |
|---|---|
| 空闲 | Shell 自身处于终端前台，通常表示正在等待下一条命令 |
| 运行中 | 终端前台进程组不是 Shell，说明有前台程序存在 |
| 已暂停 | 前台进程处于 Linux `T/t` 状态 |
| 已结束 | 注册的 Shell PID 已不存在 |
| 未知 | 监测器超时，或无法读取该终端的前台进程组 |

“运行中”不等于“持续计算”。处于休眠状态的服务、等待网络的程序和等待键盘输入的程序，在没有应用主动通知时无法完全可靠地区分；界面会显示原始内核状态说明，而不会武断地标成“等待用户”。

## 系统要求

- Linux X11 桌面（首版暂不支持 Wayland）；
- Python 3.9+ 和 Tk；
- `wmctrl`、`xdotool`。

Ubuntu/Debian 安装依赖：

```bash
sudo apt install python3-tk wmctrl xdotool
```

## 安装

```bash
git clone https://github.com/Smashwinny/terminal_manager.git
cd terminal_manager
chmod +x install.sh uninstall.sh
./install.sh
```

随后运行：

```bash
terminal-manager
```

也可以在桌面应用菜单搜索“Terminal Manager”或“终端总控”。如果 `~/.local/bin` 尚未加入当前 Shell 的 `PATH`，可先运行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 管理当前已经打开的 Shell

启动总控后，现有终端窗口会直接显示为“未注册”，此时已经可以点击进入。

要获得具体 Shell 的目录和状态，请切换到该 Shell 并执行一次：

```bash
terminal-manager-register --name "ESKF 调试"
```

无需关闭或重新打开 Shell。注册命令会记录当前活动窗口 ID、Shell PID 和 TTY，并启动一个只读监测器。重复注册可更新名称和窗口关联。

注销当前 Shell：

```bash
terminal-manager-unregister
```

也可以在总控中选择条目后点击“移除记录”。移除记录不会关闭 Shell 或终止任务。

## 开发与测试

无需安装即可从源码运行：

```bash
python3 -m terminal_manager.app
```

测试：

```bash
python3 -m pytest
```

## 已知限制

- 一个终端窗口包含多个标签页时，X11 只能可靠聚焦整个窗口，无法跨所有终端实现统一的标签页切换；每个 Shell 的状态仍可分别监测。
- Wayland 默认禁止普通应用任意聚焦其他窗口，需要后续实现 GNOME/KDE 专用适配器。
- 状态监测不读取终端输出，也不会自动判断命令业务层面的成功或失败。

## 卸载

```bash
./uninstall.sh
```

卸载不会影响任何终端或任务。

## License

MIT

