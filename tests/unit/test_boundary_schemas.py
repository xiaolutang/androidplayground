"""R001-SCH02 边界协议 Schema 单元测试。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 边界协议 Schema（第 651-709 行）
- 任务包 R001-SCH02 test_tasks（五个边界 Schema 字段完整性 + 类型断言）

覆盖：
1. ReproStep 五字段（step_no/action/target_coords/screenshot_ref/actual_signal）+ 类型
2. Signal.signal_type 四值枚举 + pattern/severity/source_config 字段
3. Anchor 三字段 + visual_features 为 Vector 类型
4. DiagnosisReport.format 二值枚举 + capability_gaps 字段
5. ManualFixEntry 五字段（patch_diff/trajectory_id/root_cause_text/trigger_conditions/kb_pattern_id）

测试策略：
- 字段完整性：用 SQLAlchemy inspect 校验列存在
- 类型断言：校验列类型（JSON / String / Vector / FK 目标）
- 枚举完整性：纯 Python enum 校验（不需要 DB）
"""
from __future__ import annotations

from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import inspect

from agent.schemas.anchor import Anchor
from agent.schemas.diagnosis_report import DiagnosisFormat, DiagnosisReport
from agent.schemas.manual_fix_entry import ManualFixEntry
from agent.schemas.repro_step import ReproStep
from agent.schemas.signal import Signal, SignalSeverity, SignalType


# ---------------------------------------------------------------------------
# 1. ReproStep 五字段 + 类型
# ---------------------------------------------------------------------------
class TestReproStepFields:
    """ReproStep 字段完整性（design 4.1 第 667-677 行）。"""

    def test_required_five_fields_exist(self):
        """验收五字段全部存在：step_no/action/target_coords/screenshot_ref/actual_signal。"""
        mapper = inspect(ReproStep)
        cols = set(mapper.columns.keys())
        required = {
            "step_no",
            "action",
            "target_coords",
            "screenshot_ref",
            "actual_signal",
        }
        missing = required - cols
        assert not missing, f"missing ReproStep fields: {missing}"

    def test_step_no_is_integer(self):
        """step_no 为 Integer（design 第 672 行）。"""
        col = inspect(ReproStep).columns["step_no"]
        assert col.type.__class__.__name__ == "Integer", (
            f"step_no should be Integer, got {col.type.__class__.__name__}"
        )

    def test_action_is_string(self):
        """action 为 String（tap/swipe/input/back/wait）。"""
        col = inspect(ReproStep).columns["action"]
        assert col.type.__class__.__name__ == "String", (
            f"action should be String, got {col.type.__class__.__name__}"
        )

    def test_target_coords_is_json(self):
        """target_coords 为 JSON（坐标结构，design 第 674 行）。"""
        col = inspect(ReproStep).columns["target_coords"]
        assert col.type.__class__.__name__ == "JSON", (
            f"target_coords should be JSON, got {col.type.__class__.__name__}"
        )

    def test_screenshot_ref_is_string(self):
        """screenshot_ref 为 String（截图引用）。"""
        col = inspect(ReproStep).columns["screenshot_ref"]
        assert col.type.__class__.__name__ == "String", (
            f"screenshot_ref should be String, got {col.type.__class__.__name__}"
        )

    def test_actual_signal_is_json(self):
        """actual_signal 为 JSON（实际采集信号，design 第 677 行）。"""
        col = inspect(ReproStep).columns["actual_signal"]
        assert col.type.__class__.__name__ == "JSON", (
            f"actual_signal should be JSON, got {col.type.__class__.__name__}"
        )

    def test_trajectory_id_fk_to_trajectories(self):
        """trajectory_id 外键指向 trajectories.id（design 第 671 行）。"""
        col = inspect(ReproStep).columns["trajectory_id"]
        fks = list(col.foreign_keys)
        assert len(fks) >= 1, "trajectory_id should have FK"
        targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("trajectories", "id") in targets, (
            f"trajectory_id FK should target trajectories.id, got {targets}"
        )


# ---------------------------------------------------------------------------
# 2. Signal 四类枚举 + 字段
# ---------------------------------------------------------------------------
class TestSignalEnumAndFields:
    """Signal signal_type 四值枚举 + pattern/severity/source_config 字段。"""

    def test_signal_type_enum_has_4_members(self):
        """signal_type 枚举正好 4 个成员（design 第 684 行）。"""
        members = list(SignalType)
        assert len(members) == 4, (
            f"expected 4 SignalType members, got {len(members)}: {members}"
        )

    def test_signal_type_values_match_design(self):
        """signal_type 值与 design 第 684 行一致：logcat/flutter_error/process/visual。"""
        expected = {"logcat", "flutter_error", "process", "visual"}
        actual = {m.value for m in SignalType}
        assert actual == expected, f"mismatch: {actual} != {expected}"

    def test_signal_type_values_unique(self):
        """枚举值无重复。"""
        values = [m.value for m in SignalType]
        assert len(values) == len(set(values))

    def test_signal_type_is_str_enum(self):
        """枚举继承 str（便于 JSON 序列化与 SQL 存储）。"""
        assert issubclass(SignalType, str)
        assert issubclass(SignalType, Enum)

    def test_signal_pattern_field_exists(self):
        """pattern 字段存在（design 第 685 行）。"""
        assert "pattern" in inspect(Signal).columns

    def test_signal_severity_field_exists(self):
        """severity 字段存在（design 第 686 行）。"""
        assert "severity" in inspect(Signal).columns

    def test_signal_source_config_field_exists(self):
        """source_config 字段存在（design 第 687 行）。"""
        assert "source_config" in inspect(Signal).columns

    def test_pattern_is_json(self):
        """pattern 为 JSON（匹配规则结构随 signal_type 变化）。"""
        col = inspect(Signal).columns["pattern"]
        assert col.type.__class__.__name__ == "JSON"

    def test_source_config_is_json(self):
        """source_config 为 JSON（监听源配置）。"""
        col = inspect(Signal).columns["source_config"]
        assert col.type.__class__.__name__ == "JSON"

    def test_severity_enum_4_levels(self):
        """severity 四档（crash/error/warn/info）。"""
        expected = {"crash", "error", "warn", "info"}
        actual = {m.value for m in SignalSeverity}
        assert actual == expected


# ---------------------------------------------------------------------------
# 3. Anchor 字段 + visual_features Vector 类型
# ---------------------------------------------------------------------------
class TestAnchorFields:
    """Anchor 字段 + visual_features pgvector Vector 类型（design 4.1 第 701-709 行）。"""

    def test_required_three_fields_exist(self):
        """验收三字段：page_id/screenshot_ref/text_expectation。"""
        cols = set(inspect(Anchor).columns.keys())
        required = {"page_id", "screenshot_ref", "text_expectation"}
        missing = required - cols
        assert not missing, f"missing Anchor fields: {missing}"

    def test_visual_features_field_exists(self):
        """visual_features 字段存在（design 第 708 行）。"""
        assert "visual_features" in inspect(Anchor).columns

    def test_visual_features_is_vector_type(self):
        """visual_features 列类型为 pgvector.sqlalchemy.Vector（design 第 708 行 vector）。

        任务包明确要求："visual_features 为 Vector 类型断言"。
        """
        col = inspect(Anchor).columns["visual_features"]
        assert isinstance(col.type, Vector), (
            f"visual_features should be pgvector Vector, got {type(col.type)}"
        )

    def test_git_commit_anchor_field_exists(self):
        """git_commit_anchor 字段存在（design 第 709 行，D5）。"""
        assert "git_commit_anchor" in inspect(Anchor).columns


# ---------------------------------------------------------------------------
# 4. DiagnosisReport.format 二值枚举 + capability_gaps
# ---------------------------------------------------------------------------
class TestDiagnosisReportFields:
    """DiagnosisReport format 二值枚举 + capability_gaps 字段。"""

    def test_format_enum_has_2_members(self):
        """format 枚举正好 2 个成员（design 第 699 行）。"""
        members = list(DiagnosisFormat)
        assert len(members) == 2, (
            f"expected 2 DiagnosisFormat members, got {len(members)}: {members}"
        )

    def test_format_values_match_design(self):
        """format 值与 design 第 699 行一致：json/markdown。"""
        expected = {"json", "markdown"}
        actual = {m.value for m in DiagnosisFormat}
        assert actual == expected, f"mismatch: {actual} != {expected}"

    def test_format_is_str_enum(self):
        """枚举继承 str。"""
        assert issubclass(DiagnosisFormat, str)
        assert issubclass(DiagnosisFormat, Enum)

    def test_capability_gaps_field_exists(self):
        """capability_gaps 字段存在（design 第 696 行：list[str] FK）。"""
        assert "capability_gaps" in inspect(DiagnosisReport).columns

    def test_capability_gaps_is_json(self):
        """capability_gaps 为 JSON（存 CapabilityGap id 数组，list[str] FK 风格）。"""
        col = inspect(DiagnosisReport).columns["capability_gaps"]
        assert col.type.__class__.__name__ == "JSON", (
            f"capability_gaps should be JSON (list[str] FK), got {col.type.__class__.__name__}"
        )

    def test_bug_report_id_fk_to_bug_reports(self):
        """bug_report_id 外键指向 bug_reports.id（design 第 693 行）。"""
        col = inspect(DiagnosisReport).columns["bug_report_id"]
        fks = list(col.foreign_keys)
        assert len(fks) >= 1, "bug_report_id should have FK"
        targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("bug_reports", "id") in targets

    def test_format_field_default_is_json(self):
        """format 默认值为 json（DiagnosisFormat.JSON.value）。"""
        col = inspect(DiagnosisReport).columns["format"]
        default_val = col.default
        if hasattr(default_val, "arg"):
            arg = default_val.arg
            value = arg(DiagnosisFormat) if callable(arg) else arg
        else:
            value = default_val
        assert value == DiagnosisFormat.JSON.value


# ---------------------------------------------------------------------------
# 5. ManualFixEntry 字段完整性（BB015 → KB pattern 写入契约）
# ---------------------------------------------------------------------------
class TestManualFixEntryFields:
    """ManualFixEntry 五字段（BB015 契约，design 4.1 第 653-665 行）。"""

    def test_required_five_fields_exist(self):
        """验收五字段：patch_diff/trajectory_id/root_cause_text/trigger_conditions/kb_pattern_id。"""
        cols = set(inspect(ManualFixEntry).columns.keys())
        required = {
            "patch_diff",
            "trajectory_id",
            "root_cause_text",
            "trigger_conditions",
            "kb_pattern_id",
        }
        missing = required - cols
        assert not missing, f"missing ManualFixEntry fields: {missing}"

    def test_patch_diff_is_string(self):
        """patch_diff 为 String（人修 patch 文本，design 第 659 行）。"""
        col = inspect(ManualFixEntry).columns["patch_diff"]
        assert col.type.__class__.__name__ == "String"

    def test_trajectory_id_fk_to_trajectories(self):
        """trajectory_id 外键指向 trajectories.id（design 第 660 行）。"""
        col = inspect(ManualFixEntry).columns["trajectory_id"]
        fks = list(col.foreign_keys)
        assert len(fks) >= 1, "trajectory_id should have FK"
        targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("trajectories", "id") in targets, (
            f"trajectory_id FK should target trajectories.id, got {targets}"
        )

    def test_root_cause_text_is_string(self):
        """root_cause_text 为 String（根因解释，design 第 661 行）。"""
        col = inspect(ManualFixEntry).columns["root_cause_text"]
        assert col.type.__class__.__name__ == "String"

    def test_trigger_conditions_is_json(self):
        """trigger_conditions 为 JSON（触发条件，pattern 检索用，design 第 662 行）。

        任务包明确要求："trigger_conditions 结构（pattern 检索用）"。
        """
        col = inspect(ManualFixEntry).columns["trigger_conditions"]
        assert col.type.__class__.__name__ == "JSON", (
            f"trigger_conditions should be JSON, got {col.type.__class__.__name__}"
        )

    def test_kb_pattern_id_fk_to_kb_entries(self):
        """kb_pattern_id 外键指向 kb_entries.id（design 第 663 行，BB015→KB pattern 契约）。

        BB015 沉淀进 KBEntry(layer=pattern) 后，kb_pattern_id 反向引用该 KBEntry。
        """
        col = inspect(ManualFixEntry).columns["kb_pattern_id"]
        fks = list(col.foreign_keys)
        assert len(fks) >= 1, "kb_pattern_id should have FK to kb_entries"
        targets = {(fk.column.table.name, fk.column.name) for fk in fks}
        assert ("kb_entries", "id") in targets, (
            f"kb_pattern_id FK should target kb_entries.id, got {targets}"
        )

    def test_git_commit_anchor_field_exists(self):
        """git_commit_anchor 字段存在（design 第 664 行，D5 陈旧失效管理）。"""
        assert "git_commit_anchor" in inspect(ManualFixEntry).columns
