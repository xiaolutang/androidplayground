"""DiagnosisReportGenerator 单元测试（R001-BB012）。

覆盖：
- AC1: JSON + markdown 双输出
- AC2: 字段缺失降级输出不崩

测试场景（13 个）：
1.  完整字段 -> JSON 含所有字段
2.  完整字段 -> markdown 含所有章节
3.  bug_report=None 降级 -> bug_id="unknown"
4.  trajectory=None 降级 -> trajectory_summary={}
5.  confirmed_hypotheses=[] 降级 -> 空列表
6.  confidence_score=None 降级 -> None
7.  gaps=[] 降级 -> 空列表
8.  root_cause=None 降级 -> is_located=False
9.  root_cause.located=False 降级 -> is_located=False
10. 字段读取异常降级（mock obj 抛异常）-> 默认值不崩
11. JSON 输出可 json.loads 解析
12. markdown 输出含关键标题
13. 多假设列表（3 个 confirmed）-> markdown 列表正确
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agent.report.diagnosis_report_generator import (
    DiagnosisReportGenerator,
)


# ---------------------------------------------------------------------------
# 测试辅助：构造对象
# ---------------------------------------------------------------------------

def make_bug_report(
    *,
    id: str = "bug-001",
    symptom_type: str | None = "crash",
) -> SimpleNamespace:
    return SimpleNamespace(id=id, symptom_type=symptom_type)


def make_trajectory(
    *,
    total_step_used: int = 15,
    total_step_budget: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        total_step_used=total_step_used,
        total_step_budget=total_step_budget,
    )


def make_hypothesis(
    *,
    id: str = "hyp-001",
    content: str = "空指针解引用",
    status: str = "confirmed",
    step_used: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        content=content,
        status=status,
        step_used=step_used,
    )


def make_confidence_score(
    *,
    tier: int = 3,
    score: float = 0.55,
    dim_info: float = 0.6,
    dim_verify: float = 0.5,
    dim_pattern: float = 0.55,
) -> SimpleNamespace:
    return SimpleNamespace(
        tier=tier,
        score=score,
        dim_info_completeness=dim_info,
        dim_verification_feasibility=dim_verify,
        dim_patternability=dim_pattern,
    )


def make_gap(
    *,
    id: str = "gap-001",
    gap_type: str = "coverage",
    description: str = "KB 缺少该崩溃模式的 pattern",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        gap_type=gap_type,
        description=description,
    )


def make_root_cause(
    *,
    located: bool = True,
    file: str = "src/main/java/com/example/MainActivity.java",
    line: int = 42,
    function: str = "onCreate",
    snippet: str = "TextView tv = findViewById(R.id.tv);\ntv.setText(null);",
    confidence: float = 0.85,
) -> SimpleNamespace:
    return SimpleNamespace(
        located=located,
        file=file,
        line=line,
        function=function,
        snippet=snippet,
        confidence=confidence,
    )


class ExplodingAttr:
    """getattr 时抛异常的 mock 对象（测试降级）。"""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"boom on attr {name!r}")


# ---------------------------------------------------------------------------
# 完整字段场景（AC1: JSON + markdown 双输出）
# ---------------------------------------------------------------------------


class TestFullReport:
    """完整字段 -> 双格式输出。"""

    def setup_method(self) -> None:
        self.gen = DiagnosisReportGenerator(
            timestamp_provider=lambda: "2026-06-21T00:00:00+00:00",
        )
        self.report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[make_hypothesis()],
            confidence_score=make_confidence_score(),
            gaps=[make_gap()],
            root_cause=make_root_cause(),
        )

    def test_json_contains_all_fields(self) -> None:
        """完整字段 -> JSON 含所有字段。"""
        data = json.loads(self.gen.to_json(self.report))
        assert data["bug_id"] == "bug-001"
        assert data["symptom_type"] == "crash"
        assert data["is_located"] is True
        assert data["root_cause"]["file"].endswith("MainActivity.java")
        assert data["root_cause"]["line"] == 42
        assert data["root_cause"]["confidence"] == 0.85
        assert len(data["confirmed_hypotheses"]) == 1
        assert data["confirmed_hypotheses"][0]["id"] == "hyp-001"
        assert data["confidence_score"]["tier"] == 3
        assert data["confidence_score"]["score"] == 0.55
        assert len(data["gaps"]) == 1
        assert data["gaps"][0]["gap_type"] == "coverage"
        assert data["trajectory_summary"]["total_steps"] == 15
        assert data["trajectory_summary"]["total_budget"] == 20
        assert data["generated_at"] == "2026-06-21T00:00:00+00:00"

    def test_markdown_contains_all_sections(self) -> None:
        """完整字段 -> markdown 含所有章节。"""
        md = self.gen.to_markdown(self.report)
        assert "# 诊断报告 - bug-001" in md
        assert "**症状类型**: crash" in md
        assert "**根因定位**: 已定位" in md
        assert "## 根因" in md
        assert "MainActivity.java:42" in md
        assert "## 诊断路径" in md
        assert "hyp-001" in md
        assert "## 置信度" in md
        assert "Tier: 3" in md
        assert "## 缺口" in md
        assert "## 元数据" in md
        assert "总步数: 15 / 20" in md


# ---------------------------------------------------------------------------
# 降级场景（AC2: 字段缺失降级输出不崩）
# ---------------------------------------------------------------------------


class TestDegradation:
    """字段缺失降级 -> 不崩。"""

    def setup_method(self) -> None:
        self.gen = DiagnosisReportGenerator(
            timestamp_provider=lambda: "2026-06-21T00:00:00+00:00",
        )

    def test_bug_report_none(self) -> None:
        """bug_report=None -> bug_id='unknown'。"""
        report = self.gen.generate(
            bug_report=None,
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.bug_id == "unknown"
        assert report.symptom_type is None

    def test_trajectory_none(self) -> None:
        """trajectory=None -> trajectory_summary={}。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=None,
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.trajectory_summary == {}

    def test_confirmed_hypotheses_empty(self) -> None:
        """confirmed_hypotheses=[] -> 空列表。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.confirmed_hypotheses == []

    def test_confidence_score_none(self) -> None:
        """confidence_score=None -> None。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.confidence_score is None

    def test_gaps_empty(self) -> None:
        """gaps=[] -> 空列表。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.gaps == []

    def test_root_cause_none(self) -> None:
        """root_cause=None -> is_located=False, root_cause=None。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        assert report.is_located is False
        assert report.root_cause is None

    def test_root_cause_not_located(self) -> None:
        """root_cause.located=False -> is_located=False。"""
        rc = make_root_cause(located=False)
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=rc,
        )
        assert report.is_located is False
        assert report.root_cause is None

    def test_field_read_exception_no_crash(self) -> None:
        """字段读取异常（mock 抛异常）-> 默认值不崩。"""
        # ExplodingAttr 的任何 getattr 都抛 RuntimeError
        report = self.gen.generate(
            bug_report=ExplodingAttr(),
            trajectory=ExplodingAttr(),
            confirmed_hypotheses=[ExplodingAttr()],
            confidence_score=ExplodingAttr(),
            gaps=[ExplodingAttr()],
            root_cause=ExplodingAttr(),
        )
        # 应降级不崩：核心字段降级为默认值
        assert report.bug_id == "unknown"
        assert report.symptom_type is None
        assert report.is_located is False
        assert report.root_cause is None
        # confidence_score 对象非 None -> 返回 dict（字段全 None），
        # 仍属降级行为（不崩），markdown 会用 N/A 占位
        assert report.confidence_score is not None
        assert report.confidence_score.get("tier") is None
        assert report.confidence_score.get("score") is None

    def test_none_lists_degraded(self) -> None:
        """confirmed_hypotheses=None / gaps=None -> 空列表（不崩）。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=None,
            confidence_score=None,
            gaps=None,
            root_cause=None,
        )
        assert report.confirmed_hypotheses == []
        assert report.gaps == []


# ---------------------------------------------------------------------------
# JSON / markdown 格式验证
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """输出格式验证。"""

    def setup_method(self) -> None:
        self.gen = DiagnosisReportGenerator(
            timestamp_provider=lambda: "2026-06-21T00:00:00+00:00",
        )

    def test_json_parses_valid(self) -> None:
        """JSON 输出可 json.loads 解析。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[make_hypothesis()],
            confidence_score=make_confidence_score(),
            gaps=[make_gap()],
            root_cause=make_root_cause(),
        )
        json_str = self.gen.to_json(report)
        data = json.loads(json_str)
        assert isinstance(data, dict)
        # 所有 dataclass 字段都在 JSON 中
        expected_keys = {
            "bug_id",
            "symptom_type",
            "root_cause",
            "confirmed_hypotheses",
            "trajectory_summary",
            "confidence_score",
            "gaps",
            "is_located",
            "generated_at",
        }
        assert expected_keys.issubset(data.keys())

    def test_markdown_has_key_headings(self) -> None:
        """markdown 输出含关键标题。"""
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=[],
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        md = self.gen.to_markdown(report)
        assert "# 诊断报告 - bug-001" in md
        assert "## 根因" in md
        assert "## 诊断路径" in md
        assert "## 置信度" in md
        assert "## 缺口" in md
        assert "## 元数据" in md
        # 降级章节应标注 N/A
        assert "N/A" in md

    def test_multiple_hypotheses_markdown(self) -> None:
        """多假设列表（3 个 confirmed）-> markdown 列表正确。"""
        hyps = [
            make_hypothesis(id=f"hyp-{i}", content=f"假设{i}")
            for i in range(3)
        ]
        report = self.gen.generate(
            bug_report=make_bug_report(),
            trajectory=make_trajectory(),
            confirmed_hypotheses=hyps,
            confidence_score=None,
            gaps=[],
            root_cause=None,
        )
        md = self.gen.to_markdown(report)
        assert "hyp-0" in md
        assert "hyp-1" in md
        assert "hyp-2" in md
        assert "假设0" in md
        assert "假设1" in md
        assert "假设2" in md
        # 确认 JSON 中也是 3 个
        data = json.loads(self.gen.to_json(report))
        assert len(data["confirmed_hypotheses"]) == 3
