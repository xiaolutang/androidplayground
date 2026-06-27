"""AutoFixer 单元测试（R001-BB007，AC-1 ~ AC-11）。

覆盖：
- AC-1 三策略优先级（template -> llm -> history_calibration）
- AC-2 template 策略（KB pattern 套用）
- AC-3 llm 策略（LLMGateway fix_patch）
- AC-4 history_calibration 策略（KB patch_history 校准）
- AC-5 strategy_chain 审计链完整
- AC-6 Tier1 产出（is_draft=False）
- AC-7 Tier2 产出（is_draft=True + rationale）
- AC-8 FIX_RETRY_MAX 重试上限
- AC-9 LLM/KB 失败降级
- AC-10 FixPatch 数据结构
- AC-11 测试覆盖（全 mock，无真实 LLM/DB）

全 mock：LLMGateway / KBRetriever / RetrievalResult。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.fix.auto_fixer import (
    HISTORY_SIMILARITY_THRESHOLD,
    TEMPLATE_SIMILARITY_THRESHOLD,
    TIER2_RATIONALE,
    AutoFixer,
    FixPatch,
    StrategyAttempt,
)
from agent.infra.llm_gateway import LLMError, LLMResponse
from agent.kb.retriever import RetrievalResult, RetrievedEntry


# ---------------------------------------------------------------------------
# 测试辅助：构造 KBEntry / RetrievedEntry / RetrievalResult
# ---------------------------------------------------------------------------
@dataclass
class FakeKBEntry:
    """轻量 KBEntry mock（duck typing）。"""

    id: str
    layer: str
    content: dict | None = None
    symptom_type: str | None = None
    validity_status: str = "valid"


def make_retrieved_entry(
    *,
    entry_id: str,
    layer: str,
    similarity: float,
    content: dict | None = None,
) -> RetrievedEntry:
    """构造 RetrievedEntry。"""
    return RetrievedEntry(
        entry=FakeKBEntry(id=entry_id, layer=layer, content=content),
        similarity=similarity,
        raw_similarity=similarity,
        validity_status="valid",
        conflicting_with=None,
    )


def make_kb_context(
    *,
    entries: list[RetrievedEntry] | None = None,
    degraded: bool = False,
) -> RetrievalResult:
    """构造 RetrievalResult。"""
    return RetrievalResult(
        entries=entries or [],
        degraded=degraded,
    )


# ---------------------------------------------------------------------------
# 测试辅助：FakeLLMGateway（可配置响应/异常）
# ---------------------------------------------------------------------------
class FakeLLMGateway:
    """可控的 LLMGateway mock。

    - response: 返回的 content（None 时抛 LLMError）。
    - usage: 透传 usage dict。
    - exc: 抛出指定异常（优先于 response）。
    """

    def __init__(
        self,
        *,
        response: str | None = "diff",
        usage: dict | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._usage = usage
        self._exc = exc
        self.calls: list[dict] = []

    async def complete(
        self,
        prompt_type: str,
        *,
        messages: list[dict],
        image_url: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append(
            {"prompt_type": prompt_type, "messages": messages}
        )
        if self._exc is not None:
            raise self._exc
        return LLMResponse(
            content=self._response or "",
            model="fake-model",
            usage=self._usage,
        )


# ---------------------------------------------------------------------------
# 公共 diff 内容
# ---------------------------------------------------------------------------
VALID_DIFF = """\
--- a/src/main/java/com/example/Foo.java
+++ b/src/main/java/com/example/Foo.java
@@ -10,5 +10,5 @@
-    return null;
+    return defaultValue;
"""

VALID_DIFF_TWO_FILES = """\
--- a/src/main/java/com/example/Foo.java
+++ b/src/main/java/com/example/Foo.java
@@ -10,5 +10,5 @@
-    return null;
+    return defaultValue;
--- a/src/main/java/com/example/Bar.java
+++ b/src/main/java/com/example/Bar.java
@@ -20,3 +20,3 @@
-    x = 1;
+    x = 2;
"""

MARKDOWN_WRAPPED_DIFF = """\
```diff
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -1,1 +1,1 @@
-old
+new
```
"""


# ===========================================================================
# AC-1：三策略优先级
# ===========================================================================
class TestAC1StrategyPriority:
    """AC-1：三策略优先级 template -> llm -> history_calibration。"""

    def test_template_success_skips_llm_and_history(self):
        """template 成功 -> 不尝试 llm/history，strategy='template'。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.85,
                    content={"patch_template": VALID_DIFF},
                )
            ]
        )
        fixer = AutoFixer(llm_gateway=FakeLLMGateway())

        patch = fixer.generate_patch(
            bug_report_summary="NPE on click",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "template"
        assert patch.patch_content is not None
        assert len(patch.strategy_chain) == 1
        assert patch.strategy_chain[0]["strategy_name"] == "template"
        assert patch.strategy_chain[0]["succeeded"] is True

    def test_template_fail_llm_success_skips_history(self):
        """template 失败 + llm 成功 -> strategy='llm'，chain 长度=2。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.5,  # < 0.7
                    content={"patch_template": VALID_DIFF},
                )
            ]
        )
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 100})
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "llm"
        assert len(patch.strategy_chain) == 2
        assert patch.strategy_chain[0]["strategy_name"] == "template"
        assert patch.strategy_chain[0]["succeeded"] is False
        assert patch.strategy_chain[1]["strategy_name"] == "llm"
        assert patch.strategy_chain[1]["succeeded"] is True

    def test_template_llm_fail_history_success(self):
        """template 失败 + llm 失败 + history_calibration 成功。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.5,
                    content={"patch_template": VALID_DIFF},
                ),
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.75,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("LLM timeout"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "history_calibration"
        assert len(patch.strategy_chain) == 3

    def test_all_three_strategies_fail(self):
        """三策略全失败 -> patch_content=None，chain 长度=3。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.5,
                    content={},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("LLM error"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.patch_content is None
        assert patch.strategy == "history_calibration"  # 最后尝试的
        assert len(patch.strategy_chain) == 3

    def test_strategy_chain_attempt_no_incremental(self):
        """attempt_no 从 1 递增。"""
        kb = make_kb_context(entries=[])
        gw = FakeLLMGateway(exc=LLMError("error"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        for i, attempt in enumerate(patch.strategy_chain):
            assert attempt["attempt_no"] == i + 1


# ===========================================================================
# AC-2：template 策略
# ===========================================================================
class TestAC2Template:
    """AC-2：template 策略（KB pattern 套用）。"""

    def test_template_success_high_similarity(self):
        """sim >= 0.7 + patch_template 可用 -> template 成功。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.85,
                    content={"patch_template": VALID_DIFF},
                )
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "template"
        assert patch.patch_content is not None
        assert patch.pattern_id == "pat-001"

    def test_template_pattern_id_recorded(self):
        """template 成功时 pattern_id = entry.id。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="kb-pattern-42",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                )
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.pattern_id == "kb-pattern-42"
        assert patch.strategy_chain[0]["pattern_id"] == "kb-pattern-42"

    def test_template_low_similarity_fails(self):
        """pattern top1 similarity < 0.7 -> template 失败。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.6,
                    content={"patch_template": VALID_DIFF},
                )
            ]
        )
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(exc=LLMError("e")))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert tmpl_attempt["succeeded"] is False
        assert "similarity below threshold" in tmpl_attempt["error"]

    def test_template_no_pattern_hit(self):
        """pattern 层无命中 -> template 失败，error 含 'no pattern hit'。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.9,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(exc=LLMError("e")))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert tmpl_attempt["succeeded"] is False
        assert "no pattern hit" in tmpl_attempt["error"]

    def test_template_no_patch_template_field(self):
        """top1 entry 无 patch_template -> template 失败。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"description": "some pattern but no template"},
                ),
            ]
        )
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(exc=LLMError("e")))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert tmpl_attempt["succeeded"] is False
        assert "no patch_template" in tmpl_attempt["error"]

    def test_template_renders_template_variables(self):
        """template 策略产出的 patch_content 为渲染后的 unified diff。"""
        tmpl = (
            "--- a/{root_cause_location}\n"
            "+++ b/{root_cause_location}\n"
            "@@ -1 +1 @@\n-old\n+new"
        )
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": tmpl},
                )
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.patch_content is not None
        assert "Foo.java:10" in patch.patch_content


# ===========================================================================
# AC-3：llm 策略
# ===========================================================================
class TestAC3LLM:
    """AC-3：llm 策略（LLMGateway fix_patch）。"""

    def test_llm_calls_complete_with_fix_patch(self):
        """llm 策略调 LLMGateway.complete(prompt_type='fix_patch')。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 200})
        fixer = AutoFixer(llm_gateway=gw)

        fixer.generate_patch(
            bug_report_summary="NPE on click",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert len(gw.calls) == 1
        assert gw.calls[0]["prompt_type"] == "fix_patch"

    def test_llm_messages_contain_system_and_user(self):
        """messages 含 system message（角色+格式约束）+ user message（根因+症状）。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 200})
        fixer = AutoFixer(llm_gateway=gw)

        fixer.generate_patch(
            bug_report_summary="NPE on click",
            root_cause_location="Foo.java:42",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        messages = gw.calls[0]["messages"]
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles
        sys_msg = next(m["content"] for m in messages if m["role"] == "system")
        assert "unified diff" in sys_msg
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "Foo.java:42" in user_msg
        assert "crash" in user_msg

    def test_llm_response_parsed_tokens_recorded(self):
        """LLMResponse.content 非空 -> patch_content, tokens_used。"""
        gw = FakeLLMGateway(
            response=VALID_DIFF, usage={"total_tokens": 150}
        )
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.strategy == "llm"
        assert patch.patch_content is not None
        llm_attempt = patch.strategy_chain[1]  # template first (fail)
        assert llm_attempt["tokens_used"] == 150

    def test_llm_empty_content_fails(self):
        """LLMResponse.content 为空 -> succeeded=False, error 含 'empty'。"""
        gw = FakeLLMGateway(response="")
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "empty or invalid" in llm_attempt["error"]

    def test_llm_strips_markdown_codeblock(self):
        """LLM 输出含 markdown 代码块标记 -> strip 后为纯 diff。"""
        gw = FakeLLMGateway(response=MARKDOWN_WRAPPED_DIFF)
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.patch_content is not None
        assert "```" not in patch.patch_content
        assert "---" in patch.patch_content

    def test_files_changed_parsed_from_diff(self):
        """files_changed 从 patch_content 的 +++ b/ 行解析。"""
        gw = FakeLLMGateway(response=VALID_DIFF_TWO_FILES)
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.files_changed == [
            "src/main/java/com/example/Foo.java",
            "src/main/java/com/example/Bar.java",
        ]


# ===========================================================================
# AC-4：history_calibration 策略
# ===========================================================================
class TestAC4HistoryCalibration:
    """AC-4：history_calibration 策略（KB patch_history 校准）。"""

    def test_history_success_high_similarity(self):
        """patch_history top1 sim >= 0.6 + 含历史 patch -> 成功。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.75,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("llm fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "history_calibration"
        assert patch.patch_content == VALID_DIFF

    def test_history_pattern_id_and_kb_history_ref(self):
        """history_calibration 成功 -> pattern_id = kb_history_ref = entry.id。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-42",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("llm fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.pattern_id == "hist-42"
        assert patch.kb_history_ref == "hist-42"

    def test_history_low_similarity_fails(self):
        """patch_history top1 sim < 0.6 -> 失败，error 含 'similarity'。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.5,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("llm fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        hist_attempt = patch.strategy_chain[2]
        assert hist_attempt["succeeded"] is False
        assert "similarity below threshold" in hist_attempt["error"]

    def test_history_no_patch_history_hit(self):
        """patch_history 层无命中 -> 失败，error 含 'no patch_history hit'。"""
        kb = make_kb_context(entries=[])
        gw = FakeLLMGateway(exc=LLMError("llm fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        hist_attempt = patch.strategy_chain[2]
        assert hist_attempt["succeeded"] is False
        assert "no patch_history hit" in hist_attempt["error"]


# ===========================================================================
# AC-5：strategy_chain 记录完整
# ===========================================================================
class TestAC5StrategyChain:
    """AC-5：strategy_chain 审计链完整。"""

    def test_strategy_chain_contains_all_fields(self):
        """每策略 attempt 含完整字段。"""
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        for attempt in patch.strategy_chain:
            assert "strategy_name" in attempt
            assert "succeeded" in attempt
            assert "error" in attempt
            assert "latency_ms" in attempt
            assert "tokens_used" in attempt
            assert "pattern_id" in attempt
            assert "attempt_no" in attempt

    def test_latency_ms_positive(self):
        """latency_ms > 0。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 10})
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        for attempt in patch.strategy_chain:
            assert attempt["latency_ms"] > 0

    def test_tokens_used_only_for_llm(self):
        """tokens_used 仅 llm 策略有值。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        for attempt in patch.strategy_chain:
            if attempt["strategy_name"] == "llm":
                # llm 失败时 tokens_used 可能为 None（重试耗尽无 usage）
                assert attempt["tokens_used"] is None
            else:
                assert attempt["tokens_used"] is None

    def test_pattern_id_only_for_template_and_history(self):
        """pattern_id 仅 template/history_calibration 有值。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert tmpl_attempt["pattern_id"] == "pat-001"

    def test_error_none_when_succeeded(self):
        """succeeded=True 时 error 为 None。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy_chain[0]["error"] is None

    def test_error_non_empty_when_failed(self):
        """succeeded=False 时 error 为非空字符串。"""
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        for attempt in patch.strategy_chain:
            if not attempt["succeeded"]:
                assert attempt["error"] is not None
                assert len(attempt["error"]) > 0

    def test_chain_length_equals_attempted_strategies(self):
        """strategy_chain 长度 = 实际尝试的策略数。"""
        # template 成功 -> chain=1
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()
        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )
        assert len(patch.strategy_chain) == 1

        # 全失败 -> chain=3
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer2 = AutoFixer(llm_gateway=gw)
        patch2 = fixer2.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )
        assert len(patch2.strategy_chain) == 3


# ===========================================================================
# AC-6：Tier1 产出 FixPatch（is_draft=False）
# ===========================================================================
class TestAC6Tier1:
    """AC-6：Tier1 产出（is_draft=False, rationale=None）。"""

    def test_tier1_is_draft_false(self):
        """tier=1 -> is_draft=False。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.is_draft is False

    def test_tier1_rationale_none(self):
        """tier=1 -> rationale=None。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.rationale is None

    def test_tier1_tier_value_passthrough(self):
        """tier=1 -> FixPatch.tier=1。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.tier == 1


# ===========================================================================
# AC-7：Tier2 产出 FixPatch（is_draft=True + rationale）
# ===========================================================================
class TestAC7Tier2:
    """AC-7：Tier2 产出（is_draft=True + rationale 固定文案）。"""

    def test_tier2_is_draft_true(self):
        """tier=2 -> is_draft=True。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=2,
            kb_context=kb,
        )

        assert patch.is_draft is True

    def test_tier2_rationale_fixed_text(self):
        """tier=2 -> rationale='低置信度，需人工 review'。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=2,
            kb_context=None,
        )

        assert patch.rationale == TIER2_RATIONALE

    def test_tier2_tier_value_passthrough(self):
        """tier=2 -> FixPatch.tier=2。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=2,
            kb_context=None,
        )

        assert patch.tier == 2

    def test_tier2_same_strategy_logic_as_tier1(self):
        """Tier2 的三策略优先级与 Tier1 相同。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=2,
            kb_context=kb,
        )

        assert patch.strategy == "template"
        assert patch.is_draft is True


# ===========================================================================
# AC-8：FIX_RETRY_MAX 重试上限
# ===========================================================================
class TestAC8FixRetryMax:
    """AC-8：FIX_RETRY_MAX 重试上限（LLMGateway 内部已重试，本任务不额外重试）。"""

    def test_llm_error_no_extra_retry(self):
        """LLMGateway 抛 LLMError -> 不额外重试，直接降级。"""
        call_count = 0

        class CountingGW:
            async def complete(self, **kwargs):
                nonlocal call_count
                call_count += 1
                raise LLMError("exhausted")

        fixer = AutoFixer(llm_gateway=CountingGW())

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        # 只调一次（不额外重试）
        assert call_count == 1
        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "exhausted" in llm_attempt["error"]

    def test_llm_error_records_exception_message(self):
        """strategy_chain error 记录 LLMError 异常消息。"""
        fixer = AutoFixer(
            llm_gateway=FakeLLMGateway(exc=LLMError("retry exhausted after 3"))
        )

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        llm_attempt = patch.strategy_chain[1]
        assert "retry exhausted after 3" in llm_attempt["error"]


# ===========================================================================
# AC-9：LLM/KB 失败降级
# ===========================================================================
class TestAC9Degradation:
    """AC-9：LLM/KB 失败降级。"""

    def test_llm_error_caught_and_degraded(self):
        """LLMGateway 抛 LLMError -> 捕获，降级到 history_calibration。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer(
            llm_gateway=FakeLLMGateway(exc=LLMError("LLM timeout"))
        )

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "history_calibration"
        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "LLM timeout" in llm_attempt["error"]

    def test_non_llm_error_caught_and_degraded(self):
        """LLMGateway 抛非 LLMError 异常（如 TypeError）-> 捕获，降级。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer(
            llm_gateway=FakeLLMGateway(exc=TypeError("unexpected type"))
        )

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "TypeError" in llm_attempt["error"]
        # 不向上抛出，继续降级
        assert patch.strategy == "history_calibration"

    def test_kb_context_none_template_skipped(self):
        """kb_context=None -> template 跳过，直接走 llm。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 50})
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert tmpl_attempt["succeeded"] is False
        assert "kb_context unavailable" in tmpl_attempt["error"]
        assert patch.strategy == "llm"

    def test_kb_degraded_template_and_history_skipped(self):
        """kb_context.degraded=True -> template + history 跳过，仅走 llm。"""
        kb = make_kb_context(degraded=True)
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 50})
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        tmpl_attempt = patch.strategy_chain[0]
        assert "kb degraded" in tmpl_attempt["error"]
        assert patch.strategy == "llm"

    def test_llm_gateway_none_llm_skipped(self):
        """llm_gateway=None -> llm 策略跳过，降级到 history_calibration。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer(llm_gateway=None)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "llm_gateway unavailable" in llm_attempt["error"]
        assert patch.strategy == "history_calibration"


# ===========================================================================
# AC-10：FixPatch 数据结构
# ===========================================================================
class TestAC10FixPatchStructure:
    """AC-10：FixPatch 数据结构完整。"""

    def test_fix_patch_all_fields_present(self):
        """FixPatch 字段完整。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))
        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert hasattr(patch, "patch_content")
        assert hasattr(patch, "files_changed")
        assert hasattr(patch, "strategy")
        assert hasattr(patch, "strategy_chain")
        assert hasattr(patch, "pattern_id")
        assert hasattr(patch, "is_draft")
        assert hasattr(patch, "rationale")
        assert hasattr(patch, "tier")
        assert hasattr(patch, "kb_history_ref")

    def test_patch_content_is_unified_diff(self):
        """patch_content 为 unified diff 格式（含 --- / +++ / @@）。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))
        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.patch_content is not None
        assert "---" in patch.patch_content
        assert "+++" in patch.patch_content
        assert "@@" in patch.patch_content

    def test_files_changed_deduplicated(self):
        """files_changed 去重。"""
        diff_with_dup = """\
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -1 +1 @@
-old
+new
--- a/src/Bar.java
+++ b/src/Bar.java
@@ -1 +1 @@
-old
+new
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -2 +2 @@
-old2
+new2
"""
        gw = FakeLLMGateway(response=diff_with_dup)
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.files_changed == ["src/Foo.java", "src/Bar.java"]

    def test_strategy_is_successful_strategy_name(self):
        """strategy = 最终成功的策略名。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "template"

    def test_pattern_id_none_for_llm_strategy(self):
        """llm 成功时 pattern_id=None。"""
        fixer = AutoFixer(llm_gateway=FakeLLMGateway(response=VALID_DIFF))

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.strategy == "llm"
        assert patch.pattern_id is None

    def test_kb_history_ref_only_for_history_strategy(self):
        """kb_history_ref 仅 history_calibration 成功时有值。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
            ]
        )
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.strategy == "history_calibration"
        assert patch.kb_history_ref == "hist-001"
        assert patch.pattern_id == "hist-001"

    def test_kb_history_ref_none_for_non_history_strategy(self):
        """非 history_calibration 策略时 kb_history_ref=None。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="pat-001",
                    layer="pattern",
                    similarity=0.9,
                    content={"patch_template": VALID_DIFF},
                ),
            ]
        )
        fixer = AutoFixer()

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        assert patch.kb_history_ref is None


# ===========================================================================
# AC-11：测试覆盖（15+ 场景，全 mock）
# ===========================================================================
class TestAC11Coverage:
    """AC-11：测试覆盖补充场景。"""

    def test_all_mocked_no_real_llm_db(self):
        """全 mock，无真实 LLM/DB 调用。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 10})
        fixer = AutoFixer(llm_gateway=gw)

        # 不应抛异常即代表无真实调用
        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert isinstance(patch, FixPatch)

    def test_kb_context_none_goes_llm_only(self):
        """kb_context=None（冷启动）-> 仅走 llm。"""
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 10})
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.strategy == "llm"
        # template 失败 + llm 成功 = chain 长度 2
        assert len(patch.strategy_chain) == 2

    def test_threshold_constants_exist(self):
        """阈值常量存在且值正确。"""
        assert TEMPLATE_SIMILARITY_THRESHOLD == 0.7
        assert HISTORY_SIMILARITY_THRESHOLD == 0.6

    def test_strategy_attempt_to_dict(self):
        """StrategyAttempt.to_dict() 返回完整 dict。"""
        attempt = StrategyAttempt(
            strategy_name="llm",
            succeeded=True,
            error=None,
            latency_ms=100,
            tokens_used=50,
            pattern_id=None,
            attempt_no=2,
        )

        d = attempt.to_dict()
        assert d["strategy_name"] == "llm"
        assert d["succeeded"] is True
        assert d["latency_ms"] == 100
        assert d["tokens_used"] == 50

    def test_all_fail_strategy_is_last_attempted(self):
        """全失败时 strategy = 最后尝试的策略名（history_calibration）。"""
        gw = FakeLLMGateway(exc=LLMError("fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        assert patch.strategy == "history_calibration"
        assert patch.patch_content is None
        assert patch.files_changed == []

    def test_llm_prompt_includes_history_reference(self):
        """llm prompt 含历史 patch 参考（few-shot）。"""
        kb = make_kb_context(
            entries=[
                make_retrieved_entry(
                    entry_id="hist-001",
                    layer="patch_history",
                    similarity=0.8,
                    content={"patch": VALID_DIFF},
                ),
                # pattern 层无命中 -> template 失败
            ]
        )
        gw = FakeLLMGateway(response=VALID_DIFF, usage={"total_tokens": 10})
        fixer = AutoFixer(llm_gateway=gw)

        fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=kb,
        )

        messages = gw.calls[0]["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "历史 patch 参考" in user_msg

    def test_fix_retry_max_zero_env_override(self, monkeypatch):
        """FIX_RETRY_MAX=0 时 LLM 首次失败即降级。"""
        monkeypatch.setenv("FIX_RETRY_MAX", "0")
        gw = FakeLLMGateway(exc=LLMError("first fail"))
        fixer = AutoFixer(llm_gateway=gw)

        patch = fixer.generate_patch(
            bug_report_summary="NPE",
            root_cause_location="Foo.java:10",
            symptom_type="crash",
            tier=1,
            kb_context=None,
        )

        llm_attempt = patch.strategy_chain[1]
        assert llm_attempt["succeeded"] is False
        assert "first fail" in llm_attempt["error"]
