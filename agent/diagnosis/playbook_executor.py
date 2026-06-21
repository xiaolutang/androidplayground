"""Playbook 执行器（双模式）—— R001-BB003。

依据：
- Sprint Contract R001-BB003（status: agreed，mode: negotiated / Mode 1）
- 技术决策 D3（双模式：复现确定性脚本 / 探测 agent tool-calling loop）
- 技术决策 D7（步数预算硬约束）

设计要点：
1. **双模式分发**（AC-1）：``playbook.reproduce_steps`` 非空 → 复现模式（Mode A）；
   为空 → 探测模式（Mode B）。
2. **复现模式**（AC-2）：调 ``reproduce_runner.run_reproduce`` 确定性执行，
   BF003 不参与；``outcomes_to_repro_steps`` 转换为 ``list[ReproStep]``。
3. **探测模式**（AC-3 ~ AC-9）：while 循环 agent loop，每步截图 → BF003 decide →
   BF002 action 分发 → BF004 信号检查；命中信号 break / 步数耗尽终止。
4. **D7 步数预算**（AC-4）：``max_steps`` 默认 10，硬约束。
5. **步数耗尽 → coverage gap**（AC-5）：``GapStore.create`` 创建覆盖率缺口，
   失败仅 warning 不崩。
6. **action 映射**（AC-7）：表驱动 ``_ACTION_MAP``，7 类 action 与 BF002 adb_tools 对齐。
7. **async 接口**：``execute()`` 为 async（因 BF003 ``vision_engine.decide()`` 是 async），
   统一 async 接口；复现模式内部无 await 但接口一致。
"""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4

from agent.gap.gap_store import GapStore
from agent.infra.adb_client import ADBClient, ADBError
from agent.playbook.schema import PlaybookDefinition
from agent.reproduce import adb_tools
from agent.reproduce.reproduce_runner import (
    StepOutcome,
    outcomes_to_repro_steps,
)
from agent.schemas.repro_step import ReproStep
from agent.signals.router import SignalRouter
from agent.vision.vision_decision_engine import (
    VisionDecision,
    VisionDecisionEngine,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# action 分发表（探测模式，与 BF002 adb_tools + BF003 action 白名单对齐）
# ---------------------------------------------------------------------------

_ACTION_MAP: dict[str, Callable[[Any, dict, Optional[str]], Any]] = {
    "tap": lambda client, p, did: adb_tools.tap(
        client, p["x"], p["y"], device_id=did
    ),
    "swipe": lambda client, p, did: adb_tools.swipe(
        client,
        p["x1"],
        p["y1"],
        p["x2"],
        p["y2"],
        duration_ms=p.get("duration_ms", 300),
        device_id=did,
    ),
    "input": lambda client, p, did: adb_tools.input_text(
        client, p["text"], device_id=did
    ),
    "press": lambda client, p, did: adb_tools.press_key(
        client, p.get("keycode", "4"), device_id=did
    ),
    "back": lambda client, p, did: adb_tools.press_key(
        client, "4", device_id=did
    ),
}


# ---------------------------------------------------------------------------
# ExecutorResult dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutorResult:
    """Playbook 执行结果（双模式统一产出）。

    Attributes:
        mode: 执行模式（"reproduce" / "explore"）。
        repro_steps: 复现步骤列表（ReproStep 或 dict）。
        signals: 命中的信号列表。
        exhausted: 步数是否耗尽（探测模式专属）。
        gap_created: 是否创建了 CapabilityGap。
        step_count: 实际执行步数。
        reasoning: 执行摘要。
    """

    mode: str
    repro_steps: list[Any]
    signals: list[Any] = field(default_factory=list)
    exhausted: bool = False
    gap_created: bool = False
    step_count: int = 0
    reasoning: str = ""


# ---------------------------------------------------------------------------
# PlaybookExecutor
# ---------------------------------------------------------------------------


class PlaybookExecutor:
    """Playbook 执行器（双模式编排）。

    根据 ``PlaybookDefinition.reproduce_steps`` 是否非空，分发到复现模式或探测模式。

    Args:
        reproduce_runner_fn: BF002 ``run_reproduce`` 可调用（复现模式）。
        vision_engine: BF003 ``VisionDecisionEngine``（探测模式用，可 None）。
        signal_router: BF004 ``SignalRouter``（探测模式用，可 None）。
        adb_client: INF05 ``ADBClient``（device 已就绪）。
        gap_store: BF008 ``GapStore``（步数耗尽建 gap，可 None）。
        max_steps: D7 步数预算硬上限（默认 10）。
        screenshot_collector: 截图采集函数（可调用，可 None → 用 adb_tools.screenshot）。
        device_id: 设备 ID（可选）。
    """

    def __init__(
        self,
        reproduce_runner_fn: Callable[..., list[StepOutcome]],
        vision_engine: Optional[VisionDecisionEngine] = None,
        signal_router: Optional[SignalRouter] = None,
        adb_client: Optional[ADBClient] = None,
        gap_store: Optional[GapStore] = None,
        max_steps: int = 10,
        screenshot_collector: Optional[Callable[..., bytes]] = None,
        device_id: Optional[str] = None,
    ) -> None:
        self._reproduce_runner_fn = reproduce_runner_fn
        self._vision_engine = vision_engine
        self._signal_router = signal_router
        self._adb_client = adb_client
        self._gap_store = gap_store
        self._max_steps = max_steps
        self._screenshot_collector = screenshot_collector
        self._device_id = device_id

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def execute(
        self,
        playbook: PlaybookDefinition,
        task_description: str = "",
    ) -> ExecutorResult:
        """执行 Playbook（双模式分发）。

        Args:
            playbook: Playbook 定义（BF006）。
            task_description: 任务描述（探测模式传给 BF003，可覆盖 playbook 内置描述）。

        Returns:
            ExecutorResult。
        """
        if playbook.reproduce_steps:
            return self._execute_reproduce(playbook)
        return await self._execute_explore(playbook, task_description)

    # ------------------------------------------------------------------
    # 复现模式（Mode A）
    # ------------------------------------------------------------------

    def _execute_reproduce(
        self, playbook: PlaybookDefinition
    ) -> ExecutorResult:
        """复现模式：确定性脚本执行（AC-2）。

        - 调 reproduce_runner_fn(client, playbook.reproduce_steps)
        - outcomes_to_repro_steps 转换
        - 不调 BF003
        - exhausted=False, gap_created=False
        """
        outcomes = self._reproduce_runner_fn(
            self._adb_client,
            playbook.reproduce_steps,
            device_id=self._device_id,
        )
        repro_steps = outcomes_to_repro_steps(outcomes)
        return ExecutorResult(
            mode="reproduce",
            repro_steps=repro_steps,
            signals=[],
            exhausted=False,
            gap_created=False,
            step_count=len(repro_steps),
            reasoning=f"reproduce mode: {len(repro_steps)} steps executed",
        )

    # ------------------------------------------------------------------
    # 探测模式（Mode B）
    # ------------------------------------------------------------------

    async def _execute_explore(
        self,
        playbook: PlaybookDefinition,
        task_description: str,
    ) -> ExecutorResult:
        """探测模式：agent loop（AC-3 ~ AC-9）。

        while step < max_steps:
            1. 截图（失败 → fallback degraded continue）
            2. vision_engine.decide（async）
            3. action=="wait" → sleep, continue
            4. 执行 adb_tools[action]
            5. 采集信号 → signal_router.dispatch
            6. 命中信号 → break
            7. step += 1

        步数耗尽 → gap_store.create（coverage）
        """
        if not task_description:
            task_description = self._build_task_description(playbook)

        repro_steps: list[ReproStep] = []
        signals: list[Any] = []
        step = 0
        exhausted = False

        while step < self._max_steps:
            step += 1

            # 1. 截图采集（失败 → None，不中断 loop）
            screenshot_url = self._capture_screenshot()

            # 2. BF003 决策
            try:
                decision = await self._vision_engine.decide(
                    screenshot_url=screenshot_url or "",
                    task_description=task_description,
                )
            except Exception as exc:
                logger.warning(
                    "PlaybookExecutor vision_engine.decide failed: %s", exc
                )
                decision = VisionDecision(
                    action="wait",
                    params={"duration_ms": 1000},
                    confidence=0.0,
                    reasoning=f"executor fallback: {exc}",
                    used_anchor=False,
                    degraded=True,
                )

            # 3. 执行 action
            repro_step = self._execute_action(decision, step, screenshot_url)
            repro_steps.append(repro_step)

            # 4. 检查信号
            step_signals = self._check_signals()
            if step_signals:
                signals.extend(step_signals)
                break

            # 5. 步数耗尽检查
            if step >= self._max_steps:
                exhausted = True

        # 步数耗尽 → 创建 coverage gap
        gap_created = False
        if exhausted and not signals:
            gap_created = self._create_coverage_gap(playbook, step)

        return ExecutorResult(
            mode="explore",
            repro_steps=repro_steps,
            signals=signals,
            exhausted=exhausted,
            gap_created=gap_created,
            step_count=step,
            reasoning=self._build_reasoning(step, signals, exhausted),
        )

    # ------------------------------------------------------------------
    # action 分发（AC-7）
    # ------------------------------------------------------------------

    def _execute_action(
        self,
        decision: VisionDecision,
        step_no: int,
        screenshot_url: Optional[str],
    ) -> ReproStep:
        """执行 VisionDecision 映射的 adb_tools action。

        Returns:
            ReproStep（含 action / target_coords / target_text / screenshot_ref）。
        """
        action = decision.action
        params = decision.params or {}
        target_coords: Optional[dict] = None
        target_text: Optional[str] = None
        error: Optional[str] = None

        try:
            if action == "wait":
                duration_ms = params.get("duration_ms", 1000)
                time.sleep(duration_ms / 1000.0)
            elif action == "screenshot":
                # no-op（截图已在步首采集）
                pass
            else:
                handler = _ACTION_MAP.get(action)
                if handler is None:
                    raise ValueError(f"unknown action: {action!r}")
                handler(self._adb_client, params, self._device_id)

                # 记录 target 信息
                if action == "tap":
                    target_coords = {
                        k: v for k, v in params.items() if k in ("x", "y")
                    }
                elif action == "swipe":
                    target_coords = {
                        k: v
                        for k, v in params.items()
                        if k in ("x1", "y1", "x2", "y2", "duration_ms")
                    }
                elif action == "input":
                    target_text = params.get("text")
                elif action == "press":
                    target_text = params.get("keycode", "4")
                elif action == "back":
                    target_text = "4"
        except ADBError as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "PlaybookExecutor action '%s' failed at step %d: %s",
                action,
                step_no,
                exc,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "PlaybookExecutor action '%s' error at step %d: %s",
                action,
                step_no,
                exc,
            )

        return ReproStep(
            id="",  # 调用方持久化时填充
            step_no=step_no,
            action=action,
            target_coords=target_coords,
            target_text=target_text,
            screenshot_ref=screenshot_url,
            actual_signal={"error": error} if error else None,
        )

    # ------------------------------------------------------------------
    # 截图采集（AC-9）
    # ------------------------------------------------------------------

    def _capture_screenshot(self) -> Optional[str]:
        """采集截图，返回 data_url；失败返回 None（不中断 loop）。"""
        try:
            if self._screenshot_collector is not None:
                png = self._screenshot_collector(
                    self._adb_client, device_id=self._device_id
                )
            else:
                png = adb_tools.screenshot(
                    self._adb_client, device_id=self._device_id
                )

            if not png:
                return None

            b64 = base64.b64encode(png).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception as exc:
            logger.warning(
                "PlaybookExecutor screenshot capture failed: %s", exc
            )
            return None

    # ------------------------------------------------------------------
    # 信号检查（AC-6）
    # ------------------------------------------------------------------

    def _check_signals(self) -> list[Any]:
        """检查信号路由器是否有命中。

        Returns:
            非空列表表示信号命中（应终止 loop）；空列表表示无信号。
        """
        if self._signal_router is None:
            return []

        # 构造一个通用信号对象供 dispatch
        # MVP：dispatch 需要一个有 signal_type 属性的对象
        probe_signal = _ProbeSignal()
        try:
            results = self._signal_router.dispatch(probe_signal)
            return results if results else []
        except Exception as exc:
            logger.warning(
                "PlaybookExecutor signal_router.dispatch failed: %s", exc
            )
            return []

    # ------------------------------------------------------------------
    # 步数耗尽 → 创建 coverage gap（AC-5）
    # ------------------------------------------------------------------

    def _create_coverage_gap(
        self, playbook: PlaybookDefinition, step: int
    ) -> bool:
        """步数耗尽时创建 coverage 类型 CapabilityGap。

        Returns:
            True 创建成功；False 创建失败或 gap_store 为 None。
        """
        if self._gap_store is None:
            return False

        gap_data = {
            "id": str(uuid4()),
            "gap_type": "coverage",
            "description": (
                f"step budget exhausted: {step} steps without signal hit "
                f"for playbook '{playbook.id}' "
                f"(symptom_type={playbook.symptom_type})"
            ),
            "linked_bug_ids": [],
        }
        try:
            self._gap_store.create(gap_data)
            return True
        except Exception as exc:
            logger.warning(
                "PlaybookExecutor gap_store.create failed: %s", exc
            )
            return False

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_task_description(playbook: PlaybookDefinition) -> str:
        """从 PlaybookDefinition 构造任务描述（Q5）。"""
        triggers = (
            ", ".join(playbook.signal_triggers)
            if playbook.signal_triggers
            else "(none)"
        )
        return (
            f"Bug 症状类型: {playbook.symptom_type}, "
            f"信号触发关键字: {triggers}, "
            f"目标: 探索 UI 诱发目标信号或定位异常"
        )

    @staticmethod
    def _build_reasoning(
        step: int, signals: list[Any], exhausted: bool
    ) -> str:
        """构造执行摘要。"""
        if signals:
            return (
                f"explore mode: signal hit at step {step}, "
                f"{len(signals)} signal(s)"
            )
        if exhausted:
            return f"explore mode: {step} steps exhausted without signal"
        return f"explore mode: {step} steps executed"


# ---------------------------------------------------------------------------
# 辅助类型
# ---------------------------------------------------------------------------


class _ProbeSignal:
    """信号探测对象（用于 signal_router.dispatch）。"""

    signal_type: str = "logcat"
    severity: str = "error"


__all__ = [
    "ExecutorResult",
    "PlaybookExecutor",
]
