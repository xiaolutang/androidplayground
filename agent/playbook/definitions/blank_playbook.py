"""白屏型 Playbook 占位骨架（R001-BF006）。

依据：analysis 5.x（崩溃型先跑通；其余 Playbook 定义已就位，调优待数据）。

MVP 阶段最小骨架：passive=True，hypothesis_space / signal_triggers 空。
后续据真实数据补全（analysis 第 922 行：第二/三/四/五个 Playbook 调优待数据）。
"""
from __future__ import annotations

from agent.playbook.schema import PlaybookDefinition

BLANK_PLAYBOOK = PlaybookDefinition(
    id="blank_v0",
    symptom_type="blank",
    passive=True,
    reproduce_steps=[],
    hypothesis_space=[],
    signal_triggers=[],
    metadata={"version": "0.1", "author": "system", "status": "skeleton"},
)


__all__ = ["BLANK_PLAYBOOK"]
