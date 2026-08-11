# Terminal Manager（终端总控）

在一个总览窗口中管理**已经打开的 Linux 终端窗口**。点击条目即可切换并高亮对应终端，同时读取 Codex 写入窗口标题的状态信号。

Terminal Manager 不接管 PTY、不迁移 Shell，也不会终止现有任务。它是现有终端之上的轻量控制面板。

## 当前能力

- 自动发现 GNOME Terminal、Konsole、Tilix、Terminator、Kitty、Alacritty、WezTerm、XTerm、Wave 等 X11 终端窗口；
- 双击或按 Enter 聚焦、抬升对应终端窗口，并以约 0.3 秒的小幅快速摆动明确提示目标；
- 在桌面点击某个终端时，管理页会自动选中并滚动到对应记录，不抢夺输入焦点；
- 自动发现 GNOME Terminal 同一窗口中的隐藏标签页；多标签窗口使用列表内 `▸ / ▾` 分组展开，单击缩进子项即可切换标签并聚焦窗口；
- 给每个终端窗口设置只保存在管理器中的用途名称；
- 显示 Codex 标题状态信号和当前状态持续时间；
- 自动排序：等待用户输入最前，正在输出其次，静态窗口最后；各组按进入状态的时间排序；
- 自动学习未来 Codex 版本采用的未知单字符旋转动画前缀；
- 区分等待用户、正在输出、静态/空闲和未知状态；
- 未登记窗口也会立即出现，状态检测无需登记或关联 Shell/TTY；
- 用户级安装，不替换默认终端，不要求关闭已有终端。
- 深色现代化总览、状态指标卡、交替行、突出选择态和响应式详情区；
- 顶部统计卡可点击，对应状态或待注册 Shell 会在工作区中整体紫色高亮；
- 单击 Shell 名称即可聚焦并震动目标窗口，同时在管理器中保留醒目的紫色定位；
- 首次点击标签时通过一次性小图像探测自动学习其 TTY，之后按“窗口 + 标签”缓存；通过 OSC 11 临时改变终端原生背景色，文字、光标、输入和窗口尺寸保持不变；
- 窗口随可见条目自动加长，屏幕空间足够时隐藏滚动条并完整展示列表；超过屏幕高度时使用窄型滚动条；
- 顶部提供独立的“拖动窗口”把手，可直接移动整个管理器；
- 可按名称、状态或窗口标题实时搜索过滤。

## 状态语义

界面有意区分事实和推断：

| 状态 | 含义 |
|---|---|
| 等待用户 | Codex 在窗口标题显示感叹号状态前缀 |
| 正在输出 | Codex 在窗口标题显示旋转动画前缀 |
| 静态/空闲 | 窗口标题没有 Codex 状态前缀 |
| 未知 | 无法读取该 X11 窗口标题 |

识别不读取终端画面或文字，因此滚动历史、光标闪烁和窗口重绘不会误判为输出。未知动画只有在标题主体不变、至少三个不同单字符前缀连续轮换后才会被学习。

## 系统要求

- Linux X11 桌面（首版暂不支持 Wayland）；
- Python 3.9+ 和 Tk；
- GNOME Terminal 隐藏标签管理需要系统的 Python AT-SPI（Ubuntu 桌面通常已预装 `python3-pyatspi`）；
- `wmctrl`、`xdotool`。

Ubuntu/Debian 安装依赖：

```bash
sudo apt install python3-tk python3-pyatspi wmctrl xdotool
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

选择一个窗口，点击“登记窗口”或“编辑记录”，直接填写用途名称并保存。

状态检测直接读取窗口标题，与登记名称相互独立，不需要选择 TTY，也不需要在终端执行命令。

命令行注册仍作为可选的高级用法保留：

```bash
terminal-manager-register --name "ESKF 调试"
```

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

- GNOME Terminal 的隐藏标签可展开、读取标题、判断标题状态和切换；其他终端模拟器是否支持隐藏标签取决于后续适配。
- Wayland 默认禁止普通应用任意聚焦其他窗口，需要后续实现 GNOME/KDE 专用适配器。
- 状态监测依赖 Agent 设置终端标题；普通 Shell 和没有标题集成的 Agent 会显示静态。

## 卸载

```bash
./uninstall.sh
```

卸载不会影响任何终端或任务。

## License

MIT
