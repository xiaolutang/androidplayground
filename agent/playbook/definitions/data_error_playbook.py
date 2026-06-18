"""数据错误型 Playbook 占位骨架（R001-BF006）。

依据：analysis 5.x（崩溃型先跑通；其余 Playbook 定义已就位，调优待数据）。

MVP 阶段最小骨架：passive=True，hypothesis_space / signal_triggers 空。
"""
from __future__ import annotations

from agent.playbook.schema import PlaybookDefinition

DATA_ERROR_PLAYBOOK = PlaybookDefinition(
    id="data_error_v0",
    symptom_type="data_error",
    passive=True,
    reproduce_steps=[],
    hypothesis_space=[],
    signal_triggers=[],
    metadata={"version": "0.1", "author": "system", "status": "skeleton"},
)


__all__ = ["DATA_ERROR_PLAYBOOK"]
