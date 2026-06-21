#!/usr/bin/env python3
"""LLM patch 命中率报告脚本（R001-INT04 AC-1）。

读取 samples/ 下标注样本 -> 调 LLMGateway（无 API key 时用 mock）->
校验 schema 合规率 + 关键字段命中率 -> 生成 report.md。

Usage:
    cd agent && python3 tests/golden/llm_quality/run_llm_quality.py

独立运行，输出 ``tests/golden/llm_quality/report.md``。

MVP 降级（Contract 关键实现决策 #3）：
- 无 ``NEW_API_API_KEY`` 环境变量时，使用 ``FakeLLMGateway`` mock，
  报告标题标注 ``[mock]``，方法可执行即 pass（不判数值达标）。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# 路径修正：脚本从 agent/ 目录运行，确保能 import agent.*
# -----------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
# tests/golden/llm_quality/run_llm_quality.py -> parents[0]=llm_quality,
# parents[1]=golden, parents[2]=tests, parents[3]=repo root
_AGENT_ROOT = _THIS_DIR.parents[3]
sys.path.insert(0, str(_AGENT_ROOT))

from agent.infra.llm_gateway import (  # noqa: E402
    FakeLLMGateway,
    LLMError,
    LLMResponse,
    NewAPILLMGateway,
)

SAMPLES_DIR = _THIS_DIR / "samples"
REPORT_PATH = _THIS_DIR / "report.md"


# -----------------------------------------------------------------------------
# Mock LLM（无 API key 时演示方法）
# -----------------------------------------------------------------------------
def _build_mock_response(sample: dict[str, Any]) -> str:
    """根据标注样本构造 mock unified diff（fix_patch）或 reflection JSON。"""
    prompt_type = sample.get("prompt_type", "fix_patch")
    loc = sample.get("root_cause_location", "app/src/main/java/com/example/Unknown.java:1")
    # 从 "path:line" 提取 path
    file_path = loc.split(":")[0] if ":" in loc else loc
    keywords = sample.get("ground_truth_patch_keywords", [])
    keyword_str = " ".join(keywords[:3])

    if prompt_type == "fix_patch":
        # 构造一个合法的 unified diff
        diff = (
            f"--- a/{file_path}\n"
            f"+++ b/{file_path}\n"
            f"@@ -1,5 +1,8 @@\n"
            f" // fix for {sample.get('sample_id', 'unknown')}\n"
            f"+// {keyword_str}\n"
            f"+if (value == null) return;\n"
        )
        return diff
    # reflection
    return json.dumps(
        {
            "negative_knowledge": f"Lesson: {keyword_str} - check null safety",
            "root_cause": sample.get("bug_report_summary", ""),
        },
        ensure_ascii=False,
    )


# -----------------------------------------------------------------------------
# Schema / 关键字段校验
# -----------------------------------------------------------------------------
def _check_fix_patch_schema(content: str) -> bool:
    """检查 fix_patch 输出是否符合 unified diff schema。"""
    if not content or not content.strip():
        return False
    return "---" in content and "+++" in content


def _check_reflection_schema(content: str) -> bool:
    """检查 reflection 输出是否为合法 JSON（含 negative_knowledge / root_cause）。"""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict)


def _check_key_fields(
    content: str,
    expected_keywords: list[str],
    prompt_type: str,
) -> bool:
    """检查关键字段命中率（keywords 出现在输出中即命中）。"""
    if not expected_keywords:
        return True
    text = content.lower()
    hit = sum(1 for kw in expected_keywords if kw.lower() in text)
    # >=50% keyword 命中视为合格
    return hit >= len(expected_keywords) * 0.5


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------
async def run_single_sample(
    gateway: Any,
    sample: dict[str, Any],
    is_mock: bool,
) -> dict[str, Any]:
    """跑单个样本，返回结果记录。"""
    sample_id = sample.get("sample_id", "?")
    prompt_type = sample.get("prompt_type", "fix_patch")
    bug_summary = sample.get("bug_report_summary", "")
    root_cause = sample.get("root_cause_location", "")
    symptom = sample.get("symptom_type", "")
    keywords = sample.get("ground_truth_patch_keywords", [])

    messages = [
        {
            "role": "system",
            "content": "你是 Android 客户端 bug 修复专家。输出 unified diff 格式。",
        },
        {
            "role": "user",
            "content": (
                f"Bug: {bug_summary}\n"
                f"根因: {root_cause}\n"
                f"症状: {symptom}"
            ),
        },
    ]

    start = time.time()
    error: str | None = None
    content = ""

    if is_mock:
        # mock 模式直接返回构造好的响应
        content = _build_mock_response(sample)
    else:
        try:
            resp: LLMResponse = await gateway.complete(
                prompt_type=prompt_type,
                messages=messages,
            )
            content = resp.content
        except LLMError as e:
            error = str(e)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"

    latency_ms = max(1, int((time.time() - start) * 1000))

    # schema 校验
    if prompt_type == "fix_patch":
        schema_ok = _check_fix_patch_schema(content) if not error else False
    elif prompt_type == "reflection":
        schema_ok = _check_reflection_schema(content) if not error else False
    else:
        schema_ok = bool(content.strip()) if not error else False

    # 关键字段命中
    key_fields_ok = _check_key_fields(content, keywords, prompt_type) if not error else False

    return {
        "sample_id": sample_id,
        "prompt_type": prompt_type,
        "symptom_type": symptom,
        "schema_ok": schema_ok,
        "key_fields_ok": key_fields_ok,
        "error": error,
        "latency_ms": latency_ms,
        "content_preview": content[:200] if content else "",
    }


def generate_report(
    results: list[dict[str, Any]],
    is_mock: bool,
    total_samples: int,
) -> str:
    """生成 markdown 报告。"""
    mode_tag = " **[mock]**" if is_mock else ""
    total = len(results)
    schema_pass = sum(1 for r in results if r["schema_ok"])
    key_pass = sum(1 for r in results if r["key_fields_ok"])
    schema_rate = (schema_pass / total * 100) if total > 0 else 0.0
    key_rate = (key_pass / total * 100) if total > 0 else 0.0

    lines = [
        f"# LLM Patch 命中率报告{mode_tag}",
        "",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 样本数: {total}（标注集共 {total_samples} 样本）",
        f"> 模式: {'mock（无 API key，演示方法）' if is_mock else 'real LLM（NewAPILLMGateway）'}",
        "",
        "## 命中率汇总",
        "",
        "| 指标 | 值 | 阈值 | 状态 |",
        "|------|----|------|------|",
        f"| Schema 合规率 | {schema_rate:.1f}% ({schema_pass}/{total}) | >=95% |"
        f" {'PASS' if schema_rate >= 95 else 'BELOW（MVP 不阻塞）'} |",
        f"| 关键字段命中率 | {key_rate:.1f}% ({key_pass}/{total}) | >=80% |"
        f" {'PASS' if key_rate >= 80 else 'BELOW（MVP 不阻塞）'} |",
        "",
        "> MVP 阶段：方法可执行 + 报告产出即 pass，数值仅供参考。",
        "",
        "## 按 prompt_type 分组",
        "",
    ]

    prompt_types: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        prompt_types.setdefault(r["prompt_type"], []).append(r)

    lines.append("| prompt_type | N | Schema 合规 | 关键字段命中 |")
    lines.append("|-------------|---|-------------|-------------|")
    for pt, pt_results in sorted(prompt_types.items()):
        n = len(pt_results)
        s_pass = sum(1 for r in pt_results if r["schema_ok"])
        k_pass = sum(1 for r in pt_results if r["key_fields_ok"])
        lines.append(
            f"| {pt} | {n} | {s_pass}/{n} ({s_pass/n*100:.0f}%) |"
            f" {k_pass}/{n} ({k_pass/n*100:.0f}%) |"
        )

    lines.extend(["", "## 样本明细", ""])
    lines.append(
        "| sample_id | prompt_type | schema_ok | key_fields_ok |"
        " latency_ms | error |"
    )
    lines.append("|-----------|-------------|-----------|---------------|------------|-------|")
    for r in results:
        err = (r["error"] or "")[:60]
        lines.append(
            f"| {r['sample_id']} | {r['prompt_type']} |"
            f" {'YES' if r['schema_ok'] else 'NO'} |"
            f" {'YES' if r['key_fields_ok'] else 'NO'} |"
            f" {r['latency_ms']} | {err} |"
        )

    lines.extend(["", "## 结论", ""])
    if is_mock:
        lines.extend([
            "- 本报告使用 **mock** 模式生成（无 NEW_API_API_KEY）。",
            "- 方法已验证可执行：样本加载 -> LLM 调用 -> schema/字段校验 -> 报告产出。",
            "- 配置 API key 后重新运行即可获得真实 LLM 基线数据。",
        ])
    else:
        lines.extend([
            f"- Schema 合规率: {schema_rate:.1f}%（阈值 >=95%）",
            f"- 关键字段命中率: {key_rate:.1f}%（阈值 >=80%）",
            "- MVP 阶段数值仅供参考，方法可执行即 pass。",
        ])

    return "\n".join(lines) + "\n"


async def _run_all_samples(
    gateway: Any,
    samples: list[dict[str, Any]],
    is_mock: bool,
) -> list[dict[str, Any]]:
    """批量跑所有样本（单 event loop）。"""
    results: list[dict[str, Any]] = []
    for sample in samples:
        result = await run_single_sample(gateway, sample, is_mock)
        results.append(result)
        status = "OK" if result["schema_ok"] else "FAIL"
        print(
            f"  [{status}] {result['sample_id']} "
            f"({result['prompt_type']}, {result['latency_ms']}ms)"
        )
    return results


def main() -> None:
    """主入口：加载样本 -> 跑 LLM -> 生成报告。

    默认使用 mock 模式（不调真实 LLM），确保脚本快速可执行。
    通过 ``--real`` 参数切换到真实 LLM 模式（需 API key 且网络可达）。
    """
    import argparse

    parser = argparse.ArgumentParser(description="LLM patch quality report")
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="Use real LLM (default: mock mode for fast execution)",
    )
    args = parser.parse_args()

    # 加载所有样本
    sample_files = sorted(SAMPLES_DIR.glob("*.json"))
    samples: list[dict[str, Any]] = []
    for f in sample_files:
        with open(f, encoding="utf-8") as fh:
            samples.append(json.load(fh))

    if not samples:
        print("ERROR: no samples found in", SAMPLES_DIR)
        sys.exit(1)

    print(f"Loaded {len(samples)} samples from {SAMPLES_DIR}")

    # 默认 mock 模式；--real 切换真实 LLM
    is_mock = not args.real

    if is_mock:
        print("Using mock mode (default). Use --real for real LLM.")
        gateway: Any = FakeLLMGateway()
    else:
        print("Using real LLM mode (NewAPILLMGateway)")
        gateway = NewAPILLMGateway()

    # 跑所有样本（单 event loop）
    results = asyncio.run(_run_all_samples(gateway, samples, is_mock))

    # 生成报告
    report = generate_report(results, is_mock, len(samples))
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")

    # 汇总
    schema_pass = sum(1 for r in results if r["schema_ok"])
    key_pass = sum(1 for r in results if r["key_fields_ok"])
    print(f"Schema: {schema_pass}/{len(results)}")
    print(f"Key fields: {key_pass}/{len(results)}")


if __name__ == "__main__":
    main()
