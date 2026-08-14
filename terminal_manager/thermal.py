from __future__ import annotations

import math
import time
from dataclasses import dataclass


HEAT_SECONDS = 10 * 60.0
COOL_SECONDS = 6 * 60.0
HOT_ROW = "#d92f45"
HOT_ACCENT = "#ef3340"
MAX_SAMPLE_GAP_SECONDS = 10.0


@dataclass
class _Temperature:
    value: float
    updated_at: float
    status: str
    cooling_rate: float = 0.0


class ThermalTracker:
    """Accumulate per-item heat from activity without changing classification."""

    def __init__(self, max_sample_gap_seconds: float = MAX_SAMPLE_GAP_SECONDS) -> None:
        self._items: dict[str, _Temperature] = {}
        self.max_sample_gap_seconds = max(0.0, max_sample_gap_seconds)

    def update(self, statuses: dict[str, str], *, now: float | None = None) -> dict[str, float]:
        timestamp = time.monotonic() if now is None else now
        for item_id, status in statuses.items():
            item = self._items.get(item_id)
            if item is None:
                item = _Temperature(0.0, timestamp, status)
                self._items[item_id] = item
            # Long GUI stalls (for example a modal edit dialog or desktop
            # suspension) are unobserved time, not evidence of continuous
            # output. Cap one sample so heat cannot jump to red at once.
            elapsed = min(self.max_sample_gap_seconds, max(0.0, timestamp - item.updated_at))
            status_changed = status != item.status
            if status_changed:
                item.status = status
                item.cooling_rate = item.value / COOL_SECONDS if status == "static" else 0.0
                # The transition sample establishes the cooling start point;
                # no unobserved time before it belongs to the new status.
                elapsed = 0.0
            if status == "active":
                item.value = min(1.0, item.value + elapsed / HEAT_SECONDS)
            elif status == "static":
                item.value = max(0.0, item.value - elapsed * item.cooling_rate)
            # waiting deliberately preserves the accumulated temperature.
            item.updated_at = timestamp

        for stale_id in set(self._items) - set(statuses):
            del self._items[stale_id]
        return {item_id: item.value for item_id, item in self._items.items()}


def blend_color(cold: str, hot: str, temperature: float) -> str:
    ratio = min(1.0, max(0.0, temperature))
    cold_rgb = _rgb(cold)
    hot_rgb = _rgb(hot)
    mixed = tuple(round(start + (end - start) * ratio) for start, end in zip(cold_rgb, hot_rgb))
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def mean_temperature(levels: dict[str, float]) -> float:
    return sum(levels.values()) / len(levels) if levels else 0.0


def visual_temperature(temperature: float) -> float:
    """Make early heat visible while preserving cold and maximum endpoints."""
    return math.sqrt(min(1.0, max(0.0, temperature)))


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(f"unsupported colour: {color}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
