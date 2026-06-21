"""PlaybookExecutor 单元测试（R001-BB003）。

全 mock，覆盖：
- TestReproduceMode：复现模式 3 场景
- TestExploreMode：探测模式 9 场景
- TestExecutorResult：结果结构 2 场景
- TestActionDispatch：7 action 映射 1 场景

无 emulator / LLM / DB 依赖。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.diagnosis.playbook_executor import PlaybookExecutor
from agent.infra.adb_client import ADBCommandError, ADBResult
from agent.playbook.schema import PlaybookDefinition
from agent.reproduce.reproduce_runner import StepOutcome
from agent.vision.vision_decision_engine import VisionDecision


# ---------------------------------------------------------------------------
# 工厂辅助
# ---------------------------------------------------------------------------


def _make_repro_playbook(steps: int = 3) -> PlaybookDefinition:
    """构造有 reproduce_steps 的 Playbook。"""
    return PlaybookDefinition(
        id="crash_v1",
        symptom_type="crash",
        passive=True,
        reproduce_steps=[
            {"action": "tap", "params": {"x": i * 100, "y": i * 200}}
            for i in range(steps)
        ],
    )


def _make_explore_playbook() -> PlaybookDefinition:
    """构造无 reproduce_steps 的 Playbook（探测模式）。"""
    return PlaybookDefinition(
        id="blank_v1",
        symptom_type="blank",
        passive=False,
        reproduce_steps=[],
        signal_triggers=["FATAL EXCEPTION", "blank screen"],
    )


def _make_step_outcomes(n: int = 3) -> list[StepOutcome]:
    return [
        StepOutcome(
            step_no=i,
            action="tap",
            target_coords={"x": i, "y": i * 2},
        )
        for i in range(1, n + 1)
    ]


def _make_decision(
    action: str = "tap",
    params: dict | None = None,
    degraded: bool = False,
) -> VisionDecision:
    return VisionDecision(
        action=action,
        params=params or {},
        confidence=0.8,
        reasoning="test",
        used_anchor=False,
        degraded=degraded,
    )


def _make_adb_client() -> MagicMock:
    c = MagicMock()
    c.tap.return_value = ADBResult(True, b"", b"", 0, 5)
    c.swipe.return_value = ADBResult(True, b"", b"", 0, 5)
    c.input_text.return_value = ADBResult(True, b"", b"", 0, 5)
    c.press_key.return_value = ADBResult(True, b"", b"", 0, 5)
    c.screenshot.return_value = ADBResult(True, b"\x89PNG", b"", 0, 5)
    return c


def _make_screenshot_collector() -> MagicMock:
    """返回 bytes（模拟 PNG）的截图采集器。"""
    return MagicMock(return_value=b"\x89PNG\xfake")


def _make_explore_executor(
    *,
    max_steps: int = 10,
    vision_decisions: list[VisionDecision] | None = None,
    signal_results: list[list] | None = None,
    gap_store: MagicMock | None = None,
    screenshot_collector: MagicMock | None = None,
    adb_client: MagicMock | None = None,
) -> PlaybookExecutor:
    """构造探测模式的 Executor（vision_engine + signal_router 全 mock）。"""
    if vision_decisions is None:
        vision_decisions = [_make_decision("wait", {"duration_ms": 0})]

    vision_engine = MagicMock()
    vision_engine.decide = AsyncMock(side_effect=list(vision_decisions))

    signal_router = MagicMock()
    if signal_results is not None:
        signal_router.dispatch.side_effect = list(signal_results)
    else:
        signal_router.dispatch.return_value = []

    return PlaybookExecutor(
        reproduce_runner_fn=MagicMock(),
        vision_engine=vision_engine,
        signal_router=signal_router,
        adb_client=adb_client or _make_adb_client(),
        gap_store=gap_store,
        max_steps=max_steps,
        screenshot_collector=screenshot_collector or _make_screenshot_collector(),
    )


# ---------------------------------------------------------------------------
# TestReproduceMode
# ---------------------------------------------------------------------------


class TestReproduceMode:
    """复现模式（Mode A）。"""

    @pytest.mark.asyncio
    async def test_reproduce_mode_calls_runner(self):
        """AC-2: 复现模式调用 reproduce_runner_fn。"""
        mock_runner = MagicMock(return_value=_make_step_outcomes(3))
        executor = PlaybookExecutor(
            reproduce_runner_fn=mock_runner,
            adb_client=_make_adb_client(),
        )
        playbook = _make_repro_playbook(3)
        result = await executor.execute(playbook)

        mock_runner.assert_called_once()
        assert result.mode == "reproduce"
        assert result.step_count == 3
        assert len(result.repro_steps) == 3

    @pytest.mark.asyncio
    async def test_reproduce_mode_no_vision_engine(self):
        """AC-2: 复现模式不调用 vision_engine.decide。"""
        vision_engine = MagicMock()
        vision_engine.decide = AsyncMock()

        mock_runner = MagicMock(return_value=_make_step_outcomes(2))
        executor = PlaybookExecutor(
            reproduce_runner_fn=mock_runner,
            vision_engine=vision_engine,
            adb_client=_make_adb_client(),
        )
        playbook = _make_repro_playbook(2)
        await executor.execute(playbook)

        vision_engine.decide.assert_not_called()

    @pytest.mark.asyncio
    async def test_reproduce_mode_not_exhausted(self):
        """AC-2: 复现模式 exhausted=False, gap_created=False。"""
        mock_runner = MagicMock(return_value=_make_step_outcomes(5))
        executor = PlaybookExecutor(
            reproduce_runner_fn=mock_runner,
            adb_client=_make_adb_client(),
        )
        result = await executor.execute(_make_repro_playbook(5))

        assert result.exhausted is False
        assert result.gap_created is False
        assert result.signals == []
        assert "reproduce mode" in result.reasoning


# ---------------------------------------------------------------------------
# TestExploreMode
# ---------------------------------------------------------------------------


class TestExploreMode:
    """探测模式（Mode B）。"""

    @pytest.mark.asyncio
    async def test_explore_mode_signal_hit_break(self):
        """AC-6: 信号命中终止 loop（第 3 步命中）。"""
        decisions = [
            _make_decision("tap", {"x": 1, "y": 2}),
            _make_decision("tap", {"x": 3, "y": 4}),
            _make_decision("tap", {"x": 5, "y": 6}),
        ]
        signal_results = [
            [],  # step 1 无信号
            [],  # step 2 无信号
            [{"signal_type": "crash", "severity": "fatal"}],  # step 3 命中
        ]
        executor = _make_explore_executor(
            max_steps=10,
            vision_decisions=decisions,
            signal_results=signal_results,
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.mode == "explore"
        assert result.step_count == 3
        assert result.exhausted is False
        assert len(result.signals) == 1
        assert result.signals[0]["signal_type"] == "crash"

    @pytest.mark.asyncio
    async def test_explore_mode_step_budget_exhausted(self):
        """AC-4: max_steps=2，2 步无信号 → exhausted。"""
        decisions = [
            _make_decision("wait", {"duration_ms": 0}),
            _make_decision("wait", {"duration_ms": 0}),
        ]
        executor = _make_explore_executor(
            max_steps=2,
            vision_decisions=decisions,
            signal_results=[[], []],
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.exhausted is True
        assert result.step_count == 2
        assert result.signals == []

    @pytest.mark.asyncio
    async def test_explore_mode_creates_gap_on_exhaust(self):
        """AC-5: 步数耗尽 → gap_store.create 被调。"""
        gap_store = MagicMock()
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            gap_store=gap_store,
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.exhausted is True
        assert result.gap_created is True
        gap_store.create.assert_called_once()
        call_args = gap_store.create.call_args[0][0]
        assert call_args["gap_type"] == "coverage"
        assert "exhausted" in call_args["description"]

    @pytest.mark.asyncio
    async def test_explore_mode_gap_store_none_no_crash(self):
        """AC-5: gap_store=None → 不崩，gap_created=False。"""
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            gap_store=None,
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.exhausted is True
        assert result.gap_created is False

    @pytest.mark.asyncio
    async def test_explore_mode_gap_store_failure_warning(self):
        """AC-5: gap_store.create 抛错 → warning，gap_created=False。"""
        gap_store = MagicMock()
        gap_store.create.side_effect = RuntimeError("DB error")
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            gap_store=gap_store,
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.exhausted is True
        assert result.gap_created is False

    @pytest.mark.asyncio
    async def test_explore_mode_screenshot_failure_continues(self):
        """AC-9: 截图失败 → continue 不崩。"""
        screenshot_collector = MagicMock(side_effect=RuntimeError("ADB error"))
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            screenshot_collector=screenshot_collector,
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.step_count == 1
        assert result.repro_steps[0].screenshot_ref is None

    @pytest.mark.asyncio
    async def test_explore_mode_wait_action_sleeps(self):
        """AC-7: action=wait → sleep，不调 adb。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("wait", {"duration_ms": 10})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        with patch("agent.diagnosis.playbook_executor.time.sleep") as mock_sleep:
            result = await executor.execute(_make_explore_playbook())

        mock_sleep.assert_called_once_with(0.01)
        assert result.repro_steps[0].action == "wait"
        adb_client.tap.assert_not_called()

    @pytest.mark.asyncio
    async def test_explore_mode_step_count_increments(self):
        """AC-3: step 从 1 递增，step_count 为实际执行步数。"""
        decisions = [
            _make_decision("wait", {"duration_ms": 0}),
            _make_decision("wait", {"duration_ms": 0}),
            _make_decision("wait", {"duration_ms": 0}),
        ]
        executor = _make_explore_executor(
            max_steps=5,
            vision_decisions=decisions,
            signal_results=[[], [], [{"hit": True}]],  # 第 3 步命中
        )
        result = await executor.execute(_make_explore_playbook())

        assert result.step_count == 3
        assert result.repro_steps[0].step_no == 1
        assert result.repro_steps[1].step_no == 2
        assert result.repro_steps[2].step_no == 3

    @pytest.mark.asyncio
    async def test_explore_mode_task_description_from_playbook(self):
        """AC-3: task_description 从 Playbook 构造（Q5）。"""
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
        )
        playbook = _make_explore_playbook()
        await executor.execute(playbook)

        # 检查 decide 被调用时 task_description 含 symptom_type
        call_kwargs = executor._vision_engine.decide.call_args
        task_desc = call_kwargs.kwargs.get(
            "task_description", call_kwargs[1].get("task_description", "")
        )
        assert "blank" in task_desc


# ---------------------------------------------------------------------------
# TestExecutorResult
# ---------------------------------------------------------------------------


class TestExecutorResult:
    """ExecutorResult 结构验证。"""

    @pytest.mark.asyncio
    async def test_result_fields_complete(self):
        """AC-8: ExecutorResult 字段完整。"""
        mock_runner = MagicMock(return_value=_make_step_outcomes(2))
        executor = PlaybookExecutor(
            reproduce_runner_fn=mock_runner,
            adb_client=_make_adb_client(),
        )
        result = await executor.execute(_make_repro_playbook(2))

        assert hasattr(result, "mode")
        assert hasattr(result, "repro_steps")
        assert hasattr(result, "signals")
        assert hasattr(result, "exhausted")
        assert hasattr(result, "gap_created")
        assert hasattr(result, "step_count")
        assert hasattr(result, "reasoning")
        assert result.mode == "reproduce"
        assert result.step_count == 2
        assert result.reasoning != ""

    @pytest.mark.asyncio
    async def test_mode_dispatch_correct(self):
        """AC-1: reproduce_steps 非空 → reproduce；空 → explore。"""
        mock_runner = MagicMock(return_value=_make_step_outcomes(1))

        # 复现模式
        executor_r = PlaybookExecutor(
            reproduce_runner_fn=mock_runner,
            adb_client=_make_adb_client(),
        )
        result_r = await executor_r.execute(_make_repro_playbook(1))
        assert result_r.mode == "reproduce"

        # 探测模式
        executor_e = _make_explore_executor(
            max_steps=1,
            vision_decisions=[_make_decision("wait", {"duration_ms": 0})],
            signal_results=[[]],
        )
        result_e = await executor_e.execute(_make_explore_playbook())
        assert result_e.mode == "explore"


# ---------------------------------------------------------------------------
# TestActionDispatch
# ---------------------------------------------------------------------------


class TestActionDispatch:
    """action 分发（AC-7）：7 类 action 正确映射。"""

    @pytest.mark.asyncio
    async def test_action_tap_dispatch(self):
        """AC-7: tap → adb_tools.tap 被调。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("tap", {"x": 100, "y": 200})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        adb_client.tap.assert_called_once()
        call_args = adb_client.tap.call_args
        assert call_args[0][0] == 100  # x
        assert call_args[0][1] == 200  # y
        assert result.repro_steps[0].action == "tap"
        assert result.repro_steps[0].target_coords == {"x": 100, "y": 200}

    @pytest.mark.asyncio
    async def test_action_swipe_dispatch(self):
        """AC-7: swipe → adb_tools.swipe 被调。"""
        adb_client = _make_adb_client()
        decisions = [
            _make_decision("swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4})
        ]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        adb_client.swipe.assert_called_once()
        assert result.repro_steps[0].action == "swipe"

    @pytest.mark.asyncio
    async def test_action_input_dispatch(self):
        """AC-7: input → adb_tools.input_text 被调。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("input", {"text": "hello"})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        adb_client.input_text.assert_called_once()
        assert result.repro_steps[0].target_text == "hello"

    @pytest.mark.asyncio
    async def test_action_press_dispatch(self):
        """AC-7: press → adb_tools.press_key 被调。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("press", {"keycode": "3"})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        adb_client.press_key.assert_called_once()
        assert result.repro_steps[0].target_text == "3"

    @pytest.mark.asyncio
    async def test_action_back_dispatch(self):
        """AC-7: back → adb_tools.press_key(keycode='4') 被调。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("back", {})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        adb_client.press_key.assert_called_once()
        call_args = adb_client.press_key.call_args
        assert call_args[0][0] == "4"  # keycode=4
        assert result.repro_steps[0].target_text == "4"

    @pytest.mark.asyncio
    async def test_action_screenshot_noop(self):
        """AC-7: screenshot → no-op（不调 adb 动作函数）。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("screenshot", {})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        result = await executor.execute(_make_explore_playbook())

        # screenshot action 不调 tap/swipe/press_key
        adb_client.tap.assert_not_called()
        adb_client.swipe.assert_not_called()
        adb_client.press_key.assert_not_called()
        assert result.repro_steps[0].action == "screenshot"

    @pytest.mark.asyncio
    async def test_action_wait_no_adb(self):
        """AC-7: wait → time.sleep，不调 adb_tools。"""
        adb_client = _make_adb_client()
        decisions = [_make_decision("wait", {"duration_ms": 5})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
            adb_client=adb_client,
        )
        with patch("agent.diagnosis.playbook_executor.time.sleep"):
            result = await executor.execute(_make_explore_playbook())

        adb_client.tap.assert_not_called()
        adb_client.swipe.assert_not_called()
        assert result.repro_steps[0].action == "wait"

    @pytest.mark.asyncio
    async def test_action_adb_error_continues(self):
        """AC-7: 单步 ADB 失败 → 不中断 loop，错误记录到 ReproStep。"""
        adb_client = _make_adb_client()
        adb_client.tap.side_effect = ADBCommandError("tap failed")
        decisions = [
            _make_decision("tap", {"x": 1, "y": 2}),
            _make_decision("wait", {"duration_ms": 0}),
        ]
        executor = _make_explore_executor(
            max_steps=2,
            vision_decisions=decisions,
            signal_results=[[], []],
            adb_client=adb_client,
        )
        with patch("agent.diagnosis.playbook_executor.time.sleep"):
            result = await executor.execute(_make_explore_playbook())

        assert result.step_count == 2
        assert result.repro_steps[0].actual_signal is not None
        assert "ADBCommandError" in result.repro_steps[0].actual_signal["error"]
        # step 2 正常执行
        assert result.repro_steps[1].actual_signal is None


# ---------------------------------------------------------------------------
# TestCustomTaskDescription
# ---------------------------------------------------------------------------


class TestCustomTaskDescription:
    """自定义 task_description 传递。"""

    @pytest.mark.asyncio
    async def test_custom_task_description_passed(self):
        """自定义 task_description 覆盖 playbook 内置描述。"""
        decisions = [_make_decision("wait", {"duration_ms": 0})]
        executor = _make_explore_executor(
            max_steps=1,
            vision_decisions=decisions,
            signal_results=[[]],
        )
        await executor.execute(
            _make_explore_playbook(),
            task_description="custom task",
        )

        call_kwargs = executor._vision_engine.decide.call_args
        task_desc = call_kwargs.kwargs.get(
            "task_description",
            call_kwargs[1].get("task_description", ""),
        )
        assert task_desc == "custom task"


# ---------------------------------------------------------------------------
# TestDefaultMaxSteps
# ---------------------------------------------------------------------------


class TestDefaultMaxSteps:
    """D7 步数预算默认值。"""

    def test_default_max_steps_is_10(self):
        """AC-4: max_steps 默认值为 10（D7）。"""
        executor = PlaybookExecutor(
            reproduce_runner_fn=MagicMock(),
            adb_client=_make_adb_client(),
        )
        assert executor._max_steps == 10

    def test_custom_max_steps(self):
        """AC-4: max_steps 可通过构造函数覆盖。"""
        executor = PlaybookExecutor(
            reproduce_runner_fn=MagicMock(),
            adb_client=_make_adb_client(),
            max_steps=5,
        )
        assert executor._max_steps == 5
