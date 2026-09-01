# Terminal Manager（终端总控）

在一个总览窗口中管理**已经打开的 Linux 终端窗口**。点击条目即可切换并高亮对应终端，同时读取 Codex 写入窗口标题的状态信号。

产品需求、实现状态和验收证据见 [REQUIREMENTS.md](REQUIREMENTS.md)。

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
- 提供适配 Ubuntu Dock 的高分辨率图标和稳定窗口类，可从应用菜单启动并固定到收藏夹；
- 窗口缩小时同步压缩字体、间距、表格行高和列宽，最小可缩至原最小尺寸的四分之一；
- 自动保存用户最后调整的窗口宽高，重启后恢复该尺寸，不再重新拉成长窗口；
- 动态保存已登记窗口的最后有效工作目录；管理器检测到上一次会话异常结束时，按目录恢复当时仍打开的登记窗口并重新建立登记关联；
- 深色现代化总览、状态指标卡、交替行、突出选择态和响应式详情区；
- 工作区在窗口与状态之间显示每个 Shell/标签当前的工作目录（PWD）；
- 顶部统计卡可点击，对应状态或待注册 Shell 会在工作区中整体紫色高亮；
- 单击 Shell 名称即可聚焦并震动目标窗口，同时在管理器中保留醒目的紫色定位；
- 单击或双击终端窗口时，对应管理器列表行变紫；单击或双击管理器列表行时，对应终端震动并显示紫色背景高亮；
- 首次点击标签时通过一次性小图像探测自动学习其 TTY，之后按“窗口 + 标签”缓存；通过 OSC 11 临时改变终端原生背景色，文字、光标、输入和窗口尺寸保持不变；
- 默认启用温度渲染：输出时逐步升温、等待用户时保温、静态时冷却；10 分钟连续输出达到红色上限，静态最多 6 分钟恢复基础色，界面强调色显示所有项目的平均温度；
- 窗口随可见条目自动加长，屏幕空间足够时隐藏滚动条并完整展示列表；超过屏幕高度时使用窄型滚动条；
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

## 支持环境与适配范围

当前版本面向 Linux X11 桌面，主要开发和验证环境为 Ubuntu + GNOME + GNOME Terminal。

| 环境 | 支持程度 | 说明 |
|---|---|---|
| Ubuntu 22.04/24.04 + Xorg + GNOME Terminal | 主要适配环境 | 窗口发现、聚焦、状态、PWD、多标签展开/切换、TTY 学习和原生背景高亮 |
| 其他 X11 桌面 + GNOME Terminal | 基本可用 | 窗口管理器的聚焦和窗口装饰行为可能略有差异 |
| Konsole、Tilix、Kitty、Alacritty、WezTerm、XTerm 等 X11 终端 | 基础支持 | 可发现和聚焦窗口；隐藏标签管理目前只完整适配 GNOME Terminal |
| GNOME/KDE Wayland | 不支持 | Wayland 默认禁止普通应用枚举、聚焦和截图其他窗口 |
| SSH 纯命令行、无桌面服务器 | 不支持 | 本项目是本机图形桌面应用，需要 `DISPLAY` 和 X11 会话 |

安装前确认当前会话：

```bash
echo "$XDG_SESSION_TYPE"
echo "$DISPLAY"
```

预期第一条输出 `x11`，第二条输出类似 `:0` 或 `:1`。如果输出 `wayland`，请退出登录，在登录界面的齿轮菜单选择“Ubuntu on Xorg”后重新登录。

## 完整依赖

- Python 3.9+、Tk 和 pip；
- `wmctrl`：枚举并激活现有窗口；
- `xdotool`：读取活动窗口、聚焦和定位反馈；
- `xinput`：只读监听终端窗口的左键双击，用于反向高亮管理器记录；
- `python3-pyatspi`：读取 GNOME Terminal 标签列表并切换隐藏标签；
- `xwd`（Ubuntu 包 `x11-apps`）和 `ffmpeg`：首次学习标签 TTY 时执行一次性小图像探测；
- GNOME Terminal 原生背景高亮使用 OSC 11，不修改终端配置文件。

Ubuntu/Debian 一次安装全部依赖：

```bash
sudo apt update
sudo apt install git python3 python3-pip python3-tk python3-pyatspi \
  wmctrl xdotool xinput x11-apps ffmpeg
```

缺少 `python3-pyatspi` 时，普通终端窗口仍能显示，但 GNOME Terminal 多标签识别不可用。缺少 `xwd` 或 `ffmpeg` 时，聚焦和震动仍可用，但未知标签无法自动学习 TTY 并改变终端背景色。

## 安装

安装是用户级操作，不要使用 `sudo ./install.sh`：

```bash
git clone https://github.com/Smashwinny/terminal_manager.git
cd terminal_manager
chmod +x install.sh uninstall.sh
./install.sh
```

安装脚本会执行以下操作：

- 将 Python 包和命令安装到 `~/.local`；
- 安装桌面入口到 `~/.local/share/applications/terminal-manager.desktop`；
- 安装无黑边图标到 `~/.local/share/icons/hicolor/64x64/apps/terminal-manager.png`；
- 不关闭、不迁移、不重启任何已经打开的 Shell。

如果系统提示 `externally-managed-environment`，说明发行版禁止 pip 直接写入用户环境。建议在虚拟环境中安装：

```bash
sudo apt install python3-venv
python3 -m venv ~/.local/share/terminal-manager/venv
~/.local/share/terminal-manager/venv/bin/pip install --no-build-isolation .
```

这种安装方式的启动命令是：

```bash
~/.local/share/terminal-manager/venv/bin/terminal-manager
```

注意：当前 `install.sh` 生成的应用菜单入口仍指向 `~/.local/bin/terminal-manager`。使用虚拟环境方案时应先用上面的命令启动；如需应用菜单入口，请把 `packaging/terminal-manager.desktop` 中的 `Exec` 改为虚拟环境中的绝对路径后复制到 `~/.local/share/applications/terminal-manager.desktop`。

推荐使用绝对路径启动：

```bash
~/.local/bin/terminal-manager
```

命令输出“已在后台启动”后会立即返回。管理器运行在独立桌面会话中，不依赖启动它的终端；此时可以关闭该终端，不会关闭管理器。重复执行启动命令不会多开，而是把已经运行的管理器切换到前台。后台启动日志位于 `~/.local/state/terminal-manager/terminal-manager.log`（设置 `XDG_STATE_HOME` 时跟随该目录）。

也可以在桌面应用菜单搜索“Terminal Manager”或“终端总控”。若希望直接输入命令，可把用户命令目录加入 PATH：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
terminal-manager
```

## 升级

升级不会影响任何正在运行的终端任务，只需要重新启动管理器本身：

```bash
cd terminal_manager
git pull --ff-only
./install.sh
```

如果旧版管理器仍在运行，关闭管理器窗口后重新执行：

```bash
~/.local/bin/terminal-manager
```

不需要关闭现有 GNOME Terminal、Codex、Agent、编译或 ROS 任务。

## 使用方式

1. 先打开或保留需要管理的终端，再启动 Terminal Manager；后续新开的终端也会在约 2 秒内自动出现。
2. 未登记窗口已经可以聚焦和查看状态；选择条目后点击“登记窗口”，只需填写便于识别的用途名称。
3. 双击普通条目可进入、震动并置顶目标终端；双击另一个终端会转移置顶，按 Enter 或“进入并高亮”只聚焦而不改变置顶。
4. 多标签窗口只有单击名称最前方的小三角 `▸ / ▾` 才会展开或折叠；双击不会改变展开状态。
5. 单击展开后的缩进标签，可切换到该隐藏标签并聚焦所属终端窗口。
6. “目录”列每约 2 秒从根 Shell 的 `/proc/<pid>/cwd` 读取真实 PWD，主目录显示为 `~`。
7. 顶部“渲染”圆点开关默认开启：输出升温、等待保温、静态冷却；关闭后恢复简版行颜色。
8. 如需适配未知 Agent，选择窗口并点击“学习信号”；依次将窗口切换到静态、输出中、等待用户并在弹窗中记录，优先采集三个状态，至少两个状态即可保存。
9. 点击顶部“信号管理”可查看各状态的信号数量、内置规则和用户学习结果；用户规则可移动到其他状态或删除，保存后立即影响状态与温度计算。

### 首次高亮学习

新标签第一次进入时，管理器需要确认它对应哪个 `/dev/pts/*`：

- 只在未知标签首次使用、TTY 失效或标签关系变化时探测；
- 候选终端会收到极短的测试背景色，管理器只采样缩小后的窗口图像；
- 学习完成后按“窗口 + 标签”缓存，后续点击直接高亮，不持续截图；
- 学习失败时仍可正常聚焦和震动，只是不改变终端原生背景色。

TTY 缓存默认位于：

```text
~/.local/state/terminal-manager/tty-bindings.json
```

异常恢复快照位于：

```text
~/.local/state/terminal-manager/runtime-session.json
```

正常退出管理器会清除待恢复快照。异常关机后只恢复已登记窗口及其目录，不会重放历史命令或 Agent 输入。

### 登记、重命名和移除

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

登记信息默认保存在：

```text
~/.local/state/terminal-manager/shells/
```

如果设置了 `XDG_STATE_HOME`，以上两个状态路径会改为 `$XDG_STATE_HOME/terminal-manager/` 下的对应位置。

## 常见问题

### 启动后看不到终端

确认当前是 X11 会话，并检查依赖：

```bash
echo "$XDG_SESSION_TYPE"
echo "$DISPLAY"
wmctrl -lx
xdotool getactivewindow
```

### GNOME Terminal 的隐藏标签没有出现

确认 AT-SPI 已安装：

```bash
python3 -c 'import pyatspi; print("pyatspi OK")'
```

然后等待 2–4 秒让后台标签扫描完成。

### 能聚焦，但终端没有紫色背景高亮

确认探测工具存在：

```bash
command -v xwd
command -v ffmpeg
```

如果标签曾被移动到其他窗口且缓存异常，可先备份缓存后重新学习：

```bash
mv ~/.local/state/terminal-manager/tty-bindings.json \
  ~/.local/state/terminal-manager/tty-bindings.json.bak
```

重新启动管理器并再次点击标签即可。

### 状态一直显示静态

状态来自 Codex/Agent 写入的窗口标题图标，不读取终端正文。普通 Shell、没有标题集成的程序或自行覆盖标题的程序会显示静态，这是预期行为。

### 更新后应用菜单图标没有变化

重新运行 `./install.sh` 后关闭并重新打开管理器。必要时注销桌面会话再登录，让桌面 Shell 重新读取用户图标缓存。

## 开发与测试

无需安装即可从源码运行：

```bash
python3 -m terminal_manager.app
```

完整测试：

```bash
python3 -m pytest
```

开发模式仍需要 X11 依赖；纯逻辑测试不要求启动图形窗口。

## 已知限制

- GNOME Terminal 的隐藏标签可展开、读取标题、判断标题状态和切换；其他终端模拟器是否支持隐藏标签取决于后续适配。
- Wayland 默认禁止普通应用任意聚焦其他窗口，需要后续实现 GNOME/KDE 专用适配器。
- 状态监测依赖 Agent 设置终端标题；普通 Shell 和没有标题集成的 Agent 会显示静态。
- Claude Code 的单点盲文动画标题（例如 `⠂ / ⠐`）按“正在输出”处理；`✳` 本身不代表运行，只有标题明确包含等待输入语义时才显示“等待用户”，无法区分时保守显示为静态。
- 未知动画不会在后台自动学习；必须由用户对选中窗口点击“学习信号”，结果保存在 `~/.local/state/terminal-manager/learned-signals.json`。
- GNOME Terminal 没有公开“标签到 TTY”的直接映射，因此首次原生背景高亮需要一次性视觉学习。

## 卸载

```bash
./uninstall.sh
```

卸载不会影响任何终端或任务。

卸载默认保留 `~/.local/state/terminal-manager/` 中的登记名称和 TTY 缓存，方便以后重新安装。若确定不再需要，可自行备份后删除。

## License

MIT
