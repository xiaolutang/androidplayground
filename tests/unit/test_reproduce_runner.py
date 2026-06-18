from unittest.mock import MagicMock

from agent.infra.adb_client import ADBResult
from agent.reproduce.reproduce_runner import (
    _default_logcat_collector,
    outcomes_to_repro_steps,
    run_reproduce,
    ReproduceConfig,
    StepOutcome,
)


def _client():
    c = MagicMock(
        spec=[
            "tap",
            "swipe",
            "input_text",
            "screenshot",
            "install_apk",
            "press_key",
            "list_devices",
        ]
    )
    c.tap.return_value = ADBResult(True, b"", b"", 0, 5)
    c.swipe.return_value = ADBResult(True, b"", b"", 0, 5)
    c.screenshot.return_value = ADBResult(True, b"\x89PNG", b"", 0, 5)
    return c


def test_run_reproduce_executes_in_order():
    c = _client()
    script = [
        {"action": "tap", "params": {"x": 100, "y": 200}},
        {"action": "swipe", "params": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}},
    ]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 2
    assert outcomes[0].action == "tap"
    assert outcomes[1].action == "swipe"
    c.tap.assert_called_once()
    c.swipe.assert_called_once()


def test_unknown_action_records_error():
    c = _client()
    script = [{"action": "bogus", "params": {}}]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1
    assert outcomes[0].error is not None
    assert "unknown action" in outcomes[0].error.lower()


def test_on_step_error_abort():
    c = _client()
    c.tap.side_effect = RuntimeError("simulated fail")
    script = [
        {"action": "tap", "params": {"x": 1, "y": 2}},
        {"action": "tap", "params": {"x": 3, "y": 4}},  # 不会执行
    ]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            on_step_error="abort",
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1  # abort 后中断


def test_on_step_error_continue():
    c = _client()
    c.tap.side_effect = RuntimeError("fail")
    script = [
        {"action": "tap", "params": {"x": 1, "y": 2}},
        {"action": "tap", "params": {"x": 3, "y": 4}},
    ]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            on_step_error="continue",
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 2


def test_on_step_error_default_is_abort():
    """AC-5 默认 abort：不设 on_step_error 时，出错即中断。"""
    c = _client()
    c.tap.side_effect = RuntimeError("fail")
    script = [
        {"action": "tap", "params": {"x": 1, "y": 2}},
        {"action": "tap", "params": {"x": 3, "y": 4}},
    ]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1


def test_signal_collector_injected():
    c = _client()
    collected = [
        {"signal_type": "logcat", "severity": "error", "pattern": "FATAL"}
    ]
    def sc(device_id):
        return collected
    script = [{"action": "tap", "params": {"x": 1, "y": 2}}]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(capture_screenshot_each_step=False),
        signal_collector=sc,
    )
    assert outcomes[0].actual_signal == collected[0]


def test_outcomes_to_repro_steps():
    outcomes = [
        StepOutcome(
            step_no=1, action="tap", target_coords={"x": 1, "y": 2}
        ),
        StepOutcome(step_no=2, action="swipe"),
    ]
    steps = outcomes_to_repro_steps(outcomes, trajectory_id=42)
    assert len(steps) == 2
    assert steps[0].step_no == 1
    assert steps[0].action == "tap"
    assert steps[0].trajectory_id == "42"


def test_default_logcat_collector_no_adb(monkeypatch):
    import subprocess as sp

    def _raise(*a, **kw):
        raise FileNotFoundError("adb")

    monkeypatch.setattr(sp, "run", _raise)
    signals = _default_logcat_collector(None)
    assert signals == []


def test_default_logcat_collector_matches_keywords(monkeypatch):
    import subprocess as sp

    fake_proc = sp.CompletedProcess(
        args=[],
        returncode=0,
        stdout="E/AndroidRuntime: FATAL EXCEPTION\nsome other line\n",
        stderr=b"",
    )
    monkeypatch.setattr(sp, "run", lambda *a, **kw: fake_proc)
    signals = _default_logcat_collector(None)
    assert len(signals) >= 1
    assert signals[0]["signal_type"] == "logcat"


def test_deterministic_business_fields():
    """同一输入两次 run，业务字段（step_no/action/target_coords）一致。"""
    c1 = _client()
    c2 = _client()
    script = [
        {"action": "tap", "params": {"x": 10, "y": 20}},
        {"action": "swipe", "params": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}},
        {"action": "input", "params": {"text": "hello"}},
    ]
    config = ReproduceConfig(
        capture_screenshot_each_step=False,
        capture_signal_each_step=False,
    )
    out1 = run_reproduce(c1, script, config=config)
    out2 = run_reproduce(c2, script, config=config)
    for o1, o2 in zip(out1, out2):
        assert o1.step_no == o2.step_no
        assert o1.action == o2.action
        assert o1.target_coords == o2.target_coords
        assert o1.target_text == o2.target_text


def test_back_action_maps_to_press_key():
    """back 动作映射到 press_key(keycode='4')。"""
    c = _client()
    script = [{"action": "back", "params": {}}]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1
    assert outcomes[0].target_text == "4"
    c.press_key.assert_called_once_with("4", device_id=None)


def test_wait_action_no_adb_call():
    """wait 动作不触发 ADB 调用。"""
    c = _client()
    script = [{"action": "wait", "params": {"duration_ms": 10}}]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1
    assert outcomes[0].action == "wait"
    assert outcomes[0].target_coords == {"duration_ms": 10}
    c.tap.assert_not_called()


def test_screenshot_action_executes():
    """screenshot 动作仅采集（不调 adb action 函数）。"""
    c = _client()
    script = [{"action": "screenshot", "params": {}}]
    outcomes = run_reproduce(
        c,
        script,
        config=ReproduceConfig(
            capture_screenshot_each_step=False,
            capture_signal_each_step=False,
        ),
    )
    assert len(outcomes) == 1
    assert outcomes[0].action == "screenshot"
