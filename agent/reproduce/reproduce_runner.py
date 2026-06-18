"""复现模式 runner（确定性脚本执行）。

输入：Playbook 脚本（list[dict]，每条含 action + params）。
执行：确定性顺序调 adb_tools。
输出：list[StepOutcome] 内存对象（不持久化，由 Orchestrator 决定何时写）。
信号采集：最小 logcat -d 抓取（fallback），可注入 signal_collector 替换。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.infra.adb_client import ADBClient
from agent.schemas.repro_step import ReproStep
from agent.schemas.signal import SignalSeverity, SignalType

from agent.reproduce import adb_tools


# 脚本动作 -> adb_tools 函数映射（screenshot/wait 为特殊动作，单独处理）
_ADB_ACTION_DISPATCH: dict[str, Callable[..., Any]] = {
    "tap": adb_tools.tap,
    "swipe": adb_tools.swipe,
    "input": adb_tools.input_text,
    "input_text": adb_tools.input_text,
    "press": adb_tools.press_key,
    "press_key": adb_tools.press_key,
    "back": adb_tools.press_key,  # back -> press_key(keycode="4")
}

# 特殊动作（不走 ADB dispatch）
_SPECIAL_ACTIONS = frozenset({"screenshot", "wait"})


@dataclass
class StepOutcome:
    """单步执行结果（含 raw result + 采集的 signals + screenshot data_url）。"""

    step_no: int
    action: str
    target_coords: Optional[dict] = None
    target_text: Optional[str] = None
    expected_signal: Optional[dict] = None
    screenshot_ref: Optional[str] = None  # data_url 或 None
    actual_signal: Optional[dict] = None  # Signal 字段 dict
    error: Optional[str] = None  # 错误描述
    duration_ms: int = 0


@dataclass
class ReproduceConfig:
    """复现执行配置。"""

    on_step_error: str = "abort"  # continue / abort（AC-5 默认 abort）
    capture_screenshot_each_step: bool = True
    capture_signal_each_step: bool = True
    signal_keywords: list[str] = field(
        default_factory=lambda: [
            "FATAL EXCEPTION",
            "AndroidRuntime",
            "flutter:",
            "EXCEPTION",
        ]
    )


def run_reproduce(
    client: ADBClient,
    script: list[dict],
    *,
    config: Optional[ReproduceConfig] = None,
    device_id: Optional[str] = None,
    signal_collector: Optional[
        Callable[[Optional[str]], list[dict]]
    ] = None,
) -> list[StepOutcome]:
    """确定性顺序执行复现脚本。

    script: [{action: "tap", params: {"x":100,"y":200}}, ...]
    signal_collector: 注入式信号采集器（device_id -> list of signal dict）；
                     默认用内置 _default_logcat_collector。
    """
    config = config or ReproduceConfig()
    signal_collector = signal_collector or _default_logcat_collector
    outcomes: list[StepOutcome] = []

    for idx, step in enumerate(script, start=1):
        action = step.get("action")
        params = step.get("params", {})
        expected_signal = step.get("expected_signal")
        outcome = StepOutcome(
            step_no=idx, action=action or "", expected_signal=expected_signal
        )
        start = time.time()
        try:
            # 特殊动作：screenshot（仅采集）/ wait（time.sleep，无 ADB 调用）
            if action == "wait":
                duration_s = params.get("duration_ms", 0) / 1000.0
                outcome.target_coords = {
                    k: v
                    for k, v in params.items()
                    if k in ("duration_ms",)
                }
                if duration_s > 0:
                    time.sleep(duration_s)
            elif action == "screenshot":
                # screenshot 动作仅采集截图（已在下方 capture_screenshot_each_step 处理）
                pass
            else:
                dispatch = _ADB_ACTION_DISPATCH.get(action)
                if dispatch is None:
                    raise ValueError(f"unknown action: {action!r}")

                # back 动作映射到 press_key(keycode="4")
                if action == "back":
                    params = {"keycode": params.get("keycode", "4")}
                    outcome.target_text = params.get("keycode")
                # 填充 target_coords / target_text（按 action 类型）
                elif action in ("tap",):
                    outcome.target_coords = {
                        k: v for k, v in params.items() if k in ("x", "y")
                    }
                elif action in ("swipe",):
                    outcome.target_coords = {
                        k: v
                        for k, v in params.items()
                        if k in ("x1", "y1", "x2", "y2", "duration_ms")
                    }
                elif action in ("input", "input_text"):
                    outcome.target_text = params.get("text")
                elif action in ("press", "press_key"):
                    outcome.target_text = params.get("keycode")

                dispatch(client, device_id=device_id, **params)
            outcome.duration_ms = int((time.time() - start) * 1000)

            # 截图
            if config.capture_screenshot_each_step:
                try:
                    from agent.reproduce.screenshot_collector import (
                        collect,
                    )

                    outcome.screenshot_ref = collect(
                        client, device_id=device_id
                    )
                except Exception:
                    outcome.screenshot_ref = None

            # 信号
            if config.capture_signal_each_step:
                signals = signal_collector(device_id)
                if signals:
                    outcome.actual_signal = signals[0]
            outcomes.append(outcome)
        except Exception as e:
            outcome.duration_ms = int((time.time() - start) * 1000)
            outcome.error = f"{type(e).__name__}: {e}"
            # 失败时仍尝试采信号
            if config.capture_signal_each_step:
                signals = signal_collector(device_id)
                if signals:
                    outcome.actual_signal = signals[0]
            outcomes.append(outcome)
            if config.on_step_error == "abort":
                break
    return outcomes


def _default_logcat_collector(
    device_id: Optional[str], *, keywords: Optional[list[str]] = None
) -> list[dict]:
    """默认 logcat -d 抓取器（最小实现）。

    抓取最近 logcat，匹配 keywords，返回 Signal dict 列表。
    BF004 实现后可替换此 fallback。
    """
    import subprocess as sp

    keywords = keywords or [
        "FATAL EXCEPTION",
        "AndroidRuntime",
        "flutter:",
        "EXCEPTION",
    ]
    args = ["adb"]
    if device_id:
        args += ["-s", device_id]
    args += ["logcat", "-d", "-t", "200"]
    try:
        proc = sp.run(args, capture_output=True, text=True, timeout=5)
    except (sp.TimeoutExpired, FileNotFoundError):
        return []
    if proc.returncode != 0:
        return []
    signals: list[dict] = []
    for line in proc.stdout.splitlines():
        for kw in keywords:
            if kw.lower() in line.lower():
                severity = SignalSeverity.ERROR
                if "FATAL" in line.upper():
                    severity = SignalSeverity.CRASH
                signals.append(
                    {
                        "signal_type": SignalType.LOGCAT.value,
                        "severity": severity.value,
                        "pattern": kw,
                        "source_config": {"line": line[:500]},
                    }
                )
                break
    return signals


def outcomes_to_repro_steps(
    outcomes: list[StepOutcome],
    *,
    trajectory_id: Optional[int] = None,
) -> list[ReproStep]:
    """StepOutcome -> ReproStep（SCH02 schema）转换。

    注意：ReproStep.id 为 String PK，调用方需在持久化时填充；
    本函数不设 id（留空字符串占位，调用方覆盖）。
    """
    steps: list[ReproStep] = []
    for o in outcomes:
        step = ReproStep(
            id="",  # 调用方持久化时填充
            trajectory_id=str(trajectory_id) if trajectory_id else None,
            step_no=o.step_no,
            action=o.action,
            target_coords=o.target_coords,
            target_text=o.target_text,
            expected_signal=o.expected_signal,
            screenshot_ref=o.screenshot_ref,
            actual_signal=o.actual_signal,
        )
        steps.append(step)
    return steps
