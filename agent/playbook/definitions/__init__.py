"""内置 Playbook 定义集合（R001-BF006）。

5 类症状各一份 Playbook（design 4.1 第 543 行：symptom_type 为 PK 索引）：
- crash：崩溃型（passive=True，已完整实现）
- blank / loading / no_response / data_error：占位骨架（调优待数据）

registry.load_builtin() 通过本模块导入全部内置 Playbook。
"""
from __future__ import annotations

from agent.playbook.definitions.blank_playbook import BLANK_PLAYBOOK
from agent.playbook.definitions.crash_playbook import CRASH_PLAYBOOK
from agent.playbook.definitions.data_error_playbook import DATA_ERROR_PLAYBOOK
from agent.playbook.definitions.loading_playbook import LOADING_PLAYBOOK
from agent.playbook.definitions.no_response_playbook import NO_RESPONSE_PLAYBOOK
from agent.playbook.schema import PlaybookDefinition

# 全部内置 Playbook（顺序即注册顺序；crash 放首位便于 load_builtin 测试断言）
BUILTIN_PLAYBOOKS: list[PlaybookDefinition] = [
    CRASH_PLAYBOOK,
    BLANK_PLAYBOOK,
    LOADING_PLAYBOOK,
    NO_RESPONSE_PLAYBOOK,
    DATA_ERROR_PLAYBOOK,
]

__all__ = [
    "BUILTIN_PLAYBOOKS",
    "CRASH_PLAYBOOK",
    "BLANK_PLAYBOOK",
    "LOADING_PLAYBOOK",
    "NO_RESPONSE_PLAYBOOK",
    "DATA_ERROR_PLAYBOOK",
]
