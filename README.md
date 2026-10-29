# Terminal Manager（终端总控）

在一个总览窗口中管理**已经打开的 Linux 终端窗口**。点击条目即可切换并高亮对应终端，同时读取 Codex 写入窗口标题的状态信号。

产品需求、实现状态和验收证据见 [REQUIREMENTS.md](REQUIREMENTS.md)。

## 可靠恢复与资源保护（0.29.0）

- Codex 启动器解析安装路径及配套 Node，整批恢复前执行环境预检；Ubuntu 桌面 PATH 指向旧 Node 时也能使用 npm 安装对应的运行环境。仍仅恢复准确 ID，不发送提示、不重放旧命令。
- `inventory.sqlite3` 是登记和恢复状态的权威来源，首次启动事务导入原 JSON；原文件保留。数据库使用 WAL、FULL 同步、自动 checkpoint；正常关闭时通过 SQLite backup API 保存 `inventory-backup.sqlite3`。恢复失败、窗口消失和干净退出都不会删除登记。明确“移除记录”留下删除标记，避免历史快照把记录重新带回。
- 后台串行恢复支持“暂停自动恢复”“重试失败／继续恢复”。恢复清单显示待恢复、启动中、失败原因、对话待确认等状态，并可跳过自动恢复。启动身份在启动前落盘，重试先查原角色及原进程；不会仅因等待超时立即再开一个窗口。普通关机后的恢复依据系统启动身份，不再单独依赖管理器的 clean 标志。
- 创建窗口和确认对话分别记录：窗口存在且子进程存活仍不足以确认原对话，必须匹配实际 Codex 进程和会话标题；无法确认时保留“对话待确认”，允许手动核对。终端内子进程退出码、TTY 与 PID 保存在有限数量的启动回执中，不采集对话正文。
- 管理器创建的恢复窗口直接报告 TTY。其他窗口首次高亮识别放到后台，设有时间预算、取消和失败退避；表格改为更新现有行，快照只在变化时写入，观测写入由单个后台线程合并处理。
- 每 5 秒采集可用内存、交换空间和 memory/I/O PSI，每 30 秒记录相关进程 RSS/Swap。指标日志最多约 3 MB。可用内存低于总内存的 15%（至少预留 1 GiB）、换页超过 4096 页/秒、内存 PSI full 达 5% / some 达 15%，或 I/O PSI full 达 20% 时，暂停新增恢复和重扫描；每次启动前还会即时复核资源。不会杀进程、清缓存或关闭真实窗口。
- 新建工作终端继续通过“新建保活任务”进入独立 tmux/systemd 服务，启用资源统计；CLI 可选 `terminal-manager-task new <目录> --memory-high 4G` 设置软预算。默认不设置会杀任务的内存硬上限。外部共享 Codex 服务的资源可能不属于任务 cgroup，应结合全局指标观察。

普通窗口退出后不会在当前运行中无限自动拉起；未恢复记录保留在清单。暂停／跳过状态跨重启保留。上一系统启动中的保活进程不能重新连接，仍需明确恢复目录或对话；不会擅自重放任务命令。自动识别仍依赖 Codex 当前索引与标题格式，无准确 ID 的旧对话不会猜测。

验证包括真实桌面旧 Node 环境预检、119 项自动化测试、独立桌面精确参数恢复、40 个真实测试终端三分钟采样及管理器重启去重、终端服务器故障后的任务保活、高亮/置顶/多标签与十轮缩放。三分钟测试不等同于长期无内存泄漏证明，也不等同于物理断电验收。测试脚本：`tests/manual_reliability_smoke.py`、`tests/manual_codex_recovery_smoke.py`、`tests/manual_protection_smoke.py`。

## 后台扫描降载（0.28.1）

窗口标题、状态和温度仍每两秒更新；GNOME 隐藏标签清单和 Codex 会话索引改为独立的十秒扫描周期。新窗口、已知多标签窗口的标题主体变化和手动“刷新”可以提前请求标签扫描，慢扫描会自动延长间隔。隐藏标签的标题和选中状态可能比窗口标题晚一轮更新；切换标签时仍在隔离子进程中重新确认目标。

标签发现只查找相关容器，跳过菜单与终端内容，每个窗口标题只读取一次。旧版频繁遍历控件树，会让 GNOME Terminal 的主线程代为处理大量查询：负载主要显示在终端进程上，而不是管理器自身。扫描失败保留上一份标签清单；没有保活任务时不启动空的查询线程。

## Codex 对话恢复（0.28.0）

管理器现在同时保存已确认的 Codex 会话 ID、会话目录和会话存储目录。异常恢复时，如果记录带有准确 ID，会在新终端中执行 `codex resume <ID> -C <会话目录>`，重新绑定原登记；不会使用 `--last`、发送新提示或重放旧 Shell 命令。已经运行的准确会话会跳过，缺失或无效会话明确报错，不替换为其他对话。

- 自动识别结合真实交互式 Codex 进程、当前窗口标题及本地会话索引；已验证的 TTY 可进一步限定对应进程。同一目录多会话时不会只按更新时间猜测，无法唯一确认时不新增自动关联。
- 从“任务保护 → 关联 Codex 会话…”可以选择本目录的准确历史对话。保存关联不会启动任务或发送消息。
- “恢复清单”显示“Codex 原对话”“连接原任务”或“仅打开目录”。保活任务优先连接存活进程；“仅打开目录”始终可以绕过对话恢复。
- 恢复窗口时清除旧 PID/TTY；读取目录只信任本次运行中验证的 TTY 关联，防止终端崩溃后编号复用导致目录串到其他项目。

旧版本没有记录准确 ID 的窗口不能凭目录还原唯一对话，需要明确关联后才会自动恢复。Codex 本地索引依赖当前 `state_5.sqlite` 格式；读取失败时不猜测、不修改 Codex 数据库。对话记录恢复不代表崩溃前正在执行的进程或命令能够继续运行。

普通模式是现有终端之上的轻量控制面板，不迁移 Shell。0.27.0 新增可选的保活任务：通过独立 tmux 服务运行新 Shell，关闭终端窗口仍可继续运行；只有明确选择“结束选中保活任务”才会停止该任务。

## 终端崩溃后的损失防护（0.27.0）

- **已有普通窗口**：动态保存登记目录；窗口消失前的清单另存历史。顶部“任务保护 → 恢复清单”可手动按目录重新打开并登记。不会重放命令或恢复已经退出的进程。
- **新建保活任务**：选择“任务保护 → 新建保活任务”，选目录后在新终端中工作。每个任务使用独立 tmux 服务器和 systemd 用户服务，与 GNOME Terminal 的进程组分离。窗口关闭或终端服务器崩溃后，从管理器重连原任务。
- **结束与移除**：“结束选中保活任务”经确认停止该任务及子进程；“移除记录”只删除管理器登记，不停止任务。移除后可用 `terminal-manager-task list` 查找，再用 `terminal-manager-task open <ID>` 重连。
- **恢复边界**：已有普通 Shell 不会自动转成保活任务。断电、重启、任务自身崩溃、系统 OOM 或用户服务被清理仍可能终止任务；重启后可以选择“仅打开目录”，但不自动重启原命令。应用自身的数据检查点仍需由应用保存。
- **目录与标签**：保活任务从 tmux 查询当前目录和标题；普通隐藏标签仅保存已成功识别 TTY 的目录，未识别目录不会猜测。当前每个保活任务以一个终端窗口为主要管理入口。

保活模式额外依赖 `tmux` 和可用的 `systemd --user`。可执行 `sudo apt install tmux`；Ubuntu amd64 无管理员权限时可在项目目录运行 `./install-protection.sh`，将发行版软件包解包到用户目录。普通模式不要求 tmux。

恢复数据位于 `${XDG_STATE_HOME:-~/.local/state}/terminal-manager/`：`runtime-session.json` 保存最近清单，`session-history/` 分别保留最多 32 份窗口消失快照和 96 份普通变更快照，`protected/` 保存保活身份。JSON 原子写入、文件权限 0600。历史是有限保留，并非永久备份。`window-operations.log` 记录带时间戳的窗口操作，2 MiB 轮转，另保留 3 份。

验证：自动化测试覆盖快照丢失、干净退出、旧启动任务拒绝重连、X11 失败停止后续动作；`tests/manual_protection_smoke.py` 在独立 Xvfb/D-Bus 桌面中结束测试 GNOME Terminal 服务器，检查任务 PID 不变、计数连续、重连和管理器高亮。此脚本需要项目 `tmp/` 下的隔离测试依赖及状态目录，不对真实桌面执行故障注入。

## 当前能力

- 自动发现 GNOME Terminal、Konsole、Tilix、Terminator、Kitty、Alacritty、WezTerm、XTerm、Wave 等 X11 终端窗口；
- 双击或按 Enter 聚焦、抬升对应终端窗口，并以约 0.3 秒的小幅快速摆动明确提示目标；
- 在桌面点击某个终端时，管理页会自动选中并滚动到对应记录，不抢夺输入焦点；
- 自动发现 GNOME Terminal 同一窗口中的隐藏标签页；多标签窗口使用列表内 `▸ / ▾` 分组展开，单击缩进子项即可切换标签并聚焦窗口；
- 给每个终端窗口设置只保存在管理器中的用途名称；
- 显示 Codex 标题状态信号和当前状态持续时间；
- 自动排序：颜色越暖的窗口越靠前；温度相同时按等待用户、正在输出、静态/空闲排序，再按进入状态的时间和名称保持稳定顺序；
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
  wmctrl xdotool xinput x11-apps x11-utils ffmpeg
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
