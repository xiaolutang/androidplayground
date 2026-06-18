"""Playbook 注册中心（R001-BF006）。

能力层（BF006）：内置方法论模板的加载 + 校验 + 按 symptom_type 检索。
- schema.py：``PlaybookDefinition``（运行时定义）+ ``validate()`` + ``PlaybookValidationError``
- registry.py：``PlaybookRegistry``（register / get_by_symptom / list_all / list_by_passive）
              + ``load_builtin()``（启动时加载全部内置 Playbook）
- definitions/：5 类症状的内置 Playbook（crash 完整实现，其余占位骨架）

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Playbook 表 + 5.x 主流程
- 任务包 R001-BF006

下游消费者：
- BB003 PlaybookExecutor：``get_by_symptom`` 路由 + ``passive`` 区分执行模式
- BB004 HypothesisEngine：``hypothesis_space`` 假设种子
- BF002 ReproduceRunner：``reproduce_steps`` 复现脚本
- BF003/BF004 信号层：``signal_triggers`` 信号关键字触发
"""
from __future__ import annotations

from agent.playbook.definitions import (
    BUILTIN_PLAYBOOKS,
    BLANK_PLAYBOOK,
    CRASH_PLAYBOOK,
    DATA_ERROR_PLAYBOOK,
    LOADING_PLAYBOOK,
    NO_RESPONSE_PLAYBOOK,
)
from agent.playbook.registry import PlaybookRegistry, load_builtin
from agent.playbook.schema import (
    VALID_SYMPTOM_TYPES,
    PlaybookDefinition,
    PlaybookValidationError,
)

__all__ = [
    # schema
    "PlaybookDefinition",
    "PlaybookValidationError",
    "VALID_SYMPTOM_TYPES",
    # registry
    "PlaybookRegistry",
    "load_builtin",
    # definitions
    "BUILTIN_PLAYBOOKS",
    "CRASH_PLAYBOOK",
    "BLANK_PLAYBOOK",
    "LOADING_PLAYBOOK",
    "NO_RESPONSE_PLAYBOOK",
    "DATA_ERROR_PLAYBOOK",
]
