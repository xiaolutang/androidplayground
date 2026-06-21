"""GapDiagnoser 单元测试（R001-BB010）。

覆盖四类缺口识别 + 写 CapabilityGap(waiting) 的 14 个测试场景：

1. information 缺口（ism_insufficient）
2. facility 缺口（emulator_unavailable）
3. facility 缺口（adb_offline）
4. pattern 缺口（kb_pattern_miss）
5. model 缺口（llm_failure）
6. model 缺口（llm_timeout）
7. step_exhausted → coverage 兜底
8. 未知 trigger_source → 默认 information + warning
9. 写入 CapabilityGap(status=waiting) → gap_store.create + transition 被调
10. gap_store=None → ValueError
11. gap_store.create 异常 → diagnosed=False 不崩
12. linked_bug_ids 含 bug_report_id
13. suggested_action 非空（每类缺口有对应建议）
14. description 人类可读（含 trigger_source 上下文）

使用 FakeGapStore（in-memory）避免真实 DB 依赖。
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from agent.gap_mgmt.gap_diagnoser import GapDiagnoser
from agent.schemas.capability_gap import CapabilityGapStatus


# ---------------------------------------------------------------------------
# FakeGapStore（in-memory，避免 Testcontainers / DB 依赖）
# ---------------------------------------------------------------------------
class FakeGapStore:
    """in-memory GapStore 双。

    模拟 GapStore.create（强制 IDENTIFIED）+ transition（IDENTIFIED->WAITING 合法）。
    支持 inject_failure 在 create/transition 抛异常，验证降级行为。
    """

    def __init__(
        self,
        *,
        create_failure: Exception | None = None,
        transition_failure: Exception | None = None,
    ) -> None:
        self.created: list[dict] = []
        self.transitions: list[tuple[str, str, dict]] = []
        self._status: dict[str, str] = {}
        self._create_failure = create_failure
        self._transition_failure = transition_failure

    def create(self, gap_data: dict[str, Any]) -> Any:
        if self._create_failure is not None:
            raise self._create_failure
        # 模拟 GapStore.create：强制 IDENTIFIED
        record = {**gap_data, "status": CapabilityGapStatus.IDENTIFIED.value}
        self.created.append(record)
        self._status[gap_data["id"]] = CapabilityGapStatus.IDENTIFIED.value
        return MagicMock(id=gap_data["id"], status=CapabilityGapStatus.IDENTIFIED.value)

    def transition(
        self,
        gap_id: str,
        to_status: CapabilityGapStatus,
        *,
        reason: str = "",
    ) -> Any:
        if self._transition_failure is not None:
            raise self._transition_failure
        self.transitions.append((gap_id, to_status.value, {"reason": reason}))
        self._status[gap_id] = to_status.value
        return MagicMock(id=gap_id, status=to_status.value)


# ---------------------------------------------------------------------------
# 测试 1-6: 四类缺口分类
# ---------------------------------------------------------------------------
class TestGapClassification:
    """四类缺口识别（gap_type + waiting_reason）。"""

    @pytest.fixture
    def diagnoser(self) -> GapDiagnoser:
        return GapDiagnoser(gap_store=FakeGapStore())

    def test_information_gap_ism_insufficient(self, diagnoser: GapDiagnoser) -> None:
        """测试 1: ism_insufficient → information / information_missing。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-001",
            trigger_context={
                "trigger_source": "ism_insufficient",
                "ism_result": {"level": "insufficient", "score": 0.3},
            },
        )
        assert result.gap_type == "information"
        assert result.waiting_reason == "information_missing"

    def test_facility_gap_emulator_unavailable(self, diagnoser: GapDiagnoser) -> None:
        """测试 2: emulator_unavailable → facility。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-002",
            trigger_context={
                "trigger_source": "emulator_unavailable",
                "facility_error": "no available emulator",
            },
        )
        assert result.gap_type == "facility"
        assert result.waiting_reason == "facility_unavailable"

    def test_facility_gap_adb_offline(self, diagnoser: GapDiagnoser) -> None:
        """测试 3: adb_offline → facility。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-003",
            trigger_context={
                "trigger_source": "adb_offline",
                "facility_error": "device offline",
            },
        )
        assert result.gap_type == "facility"
        assert result.waiting_reason == "facility_unavailable"

    def test_pattern_gap_kb_pattern_miss(self, diagnoser: GapDiagnoser) -> None:
        """测试 4: kb_pattern_miss → pattern / pattern_not_learned。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-004",
            trigger_context={
                "trigger_source": "kb_pattern_miss",
                "kb_retrieval_result": {"degraded": False, "hits": 0},
            },
        )
        assert result.gap_type == "pattern"
        assert result.waiting_reason == "pattern_not_learned"

    def test_model_gap_llm_failure(self, diagnoser: GapDiagnoser) -> None:
        """测试 5: llm_failure → model。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-005",
            trigger_context={
                "trigger_source": "llm_failure",
                "llm_error": "HTTP 500 from provider",
            },
        )
        assert result.gap_type == "model"
        assert result.waiting_reason == "model_unable"

    def test_model_gap_llm_timeout(self, diagnoser: GapDiagnoser) -> None:
        """测试 6: llm_timeout → model。"""
        result = diagnoser.diagnose(
            bug_report_id="bug-006",
            trigger_context={
                "trigger_source": "llm_timeout",
                "llm_error": "request timed out after 30s",
            },
        )
        assert result.gap_type == "model"
        assert result.waiting_reason == "model_unable"


# ---------------------------------------------------------------------------
# 测试 7-8: 边界场景
# ---------------------------------------------------------------------------
class TestEdgeCases:
    """边界场景：step_exhausted / 未知 trigger_source。"""

    def test_step_exhausted_coverage_fallback(self) -> None:
        """测试 7: step_exhausted → coverage（兜底，与 HypothesisEngine 口径一致）。"""
        diagnoser = GapDiagnoser(gap_store=FakeGapStore())
        result = diagnoser.diagnose(
            bug_report_id="bug-007",
            trigger_context={
                "trigger_source": "step_exhausted",
                "hypothesis_id": "hyp-123",
            },
        )
        assert result.gap_type == "coverage"
        assert result.waiting_reason == "budget_exhausted"

    def test_unknown_trigger_source_defaults_information(self) -> None:
        """测试 8: 未知 trigger_source → 默认 information + warning。"""
        diagnoser = GapDiagnoser(gap_store=FakeGapStore())
        result = diagnoser.diagnose(
            bug_report_id="bug-008",
            trigger_context={"trigger_source": "totally_unknown_source"},
        )
        assert result.gap_type == "information"
        assert result.waiting_reason == "information_missing"


# ---------------------------------------------------------------------------
# 测试 9-12: 写入行为 / 错误处理
# ---------------------------------------------------------------------------
class TestWriteAndErrorHandling:
    """写入 CapabilityGap(waiting) + 错误处理。"""

    def test_writes_capability_gap_waiting(self) -> None:
        """测试 9: create + transition(WAITING) 均被调。"""
        fake_store = FakeGapStore()
        diagnoser = GapDiagnoser(gap_store=fake_store)

        result = diagnoser.diagnose(
            bug_report_id="bug-009",
            trigger_context={"trigger_source": "ism_insufficient"},
        )

        assert result.diagnosed is True
        assert len(fake_store.created) == 1
        # transition 到 WAITING 必须被调用
        assert len(fake_store.transitions) == 1
        gap_id, to_status, _ = fake_store.transitions[0]
        assert to_status == CapabilityGapStatus.WAITING.value
        assert gap_id == result.gap_id

    def test_gap_store_none_raises_value_error(self) -> None:
        """测试 10: gap_store=None → ValueError。"""
        with pytest.raises(ValueError, match="gap_store is required"):
            GapDiagnoser(gap_store=None)

    def test_gap_store_create_exception_no_crash(self) -> None:
        """测试 11: gap_store.create 异常 → diagnosed=False 不崩。"""
        failing_store = FakeGapStore(
            create_failure=RuntimeError("DB connection lost"),
        )
        diagnoser = GapDiagnoser(gap_store=failing_store)

        result = diagnoser.diagnose(
            bug_report_id="bug-011",
            trigger_context={"trigger_source": "ism_insufficient"},
        )

        assert result.diagnosed is False
        assert result.gap_id is None
        # 分类信息仍应填充（即使写入失败）
        assert result.gap_type == "information"

    def test_linked_bug_ids_contains_bug_report_id(self) -> None:
        """测试 12: linked_bug_ids 含 bug_report_id。"""
        diagnoser = GapDiagnoser(gap_store=FakeGapStore())
        result = diagnoser.diagnose(
            bug_report_id="bug-012",
            trigger_context={"trigger_source": "emulator_unavailable"},
        )
        assert result.diagnosed is True
        assert "bug-012" in result.linked_bug_ids


# ---------------------------------------------------------------------------
# 测试 13-14: suggested_action / description
# ---------------------------------------------------------------------------
class TestActionAndDescription:
    """suggested_action 非空 / description 含上下文。"""

    @pytest.mark.parametrize(
        "trigger_source, expected_gap_type",
        [
            ("ism_insufficient", "information"),
            ("emulator_unavailable", "facility"),
            ("adb_offline", "facility"),
            ("kb_pattern_miss", "pattern"),
            ("llm_failure", "model"),
            ("llm_timeout", "model"),
            ("step_exhausted", "coverage"),
        ],
    )
    def test_suggested_action_non_empty(
        self,
        trigger_source: str,
        expected_gap_type: str,
    ) -> None:
        """测试 13: 每类缺口 suggested_action 非空。"""
        diagnoser = GapDiagnoser(gap_store=FakeGapStore())
        result = diagnoser.diagnose(
            bug_report_id=f"bug-{trigger_source}",
            trigger_context={"trigger_source": trigger_source},
        )
        assert result.gap_type == expected_gap_type
        assert result.suggested_action, (
            f"suggested_action should be non-empty for {trigger_source}"
        )
        assert isinstance(result.suggested_action, str)

    def test_description_human_readable_with_trigger_source(self) -> None:
        """测试 14: description 人类可读且含 trigger_source 上下文。"""
        diagnoser = GapDiagnoser(gap_store=FakeGapStore())
        result = diagnoser.diagnose(
            bug_report_id="bug-014",
            trigger_context={
                "trigger_source": "ism_insufficient",
                "ism_result": {"level": "insufficient"},
                "facility_error": "n/a",
            },
            symptom_type="crash",
        )
        assert result.description
        assert "bug-014" in result.description
        assert "ism_insufficient" in result.description
        # symptom_type 应被纳入
        assert "crash" in result.description
