"""PlaybookRegistry + Schema 单元测试（R001-BF006）。

覆盖：
1. schema: validate（valid / missing_id / invalid_symptom / invalid_reproduce_steps / invalid_hypothesis）
2. registry: register_and_get / get_not_found / list_all / list_by_passive / register_invalid_raises /
             register_duplicate_symptom_raises
3. crash_playbook: schema_valid / passive_true / has_signal_triggers / has_hypothesis_space
4. load_builtin: includes_crash / count / all_valid

纯单元测试：registry 是内存索引，无 DB 依赖，无需 Testcontainers。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.playbook.definitions.crash_playbook import CRASH_PLAYBOOK
from agent.playbook.registry import PlaybookRegistry, load_builtin
from agent.playbook.schema import (
    VALID_SYMPTOM_TYPES,
    PlaybookDefinition,
    PlaybookValidationError,
)


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------
def _make_valid(**overrides) -> PlaybookDefinition:
    """构造一个合法 PlaybookDefinition（测试用）。"""
    base = dict(
        id="test_crash",
        symptom_type="crash",
        passive=True,
        reproduce_steps=[{"action": "restart_app"}],
        hypothesis_space=[{"text": "NPE 假设"}],
        signal_triggers=["FATAL EXCEPTION"],
        metadata={"version": "test"},
    )
    base.update(overrides)
    return PlaybookDefinition(**base)


# ---------------------------------------------------------------------------
# schema.validate()
# ---------------------------------------------------------------------------
class TestSchemaValidate:
    """PlaybookDefinition.validate() 校验。"""

    def test_validate_valid(self) -> None:
        """合法 Playbook validate 通过并返回 self。"""
        pb = _make_valid()
        result = pb.validate()
        assert result is pb

    def test_validate_missing_id(self) -> None:
        """缺 id（pydantic 必填）→ PlaybookValidationError。"""
        # 直接构造会抛 ValidationError（pydantic 必填拦截）
        with pytest.raises(ValidationError):
            PlaybookDefinition(symptom_type="crash", passive=True)  # type: ignore[call-arg]

    def test_validate_empty_id(self) -> None:
        """id 为空串 → 构造期 ValidationError（pydantic min_length=1 拦截）。

        pydantic 在 __init__ 阶段就校验 min_length，故空 id 在构造时即抛
        ValidationError（而非 validate() 阶段包成 PlaybookValidationError）。
        这也是 fail-fast 的体现：非法定义无法构造出实例。
        """
        with pytest.raises(ValidationError, match="string_too_short"):
            _make_valid(id="")

    def test_validate_invalid_symptom(self) -> None:
        """symptom_type 不在枚举 → PlaybookValidationError。"""
        pb = _make_valid(symptom_type="unknown_symptom")
        with pytest.raises(PlaybookValidationError, match="symptom_type='unknown_symptom' 非法"):
            pb.validate()

    def test_validate_invalid_reproduce_steps_missing_action(self) -> None:
        """reproduce_steps 缺 action 键 → PlaybookValidationError。"""
        pb = _make_valid(
            reproduce_steps=[{"step": "no_action_key"}],  # 缺 action
        )
        with pytest.raises(PlaybookValidationError, match="reproduce_steps\\[0\\] 缺少 'action' 键"):
            pb.validate()

    def test_validate_invalid_hypothesis_missing_text(self) -> None:
        """hypothesis_space 缺 text 键 → PlaybookValidationError。"""
        pb = _make_valid(
            hypothesis_space=[{"desc": "no_text_key"}],  # 缺 text
        )
        with pytest.raises(PlaybookValidationError, match="hypothesis_space\\[0\\] 缺少 'text' 键"):
            pb.validate()

    def test_validate_extra_field_forbidden(self) -> None:
        """未知字段 extra=forbid → ValidationError。"""
        with pytest.raises(ValidationError):
            PlaybookDefinition(  # type: ignore[call-arg]
                id="x",
                symptom_type="crash",
                passive=True,
                unknown_field="should_be_rejected",
            )

    def test_valid_symptom_types_complete(self) -> None:
        """VALID_SYMPTOM_TYPES 覆盖 design 4.1 的 5 类症状。"""
        assert VALID_SYMPTOM_TYPES == (
            "crash",
            "blank",
            "loading",
            "no_response",
            "data_error",
        )


# ---------------------------------------------------------------------------
# PlaybookRegistry
# ---------------------------------------------------------------------------
class TestRegistry:
    """PlaybookRegistry 注册与检索。"""

    def test_register_and_get(self) -> None:
        """register 后 get_by_symptom 能取回。"""
        reg = PlaybookRegistry()
        pb = _make_valid()
        reg.register(pb)
        got = reg.get_by_symptom("crash")
        assert got is pb

    def test_get_by_symptom_not_found(self) -> None:
        """未注册的 symptom_type 返回 None。"""
        reg = PlaybookRegistry()
        assert reg.get_by_symptom("crash") is None

    def test_list_all_empty(self) -> None:
        """空 registry list_all 返回 []。"""
        reg = PlaybookRegistry()
        assert reg.list_all() == []

    def test_list_all_after_register(self) -> None:
        """注册后 list_all 返回全部。"""
        reg = PlaybookRegistry()
        pb1 = _make_valid(id="pb1", symptom_type="crash")
        pb2 = _make_valid(id="pb2", symptom_type="blank")
        reg.register(pb1)
        reg.register(pb2)
        all_pbs = reg.list_all()
        assert len(all_pbs) == 2
        assert pb1 in all_pbs
        assert pb2 in all_pbs

    def test_list_by_passive_true(self) -> None:
        """list_by_passive(True) 只返回 passive=True 的。"""
        reg = PlaybookRegistry()
        reg.register(_make_valid(id="p1", symptom_type="crash", passive=True))
        reg.register(_make_valid(id="p2", symptom_type="blank", passive=False))
        passive_list = reg.list_by_passive(True)
        assert len(passive_list) == 1
        assert passive_list[0].id == "p1"

    def test_list_by_passive_false(self) -> None:
        """list_by_passive(False) 只返回 passive=False 的。"""
        reg = PlaybookRegistry()
        reg.register(_make_valid(id="p1", symptom_type="crash", passive=True))
        reg.register(_make_valid(id="p2", symptom_type="blank", passive=False))
        active_list = reg.list_by_passive(False)
        assert len(active_list) == 1
        assert active_list[0].id == "p2"

    def test_register_invalid_raises(self) -> None:
        """register 非法 Playbook 抛 PlaybookValidationError（fail-fast）。"""
        reg = PlaybookRegistry()
        bad = _make_valid(symptom_type="invalid")
        with pytest.raises(PlaybookValidationError, match="symptom_type='invalid' 非法"):
            reg.register(bad)
        # 校验失败不应进入 registry
        assert len(reg) == 0

    def test_register_duplicate_symptom_raises(self) -> None:
        """重复 symptom_type 抛 ValueError（PK 冲突）。"""
        reg = PlaybookRegistry()
        reg.register(_make_valid(id="first", symptom_type="crash"))
        with pytest.raises(ValueError, match="symptom_type='crash' 已注册"):
            reg.register(_make_valid(id="second", symptom_type="crash"))
        # 第二个未注册
        assert len(reg) == 1

    def test_contains_and_len(self) -> None:
        """__contains__ / __len__ 辅助断言。"""
        reg = PlaybookRegistry()
        assert "crash" not in reg
        assert len(reg) == 0
        reg.register(_make_valid())
        assert "crash" in reg
        assert len(reg) == 1


# ---------------------------------------------------------------------------
# CRASH_PLAYBOOK
# ---------------------------------------------------------------------------
class TestCrashPlaybook:
    """崩溃型 Playbook（BF006 第一个完整实现）。"""

    def test_crash_playbook_schema_valid(self) -> None:
        """CRASH_PLAYBOOK 自身 validate 通过。"""
        result = CRASH_PLAYBOOK.validate()
        assert result is CRASH_PLAYBOOK

    def test_crash_playbook_passive_true(self) -> None:
        """崩溃型 passive=True（被动等信号）。"""
        assert CRASH_PLAYBOOK.passive is True

    def test_crash_playbook_symptom_type(self) -> None:
        """symptom_type='crash'。"""
        assert CRASH_PLAYBOOK.symptom_type == "crash"

    def test_crash_playbook_has_signal_triggers(self) -> None:
        """signal_triggers 覆盖 FATAL EXCEPTION / SIGSEGV / ANR。"""
        triggers = CRASH_PLAYBOOK.signal_triggers
        assert "FATAL EXCEPTION" in triggers
        assert "SIGSEGV" in triggers
        assert "ANR" in triggers
        assert len(triggers) >= 3

    def test_crash_playbook_has_hypothesis_space(self) -> None:
        """hypothesis_space 含 4 类崩溃假设种子（NPE/OOM/ANR/native）。"""
        hyps = CRASH_PLAYBOOK.hypothesis_space
        assert len(hyps) == 4
        texts = " ".join(h["text"] for h in hyps)
        assert "NullPointerException" in texts
        assert "OutOfMemoryError" in texts
        assert "ANR" in texts
        assert "Native crash" in texts
        # 每条含 expected_signal（可证伪信号，BB004 消费）
        for h in hyps:
            assert "expected_signal" in h

    def test_crash_playbook_reproduce_steps_has_action(self) -> None:
        """reproduce_steps 每步含 action 键（BF002 消费契约）。"""
        for step in CRASH_PLAYBOOK.reproduce_steps:
            assert "action" in step

    def test_crash_playbook_reproduce_steps_align_bf002(self) -> None:
        """reproduce_steps 字段名对齐 BF002 run_reproduce 消费契约。

        BF002 消费 step['action'] + step['params'] + step['expected_signal']；
        action 必须在 BF002 dispatch 表内（tap/swipe/input/press/back/screenshot/wait）。
        断言 crash_playbook 不用已废弃的 args/expect 键名。
        """
        bf002_actions = {"tap", "swipe", "input", "press", "back", "screenshot", "wait"}
        for step in CRASH_PLAYBOOK.reproduce_steps:
            assert step["action"] in bf002_actions, (
                f"action='{step['action']}' 不在 BF002 dispatch 表，BF002 会抛 ValueError"
            )
            assert "args" not in step, "应用 'params' 而非 'args'（BF002 消费 params）"
            assert "expect" not in step, "应用 'expected_signal' 而非 'expect'（BF002 消费 expected_signal）"

    def test_crash_playbook_metadata(self) -> None:
        """metadata 含 version / author。"""
        assert CRASH_PLAYBOOK.metadata["version"] == "1.0"
        assert CRASH_PLAYBOOK.metadata["author"] == "system"


# ---------------------------------------------------------------------------
# load_builtin
# ---------------------------------------------------------------------------
class TestLoadBuiltin:
    """load_builtin() 启动期加载全部内置 Playbook。"""

    def test_load_builtin_returns_registry(self) -> None:
        """load_builtin 返回 PlaybookRegistry 实例。"""
        reg = load_builtin()
        assert isinstance(reg, PlaybookRegistry)

    def test_load_builtin_includes_crash(self) -> None:
        """加载后 crash 可按 symptom_type 检索到。"""
        reg = load_builtin()
        crash = reg.get_by_symptom("crash")
        assert crash is not None
        assert crash.id == "crash_v1"

    def test_load_builtin_count(self) -> None:
        """加载全部 5 类症状 Playbook（design 4.1 第 543 行：5 类 PK）。"""
        reg = load_builtin()
        assert len(reg) == 5
        # 每类症状都有对应 Playbook
        for st in VALID_SYMPTOM_TYPES:
            assert st in reg, f"symptom_type='{st}' 未加载"

    def test_load_builtin_all_valid(self) -> None:
        """全部内置 Playbook 都能通过 validate（启动期不应 fail-fast）。"""
        reg = load_builtin()
        for pb in reg.list_all():
            # validate() 不抛异常即通过
            assert pb.validate() is pb

    def test_load_builtin_independent_instances(self) -> None:
        """每次 load_builtin 返回独立 registry（无全局污染）。"""
        reg1 = load_builtin()
        reg2 = load_builtin()
        assert reg1 is not reg2
        # 在 reg1 注册不影响 reg2（虽然 builtin 已满，这里测隔离性用空 registry）
        empty1 = PlaybookRegistry()
        empty2 = PlaybookRegistry()
        empty1.register(_make_valid())
        assert len(empty1) == 1
        assert len(empty2) == 0
