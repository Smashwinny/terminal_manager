from terminal_manager.activity import ActivityState
from terminal_manager.app import signal_text


def state(status: str, prefix: str = "", learned: bool = False) -> ActivityState:
    return ActivityState(status, 1.0, 1, prefix, learned)


def test_signal_text_explains_detection_source() -> None:
    assert signal_text(state("active", "⠹")) == "Codex 旋转动画"
    assert signal_text(state("active", "⠂")) == "Claude 点动画"
    assert signal_text(state("active", "◐", True)) == "自动学习动画"
    assert signal_text(state("waiting", "!")) == "明确等待提示"
    assert signal_text(state("static", "✳")) == "未检测到 Agent 信号"
    assert signal_text(None) == "窗口不可用"
