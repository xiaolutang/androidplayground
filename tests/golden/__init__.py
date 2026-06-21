"""Golden set 测试包（R001-INT04）。

三类 golden 报告：
- llm_quality: LLM patch 命中率报告
- confidence: 置信度校准报告
- vision: 视觉决策 golden 报告

所有 golden 测试标记 ``@pytest.mark.golden``，需 ``--run-golden`` 显式触发。
"""
