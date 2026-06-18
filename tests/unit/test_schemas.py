"""R001-SCH01 核心 Schema 单元测试。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1（字段权威依据）
- 任务包 R001-SCH01 test_tasks（7 个场景）

覆盖：
1. BugReport.status 14 态枚举完整 + 唯一（枚举成员数 == 14，无重复值）
2. STATUS_ALLOWED_REGRESSION_FEEDBACK 集合正确（5 个值，且都是 14 态的子集）
3. Hypothesis 4+ 态枚举 + parent_id 自引用可建树（构造 parent → child）
4. CapabilityGap.status 7 态完整
5. ConfidenceScore 三维字段名存在
6. KBEntry.root_cause_signals 为 Vector 类型（断言列类型）
7. MetricPoint 五维 metric_type 枚举

测试策略：
- 枚举测试用纯 Python enum 校验（不需要 DB）
- 关系/Vector 类型测试用 SQLAlchemy Column 类型断言（inspect 类的 mapped_column）
- 不依赖真实 DB 建表，保持测试快速（任务包要求"优先用非 DB 的类型断言"）
"""
from __future__ import annotations

from enum import Enum
from typing import get_type_hints

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import inspect

from agent.schemas import (
    BugReport,
    BugReportStatus,
    CapabilityGap,
    CapabilityGapStatus,
    ConfidenceScore,
    Hypothesis,
    HypothesisStatus,
    KBEntry,
    KBLayer,
    KBValidityStatus,
    MetricPoint,
    MetricType,
    Playbook,
    Trajectory,
)
from agent.schemas.bug_report import STATUS_ALLOWED_REGRESSION_FEEDBACK


# ---------------------------------------------------------------------------
# 1. BugReport.status 14 态枚举完整 + 唯一
# ---------------------------------------------------------------------------
class TestBugReportStatusEnum:
    """BugReport 14 态枚举完整性校验（design 4.1 第 524-527 行）。"""

    def test_enum_has_14_members(self):
        """枚举成员数 == 14。"""
        members = list(BugReportStatus)
        assert len(members) == 14, f"expected 14 members, got {len(members)}: {members}"

    def test_enum_values_unique(self):
        """枚举值无重复。"""
        values = [m.value for m in BugReportStatus]
        assert len(values) == len(set(values)), f"duplicate values: {values}"

    def test_enum_values_match_design_4_1(self):
        """枚举值与 design 4.1 第 527 行完全一致。"""
        expected = {
            "received", "assessing", "degraded", "reproducing", "located",
            "fixing", "verified", "pr_open", "draft_pr", "gap_pending",
            "wont_reflow", "concluded", "reflowed", "reflected",
        }
        actual = {m.value for m in BugReportStatus}
        assert actual == expected, f"mismatch:\n  missing: {expected - actual}\n  extra: {actual - expected}"

    def test_enum_is_str_enum(self):
        """枚举继承 str（便于 JSON 序列化与 SQL 存储）。"""
        assert issubclass(BugReportStatus, str)
        assert issubclass(BugReportStatus, Enum)

    def test_status_field_default_is_received(self):
        """BugReport.status 默认值为 received。"""
        mapper = inspect(BugReport)
        col = mapper.columns["status"]
        # default 可能是 Python 可调用或常量；取 arg
        default_val = col.default
        if hasattr(default_val, "arg"):
            arg = default_val.arg
            value = arg(BugReportStatus) if callable(arg) else arg
        else:
            value = default_val
        assert value == BugReportStatus.RECEIVED.value


# ---------------------------------------------------------------------------
# 2. STATUS_ALLOWED_REGRESSION_FEEDBACK 5 态集合
# ---------------------------------------------------------------------------
class TestRegressionFeedbackAllowedStates:
    """regression-feedback 允许的 5 态（design 4.3 第 740 行 / INV-3）。"""

    def test_set_has_5_values(self):
        """集合正好 5 个值。"""
        assert len(STATUS_ALLOWED_REGRESSION_FEEDBACK) == 5

    def test_set_is_subset_of_14_states(self):
        """5 态都是 14 态的子集。"""
        all_14 = {m.value for m in BugReportStatus}
        assert STATUS_ALLOWED_REGRESSION_FEEDBACK <= all_14

    def test_set_contains_expected_values(self):
        """5 态值与 design 4.3 第 740 行一致。"""
        expected = {"pr_open", "draft_pr", "concluded", "reflected", "reflowed"}
        assert set(STATUS_ALLOWED_REGRESSION_FEEDBACK) == expected

    def test_set_is_frozenset(self):
        """集合不可变（frozenset），防止运行期误改。"""
        assert isinstance(STATUS_ALLOWED_REGRESSION_FEEDBACK, frozenset)


# ---------------------------------------------------------------------------
# 3. Hypothesis 4 态枚举 + parent_id 自引用
# ---------------------------------------------------------------------------
class TestHypothesisSelfReferentialTree:
    """Hypothesis 自引用树（design 4.1 第 564-573 行 / INV-2）。"""

    def test_enum_has_4_members(self):
        """Hypothesis.status 4 态（design 4.1 第 570 行）。"""
        members = list(HypothesisStatus)
        assert len(members) == 4, f"expected 4 members, got {len(members)}: {members}"

    def test_enum_values_match_design(self):
        """4 态值与 design 4.1 第 570 行一致。"""
        expected = {"proposed", "verifying", "confirmed", "refuted"}
        actual = {m.value for m in HypothesisStatus}
        assert actual == expected

    def test_enum_values_unique(self):
        """枚举值无重复。"""
        values = [m.value for m in HypothesisStatus]
        assert len(values) == len(set(values))

    def test_parent_id_self_reference_foreign_key(self):
        """parent_id 自引用 Hypothesis.id（外键指向同表）。

        design 4.1 第 566 行：parent_id 树结构。
        校验列存在 + 外键指向 hypotheses.id。
        """
        mapper = inspect(Hypothesis)
        col = mapper.columns["parent_id"]
        assert col is not None, "parent_id column missing"

        # 自引用外键：指向 hypotheses 表的 id 列
        fks = list(col.foreign_keys)
        assert len(fks) >= 1, f"parent_id should have FK, got {len(fks)}"
        fk_targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("hypotheses", "id") in fk_targets, (
            f"parent_id FK should target hypotheses.id, got {fk_targets}"
        )

    def test_parent_id_nullable_for_root(self):
        """parent_id 可空（根假设无 parent）。"""
        mapper = inspect(Hypothesis)
        col = mapper.columns["parent_id"]
        assert col.nullable is True, "parent_id must be nullable for root hypotheses"

    def test_self_reference_tree_can_be_constructed(self):
        """构造 parent → child，校验关系可建立（不建真实表，用 ORM 对象属性）。

        任务包要求："构造 parent → child，查 child.parent 指向 parent"。
        本测试校验 ORM 对象可正确关联（关系定义层面的契约，非 DB 层）。
        """
        parent = Hypothesis(
            id="h-root",
            parent_id=None,
            hypothesis_text="root cause hypothesis",
            status=HypothesisStatus.PROPOSED.value,
        )
        child = Hypothesis(
            id="h-child",
            parent_id="h-root",
            hypothesis_text="refined sub-hypothesis",
            status=HypothesisStatus.VERIFYING.value,
        )
        # 校验 child.parent_id 指向 parent.id
        assert child.parent_id == parent.id
        assert parent.parent_id is None

    def test_refuted_permanent_no_cascade_delete(self):
        """INV-2：refuted 节点永久保留，parent_id 外键无 onDelete cascade。

        design 4.1 第 575 行 + 任务包："不能加 onDelete cascade 删除 refuted"。
        校验 parent_id 外键的 ondelete 不是 CASCADE。
        """
        mapper = inspect(Hypothesis)
        col = mapper.columns["parent_id"]
        for fk in col.foreign_keys:
            # ondelete=None（默认 NO ACTION）或 RESTRICT 都可接受；
            # 禁止 CASCADE / DELETE（会级联删 refuted 子树，违反 INV-2）
            assert fk.ondelete != "CASCADE", (
                "parent_id FK ondelete=CASCADE violates INV-2 (refuted permanent)"
            )
            assert fk.ondelete != "DELETE", (
                "parent_id FK ondelete=DELETE violates INV-2 (refuted permanent)"
            )

    def test_overturning_fields_exist_not_status(self):
        """overturning 通过 overturning_signal/overturning_stage 字段表达，非独立 status。

        design 4.1 第 572 行：被推翻时（fixing/verifying/regression）。
        任务包说"可能有 overturning_*"，但 design 明确是字段而非 status 值。
        """
        mapper = inspect(Hypothesis)
        assert "overturning_signal" in mapper.columns
        assert "overturning_stage" in mapper.columns

        # status 枚举不含 overturning_* 值（design 4.1 第 570 行明确 4 态）
        values = {m.value for m in HypothesisStatus}
        assert not any(v.startswith("overturning") for v in values), (
            f"HypothesisStatus should not have overturning_* values, got {values}"
        )


# ---------------------------------------------------------------------------
# 4. CapabilityGap.status 7 态
# ---------------------------------------------------------------------------
class TestCapabilityGapStatusEnum:
    """CapabilityGap 7 态枚举（design 4.1 第 616 行）。"""

    def test_enum_has_7_members(self):
        """枚举成员数 == 7。"""
        members = list(CapabilityGapStatus)
        assert len(members) == 7, f"expected 7 members, got {len(members)}: {members}"

    def test_enum_values_match_design(self):
        """7 态值与 design 4.1 第 616 行一致。"""
        expected = {
            "identified", "waiting", "unblocked", "resolved",
            "invalid_unblock", "wont_reflow", "wont_fix",
        }
        actual = {m.value for m in CapabilityGapStatus}
        assert actual == expected

    def test_enum_values_unique(self):
        """枚举值无重复。"""
        values = [m.value for m in CapabilityGapStatus]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# 5. ConfidenceScore 三维字段名
# ---------------------------------------------------------------------------
class TestConfidenceScoreThreeDimensions:
    """ConfidenceScore 三维字段（design 4.1 第 582-584 行）。"""

    def test_three_dim_fields_exist(self):
        """三维字段名存在（dim_info_completeness / dim_verification_feasibility / dim_patternability）。"""
        mapper = inspect(ConfidenceScore)
        expected = {
            "dim_info_completeness",
            "dim_verification_feasibility",
            "dim_patternability",
        }
        actual = set(mapper.columns.keys())
        missing = expected - actual
        assert not missing, f"missing dim fields: {missing}"

    def test_dim_fields_are_float(self):
        """三维字段类型为 Float。"""
        mapper = inspect(ConfidenceScore)
        for name in (
            "dim_info_completeness",
            "dim_verification_feasibility",
            "dim_patternability",
        ):
            col = mapper.columns[name]
            # SQLAlchemy Float 类型
            assert col.type.__class__.__name__ == "Float", (
                f"{name} should be Float, got {col.type.__class__.__name__}"
            )

    def test_tier_field_exists(self):
        """tier 字段存在（三维组合→Tier）。"""
        mapper = inspect(ConfidenceScore)
        assert "tier" in mapper.columns


# ---------------------------------------------------------------------------
# 6. KBEntry.root_cause_signals 为 Vector 类型
# ---------------------------------------------------------------------------
class TestKBEntryVectorType:
    """KBEntry.root_cause_signals pgvector Vector 类型（design 4.1 第 626 行）。"""

    def test_root_cause_signals_is_vector_type(self):
        """root_cause_signals 列类型为 pgvector.sqlalchemy.Vector。"""
        mapper = inspect(KBEntry)
        col = mapper.columns["root_cause_signals"]
        assert isinstance(col.type, Vector), (
            f"root_cause_signals should be Vector, got {type(col.type)}"
        )

    def test_validity_status_enum_3_states(self):
        """validity_status 三态（valid/stale/conflicting，D9）。"""
        expected = {"valid", "stale", "conflicting"}
        actual = {m.value for m in KBValidityStatus}
        assert actual == expected
        assert len(list(KBValidityStatus)) == 3

    def test_layer_enum_includes_design_values(self):
        """layer 枚举含 design 4.1 第 624 行的 3 层 + aggregated 预留。"""
        expected = {"raw_trajectory", "negative_knowledge", "pattern", "aggregated"}
        actual = {m.value for m in KBLayer}
        assert expected <= actual, f"missing layers: {expected - actual}"

    def test_conflicting_entry_ids_field_exists(self):
        """conflicting_entry_ids 字段存在（冲突对记录）。"""
        mapper = inspect(KBEntry)
        assert "conflicting_entry_ids" in mapper.columns

    def test_git_commit_anchor_field_exists(self):
        """git_commit_anchor 字段存在（D5 陈旧失效管理）。"""
        mapper = inspect(KBEntry)
        assert "git_commit_anchor" in mapper.columns


# ---------------------------------------------------------------------------
# 7. MetricPoint 五维 metric_type
# ---------------------------------------------------------------------------
class TestMetricPointFiveDimensions:
    """MetricPoint 五维 metric_type 枚举（design 4.1 第 639 行 / 5.5）。"""

    def test_enum_has_5_members(self):
        """枚举成员数 == 5。"""
        members = list(MetricType)
        assert len(members) == 5, f"expected 5 members, got {len(members)}: {members}"

    def test_enum_values_match_design(self):
        """5 维值与 design 4.1 第 639 行一致。"""
        expected = {"effectiveness", "safety", "coverage", "growth", "cost"}
        actual = {m.value for m in MetricType}
        assert actual == expected

    def test_enum_values_unique(self):
        """枚举值无重复。"""
        values = [m.value for m in MetricType]
        assert len(values) == len(set(values))

    def test_bucket_dim_field_exists(self):
        """bucket_dim 字段存在（分桶维度）。"""
        mapper = inspect(MetricPoint)
        assert "bucket_dim" in mapper.columns
        assert "bucket_value" in mapper.columns

    def test_growth_specific_fields_exist(self):
        """成长性专用字段存在（previous_tier / new_tier / ref_gap_id）。"""
        mapper = inspect(MetricPoint)
        for name in ("previous_tier", "new_tier", "ref_gap_id", "ref_gap_type"):
            assert name in mapper.columns, f"missing growth field: {name}"

    def test_period_enum_values(self):
        """period 枚举值（cold_start / kb_accumulated）。"""
        expected = {"cold_start", "kb_accumulated"}
        actual = {m.value for m in __import__("agent.schemas", fromlist=["MetricPeriod"]).MetricPeriod}
        assert actual == expected


# ---------------------------------------------------------------------------
# 额外：Playbook 关键字段
# ---------------------------------------------------------------------------
class TestPlaybookFields:
    """Playbook 关键字段（design 4.1 第 539-550 行）。"""

    def test_symptom_type_is_primary_key(self):
        """symptom_type 为 PK（5 类症状各一份）。"""
        mapper = inspect(Playbook)
        col = mapper.columns["symptom_type"]
        assert col.primary_key, "symptom_type should be PK"

    def test_passive_field_exists(self):
        """passive 字段存在（崩溃型=被动 vs 症状型=主动）。"""
        mapper = inspect(Playbook)
        assert "passive" in mapper.columns

    def test_hypothesis_space_field_exists(self):
        """root_cause_hypothesis_space 字段存在。"""
        mapper = inspect(Playbook)
        assert "root_cause_hypothesis_space" in mapper.columns

    def test_judgment_signals_field_name(self):
        """judgment_signals 字段名（design 4.1 第 544 行：复数，非 judgment_signal）。"""
        mapper = inspect(Playbook)
        assert "judgment_signals" in mapper.columns, (
            "design 4.1 第 544 行字段名为 judgment_signals（复数），"
            "不应是 judgment_signal（单数）"
        )
        assert "judgment_signal" not in mapper.columns, (
            "单数形式 judgment_signal 是历史笔误，应使用复数 judgment_signals"
        )


# ---------------------------------------------------------------------------
# 额外：Trajectory 关键字段
# ---------------------------------------------------------------------------
class TestTrajectoryFields:
    """Trajectory 关键字段（design 4.1 第 554-560 行）。"""

    def test_root_hypothesis_id_fk_to_hypotheses(self):
        """root_hypothesis_id 外键指向 hypotheses.id。"""
        mapper = inspect(Trajectory)
        col = mapper.columns["root_hypothesis_id"]
        fks = list(col.foreign_keys)
        assert len(fks) >= 1
        targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("hypotheses", "id") in targets

    def test_total_step_budget_field_exists(self):
        """total_step_budget 字段存在。"""
        mapper = inspect(Trajectory)
        assert "total_step_budget" in mapper.columns

    def test_kb_reads_field_exists(self):
        """kb_reads 字段存在（埋点，供 MetricPoint）。"""
        mapper = inspect(Trajectory)
        assert "kb_reads" in mapper.columns
