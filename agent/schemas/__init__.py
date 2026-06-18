"""R001 核心 Schema（SCH01 8 个 + MetricPoint + SCH02 5 个边界协议 Schema）。

依据：.dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1

聚合导出所有核心 Schema 与枚举，供业务层 / 契约测试 / frontend 引用。
枚举值（BugReport 14 态 / Hypothesis 4 态 / CapabilityGap 7 态 /
validity_status 3 态 / metric_type 5 维 / signal_type 4 类 /
signal_severity 4 档 / diagnosis_format 2 值）唯一定义于此包。
"""
from agent.schemas.anchor import Anchor
from agent.schemas.bug_report import (
    BugReport,
    BugReportStatus,
    STATUS_ALLOWED_REGRESSION_FEEDBACK,
)
from agent.schemas.capability_gap import CapabilityGap, CapabilityGapStatus
from agent.schemas.confidence import ConfidenceScore
from agent.schemas.diagnosis_report import DiagnosisFormat, DiagnosisReport
from agent.schemas.fix_patch import FixPatch
from agent.schemas.kb_entry import KBEntry, KBLayer, KBValidityStatus
from agent.schemas.manual_fix_entry import ManualFixEntry
from agent.schemas.metric_point import MetricPeriod, MetricPoint, MetricType
from agent.schemas.playbook import Playbook
from agent.schemas.repro_step import ReproStep
from agent.schemas.signal import Signal, SignalSeverity, SignalType
from agent.schemas.trajectory import Hypothesis, HypothesisStatus, Trajectory

__all__ = [
    # BugReport + 14 态枚举
    "BugReport",
    "BugReportStatus",
    "STATUS_ALLOWED_REGRESSION_FEEDBACK",
    # Playbook
    "Playbook",
    # Trajectory + Hypothesis 自引用树
    "Trajectory",
    "Hypothesis",
    "HypothesisStatus",
    # ConfidenceScore
    "ConfidenceScore",
    # FixPatch
    "FixPatch",
    # CapabilityGap + 7 态枚举
    "CapabilityGap",
    "CapabilityGapStatus",
    # KBEntry + validity_status / layer 枚举
    "KBEntry",
    "KBValidityStatus",
    "KBLayer",
    # MetricPoint + metric_type / period 枚举
    "MetricPoint",
    "MetricType",
    "MetricPeriod",
    # SCH02 边界协议 Schema（design 4.1 第 651-709 行）
    "ReproStep",
    "Signal",
    "SignalType",
    "SignalSeverity",
    "Anchor",
    "DiagnosisReport",
    "DiagnosisFormat",
    "ManualFixEntry",
]
