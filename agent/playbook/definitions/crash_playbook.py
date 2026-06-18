"""崩溃型 Playbook（R001-BF006，第一个内置 Playbook）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Playbook 表 + 5.x 主流程
- 任务包 R001-BF006（崩溃型 passive=true，含 NPE/OOM/ANR/native crash 假设种子）

设计要点：
1. **passive=True**（design 4.1 第 550 行）：崩溃型被动等信号，不主动探测。
   崩溃本身即强信号（FATAL EXCEPTION / SIGSEGV / ANR），无需主动诱发；
   BB003 收到信号后从 hypothesis_space 取种子启动假设树推理。
2. **reproduce_steps 最小化**：被动型不主动复现，保留一个 ``wait`` 最小脚本作为 BF002 兜底
  （BF002 ``run_reproduce`` 消费 ``action`` + ``params`` + ``expected_signal``，
   action 必须在 BF002 dispatch 表内：tap/swipe/input/press/back/screenshot/wait）。
   崩溃型等信号即用 ``wait``，不主动诱发。
3. **hypothesis_space 覆盖 4 类崩溃**（NPE / OOM / ANR / native crash），
   每条含 ``text``（假设文本）+ ``expected_signal``（可证伪信号，BB004 消费）。
4. **signal_triggers 对齐 BF004 信号监听器**：FATAL EXCEPTION（logcat）/
   SIGSEGV（native crash，tombstone）/ ANR（process_listener）。
"""
from __future__ import annotations

from agent.playbook.schema import PlaybookDefinition

CRASH_PLAYBOOK = PlaybookDefinition(
    id="crash_v1",
    symptom_type="crash",
    passive=True,
    # 被动型：wait 等 crash 信号（BF002 兜底，action 必须在 dispatch 表内）
    reproduce_steps=[
        {
            "action": "wait",
            "params": {"duration_ms": 30000},
            "expected_signal": {
                "pattern": "FATAL EXCEPTION|SIGSEGV|ANR",
                "signal_type": "logcat",
            },
        },
    ],
    # 4 类崩溃假设种子（BB004 消费，启动假设树推理）
    hypothesis_space=[
        {
            "text": "NullPointerException：空对象引用，常见于异步回调后 UI 已销毁",
            "expected_signal": {
                "log_pattern": "java.lang.NullPointerException",
                "stacktrace_contains": "at ${PACKAGE_NAME}.",
            },
        },
        {
            "text": "OutOfMemoryError：堆内存耗尽（OOM），常见于大图/Bitmap/内存泄漏",
            "expected_signal": {
                "log_pattern": "java.lang.OutOfMemoryError",
                "heap_dump": "可能触发 hprof 自动 dump",
            },
        },
        {
            "text": "ANR：主线程阻塞超 5s（Input dispatching timed out / Broadcast queue）",
            "expected_signal": {
                "log_pattern": "ANR in ${PACKAGE_NAME}",
                "traces_file": "/data/anr/traces.txt",
            },
        },
        {
            "text": "Native crash：SIGSEGV/SIGABRT，常见于 NDK 库 / JNI / 第三方 so",
            "expected_signal": {
                "log_pattern": "SIGSEGV",
                "tombstone": "/data/tombstones/tombstone_*",
            },
        },
    ],
    # 对齐 BF004 信号监听器（logcat_listener / process_listener）
    signal_triggers=["FATAL EXCEPTION", "SIGSEGV", "ANR"],
    metadata={"version": "1.0", "author": "system"},
)


__all__ = ["CRASH_PLAYBOOK"]
