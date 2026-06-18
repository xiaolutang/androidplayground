"""PlaybookRegistry（R001-BF006，注册中心 + 按 symptom_type 检索）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Playbook 表 + 主流程 5.x
- 任务包 R001-BF006（register 自动验证；get_by_symptom / list_all / list_by_passive / load_builtin）

设计要点：
1. **纯内存注册中心**：本 registry 是进程内 dict 索引，不落库。
   启动时 ``load_builtin()`` 加载内置 Playbook（``definitions/``）；
   DB 持久化的历史 Playbook 由 SCH01 的 ``agent/schemas/playbook.py`` 负责，与本层解耦。
2. **symptom_type 为唯一键**（design 4.1 第 543 行：PK 索引）：
   register 重复 symptom_type 抛 ``ValueError``（fail-fast），防 BB003 路由歧义。
3. **register 自动 validate()**：启动期 fail-fast（D4 决策），
   非法 Playbook 定义直接阻止启动，而非运行时才发现。
4. **load_builtin() 返回新实例**：每次调用新建 registry 并注册全部内置 Playbook，
   便于测试隔离（每个测试用例独立 registry，无全局状态污染）。
"""
from __future__ import annotations

from agent.playbook.definitions import BUILTIN_PLAYBOOKS
from agent.playbook.schema import PlaybookDefinition


class PlaybookRegistry:
    """Playbook 注册中心（内存索引，按 symptom_type 检索）。

    启动时 ``load_builtin()`` 加载；业务层（BB003 PlaybookExecutor）通过
    ``get_by_symptom()`` 按 BugReport.symptom_type 路由到对应 Playbook。
    """

    def __init__(self) -> None:
        # symptom_type -> PlaybookDefinition（symptom_type 为 PK，唯一）
        self._by_symptom: dict[str, PlaybookDefinition] = {}

    def register(self, playbook: PlaybookDefinition) -> None:
        """注册一个 Playbook。

        启动期调用（``load_builtin`` 内 / 手动注册自定义 Playbook）。
        自动调 ``validate()``，非法定义抛 ``PlaybookValidationError``（fail-fast）。

        Args:
            playbook: 待注册的 PlaybookDefinition。

        Raises:
            PlaybookValidationError: 校验失败（必填缺失 / symptom_type 非法 / 格式错误）。
            ValueError: symptom_type 已存在（PK 冲突，防 BB003 路由歧义）。
        """
        playbook.validate()

        if playbook.symptom_type in self._by_symptom:
            existing = self._by_symptom[playbook.symptom_type]
            raise ValueError(
                f"symptom_type='{playbook.symptom_type}' 已注册 "
                f"(existing id='{existing.id}', new id='{playbook.id}')；"
                f"symptom_type 为 PK，不允许重复"
            )

        self._by_symptom[playbook.symptom_type] = playbook

    def get_by_symptom(self, symptom_type: str) -> PlaybookDefinition | None:
        """按 symptom_type 检索 Playbook。

        BB003 PlaybookExecutor 主路由入口：BugReport.symptom_type → Playbook。
        不存在返回 None（调用方应兜底降级处理）。

        Args:
            symptom_type: 症状类型（crash/blank/loading/no_response/data_error）。

        Returns:
            对应的 PlaybookDefinition；未注册返回 None。
        """
        return self._by_symptom.get(symptom_type)

    def list_all(self) -> list[PlaybookDefinition]:
        """列出全部已注册 Playbook。

        Returns:
            PlaybookDefinition 列表（注册顺序；非只读视图的浅拷贝，外部修改不影响内部）。
        """
        return list(self._by_symptom.values())

    def list_by_passive(self, passive: bool) -> list[PlaybookDefinition]:
        """按 passive 标志过滤 Playbook。

        BB003 据 passive 区分执行模式：
        - ``passive=True``（崩溃型）：被动等信号触发，不主动探测。
        - ``passive=False``（症状型）：主动诱发 + 探测。

        Args:
            passive: 过滤标志。

        Returns:
            符合 passive 条件的 PlaybookDefinition 列表。
        """
        return [pb for pb in self._by_symptom.values() if pb.passive == passive]

    def __len__(self) -> int:
        """已注册 Playbook 数量（测试断言用）。"""
        return len(self._by_symptom)

    def __contains__(self, symptom_type: object) -> bool:
        """是否已注册某 symptom_type（测试断言用）。"""
        return symptom_type in self._by_symptom


def load_builtin() -> PlaybookRegistry:
    """加载全部内置 Playbook，返回新 registry 实例。

    启动时调用（main.py / BB003 初始化）。
    每次调用新建 registry，无全局单例污染（便于测试隔离）。

    Returns:
        已注册全部内置 Playbook 的 PlaybookRegistry。

    Raises:
        PlaybookValidationError / ValueError: 内置 Playbook 定义有误（启动 fail-fast）。
    """
    registry = PlaybookRegistry()
    for playbook in BUILTIN_PLAYBOOKS:
        registry.register(playbook)
    return registry


__all__ = ["PlaybookRegistry", "load_builtin"]
