"""Playbook Schema（R001-BF006，方法论层运行时定义）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Playbook 表（第 539-550 行）
- 任务包 R001-BF006（Schema 校验；按 symptom_type 检索；崩溃型 passive=true 可加载）
- D4

设计要点：
1. **与 SCH01 的 DB Schema 解耦**：``agent/schemas/playbook.py`` 是 SQLAlchemy ORM（持久化层），
   本模块是 **运行时 Playbook 定义**（pydantic BaseModel），供 registry 加载内置 Playbook。
   两者字段对齐 design 4.1，但职责不同：DB Schema 存历史排查沉淀的 Playbook；
   本 schema 定义进程启动时加载的内置方法论模板（crash/blank/...）。
   任务包 BF006 明确要求 ``PlaybookDefinition`` + ``validate()`` 方法 + 自定义异常，
   pydantic 的声明式字段 + ``model_config = extra="forbid"`` 保证未知字段被拒。
2. **symptom_type 为主键**（design 4.1 第 543 行：str(PK 索引)），5 类各一份。
   字段名沿用任务包指定：``reproduce_steps`` / ``hypothesis_space`` / ``signal_triggers``
   （对应 design 4.1 的 detection_actions / root_cause_hypothesis_space / judgment_signals 的
   运行时消费视角——BF002 消费 reproduce_steps，BB003 消费 signal_triggers，BB004 消费 hypothesis_space）。
3. **validate() 显式入口**：``register()`` 启动时调用，统一抛 ``PlaybookValidationError``，
   把 pydantic 的 ``ValidationError`` 包成领域异常，调用方无需 import pydantic。
4. **reproduce_steps 格式**：每个 step 是 dict，必含 ``action`` 键（BF002 消费的脚本入口）。
   BF002 ``run_reproduce`` 消费契约为 ``action`` + ``params``（可选 dict）+ ``expected_signal``
  （可选 dict，含 ``pattern`` 正则/关键字）；``action`` 必须在 BF002 dispatch 表内
  （tap/swipe/input/press/back/screenshot/wait）。schema 层只保证 ``action`` 存在，
   ``params`` / ``expected_signal`` 由 BF002 运行时解释。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PlaybookValidationError(Exception):
    """Playbook 校验失败（领域异常）。

    包装 pydantic ``ValidationError``，调用方无需依赖 pydantic 类型。
    register() 时抛出 → 启动失败 fail-fast（D4 决策：启动期校验）。
    """


# 5 类症状枚举（design 4.1 第 543 行：crash/blank/loading/no_response/data_error）
VALID_SYMPTOM_TYPES: tuple[str, ...] = (
    "crash",
    "blank",
    "loading",
    "no_response",
    "data_error",
)


class PlaybookDefinition(BaseModel):
    """运行时 Playbook 定义（内置方法论模板）。

    字段对应任务包 BF006 规格与 design 4.1 Playbook 表：
    - ``id``：Playbook 唯一标识（如 ``"crash_v1"``）。
    - ``symptom_type``：5 类症状之一（PK 索引）。
    - ``passive``：崩溃型=被动等信号（True）；症状型=主动探测（False）。
    - ``reproduce_steps``：复现脚本（BF002 消费），每步必含 ``action`` 键，
      BF002 消费 ``action`` + ``params`` + ``expected_signal`` 三键。
    - ``hypothesis_space``：假设种子（BB004 消费），每条必含 ``text`` 键。
    - ``signal_triggers``：信号关键字触发（BB003 消费）。
    - ``metadata``：版本、作者等（非业务字段）。

    pydantic 配置：
    - ``extra="forbid"``：未知字段直接拒绝（防 typo 写错字段名）。
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: str = Field(..., min_length=1, description="Playbook 唯一标识")
    symptom_type: str = Field(..., description="5 类症状之一（crash/blank/loading/no_response/data_error）")
    passive: bool = Field(..., description="被动等信号(True)/主动探测(False)")
    reproduce_steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="复现脚本，每个 step 必含 'action' 键；BF002 消费 action+params+expected_signal",
    )
    hypothesis_space: list[dict[str, Any]] = Field(
        default_factory=list,
        description="假设种子，每条必含 'text' 键（BB004 消费）",
    )
    signal_triggers: list[str] = Field(
        default_factory=list,
        description="信号关键字触发列表（BB003 消费）",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="版本、作者等非业务元信息",
    )

    def validate(self) -> "PlaybookDefinition":
        """显式校验入口（register 时调用）。

        校验内容：
        1. pydantic 字段类型 / 必填（``model_validate`` 重新跑一遍）。
        2. ``symptom_type`` 在 ``VALID_SYMPTOM_TYPES`` 枚举内。
        3. 每个 ``reproduce_steps[*]`` 含 ``action`` 键（BF002 消费契约）。
        4. 每个 ``hypothesis_space[*]`` 含 ``text`` 键（BB004 消费契约）。

        Raises:
            PlaybookValidationError: 任一校验失败。

        Returns:
            self（校验通过后返回自身，便于链式调用）。
        """
        try:
            # 重新跑一遍 pydantic 校验（捕获构造期漏网的场景，如直接 __dict__ 篡改）
            PlaybookDefinition.model_validate(self.model_dump())
        except ValidationError as exc:
            raise PlaybookValidationError(
                f"Playbook '{getattr(self, 'id', '<unknown>')}' pydantic 校验失败: {exc}"
            ) from exc

        if self.symptom_type not in VALID_SYMPTOM_TYPES:
            raise PlaybookValidationError(
                f"Playbook '{self.id}' symptom_type='{self.symptom_type}' 非法，"
                f"合法值: {VALID_SYMPTOM_TYPES}"
            )

        for idx, step in enumerate(self.reproduce_steps):
            if "action" not in step:
                raise PlaybookValidationError(
                    f"Playbook '{self.id}' reproduce_steps[{idx}] 缺少 'action' 键"
                )

        for idx, hyp in enumerate(self.hypothesis_space):
            if "text" not in hyp:
                raise PlaybookValidationError(
                    f"Playbook '{self.id}' hypothesis_space[{idx}] 缺少 'text' 键"
                )

        return self


__all__ = [
    "PlaybookDefinition",
    "PlaybookValidationError",
    "VALID_SYMPTOM_TYPES",
]
