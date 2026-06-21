"""回归验证器（R001-BB008）。

依据：
- Sprint Contract R001-BB008（mode: negotiated，10 AC）
- backend 5.1 Tier1 自动修复主链（第 746-778 行）
- INV-2（architecture 第 40-46 行）：按 Tier 分级回归 + 人在合并闸门
- BF002 run_reproduce + StepOutcome（reproduce_runner.py）
- BB004 overturn_root_cause 接口（hypothesis_engine.py）
- INF02 Settings.FIX_RETRY_MAX

设计要点：
1. **Tier1 三关全过才提普通 PR**：复现序列回归 → 既有测试 → 静态检查（串行短路）。
2. **Tier2 轻量验证 + is_draft**：静态检查 + 测试子集（不跑复现序列回归）。
3. **fail 分类**：
   - root_cause_error：复现序列回归关 fail（原 bug 信号仍出现）→ overturn_signal（触发 BB004 根因回退）。
   - patch_error：复现序列通过但其他关 fail / Tier2 任意关 fail → retry_signal（触发 BB007 重试）。
4. **INV-2 守护**：本类不提供 merge 方法，不自主合并。
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.infra.config import settings
from agent.reproduce.reproduce_runner import (
    ReproduceConfig,
    StepOutcome,
    run_reproduce,
)

logger = logging.getLogger(__name__)

__all__ = [
    "VerificationResult",
    "RegressionVerifier",
]

# 默认静态检查命令（Python 项目）
_DEFAULT_STATIC_CHECK_COMMANDS: list[str] = ["ruff check .", "mypy ."]

# 默认测试命令
_DEFAULT_TEST_COMMAND = "pytest tests/"
_DEFAULT_TIER2_TEST_SUBSET_COMMAND = "pytest tests/unit/"

# 默认超时（秒）
_DEFAULT_STATIC_CHECK_TIMEOUT = 60
_DEFAULT_TEST_TIMEOUT = 300

# 策略链（patch_error 时建议下一策略）
_STRATEGY_CHAIN: list[str] = ["template", "llm", "history_calibration"]

# bug 信号 severity 集合（crash / error 视为 bug 信号）
_BUG_SEVERITIES = frozenset({"crash", "error"})


@dataclass
class VerificationResult:
    """回归验证结果。

    Attributes:
        passed: 是否通过（Tier1 三关全过 / Tier2 轻量全过）。
        tier: 1 或 2（由调用方传入，本任务不重算）。
        failed_gate: 失败关卡名（"repro_regression" / "existing_tests" /
            "static_check" / "tier2_test_subset" / None）。
        fail_category: 失败分类（"root_cause_error" / "patch_error" / None）。
        details: 各关详细结果（per-gate pass/fail + error info + stdout/stderr 摘要）。
        overturn_signal: root_cause_error 时携带的推翻信号（供 BB004 overturn_root_cause）。
        retry_signal: patch_error 时携带的重试信号（供 BB007 换策略）。
    """

    passed: bool
    tier: int
    failed_gate: Optional[str] = None
    fail_category: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    overturn_signal: Optional[dict[str, Any]] = None
    retry_signal: Optional[dict[str, Any]] = None


class RegressionVerifier:
    """回归验证器：三关验证 + Tier 分级执行 + fail 分类。

    Tier1 三关全过才提普通 PR；Tier2 轻量验证 + is_draft。
    fail 区分 root_cause_error（→BB004 根因回退）vs patch_error（→BB007 重试）。

    INV-2 守护：**禁止自主合并**（merge），合并由人在闸门批准后执行。
    本类不提供 merge / merge_pr / auto_merge 方法。
    """

    def __init__(
        self,
        *,
        static_check_commands: Optional[list[str]] = None,
        test_command: Optional[str] = None,
        tier2_test_subset_command: Optional[str] = None,
        static_check_timeout: int = _DEFAULT_STATIC_CHECK_TIMEOUT,
        test_timeout: int = _DEFAULT_TEST_TIMEOUT,
        fix_retry_max: Optional[int] = None,
    ) -> None:
        """初始化回归验证器。

        Args:
            static_check_commands: 静态检查命令列表（默认 ruff + mypy）。
            test_command: Tier1 全量测试命令（默认 pytest tests/）。
            tier2_test_subset_command: Tier2 测试子集命令（默认 pytest tests/unit/）。
            static_check_timeout: 静态检查单条超时秒数。
            test_timeout: 测试命令超时秒数。
            fix_retry_max: patch 重试上限（None → 从 settings.FIX_RETRY_MAX 读）。
        """
        self._static_check_commands = static_check_commands or list(
            _DEFAULT_STATIC_CHECK_COMMANDS
        )
        self._test_command = test_command or _DEFAULT_TEST_COMMAND
        self._tier2_test_subset_command = (
            tier2_test_subset_command or _DEFAULT_TIER2_TEST_SUBSET_COMMAND
        )
        self._static_check_timeout = static_check_timeout
        self._test_timeout = test_timeout
        self._fix_retry_max = (
            fix_retry_max if fix_retry_max is not None else settings.FIX_RETRY_MAX
        )

    # ------------------------------------------------------------------
    # INV-2 守护
    # ------------------------------------------------------------------
    @classmethod
    def available_operations(cls) -> list[str]:
        """返回本类支持的操作列表（**不含 merge**）。

        供调用方自检：合并由人工在 PR 平台批准后执行（INV-2）。

        Returns:
            ["verify"]
        """
        return ["verify"]

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def verify(
        self,
        *,
        tier: int,
        client: Any = None,
        reproduce_script: Optional[list[dict]] = None,
        baseline_outcomes: Optional[list[StepOutcome]] = None,
        device_id: Optional[str] = None,
        reproduce_config: Optional[ReproduceConfig] = None,
        signal_collector: Optional[Callable] = None,
        attempt_no: int = 0,
        current_strategy: Optional[str] = None,
    ) -> VerificationResult:
        """执行回归验证。

        Args:
            tier: 1（三关全量）或 2（轻量验证）。
            client: ADBClient（Tier1 复现序列回归需要）。
            reproduce_script: 原始复现脚本（Tier1 复现序列回归需要）。
            baseline_outcomes: 修复前的 StepOutcome 列表（Tier1 复现序列回归比对基准）。
            device_id: 模拟器设备 id。
            reproduce_config: 复现配置（可选）。
            signal_collector: 信号采集器（可选注入）。
            attempt_no: 当前修复尝试号（用于 retry_signal 的 should_retry 判定）。
            current_strategy: 当前修复策略（用于推荐下一策略）。

        Returns:
            VerificationResult。

        Raises:
            ValueError: tier 不在 {1, 2}。
        """
        if tier not in (1, 2):
            raise ValueError(
                f"tier must be 1 or 2, got {tier!r}"
            )

        details: dict[str, Any] = {}

        if tier == 1:
            return self._verify_tier1(
                details=details,
                client=client,
                reproduce_script=reproduce_script,
                baseline_outcomes=baseline_outcomes,
                device_id=device_id,
                reproduce_config=reproduce_config,
                signal_collector=signal_collector,
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
        return self._verify_tier2(
            details=details,
            attempt_no=attempt_no,
            current_strategy=current_strategy,
        )

    # ------------------------------------------------------------------
    # Tier1 三关全量
    # ------------------------------------------------------------------
    def _verify_tier1(
        self,
        *,
        details: dict[str, Any],
        client: Any,
        reproduce_script: Optional[list[dict]],
        baseline_outcomes: Optional[list[StepOutcome]],
        device_id: Optional[str],
        reproduce_config: Optional[ReproduceConfig],
        signal_collector: Optional[Callable],
        attempt_no: int,
        current_strategy: Optional[str],
    ) -> VerificationResult:
        """Tier1 三关：复现序列回归 → 既有测试 → 静态检查（串行短路）。"""

        # 第一关：复现序列回归
        repro_passed, repro_fail_cat, repro_details = self._verify_repro_regression(
            client=client,
            script=reproduce_script or [],
            baseline_outcomes=baseline_outcomes or [],
            device_id=device_id,
            reproduce_config=reproduce_config,
            signal_collector=signal_collector,
        )
        details["repro_regression"] = repro_details

        if not repro_passed:
            fail_cat = repro_fail_cat or "patch_error"
            failed_gate = "repro_regression"
            if fail_cat == "root_cause_error":
                # root_cause_error → overturn_signal
                evidence = repro_details.get("evidence", {})
                overturn_signal = self._build_overturn_signal(
                    reason=repro_details.get(
                        "reason",
                        "repro regression failed: original bug signal still present",
                    ),
                    baseline_signal=evidence.get("baseline_signal", {}),
                    new_signal=evidence.get("new_signal", {}),
                    matching_step_no=evidence.get("matching_step_no", 0),
                )
                return VerificationResult(
                    passed=False,
                    tier=1,
                    failed_gate=failed_gate,
                    fail_category=fail_cat,
                    details=details,
                    overturn_signal=overturn_signal,
                    retry_signal=None,
                )
            # patch_error（run_reproduce 异常降级）→ retry_signal
            retry_signal = self._build_retry_signal(
                failed_gate=failed_gate,
                error_info=repro_details.get("error_info", {}),
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
            return VerificationResult(
                passed=False,
                tier=1,
                failed_gate=failed_gate,
                fail_category=fail_cat,
                details=details,
                overturn_signal=None,
                retry_signal=retry_signal,
            )

        # 第二关：既有测试
        test_passed, test_details = self._verify_existing_tests()
        details["existing_tests"] = test_details
        if not test_passed:
            retry_signal = self._build_retry_signal(
                failed_gate="existing_tests",
                error_info=test_details.get("error_info", {}),
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
            return VerificationResult(
                passed=False,
                tier=1,
                failed_gate="existing_tests",
                fail_category="patch_error",
                details=details,
                overturn_signal=None,
                retry_signal=retry_signal,
            )

        # 第三关：静态检查
        static_passed, static_details = self._verify_static_check()
        details["static_check"] = static_details
        if not static_passed:
            retry_signal = self._build_retry_signal(
                failed_gate="static_check",
                error_info=static_details.get("error_info", {}),
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
            return VerificationResult(
                passed=False,
                tier=1,
                failed_gate="static_check",
                fail_category="patch_error",
                details=details,
                overturn_signal=None,
                retry_signal=retry_signal,
            )

        # 三关全过
        return VerificationResult(
            passed=True,
            tier=1,
            failed_gate=None,
            fail_category=None,
            details=details,
            overturn_signal=None,
            retry_signal=None,
        )

    # ------------------------------------------------------------------
    # Tier2 轻量验证
    # ------------------------------------------------------------------
    def _verify_tier2(
        self,
        *,
        details: dict[str, Any],
        attempt_no: int,
        current_strategy: Optional[str],
    ) -> VerificationResult:
        """Tier2 轻量验证：静态检查 + 测试子集（不跑复现序列回归）。"""

        # 静态检查
        static_passed, static_details = self._verify_static_check()
        details["static_check"] = static_details
        if not static_passed:
            retry_signal = self._build_retry_signal(
                failed_gate="static_check",
                error_info=static_details.get("error_info", {}),
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
            return VerificationResult(
                passed=False,
                tier=2,
                failed_gate="static_check",
                fail_category="patch_error",
                details=details,
                overturn_signal=None,
                retry_signal=retry_signal,
            )

        # 测试子集
        subset_passed, subset_details = self._verify_tier2_subset()
        details["tier2_test_subset"] = subset_details
        if not subset_passed:
            retry_signal = self._build_retry_signal(
                failed_gate="tier2_test_subset",
                error_info=subset_details.get("error_info", {}),
                attempt_no=attempt_no,
                current_strategy=current_strategy,
            )
            return VerificationResult(
                passed=False,
                tier=2,
                failed_gate="tier2_test_subset",
                fail_category="patch_error",
                details=details,
                overturn_signal=None,
                retry_signal=retry_signal,
            )

        # 轻量全过
        return VerificationResult(
            passed=True,
            tier=2,
            failed_gate=None,
            fail_category=None,
            details=details,
            overturn_signal=None,
            retry_signal=None,
        )

    # ------------------------------------------------------------------
    # 第一关：复现序列回归
    # ------------------------------------------------------------------
    def _verify_repro_regression(
        self,
        *,
        client: Any,
        script: list[dict],
        baseline_outcomes: list[StepOutcome],
        device_id: Optional[str] = None,
        reproduce_config: Optional[ReproduceConfig] = None,
        signal_collector: Optional[Callable] = None,
    ) -> tuple[bool, str, dict]:
        """复现序列回归关。

        Returns:
            (passed, fail_category, details)。
            fail_category: "root_cause_error" / "patch_error" / ""（通过时空串）。
        """
        start = time.time()

        # baseline 为空 → 无基准可比，降级为 pass
        if not baseline_outcomes:
            return (
                True,
                "",
                {
                    "passed": True,
                    "reason": "no baseline outcomes, skip repro regression",
                    "duration_ms": int((time.time() - start) * 1000),
                },
            )

        # 调 run_reproduce 重跑
        try:
            new_outcomes = run_reproduce(
                client,
                script,
                config=reproduce_config,
                device_id=device_id,
                signal_collector=signal_collector,
            )
        except Exception as e:
            # 执行异常 → patch_error 降级（不确定根因错）
            return (
                False,
                "patch_error",
                {
                    "passed": False,
                    "error": f"{type(e).__name__}: {e}",
                    "error_info": {
                        "exception_type": type(e).__name__,
                        "exception_message": str(e),
                    },
                    "duration_ms": int((time.time() - start) * 1000),
                },
            )

        # 信号比对
        bug_still_present, evidence = self._compare_signals(
            baseline_outcomes, new_outcomes
        )

        duration_ms = int((time.time() - start) * 1000)

        if bug_still_present:
            reason = (
                f"repro regression failed: original bug signal still present "
                f"at step {evidence.get('matching_step_no', 0)}"
            )
            return (
                False,
                "root_cause_error",
                {
                    "passed": False,
                    "reason": reason,
                    "evidence": evidence,
                    "duration_ms": duration_ms,
                },
            )

        return (
            True,
            "",
            {
                "passed": True,
                "new_outcomes_count": len(new_outcomes),
                "duration_ms": duration_ms,
            },
        )

    # ------------------------------------------------------------------
    # 第二关：既有测试
    # ------------------------------------------------------------------
    def _verify_existing_tests(self) -> tuple[bool, dict]:
        """既有测试关。返回 (passed, details)。"""
        return self._run_command_gate(
            command=self._test_command,
            timeout=self._test_timeout,
            gate_name="existing_tests",
        )

    # ------------------------------------------------------------------
    # 第三关：静态检查
    # ------------------------------------------------------------------
    def _verify_static_check(self) -> tuple[bool, dict]:
        """静态检查关。逐条执行命令，任一失败即 fail。"""
        commands_results: list[dict[str, Any]] = []
        start = time.time()

        for cmd in self._static_check_commands:
            result = self._run_single_command(
                cmd, timeout=self._static_check_timeout
            )
            commands_results.append(result)
            if not result["passed"]:
                return (
                    False,
                    {
                        "passed": False,
                        "commands": commands_results,
                        "error_info": {
                            "command": cmd,
                            "exit_code": result.get("exit_code"),
                            "stderr": result.get("stderr", ""),
                            "stdout_summary": result.get("stdout", "")[:500],
                        },
                        "duration_ms": int((time.time() - start) * 1000),
                    },
                )

        return (
            True,
            {
                "passed": True,
                "commands": commands_results,
                "duration_ms": int((time.time() - start) * 1000),
            },
        )

    # ------------------------------------------------------------------
    # Tier2 测试子集
    # ------------------------------------------------------------------
    def _verify_tier2_subset(self) -> tuple[bool, dict]:
        """Tier2 测试子集关。返回 (passed, details)。"""
        return self._run_command_gate(
            command=self._tier2_test_subset_command,
            timeout=self._test_timeout,
            gate_name="tier2_test_subset",
        )

    # ------------------------------------------------------------------
    # 通用：执行单条 shell 命令关卡
    # ------------------------------------------------------------------
    def _run_command_gate(
        self,
        *,
        command: str,
        timeout: int,
        gate_name: str,
    ) -> tuple[bool, dict]:
        """执行单条命令作为关卡。返回 (passed, details)。"""
        start = time.time()
        result = self._run_single_command(command, timeout=timeout)
        result["gate_name"] = gate_name
        result["duration_ms"] = int((time.time() - start) * 1000)

        if not result["passed"]:
            result["error_info"] = {
                "command": command,
                "exit_code": result.get("exit_code"),
                "stderr": result.get("stderr", ""),
                "stdout_summary": result.get("stdout", "")[:500],
            }

        return (result["passed"], result)

    def _run_single_command(
        self,
        command: str,
        *,
        timeout: int,
    ) -> dict[str, Any]:
        """执行单条 shell 命令，返回结果 dict。"""
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "passed": proc.returncode == 0,
                "command": command,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "command": command,
                "timeout": True,
                "exit_code": None,
                "stdout": "",
                "stderr": f"timeout after {timeout}s",
            }
        except Exception as e:
            return {
                "passed": False,
                "command": command,
                "error": f"{type(e).__name__}: {e}",
                "exit_code": None,
                "stdout": "",
                "stderr": str(e),
            }

    # ------------------------------------------------------------------
    # 信号比对
    # ------------------------------------------------------------------
    def _compare_signals(
        self,
        baseline_outcomes: list[StepOutcome],
        new_outcomes: list[StepOutcome],
    ) -> tuple[bool, Optional[dict]]:
        """比对 baseline 与新执行的信号。

        Returns:
            (bug_still_present, evidence)。
            bug_still_present=True 表示原 bug 信号仍出现（root_cause_error）。
        """
        # 构建 new_outcomes 的 step_no → outcome 索引
        new_by_step: dict[int, StepOutcome] = {
            o.step_no: o for o in new_outcomes
        }

        for base_o in baseline_outcomes:
            base_signal = base_o.actual_signal
            # 只关注 baseline 中有 bug 信号的 step
            if base_signal is None:
                continue
            base_severity = (base_signal.get("severity") or "").lower()
            if base_severity not in _BUG_SEVERITIES:
                continue

            # 找新执行中同 step_no 的 outcome
            new_o = new_by_step.get(base_o.step_no)
            if new_o is None:
                # 同位置缺失 → 视为 bug 信号消失（通过）
                continue

            new_signal = new_o.actual_signal
            if new_signal is None:
                # 信号消失 → 通过
                continue

            new_severity = (new_signal.get("severity") or "").lower()
            if new_severity not in _BUG_SEVERITIES:
                # severity 降级 → 通过
                continue

            # signal_type + pattern 匹配 → bug 仍存在
            base_type = base_signal.get("signal_type")
            new_type = new_signal.get("signal_type")
            base_pattern = base_signal.get("pattern")
            new_pattern = new_signal.get("pattern")

            type_match = base_type == new_type
            pattern_match = self._pattern_match(base_pattern, new_pattern)

            if type_match and pattern_match:
                return (
                    True,
                    {
                        "matching_step_no": base_o.step_no,
                        "baseline_signal": {
                            "signal_type": base_type,
                            "severity": base_severity,
                            "pattern": base_pattern,
                        },
                        "new_signal": {
                            "signal_type": new_type,
                            "severity": new_severity,
                            "pattern": new_pattern,
                        },
                    },
                )

        return (False, None)

    @staticmethod
    def _pattern_match(
        base_pattern: Any, new_pattern: Any
    ) -> bool:
        """比对两个 pattern 是否匹配。

        pattern 为 None → 视为匹配（宽松）。
        pattern 为字符串 → 子串匹配。
        pattern 为 dict → 所有值子串匹配。
        """
        if base_pattern is None or new_pattern is None:
            return True
        if isinstance(base_pattern, str) and isinstance(new_pattern, str):
            return base_pattern.lower() in new_pattern.lower()
        if isinstance(base_pattern, dict) and isinstance(new_pattern, dict):
            for k, v in base_pattern.items():
                nv = new_pattern.get(k)
                if nv is None:
                    continue
                if isinstance(v, str) and isinstance(nv, str):
                    if v.lower() not in nv.lower():
                        return False
            return True
        return True

    # ------------------------------------------------------------------
    # 构建 overturn_signal（root_cause_error → BB004）
    # ------------------------------------------------------------------
    def _build_overturn_signal(
        self,
        reason: str,
        baseline_signal: dict,
        new_signal: dict,
        matching_step_no: int,
    ) -> dict[str, Any]:
        """构建 root_cause_error 的推翻信号（供 BB004 overturn_root_cause）。"""
        return {
            "overturning_stage": "regression",
            "reason": reason,
            "overturning_signal": {
                "gate": "repro_regression",
                "matching_step_no": matching_step_no,
                "baseline_signal": baseline_signal,
                "new_signal": new_signal,
            },
        }

    # ------------------------------------------------------------------
    # 构建 retry_signal（patch_error → BB007）
    # ------------------------------------------------------------------
    def _build_retry_signal(
        self,
        failed_gate: str,
        error_info: dict,
        attempt_no: int,
        current_strategy: Optional[str] = None,
    ) -> dict[str, Any]:
        """构建 patch_error 的重试信号（供 BB007 换策略）。"""
        next_strategy = self._next_strategy(current_strategy, attempt_no)
        should_retry = attempt_no < self._fix_retry_max
        return {
            "failed_gate": failed_gate,
            "error_info": error_info,
            "attempt_no": attempt_no,
            "next_strategy": next_strategy,
            "should_retry": should_retry,
        }

    # ------------------------------------------------------------------
    # 策略链推进
    # ------------------------------------------------------------------
    @staticmethod
    def _next_strategy(
        current_strategy: Optional[str], attempt_no: int
    ) -> str:
        """根据当前策略推荐下一策略。

        推进顺序：template → llm → history_calibration（末端钉住）。
        """
        if current_strategy is None:
            return _STRATEGY_CHAIN[0]
        try:
            idx = _STRATEGY_CHAIN.index(current_strategy)
        except ValueError:
            return _STRATEGY_CHAIN[0]
        next_idx = min(idx + 1, len(_STRATEGY_CHAIN) - 1)
        return _STRATEGY_CHAIN[next_idx]
