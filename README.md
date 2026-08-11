# Terminal Manager（终端总控）

在一个总览窗口中管理**已经打开的 Linux 终端窗口**。点击条目即可切换并高亮对应终端，同时按窗口画面是否持续变化判断“正在输出”或“静态/空闲”。

Terminal Manager 不接管 PTY、不迁移 Shell，也不会终止现有任务。它是现有终端之上的轻量控制面板。

## 当前能力

- 自动发现 GNOME Terminal、Konsole、Tilix、Terminator、Kitty、Alacritty、WezTerm、XTerm、Wave 等 X11 终端窗口；
- 双击或按 Enter 聚焦、抬升对应终端窗口，并以约 0.3 秒的小幅快速摆动明确提示目标；
- 在桌面点击某个终端时，管理页会自动选中并滚动到对应记录，不抢夺输入焦点；
- 给每个终端窗口设置只保存在管理器中的用途名称；
- 显示本次画面变化比例和最近一次变化时间；
- 区分正在输出、静态/空闲、正在采样和未知状态；
- 未登记窗口也会立即出现，状态检测无需登记或关联 Shell/TTY；
- 用户级安装，不替换默认终端，不要求关闭已有终端。
- 深色现代化总览、状态指标卡、交替行、突出选择态和响应式详情区；
- 可按名称、状态或窗口标题实时搜索过滤。

## 状态语义

界面有意区分事实和推断：

| 状态 | 含义 |
|---|---|
| 正在输出 | 两次采样之间的窗口画面变化达到阈值，并保持约 4 秒 |
| 静态/空闲 | 窗口画面连续一段时间没有达到阈值的变化 |
| 正在采样 | 刚发现窗口，等待第二帧用于比较 |
| 未知 | 无法读取该 X11 窗口的像素缓冲 |

默认变化阈值为 `0.05%`：这会忽略约 `0.01%` 的普通光标闪烁，但能识别 Codex 标题动画和真正的日志/构建输出。状态描述的是“终端画面活动”，不是 CPU 或业务任务状态；安静运行但不输出的程序会显示静态。

## 系统要求

- Linux X11 桌面（首版暂不支持 Wayland）；
- Python 3.9+ 和 Tk；
- `wmctrl`、`xdotool`、`xwd`。

Ubuntu/Debian 安装依赖：

```bash
sudo apt install python3-tk wmctrl xdotool x11-apps
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

状态检测直接比较窗口画面，与登记名称相互独立，不需要选择 TTY，也不需要在终端执行命令。

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

- 一个终端窗口包含多个标签页时，状态反映当前可绘制的活动标签页，无法同时判断隐藏标签页。
- Wayland 默认禁止普通应用任意聚焦其他窗口，需要后续实现 GNOME/KDE 专用适配器。
- 状态监测只比较窗口像素，不读取或保存终端文字，也不会判断命令业务层面的成功或失败。

## 卸载

```bash
./uninstall.sh
```

卸载不会影响任何终端或任务。

## License

MIT
