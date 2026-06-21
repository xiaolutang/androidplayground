"""RegressionVerifier 单元测试（R001-BB008，AC-1 ~ AC-10）。

覆盖：
- AC-1: Tier1 三关全过
- AC-2: Tier2 轻量验证 + is_draft
- AC-3: fail 分类（root_cause_error / patch_error）
- AC-4: root_cause_error → overturn_signal
- AC-5: patch_error → retry_signal
- AC-6: 三关执行顺序（短路）
- AC-7: 静态检查命令可配置
- AC-8: 复现序列回归（BF002 重放 + 比对）
- AC-9: VerificationResult 数据结构
- AC-10: 测试覆盖（15+ 场景）
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent.fix.regression_verifier import (
    RegressionVerifier,
    VerificationResult,
)
from agent.reproduce.reproduce_runner import StepOutcome


# ---------------------------------------------------------------------------
# 辅助构造
# ---------------------------------------------------------------------------
def _make_bug_signal(
    signal_type: str = "logcat",
    severity: str = "crash",
    pattern: str = "FATAL EXCEPTION",
) -> dict:
    """构造 bug 信号 dict。"""
    return {
        "signal_type": signal_type,
        "severity": severity,
        "pattern": pattern,
    }


def _make_outcome(
    step_no: int = 1,
    action: str = "tap",
    actual_signal: dict | None = None,
) -> StepOutcome:
    """构造 StepOutcome。"""
    return StepOutcome(
        step_no=step_no,
        action=action,
        actual_signal=actual_signal,
    )


def _make_completed_proc(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    """构造模拟的 subprocess.run 返回值。"""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@pytest.fixture
def verifier() -> RegressionVerifier:
    """默认 RegressionVerifier（FIX_RETRY_MAX=3）。"""
    return RegressionVerifier(fix_retry_max=3)


@pytest.fixture
def mock_client() -> MagicMock:
    """模拟 ADBClient。"""
    return MagicMock()


# ---------------------------------------------------------------------------
# AC-1: Tier1 三关全过
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_all_gates_pass(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-1：Tier1 三关全过 → passed=True, tier=1, failed_gate=None。"""
    # 复现序列回归：baseline 无 bug 信号 → 通过
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=None)]
    # 测试 + 静态检查全过
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [_make_outcome(step_no=1, actual_signal=None)]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap", "params": {"x": 100, "y": 200}}],
        baseline_outcomes=baseline,
    )

    assert result.passed is True
    assert result.tier == 1
    assert result.failed_gate is None
    assert result.fail_category is None
    assert result.overturn_signal is None
    assert result.retry_signal is None
    # details 含三关记录
    assert "repro_regression" in result.details
    assert "existing_tests" in result.details
    assert "static_check" in result.details
    assert result.details["repro_regression"]["passed"] is True
    assert result.details["existing_tests"]["passed"] is True
    assert result.details["static_check"]["passed"] is True


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_all_gates_pass_details_structure(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-1：三关全过时 details 含三关各自的 pass 记录。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.details["repro_regression"]["passed"] is True
    assert result.details["existing_tests"]["passed"] is True
    assert result.details["static_check"]["passed"] is True


# ---------------------------------------------------------------------------
# AC-2: Tier2 轻量验证 + is_draft
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier2_lightweight_pass(
    mock_subproc,
    mock_repro,
    verifier,
):
    """AC-2：Tier2 轻量验证全过 → passed=True, tier=2。"""
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    result = verifier.verify(tier=2)

    assert result.passed is True
    assert result.tier == 2
    assert result.failed_gate is None
    assert result.fail_category is None


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier2_details_no_repro_regression(
    mock_subproc,
    mock_repro,
    verifier,
):
    """AC-2：Tier2 details 不含 repro_regression，只含 static_check + tier2_test_subset。"""
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    result = verifier.verify(tier=2)

    assert "repro_regression" not in result.details
    assert "static_check" in result.details
    assert "tier2_test_subset" in result.details


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier2_does_not_call_run_reproduce(
    mock_subproc,
    mock_repro,
    verifier,
):
    """AC-2：Tier2 不调 run_reproduce。"""
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    verifier.verify(tier=2)

    mock_repro.assert_not_called()


# ---------------------------------------------------------------------------
# AC-3: fail 分类（root_cause_error vs patch_error）
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
def test_tier1_repro_fail_root_cause_error(
    mock_repro,
    verifier,
    mock_client,
):
    """AC-3：复现序列回归 fail 且原 bug 信号仍出现 → root_cause_error。"""
    bug_signal = _make_bug_signal(severity="crash", pattern="FATAL EXCEPTION")
    # baseline 有 bug 信号，新执行也有同样信号
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=bug_signal)]

    baseline = [_make_outcome(step_no=1, actual_signal=bug_signal)]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=baseline,
    )

    assert result.passed is False
    assert result.fail_category == "root_cause_error"
    assert result.failed_gate == "repro_regression"


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_existing_tests_fail_patch_error(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-3：复现序列通过但既有测试 fail → patch_error。"""
    mock_repro.return_value = []
    # 既有测试失败（exit=1），静态检查通过
    mock_subproc.side_effect = [
        _make_completed_proc(returncode=1, stderr="test failed"),
        _make_completed_proc(returncode=0),
    ]

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.passed is False
    assert result.fail_category == "patch_error"
    assert result.failed_gate == "existing_tests"


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_static_check_fail_patch_error(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-3：前两关通过但静态检查 fail → patch_error。"""
    mock_repro.return_value = []
    # 测试通过，静态检查失败
    mock_subproc.side_effect = [
        _make_completed_proc(returncode=0),  # test
        _make_completed_proc(returncode=1, stderr="lint error"),  # ruff
        _make_completed_proc(returncode=0),  # mypy（不会执行，短路）
    ]

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.passed is False
    assert result.fail_category == "patch_error"
    assert result.failed_gate == "static_check"


@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier2_static_check_fail_patch_error(mock_subproc, verifier):
    """AC-3：Tier2 静态检查 fail → patch_error。"""
    mock_subproc.return_value = _make_completed_proc(
        returncode=1, stderr="lint error"
    )

    result = verifier.verify(tier=2)

    assert result.passed is False
    assert result.fail_category == "patch_error"
    assert result.failed_gate == "static_check"


@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier2_test_subset_fail_patch_error(mock_subproc, verifier):
    """AC-3：Tier2 测试子集 fail → patch_error。"""
    # 静态检查通过，测试子集失败
    mock_subproc.side_effect = [
        _make_completed_proc(returncode=0),  # ruff
        _make_completed_proc(returncode=0),  # mypy
        _make_completed_proc(returncode=1, stderr="subset test failed"),
    ]

    result = verifier.verify(tier=2)

    assert result.passed is False
    assert result.fail_category == "patch_error"
    assert result.failed_gate == "tier2_test_subset"


# ---------------------------------------------------------------------------
# AC-4: root_cause_error → overturn_signal
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
def test_root_cause_error_overturn_signal(
    mock_repro,
    verifier,
    mock_client,
):
    """AC-4：root_cause_error → overturn_signal 非 None + overturning_stage=regression。"""
    bug_signal = _make_bug_signal(severity="crash", pattern="FATAL EXCEPTION")
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=bug_signal)]

    baseline = [_make_outcome(step_no=1, actual_signal=bug_signal)]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=baseline,
    )

    assert result.overturn_signal is not None
    assert result.overturn_signal["overturning_stage"] == "regression"
    assert "reason" in result.overturn_signal
    assert "overturning_signal" in result.overturn_signal
    sig = result.overturn_signal["overturning_signal"]
    assert sig["gate"] == "repro_regression"
    assert sig["matching_step_no"] == 1
    assert sig["baseline_signal"]["signal_type"] == "logcat"
    assert sig["new_signal"]["severity"] == "crash"


@patch("agent.fix.regression_verifier.run_reproduce")
def test_root_cause_error_no_retry_signal(
    mock_repro,
    verifier,
    mock_client,
):
    """AC-4：root_cause_error 时 retry_signal=None。"""
    bug_signal = _make_bug_signal()
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=bug_signal)]

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=[_make_outcome(step_no=1, actual_signal=bug_signal)],
    )

    assert result.retry_signal is None


# ---------------------------------------------------------------------------
# AC-5: patch_error → retry_signal
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_patch_error_retry_signal(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-5：patch_error → retry_signal 含 next_strategy + should_retry。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(
        returncode=1, stderr="test failed"
    )

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
        attempt_no=1,
        current_strategy="template",
    )

    assert result.retry_signal is not None
    assert result.retry_signal["failed_gate"] == "existing_tests"
    assert result.retry_signal["attempt_no"] == 1
    assert result.retry_signal["next_strategy"] == "llm"
    assert result.retry_signal["should_retry"] is True


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_patch_error_no_overturn_signal(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-5：patch_error 时 overturn_signal=None。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(returncode=1)

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.overturn_signal is None


def test_retry_signal_should_retry_false_when_exhausted(verifier):
    """AC-5/AC-10：attempt_no >= FIX_RETRY_MAX → should_retry=False。"""
    signal = verifier._build_retry_signal(
        failed_gate="static_check",
        error_info={},
        attempt_no=3,  # == FIX_RETRY_MAX=3
        current_strategy="llm",
    )

    assert signal["should_retry"] is False


def test_retry_signal_should_retry_false_when_zero_max():
    """AC-5：FIX_RETRY_MAX=0 → should_retry 始终 False。"""
    v = RegressionVerifier(fix_retry_max=0)
    signal = v._build_retry_signal(
        failed_gate="static_check",
        error_info={},
        attempt_no=0,
    )

    assert signal["should_retry"] is False


def test_retry_signal_next_strategy_chain(verifier):
    """AC-5：next_strategy 按 template → llm → history_calibration 推进。"""
    s0 = verifier._next_strategy(None, 0)
    assert s0 == "template"

    s1 = verifier._next_strategy("template", 1)
    assert s1 == "llm"

    s2 = verifier._next_strategy("llm", 2)
    assert s2 == "history_calibration"

    # 末端钉住
    s3 = verifier._next_strategy("history_calibration", 3)
    assert s3 == "history_calibration"


# ---------------------------------------------------------------------------
# AC-6: 三关执行顺序（短路）
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_short_circuit_on_repro_fail(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-6：复现序列 fail 时既有测试/静态检查不执行。"""
    bug_signal = _make_bug_signal()
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=bug_signal)]

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=[_make_outcome(step_no=1, actual_signal=bug_signal)],
    )

    assert result.passed is False
    assert "existing_tests" not in result.details
    assert "static_check" not in result.details
    mock_subproc.assert_not_called()


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_short_circuit_on_test_fail(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-6：既有测试 fail 时静态检查不执行。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(
        returncode=1, stderr="test failed"
    )

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.passed is False
    assert "repro_regression" in result.details
    assert result.details["repro_regression"]["passed"] is True
    assert "existing_tests" in result.details
    assert result.details["existing_tests"]["passed"] is False
    # static_check 不应出现在 details
    assert "static_check" not in result.details


@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_tier1_execution_order(mock_subproc, mock_repro, verifier, mock_client):
    """AC-6：三关执行顺序：repro → test → static。

    baseline 非空（有 outcome 但无 bug 信号）才会调 run_reproduce。
    """
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=None)]
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=[_make_outcome(step_no=1, actual_signal=None)],
    )

    # run_reproduce 先被调
    mock_repro.assert_called_once()
    # subprocess.run 被调（test + static commands）
    assert mock_subproc.call_count >= 2


# ---------------------------------------------------------------------------
# AC-7: 静态检查命令可配置
# ---------------------------------------------------------------------------
def test_default_static_check_commands():
    """AC-7：默认 static_check_commands=["ruff check .", "mypy ."]。"""
    v = RegressionVerifier()
    assert v._static_check_commands == ["ruff check .", "mypy ."]


def test_custom_static_check_commands():
    """AC-7：自定义 static_check_commands 生效。"""
    v = RegressionVerifier(static_check_commands=["flutter analyze"])
    assert v._static_check_commands == ["flutter analyze"]


@patch("agent.fix.regression_verifier.subprocess.run")
def test_static_check_custom_command_used(mock_subproc):
    """AC-7：自定义静态检查命令传给 subprocess.run。"""
    mock_subproc.return_value = _make_completed_proc(returncode=0)
    v = RegressionVerifier(
        static_check_commands=[
            "flutter analyze",
            "dart format --set-exit-if-changed .",
        ]
    )

    v.verify(tier=2)

    commands_called = [
        call.args[0] if call.args else call.kwargs.get("args", "")
        for call in mock_subproc.call_args_list
    ]
    assert "flutter analyze" in commands_called
    assert "dart format --set-exit-if-changed ." in commands_called


@patch("agent.fix.regression_verifier.subprocess.run")
def test_static_check_timeout(mock_subproc):
    """AC-7：静态检查超时 → fail + details timeout=True。"""
    mock_subproc.side_effect = subprocess.TimeoutExpired(
        cmd="ruff check .", timeout=60
    )

    v = RegressionVerifier(fix_retry_max=3)
    result = v.verify(tier=2)

    assert result.passed is False
    assert result.failed_gate == "static_check"
    static_details = result.details["static_check"]
    assert static_details["commands"][0]["timeout"] is True


@patch("agent.fix.regression_verifier.subprocess.run")
def test_static_check_exception(mock_subproc):
    """AC-7：静态检查命令异常 → fail + details 含 error。"""
    mock_subproc.side_effect = FileNotFoundError("ruff not found")

    v = RegressionVerifier(fix_retry_max=3)
    result = v.verify(tier=2)

    assert result.passed is False
    assert result.failed_gate == "static_check"
    static_details = result.details["static_check"]
    assert "error" in static_details["commands"][0]


@patch("agent.fix.regression_verifier.subprocess.run")
def test_static_check_multiple_commands_first_fails(mock_subproc):
    """AC-7：多条静态检查命令，第一条 fail 即短路。"""
    mock_subproc.side_effect = [
        _make_completed_proc(returncode=1, stderr="ruff error"),
        _make_completed_proc(returncode=0),  # 不应执行
    ]

    v = RegressionVerifier(
        static_check_commands=["ruff check .", "mypy ."],
        fix_retry_max=3,
    )
    result = v.verify(tier=2)

    assert result.passed is False
    # 只调了一次（短路）
    assert mock_subproc.call_count == 1


# ---------------------------------------------------------------------------
# AC-8: 复现序列回归（BF002 重放 + 比对 StepOutcome）
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_repro_regression_calls_run_reproduce(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-8：复现序列回归关调 run_reproduce。"""
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=None)]
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [_make_outcome(step_no=1, actual_signal=None)]
    script = [{"action": "tap", "params": {"x": 100, "y": 200}}]
    verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=script,
        baseline_outcomes=baseline,
        device_id="emulator-5554",
    )

    mock_repro.assert_called_once()
    call_args = mock_repro.call_args
    assert call_args.args[0] is mock_client
    assert call_args.args[1] == script


@patch("agent.fix.regression_verifier.subprocess.run")
@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_regression_bug_signal_disappears_passes(
    mock_repro,
    mock_subproc,
    verifier,
    mock_client,
):
    """AC-8：baseline 有 bug 信号，新执行信号消失 → 通过。"""
    bug_signal = _make_bug_signal(severity="crash")
    # baseline 有 crash 信号，新执行 actual_signal=None
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=None)]
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [_make_outcome(step_no=1, actual_signal=bug_signal)]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=baseline,
    )

    # 只看复现序列回归关（后续测试关也需 mock，但这里只断言复现关通过）
    assert result.details["repro_regression"]["passed"] is True


@patch("agent.fix.regression_verifier.subprocess.run")
@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_regression_severity_downgrade_passes(
    mock_repro,
    mock_subproc,
    verifier,
    mock_client,
):
    """AC-8：baseline crash → 新执行 severity 降级为 warn → 通过。"""
    crash_signal = _make_bug_signal(severity="crash")
    warn_signal = _make_bug_signal(severity="warn", pattern="FATAL EXCEPTION")
    mock_repro.return_value = [_make_outcome(step_no=1, actual_signal=warn_signal)]
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [_make_outcome(step_no=1, actual_signal=crash_signal)]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=baseline,
    )

    assert result.details["repro_regression"]["passed"] is True


@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_regression_exception_patch_error(
    mock_repro,
    verifier,
    mock_client,
):
    """AC-8：run_reproduce 抛异常 → patch_error 降级。"""
    mock_repro.side_effect = RuntimeError("emulator connection lost")

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[{"action": "tap"}],
        baseline_outcomes=[
            _make_outcome(step_no=1, actual_signal=_make_bug_signal())
        ],
    )

    assert result.passed is False
    assert result.fail_category == "patch_error"
    assert result.failed_gate == "repro_regression"
    assert result.retry_signal is not None
    repro_details = result.details["repro_regression"]
    assert "error" in repro_details
    assert "emulator connection lost" in repro_details["error"]


@patch("agent.fix.regression_verifier.subprocess.run")
@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_baseline_no_bug_signal_passes(
    mock_repro,
    mock_subproc,
    verifier,
    mock_client,
):
    """AC-10：baseline 无 bug 信号（全 None）→ 复现序列回归关通过。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [
        _make_outcome(step_no=1, actual_signal=None),
        _make_outcome(step_no=2, actual_signal=None),
    ]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=baseline,
    )

    assert result.details["repro_regression"]["passed"] is True


@patch("agent.fix.regression_verifier.subprocess.run")
@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_baseline_empty_passes(mock_repro, mock_subproc, verifier, mock_client):
    """AC-8：baseline_outcomes 为空 → 无基准可比 → 降级为 pass。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
    )

    assert result.details["repro_regression"]["passed"] is True
    assert "no baseline" in result.details["repro_regression"]["reason"]


@patch("agent.fix.regression_verifier.subprocess.run")
@patch("agent.fix.regression_verifier.run_reproduce")
def test_repro_action_mismatch_warning_not_fail(
    mock_repro,
    mock_subproc,
    verifier,
    mock_client,
):
    """AC-8/Q2：action 不一致不直接判 fail（信号比对为主判据）。"""
    bug_signal = _make_bug_signal()
    # baseline action=tap，新执行 action=swipe，但信号消失
    mock_repro.return_value = [
        StepOutcome(step_no=1, action="swipe", actual_signal=None),
    ]
    mock_subproc.return_value = _make_completed_proc(returncode=0)

    baseline = [
        StepOutcome(step_no=1, action="tap", actual_signal=bug_signal),
    ]
    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=baseline,
    )

    # 信号消失 → 通过（action 不一致不判 fail）
    assert result.details["repro_regression"]["passed"] is True


# ---------------------------------------------------------------------------
# AC-9: VerificationResult 数据结构
# ---------------------------------------------------------------------------
def test_verification_result_dataclass_fields():
    """AC-9：VerificationResult 为 dataclass，含全部必需字段。"""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(VerificationResult)}
    assert fields == {
        "passed",
        "tier",
        "failed_gate",
        "fail_category",
        "details",
        "overturn_signal",
        "retry_signal",
    }


@patch("agent.fix.regression_verifier.subprocess.run")
def test_passed_result_clean_fields(mock_subproc):
    """AC-9：passed=True 时 failed_gate/fail_category/overturn/retry 全 None。"""
    mock_subproc.return_value = _make_completed_proc(returncode=0)
    v = RegressionVerifier(fix_retry_max=3)

    result = v.verify(tier=2)

    assert result.passed is True
    assert result.failed_gate is None
    assert result.fail_category is None
    assert result.overturn_signal is None
    assert result.retry_signal is None


def test_failed_result_has_gate_and_category():
    """AC-9：passed=False 时 failed_gate 和 fail_category 非 None。"""
    result = VerificationResult(
        passed=False,
        tier=1,
        failed_gate="static_check",
        fail_category="patch_error",
    )

    assert result.failed_gate is not None
    assert result.fail_category is not None


def test_details_always_dict():
    """AC-9：details 始终为 dict（即使空）。"""
    result = VerificationResult(passed=True, tier=1)
    assert isinstance(result.details, dict)


def test_tier_field_values():
    """AC-9：tier 取值为 1 或 2。"""
    r1 = VerificationResult(passed=True, tier=1)
    r2 = VerificationResult(passed=True, tier=2)
    assert r1.tier == 1
    assert r2.tier == 2


# ---------------------------------------------------------------------------
# AC-10: tier 非法 → ValueError
# ---------------------------------------------------------------------------
def test_invalid_tier_raises_value_error(verifier):
    """AC-10/Q5：tier 不在 {1,2} → ValueError。"""
    with pytest.raises(ValueError, match="tier must be 1 or 2"):
        verifier.verify(tier=3)

    with pytest.raises(ValueError, match="tier must be 1 or 2"):
        verifier.verify(tier=0)


# ---------------------------------------------------------------------------
# INV-2 守护
# ---------------------------------------------------------------------------
def test_class_has_no_merge_method():
    """INV-2：RegressionVerifier 类无 merge / merge_pr / auto_merge 方法。"""
    assert not hasattr(RegressionVerifier, "merge")
    assert not hasattr(RegressionVerifier, "merge_pr")
    assert not hasattr(RegressionVerifier, "auto_merge")


def test_available_operations_excludes_merge():
    """INV-2：available_operations() 不含 merge。"""
    ops = RegressionVerifier.available_operations()
    assert "merge" not in ops
    assert "merge_pr" not in ops
    assert "auto_merge" not in ops


# ---------------------------------------------------------------------------
# 补充：strategy_chain 未知策略
# ---------------------------------------------------------------------------
def test_next_strategy_unknown_returns_first(verifier):
    """当前策略不在链中 → 返回第一个策略。"""
    assert verifier._next_strategy("unknown_strategy", 0) == "template"


# ---------------------------------------------------------------------------
# 补充：retry_signal error_info 含 stdout/stderr 摘要
# ---------------------------------------------------------------------------
@patch("agent.fix.regression_verifier.run_reproduce")
@patch("agent.fix.regression_verifier.subprocess.run")
def test_retry_signal_error_info_has_summary(
    mock_subproc,
    mock_repro,
    verifier,
    mock_client,
):
    """AC-5：retry_signal 的 error_info 含 stdout_summary。"""
    mock_repro.return_value = []
    mock_subproc.return_value = _make_completed_proc(
        returncode=1,
        stdout="test output",
        stderr="AssertionError at line 42",
    )

    result = verifier.verify(
        tier=1,
        client=mock_client,
        reproduce_script=[],
        baseline_outcomes=[],
        attempt_no=0,
    )

    assert result.retry_signal is not None
    assert "stdout_summary" in result.retry_signal["error_info"]
    assert "stderr" in result.retry_signal["error_info"]
