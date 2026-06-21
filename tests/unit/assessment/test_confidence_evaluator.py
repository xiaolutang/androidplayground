"""ConfidenceEvaluator 单元测试（R001-BB006，AC-1 ~ AC-8）。

纯规则测试（确定性，无需 LLM mock、无需 DB）。

覆盖：
- AC-1 评估接口（ConfidenceScore 字段完整 + duck typing）
- AC-2 三维打分范围 [0,1]
- AC-3 Tier 分级规则 + 边界值
- AC-4 KB 模式命中加成（0/1/2+ 条 / degraded / None）
- AC-5 ConfidenceScore 字段完整 + rationale 非空
- AC-6 纯计算函数（不调 LLM）
- AC-7 确定性（相同输入相同输出）
- AC-8 测试覆盖（>= 15 场景全绿）
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.assessment.confidence_evaluator import (
    KB_DEGRADED_PATTERN_SCORE,
    KB_NO_PATTERN_HIT_SCORE,
    KB_PATTERN_BONUS,
    TIER1_DIM_THRESHOLD,
    TIER2_AVG_THRESHOLD,
    TIER2_DIM_FLOOR,
    TIER3_AVG_THRESHOLD,
    ConfidenceEvaluator,
    build_rationale,
    classify_tier,
    compute_dim_info,
    compute_dim_pattern,
    compute_dim_verify,
)
from agent.schemas.confidence import ConfidenceScore


# ---------------------------------------------------------------------------
# 测试辅助：构造对象
# ---------------------------------------------------------------------------
def make_bug_report(
    *,
    raw_report: dict | str | None = None,
    version_code: str | None = None,
    symptom_type: str | None = None,
    stacktrace: str | None = None,
) -> SimpleNamespace:
    """构造 BugReport-like 对象（duck typing）。"""
    return SimpleNamespace(
        raw_report=raw_report,
        version_code=version_code,
        symptom_type=symptom_type,
        stacktrace=stacktrace,
    )


def make_hypothesis(
    *,
    is_rootcause: bool | None = None,
    status: str | None = None,
    confirming_evidence: dict | None = None,
    falsifying_signal: dict | None = None,
    overturning_signal: dict | None = None,
) -> SimpleNamespace:
    """构造 Hypothesis-like 对象。"""
    return SimpleNamespace(
        is_rootcause=is_rootcause,
        status=status,
        confirming_evidence=confirming_evidence,
        falsifying_signal=falsifying_signal,
        overturning_signal=overturning_signal,
    )


def make_trajectory(hypotheses: list | None = None) -> SimpleNamespace:
    """构造 Trajectory-like 对象。"""
    return SimpleNamespace(hypotheses=hypotheses or [])


def make_kb_entry(layer: str, similarity: float) -> SimpleNamespace:
    """构造 RetrievedEntry-like 对象（含 entry.layer + similarity）。"""
    return SimpleNamespace(
        entry=SimpleNamespace(layer=layer),
        similarity=similarity,
    )


def make_kb_result(
    entries: list | None = None,
    degraded: bool = False,
) -> SimpleNamespace:
    """构造 RetrievalResult-like 对象。"""
    return SimpleNamespace(entries=entries or [], degraded=degraded)


# ---------------------------------------------------------------------------
# AC-1：评估接口
# ---------------------------------------------------------------------------
class TestEvaluateInterface:
    """AC-1：evaluate 接口 + duck typing。"""

    def test_returns_confidence_score(self):
        """evaluate 返回 ConfidenceScore 实例。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(raw_report={"reproduction_steps": ["step1"]})
        result = evaluator.evaluate(bug)
        assert isinstance(result, ConfidenceScore)

    def test_confidence_score_fields(self):
        """ConfidenceScore 字段完整。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(version_code="1.0")
        result = evaluator.evaluate(bug)
        assert result.tier in (1, 2, 3, 4)
        assert 0.0 <= result.dim_info_completeness <= 1.0
        assert 0.0 <= result.dim_verification_feasibility <= 1.0
        assert 0.0 <= result.dim_patternability <= 1.0
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.rationale, str)
        assert result.rationale

    def test_bug_report_dict_input(self):
        """BugReport 接受 dict 输入（duck typing）。"""
        evaluator = ConfidenceEvaluator()
        bug_dict = {
            "raw_report": {"reproduction_steps": ["step1"]},
            "version_code": "2.0",
        }
        result = evaluator.evaluate(bug_dict)
        assert isinstance(result, ConfidenceScore)
        assert result.dim_info_completeness > 0

    def test_trajectory_none(self):
        """trajectory=None 时 dim_verify 给低分 0.3。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()
        result = evaluator.evaluate(bug, trajectory=None)
        assert result.dim_verification_feasibility == 0.3

    def test_kb_context_none(self):
        """kb_context=None 时 dim_pattern=0.2，kb_pattern_hit=None。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()
        result = evaluator.evaluate(bug, kb_context=None)
        assert result.dim_patternability == 0.2
        assert result.kb_pattern_hit is None


# ---------------------------------------------------------------------------
# AC-2：三维打分范围
# ---------------------------------------------------------------------------
class TestDimRanges:
    """AC-2：三维打分始终在 [0, 1]。"""

    def test_empty_bug_report(self):
        """空 BugReport → dim_info 在 [0,1]。"""
        score = compute_dim_info(make_bug_report())
        assert 0.0 <= score <= 1.0

    def test_full_bug_report(self):
        """完备 BugReport → dim_info 接近 1.0。"""
        bug = make_bug_report(
            raw_report={
                "reproduction_steps": ["step1", "step2"],
                "device_model": "Pixel 6",
                "stacktrace": "NullPointerException at ...",
                "expected_behavior": "should not crash",
            },
            version_code="1.0",
        )
        score = compute_dim_info(bug)
        assert score == 1.0  # 0.3 + 0.2 + 0.3 + 0.2 = 1.0

    def test_dim_verify_none(self):
        """trajectory=None → 0.3。"""
        assert compute_dim_verify(None) == 0.3

    def test_dim_verify_confirmed(self):
        """confirmed hypothesis + 全证据 → 1.0。"""
        hyp = make_hypothesis(
            is_rootcause=True,
            confirming_evidence={"signal": "found"},
        )
        traj = make_trajectory([hyp])
        assert compute_dim_verify(traj) == 1.0  # 0.6 + 0.2 + 0.1 + 0.1

    def test_dim_verify_no_falsifying_no_overturning(self):
        """confirmed 但无 confirming_evidence → 0.8。"""
        hyp = make_hypothesis(status="confirmed")
        traj = make_trajectory([hyp])
        # 0.6 + 0 + 0.1 + 0.1 = 0.8
        assert compute_dim_verify(traj) == 0.8

    def test_dim_verify_with_falsifying(self):
        """有 falsifying_signal → 不加分。"""
        hyp = make_hypothesis(
            is_rootcause=True,
            falsifying_signal={"signal": "found"},
        )
        traj = make_trajectory([hyp])
        # 0.6 + 0 + 0 + 0.1 = 0.7
        assert compute_dim_verify(traj) == 0.7

    def test_dim_verify_no_confirmed(self):
        """无 confirmed hypothesis → 0.3。"""
        hyp = make_hypothesis(status="proposed")
        traj = make_trajectory([hyp])
        assert compute_dim_verify(traj) == 0.3


# ---------------------------------------------------------------------------
# AC-3：Tier 分级规则 + 边界值
# ---------------------------------------------------------------------------
class TestTierClassification:
    """AC-3：Tier 分级 + 边界值。"""

    def test_tier1_all_high(self):
        """三维均 >= 0.7 → Tier 1。"""
        assert classify_tier(0.8, 0.75, 0.9) == 1

    def test_tier1_boundary(self):
        """边界 (0.7, 0.7, 0.7) → Tier 1。"""
        assert classify_tier(0.7, 0.7, 0.7) == 1

    def test_tier1_just_below(self):
        """(0.69, 0.7, 0.7) → 不满足 Tier1，转 Tier2（平均 0.697 >= 0.5，无 < 0.3）。"""
        assert classify_tier(0.69, 0.7, 0.7) == 2

    def test_tier2_medium(self):
        """(0.6, 0.5, 0.4) → 平均 0.5，无 < 0.3 → Tier 2。"""
        assert classify_tier(0.6, 0.5, 0.4) == 2

    def test_tier2_boundary_avg(self):
        """平均恰好 0.5 → Tier 2（无维度 < 0.3）。"""
        # 0.6 + 0.5 + 0.4 = 1.5 / 3 = 0.5
        assert classify_tier(0.6, 0.5, 0.4) == 2

    def test_tier2_dim_floor_boundary(self):
        """一维恰好 0.3，平均 >= 0.5 → 仍 Tier 2（>= 0.3 满足 floor）。"""
        assert classify_tier(0.7, 0.7, 0.3) == 2

    def test_tier2_dim_below_floor(self):
        """一维 0.29 < 0.3 → 不满足 Tier2，降 Tier3（平均 >= 0.3）。"""
        # avg = (0.7 + 0.7 + 0.29) / 3 = 0.563 >= 0.3
        assert classify_tier(0.7, 0.7, 0.29) == 3

    def test_tier3_low(self):
        """(0.4, 0.3, 0.2) → 平均 0.3，有维度 < 0.3 → Tier 3。"""
        assert classify_tier(0.4, 0.3, 0.2) == 3

    def test_tier3_boundary_avg(self):
        """平均恰好 0.3 → Tier 3。"""
        # 0.4 + 0.3 + 0.2 = 0.9 / 3 = 0.3
        assert classify_tier(0.4, 0.3, 0.2) == 3

    def test_tier4_very_low(self):
        """(0.1, 0.1, 0.1) → 平均 0.1 < 0.3 → Tier 4。"""
        assert classify_tier(0.1, 0.1, 0.1) == 4

    def test_tier4_boundary(self):
        """平均 0.29 < 0.3 → Tier 4。"""
        # (0.3 + 0.3 + 0.27) / 3 = 0.29
        assert classify_tier(0.3, 0.3, 0.27) == 4


# ---------------------------------------------------------------------------
# AC-4：KB 模式命中加成
# ---------------------------------------------------------------------------
class TestKBPatternBonus:
    """AC-4：dim_patternability KB 模式命中加成。"""

    def test_kb_none(self):
        """kb_context=None → 0.2, kb_pattern_hit=None。"""
        score, hit = compute_dim_pattern(None)
        assert score == 0.2
        assert hit is None

    def test_kb_degraded(self):
        """degraded=True → 0.2, hit.degraded=True。"""
        kb = make_kb_result(degraded=True)
        score, hit = compute_dim_pattern(kb)
        assert score == 0.2
        assert hit is not None
        assert hit["degraded"] is True
        assert hit["hit_count"] == 0

    def test_kb_no_pattern_hit(self):
        """有 entries 但无 pattern 层 → 0.4。"""
        entries = [make_kb_entry("negative_knowledge", 0.9)]
        kb = make_kb_result(entries=entries)
        score, hit = compute_dim_pattern(kb)
        assert score == 0.4
        assert hit is not None
        assert hit["hit_count"] == 0
        assert hit["top1_similarity"] is None

    def test_kb_one_pattern_hit(self):
        """1 条 pattern 命中 sim=0.85 → 0.85。"""
        entries = [make_kb_entry("pattern", 0.85)]
        kb = make_kb_result(entries=entries)
        score, hit = compute_dim_pattern(kb)
        assert score == 0.85
        assert hit["hit_count"] == 1
        assert hit["top1_similarity"] == 0.85
        assert hit["degraded"] is False

    def test_kb_two_pattern_hits_bonus(self):
        """>=2 条 pattern 命中 → top1 + 0.1 cap 1.0。"""
        entries = [
            make_kb_entry("pattern", 0.8),
            make_kb_entry("pattern", 0.75),
        ]
        kb = make_kb_result(entries=entries)
        score, hit = compute_dim_pattern(kb)
        assert score == 0.9  # min(0.8 + 0.1, 1.0)
        assert hit["hit_count"] == 2
        assert hit["top1_similarity"] == 0.8

    def test_kb_two_pattern_hits_cap(self):
        """>=2 条 pattern 命中 top1=0.95 → min(0.95+0.1, 1.0) = 1.0。"""
        entries = [
            make_kb_entry("pattern", 0.95),
            make_kb_entry("pattern", 0.7),
        ]
        kb = make_kb_result(entries=entries)
        score, hit = compute_dim_pattern(kb)
        assert score == 1.0

    def test_kb_mixed_layers(self):
        """混合层，仅 pattern 层计入。"""
        entries = [
            make_kb_entry("negative_knowledge", 0.99),
            make_kb_entry("pattern", 0.6),
        ]
        kb = make_kb_result(entries=entries)
        score, hit = compute_dim_pattern(kb)
        assert score == 0.6
        assert hit["hit_count"] == 1

    def test_kb_dict_input(self):
        """dict 输入（duck typing）。"""
        kb = {
            "entries": [
                {"entry": {"layer": "pattern"}, "similarity": 0.8},
            ],
            "degraded": False,
        }
        score, hit = compute_dim_pattern(kb)
        assert score == 0.8
        assert hit["hit_count"] == 1


# ---------------------------------------------------------------------------
# AC-5：ConfidenceScore 字段完整
# ---------------------------------------------------------------------------
class TestConfidenceScoreFields:
    """AC-5：ConfidenceScore 对象字段完整 + rationale 非空 + id UUID。"""

    def test_id_is_uuid_string(self):
        """id 为 UUID 字符串，每次评估生成新 id。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()
        r1 = evaluator.evaluate(bug)
        r2 = evaluator.evaluate(bug)
        assert isinstance(r1.id, str)
        assert len(r1.id) == 36  # UUID 格式
        assert r1.id != r2.id  # 每次新 UUID

    def test_bug_report_id_none(self):
        """bug_report_id 为 None（由持久化方填）。"""
        evaluator = ConfidenceEvaluator()
        result = evaluator.evaluate(make_bug_report())
        assert result.bug_report_id is None

    def test_rationale_non_empty(self):
        """rationale 非空，含 Tier 分级理由。"""
        evaluator = ConfidenceEvaluator()
        result = evaluator.evaluate(make_bug_report())
        assert result.rationale
        assert "Tier" in result.rationale
        assert "dim_info=" in result.rationale

    def test_rationale_tier1(self):
        """Tier 1 rationale 含 'all dims >= 0.7'。"""
        rationale = build_rationale(1, 0.8, 0.8, 0.8, 0.8)
        assert "all dims >= 0.7" in rationale
        assert "Tier 1" in rationale


# ---------------------------------------------------------------------------
# AC-6：纯计算函数（不调 LLM）
# ---------------------------------------------------------------------------
class TestPureComputation:
    """AC-6：纯计算函数。"""

    def test_no_llm_gateway_param(self):
        """ConfidenceEvaluator 构造函数无 llm_gateway 参数。"""
        import inspect

        sig = inspect.signature(ConfidenceEvaluator.__init__)
        assert "llm_gateway" not in sig.parameters
        assert "llm" not in sig.parameters

    def test_evaluate_is_sync(self):
        """evaluate 为同步 def（非 async def）。"""
        import inspect

        assert not inspect.iscoroutinefunction(ConfidenceEvaluator.evaluate)

    def test_no_llm_import(self):
        """模块不导入 LLMGateway / LLMError。"""
        import agent.assessment.confidence_evaluator as mod

        source = open(mod.__file__).read()
        assert "LLMGateway" not in source
        assert "LLMError" not in source


# ---------------------------------------------------------------------------
# AC-7：确定性 + 阈值参数化
# ---------------------------------------------------------------------------
class TestDeterminism:
    """AC-7：确定性 + 无随机数 + 阈值参数化。"""

    def test_same_input_same_output(self):
        """相同输入 → 相同 tier/dims/score（id 不同因 UUID）。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(
            raw_report={"reproduction_steps": ["s1"], "stacktrace": "err"},
            version_code="1.0",
        )
        traj = make_trajectory([
            make_hypothesis(is_rootcause=True, confirming_evidence={"x": 1}),
        ])
        kb = make_kb_result([make_kb_entry("pattern", 0.85)])

        r1 = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)
        r2 = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)

        assert r1.tier == r2.tier
        assert r1.dim_info_completeness == r2.dim_info_completeness
        assert r1.dim_verification_feasibility == r2.dim_verification_feasibility
        assert r1.dim_patternability == r2.dim_patternability
        assert r1.score == r2.score
        assert r1.id != r2.id  # UUID 不同

    def test_no_random_module(self):
        """模块不导入 random，不使用 random.random()。"""
        import agent.assessment.confidence_evaluator as mod

        source = open(mod.__file__).read()
        assert "import random" not in source
        assert "random.random" not in source

    def test_thresholds_are_module_constants(self):
        """阈值为模块级常量。"""
        assert TIER1_DIM_THRESHOLD == 0.7
        assert TIER2_AVG_THRESHOLD == 0.5
        assert TIER2_DIM_FLOOR == 0.3
        assert TIER3_AVG_THRESHOLD == 0.3
        assert KB_PATTERN_BONUS == 0.1
        assert KB_DEGRADED_PATTERN_SCORE == 0.2
        assert KB_NO_PATTERN_HIT_SCORE == 0.4

    def test_threshold_patchable(self):
        """阈值可被运行时覆盖（monkeypatch）。"""
        with patch(
            "agent.assessment.confidence_evaluator.TIER1_DIM_THRESHOLD", 0.6
        ):
            assert classify_tier(0.65, 0.65, 0.65) == 1


# ---------------------------------------------------------------------------
# AC-8：完整场景测试（Integration-style）
# ---------------------------------------------------------------------------
class TestFullScenarios:
    """AC-8：15+ 场景覆盖（Contract 测试策略表）。"""

    def test_scenario_tier1(self):
        """场景：Tier1（三维高，均 >= 0.7）。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(
            raw_report={
                "reproduction_steps": ["s1"],
                "device_model": "Pixel",
                "stacktrace": "NPE",
                "expected_behavior": "no crash",
            },
            version_code="1.0",
        )
        traj = make_trajectory([
            make_hypothesis(
                is_rootcause=True,
                confirming_evidence={"signal": "found"},
            ),
        ])
        kb = make_kb_result([
            make_kb_entry("pattern", 0.85),
            make_kb_entry("pattern", 0.7),
        ])
        result = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)
        assert result.tier == 1
        assert all(
            d >= 0.7
            for d in [
                result.dim_info_completeness,
                result.dim_verification_feasibility,
                result.dim_patternability,
            ]
        )

    def test_scenario_tier2(self):
        """场景：Tier2（中置信）。"""
        # dim_info=0.5（steps+version），dim_verify=0.3（无 confirmed），dim_pattern=0.4
        # → 平均 0.4 < 0.5，实际 Tier3；需调整构造使平均 >= 0.5
        # 用 confirmed 但无 evidence：dim_verify=0.8
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(
            raw_report={"reproduction_steps": ["s1"]},
            version_code="1.0",
        )
        # dim_info = 0.3 + 0.2 = 0.5
        traj = make_trajectory([make_hypothesis(status="confirmed")])
        # dim_verify = 0.8
        kb = make_kb_result([make_kb_entry("negative_knowledge", 0.9)])
        # dim_pattern = 0.4
        result = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)
        # avg = (0.5 + 0.8 + 0.4) / 3 = 0.567 >= 0.5, 无 < 0.3 → Tier 2
        assert result.tier == 2

    def test_scenario_tier3(self):
        """场景：Tier3（低置信）。"""
        evaluator = ConfidenceEvaluator()
        # dim_info = 0.3
        traj = make_trajectory([make_hypothesis(status="proposed")])
        # dim_verify = 0.3
        kb = make_kb_result(degraded=True)
        # dim_pattern = 0.2
        # avg = (0.3 + 0.3 + 0.2) / 3 = 0.267 < 0.3 → Tier 4
        # 需调整：dim_info=0.5
        bug2 = make_bug_report(
            raw_report={"reproduction_steps": ["s1"]},
            version_code="1.0",
        )
        result2 = evaluator.evaluate(bug2, trajectory=traj, kb_context=kb)
        # avg = (0.5 + 0.3 + 0.2) / 3 = 0.333 >= 0.3 → Tier 3
        assert result2.tier == 3

    def test_scenario_tier4(self):
        """场景：Tier4（极低，平均 < 0.3）。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()  # 空 → dim_info=0
        result = evaluator.evaluate(bug, trajectory=None, kb_context=None)
        # dim_info=0, dim_verify=0.3, dim_pattern=0.2 → avg=0.167 < 0.3
        assert result.tier == 4

    def test_scenario_ism_result_reuse(self):
        """场景：dim_info 复用 ISMResult.score。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()  # 空 BugReport
        ism_result = SimpleNamespace(score=0.85)
        result = evaluator.evaluate(bug, ism_result=ism_result)
        assert result.dim_info_completeness == 0.85

    def test_scenario_kb_pattern_two_hits_in_evaluate(self):
        """场景：evaluate 端到端 KB >=2 pattern 命中。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()
        kb = make_kb_result([
            make_kb_entry("pattern", 0.8),
            make_kb_entry("pattern", 0.75),
        ])
        result = evaluator.evaluate(bug, kb_context=kb)
        assert result.dim_patternability == 0.9
        assert result.kb_pattern_hit["hit_count"] == 2
        assert result.kb_pattern_hit["top1_similarity"] == 0.8

    def test_scenario_kb_degraded_in_evaluate(self):
        """场景：evaluate 端到端 KB degraded。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report()
        kb = make_kb_result(degraded=True)
        result = evaluator.evaluate(bug, kb_context=kb)
        assert result.dim_patternability == 0.2
        assert result.kb_pattern_hit["degraded"] is True

    def test_scenario_dict_trajectory(self):
        """场景：trajectory 为 dict 输入。"""
        evaluator = ConfidenceEvaluator()
        traj_dict = {
            "hypotheses": [
                {"is_rootcause": True, "confirming_evidence": {"x": 1}},
            ],
        }
        result = evaluator.evaluate(make_bug_report(), trajectory=traj_dict)
        assert result.dim_verification_feasibility == 1.0

    def test_scenario_hypothesis_dict_input(self):
        """场景：trajectory 直接传 Hypothesis dict（无 hypotheses 包裹）。"""
        evaluator = ConfidenceEvaluator()
        hyp_dict = {"is_rootcause": True, "confirming_evidence": {"x": 1}}
        result = evaluator.evaluate(make_bug_report(), trajectory=hyp_dict)
        assert result.dim_verification_feasibility == 1.0

    def test_scenario_score_is_avg(self):
        """score = 三维平均值（round 4 位）。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(
            raw_report={"reproduction_steps": ["s1"]},
            version_code="1.0",
        )
        traj = make_trajectory([make_hypothesis(status="confirmed")])
        kb = make_kb_result([make_kb_entry("negative_knowledge", 0.9)])
        result = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)
        expected = round(
            (
                result.dim_info_completeness
                + result.dim_verification_feasibility
                + result.dim_patternability
            )
            / 3.0,
            4,
        )
        assert result.score == expected


# ---------------------------------------------------------------------------
# 端到端 Tier 分级（使用 evaluate 接口）
# ---------------------------------------------------------------------------
class TestEvaluateTierScenarios:
    """通过 evaluate 接口验证 Tier 1-4 分级端到端。"""

    def test_evaluate_tier1_boundary(self):
        """三维恰为 0.7/0.7/0.7 → Tier 1。"""
        evaluator = ConfidenceEvaluator()
        # 构造 dim_info=0.7 不易（规则式），用 ISMResult 强制
        bug = make_bug_report()
        ism = SimpleNamespace(score=0.7)
        # dim_verify = 0.6 + 0.2 + 0 + 0.1 = 0.9，不满足 0.7 边界
        # 调整：无 confirming 但也无 falsifying/overturning → 0.6 + 0.1 + 0.1 = 0.8
        traj2 = make_trajectory([make_hypothesis(is_rootcause=True)])
        # dim_verify = 0.6 + 0 + 0.1 + 0.1 = 0.8
        kb = make_kb_result([make_kb_entry("pattern", 0.7)])
        # dim_pattern = 0.7
        result = evaluator.evaluate(
            bug, trajectory=traj2, kb_context=kb, ism_result=ism,
        )
        # dim_info=0.7, dim_verify=0.8, dim_pattern=0.7
        # d_info >= 0.7, d_verify >= 0.7, d_pattern >= 0.7 → Tier 1
        assert result.tier == 1

    def test_evaluate_tier2_with_kb_no_pattern(self):
        """Tier2 端到端：有 KB 无 pattern → dim_pattern=0.4。"""
        evaluator = ConfidenceEvaluator()
        bug = make_bug_report(
            raw_report={"reproduction_steps": ["s1"]},
            version_code="1.0",
        )
        traj = make_trajectory([make_hypothesis(status="confirmed")])
        kb = make_kb_result([make_kb_entry("negative_knowledge", 0.9)])
        result = evaluator.evaluate(bug, trajectory=traj, kb_context=kb)
        assert result.tier == 2

    def test_evaluate_tier4_all_none(self):
        """Tier4 端到端：全空输入。"""
        evaluator = ConfidenceEvaluator()
        result = evaluator.evaluate(
            make_bug_report(), trajectory=None, kb_context=None,
        )
        assert result.tier == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
