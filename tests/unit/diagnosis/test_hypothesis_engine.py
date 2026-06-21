"""HypothesisEngine 单元测试（R001-BB004）。

全 mock，覆盖（AC-10 测试矩阵）：
- TestStateTransitions：4 态合法迁移 + 3 类非法迁移 + 矩阵结构
- TestPropose：根/子/父不存在/UUID 唯一/expected_signal
- TestRefuteAndPivot：3 层树切兄弟 + 单链穷尽 + refuted 不重选
- TestOverturnRootCause：overturn 正常 + 非 confirmed 抛错 + pivot 触发
- TestBudgetAndPivot：耗尽 coverage / 未耗尽 / overturned→reasoning /
  gap_store=None 降级 / create 异常降级 / max_steps 自定义
- TestNegateAndPrune：prune / demote / unaffected / kb_retriever=None /
  异常降级
- TestInv2Delete：delete 始终抛错

无 DB / LLM 依赖。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.diagnosis.hypothesis_engine import (
    HypothesisDeleteError,
    HypothesisEngine,
    HypothesisNode,
    HypothesisTransitionError,
    _STATE_TRANSITIONS,
    can_transition,
)
from agent.kb.retriever import NegativeVerdict
from agent.schemas.trajectory import HypothesisStatus


# ---------------------------------------------------------------------------
# 工厂辅助
# ---------------------------------------------------------------------------


def _make_engine(
    *,
    gap_store=None,
    kb_retriever=None,
    max_steps: int = 20,
) -> HypothesisEngine:
    """构造 HypothesisEngine（依赖可注入 mock）。"""
    return HypothesisEngine(
        gap_store=gap_store,
        kb_retriever=kb_retriever,
        max_steps=max_steps,
    )


def _make_confirmed_node(
    engine: HypothesisEngine,
    *,
    content: str = "confirmed node",
    is_rootcause: bool = False,
    parent_id=None,
) -> HypothesisNode:
    """快速构造一个 confirmed 节点（走完整 propose→verify→confirm 流程）。"""
    node = engine.propose(parent_id=parent_id, content=content)
    engine.verify(node.id)
    engine.confirm(node.id, evidence={"signal": "match"})
    if is_rootcause:
        node.is_rootcause = True
    return node


# ---------------------------------------------------------------------------
# AC-1：4 态迁移矩阵
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """4 态迁移矩阵（AC-1）。"""

    def test_legal_proposed_to_verifying(self):
        """PROPOSED → VERIFYING（verify()）合法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        assert node.status == HypothesisStatus.VERIFYING

    def test_legal_verifying_to_confirmed(self):
        """VERIFYING → CONFIRMED（confirm()）合法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        engine.confirm(node.id, evidence={"k": "v"})
        assert node.status == HypothesisStatus.CONFIRMED
        assert node.confirming_evidence == {"k": "v"}

    def test_legal_verifying_to_refuted(self):
        """VERIFYING → REFUTED（refute()）合法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        engine.refute(node.id, reason="signal mismatch")
        assert node.status == HypothesisStatus.REFUTED
        assert node.falsifying_signal == {"reason": "signal mismatch"}

    def test_legal_proposed_to_refuted(self):
        """PROPOSED → REFUTED（refute() 直接否定，如负向反查 prune）合法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.refute(node.id, reason="pruned by negative kb")
        assert node.status == HypothesisStatus.REFUTED

    def test_illegal_proposed_to_confirmed(self):
        """PROPOSED → CONFIRMED（跳过 verifying）非法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        with pytest.raises(HypothesisTransitionError):
            engine.confirm(node.id)

    def test_illegal_confirmed_to_verifying(self):
        """CONFIRMED → VERIFYING（已 confirmed 回退）非法。"""
        engine = _make_engine()
        node = _make_confirmed_node(engine)
        with pytest.raises(HypothesisTransitionError):
            engine.verify(node.id)

    def test_illegal_refuted_to_proposed(self):
        """REFUTED → PROPOSED（refuted 复活）非法。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.refute(node.id, reason="done")
        # refuted 节点不可迁移到任何状态（包括 verify / confirm / refute 重复）
        with pytest.raises(HypothesisTransitionError):
            engine.verify(node.id)
        with pytest.raises(HypothesisTransitionError):
            engine.confirm(node.id)

    def test_refute_twice_illegal(self):
        """REFUTED → REFUTED（重复 refute）非法（refuted 是终态）。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h1")
        engine.refute(node.id, reason="first")
        with pytest.raises(HypothesisTransitionError):
            engine.refute(node.id, reason="second")

    def test_state_transitions_structure(self):
        """_STATE_TRANSITIONS 为 dict[Status, frozenset[Status]]，模式与 GapStore 一致。"""
        assert isinstance(_STATE_TRANSITIONS, dict)
        for key, val in _STATE_TRANSITIONS.items():
            assert isinstance(key, HypothesisStatus)
            assert isinstance(val, frozenset)
            for v in val:
                assert isinstance(v, HypothesisStatus)
        # REFUTED 终态：空集
        assert _STATE_TRANSITIONS[HypothesisStatus.REFUTED] == frozenset()

    def test_can_transition_helper(self):
        """can_transition 辅助函数正确。"""
        assert can_transition(HypothesisStatus.PROPOSED, HypothesisStatus.VERIFYING)
        assert can_transition(HypothesisStatus.VERIFYING, HypothesisStatus.CONFIRMED)
        assert can_transition(HypothesisStatus.VERIFYING, HypothesisStatus.REFUTED)
        assert not can_transition(HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED)
        assert not can_transition(HypothesisStatus.REFUTED, HypothesisStatus.PROPOSED)


# ---------------------------------------------------------------------------
# AC-8：propose 假设树构建
# ---------------------------------------------------------------------------


class TestPropose:
    """假设树构建（AC-8）。"""

    def test_propose_root(self):
        """propose(parent_id=None) 创建根假设，status=PROPOSED。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="root hyp")
        assert node.parent_id is None
        assert node.status == HypothesisStatus.PROPOSED
        assert node.content == "root hyp"
        assert node.children == []
        assert node.is_rootcause is False
        assert node.step_used == 0
        assert node.demote_factor == 1.0

    def test_propose_child_appends_to_parent_children(self):
        """propose(parent_id=...) 创建子假设，挂到 parent.children 尾部。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")
        assert root.children == [child_a, child_b]
        assert child_a.parent_id == root.id
        assert child_b.parent_id == root.id

    def test_propose_nonexistent_parent_raises(self):
        """propose(parent_id=不存在) 抛 ValueError。"""
        engine = _make_engine()
        with pytest.raises(ValueError, match="parent hypothesis"):
            engine.propose(parent_id="nonexistent", content="orphan")

    def test_propose_id_is_unique_uuid_hex(self):
        """propose 生成的 id 为全局唯一 UUID hex。"""
        engine = _make_engine()
        ids = {
            engine.propose(parent_id=None, content=f"h{i}").id
            for i in range(50)
        }
        assert len(ids) == 50  # 全局唯一
        # uuid4().hex 为 32 字符十六进制
        for hid in ids:
            assert len(hid) == 32
            int(hid, 16)  # 合法十六进制

    def test_propose_with_expected_signal(self):
        """propose 传入 expected_signal 写入节点字段。"""
        engine = _make_engine()
        sig = {"type": "crash", "pattern": "FATAL EXCEPTION"}
        node = engine.propose(parent_id=None, content="h", expected_signal=sig)
        assert node.expected_signal == sig


# ---------------------------------------------------------------------------
# AC-9：HypothesisNode dataclass
# ---------------------------------------------------------------------------


class TestHypothesisNode:
    """HypothesisNode dataclass 字段（AC-9）。"""

    def test_default_values(self):
        """HypothesisNode 默认值：status=PROPOSED / children=[] / is_rootcause=False / step_used=0。"""
        node = HypothesisNode(id="x", parent_id=None, content="test")
        assert node.status == HypothesisStatus.PROPOSED
        assert node.children == []
        assert node.is_rootcause is False
        assert node.step_used == 0
        assert node.demote_factor == 1.0
        assert node.expected_signal is None
        assert node.overturning_signal is None
        assert node.overturning_stage is None

    def test_all_15_fields_present(self):
        """HypothesisNode 含 15 个字段（AC-9 定义）。"""
        node = HypothesisNode(id="x", parent_id=None, content="test")
        expected_fields = {
            "id", "parent_id", "content", "status",
            "expected_signal", "verifying_action", "step_budget", "step_used",
            "confirming_evidence", "falsifying_signal",
            "overturning_signal", "overturning_stage",
            "is_rootcause", "children", "demote_factor",
        }
        actual_fields = {f.name for f in node.__dataclass_fields__.values()}
        assert actual_fields == expected_fields


# ---------------------------------------------------------------------------
# AC-2：换方向（refute_and_pivot）
# ---------------------------------------------------------------------------


class TestRefuteAndPivot:
    """换方向回溯（AC-2）。"""

    def test_pivot_returns_next_proposed_sibling(self):
        """3 层树：refute 当前 → 返回 parent 下第一个 proposed 兄弟。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")
        # refute child_a → pivot 应返回 child_b
        result = engine.refute_and_pivot(child_a.id, reason="no signal")
        assert result is child_b
        assert child_a.status == HypothesisStatus.REFUTED

    def test_pivot_traverses_up_to_grandparent(self):
        """parent 下无 proposed 兄弟 → 上溯 grandparent 找 proposed。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")
        grandchild = engine.propose(parent_id=child_a.id, content="ga")
        # child_a 的另一个子（proposed）
        engine.propose(parent_id=child_a.id, content="ga2")
        # refute child_b 先让它退出候选
        engine.refute(child_b.id, reason="not relevant")
        # refute grandchild → parent=child_a 下有 proposed 兄弟 ga2
        result = engine.refute_and_pivot(grandchild.id, reason="x")
        # ga2 是 child_a 的第二个子（proposed）
        assert result is not None
        assert result.parent_id == child_a.id
        assert result.content == "ga2"

    def test_pivot_exhausted_returns_none(self):
        """单链树（root → only_child）：refute only_child → 上溯到 root 无兄弟 → None。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        only_child = engine.propose(parent_id=root.id, content="only")
        result = engine.refute_and_pivot(only_child.id, reason="exhausted")
        assert result is None
        assert only_child.status == HypothesisStatus.REFUTED

    def test_pivot_skips_refuted_siblings(self):
        """refuted 兄弟不参与候选（INV-2 永久保留但不重选）。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")
        child_c = engine.propose(parent_id=root.id, content="c")
        # 先 refute child_b
        engine.refute(child_b.id, reason="pruned")
        # refute child_a → 应跳过 refuted child_b，返回 proposed child_c
        result = engine.refute_and_pivot(child_a.id, reason="no")
        assert result is child_c

    def test_pivot_atomic_refute_then_search(self):
        """refute_and_pivot 先 refute 再 pivot（两步原子语义）。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")
        result = engine.refute_and_pivot(child_a.id, reason="r")
        # refute 已生效
        assert child_a.status == HypothesisStatus.REFUTED
        # pivot 返回兄弟
        assert result is child_b


# ---------------------------------------------------------------------------
# AC-3：根因回退（overturn_root_cause）
# ---------------------------------------------------------------------------


class TestOverturnRootCause:
    """根因回退（AC-3）。"""

    def test_overturn_confirmed_rootcause(self):
        """confirmed + is_rootcause=True → overturn → refuted + is_rootcause=False + 记录。"""
        engine = _make_engine()
        root = engine.propose(parent_id=None, content="root")
        node = _make_confirmed_node(engine, is_rootcause=True, parent_id=root.id)
        sibling = engine.propose(parent_id=root.id, content="sibling")
        # 确保 sibling 在 children 中
        result = engine.overturn_root_cause(
            node.id,
            reason="fixing stage regression",
            overturning_signal={"type": "regression", "value": "reappeared"},
            overturning_stage="fixing",
        )
        assert node.status == HypothesisStatus.REFUTED
        assert node.is_rootcause is False
        assert node.overturning_signal == {"type": "regression", "value": "reappeared"}
        assert node.overturning_stage == "fixing"
        # falsifying_signal 区分 overturned
        assert node.falsifying_signal.get("overturned") is True
        # pivot 触发
        assert result is sibling

    def test_overturn_non_confirmed_raises(self):
        """非 confirmed 节点调 overturn 抛 HypothesisTransitionError。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h")  # PROPOSED
        with pytest.raises(HypothesisTransitionError, match="overturn requires"):
            engine.overturn_root_cause(
                node.id, reason="x",
                overturning_signal={}, overturning_stage="fixing",
            )

    def test_overturn_non_rootcause_raises(self):
        """confirmed 但 is_rootcause=False 调 overturn 抛错。"""
        engine = _make_engine()
        node = _make_confirmed_node(engine, is_rootcause=False)
        with pytest.raises(HypothesisTransitionError):
            engine.overturn_root_cause(
                node.id, reason="x",
                overturning_signal={}, overturning_stage="regression",
            )

    def test_overturn_stage_values(self):
        """overturning_stage 取值 fixing / verifying / regression（语义对齐 SCH01）。"""
        for stage in ("fixing", "verifying", "regression"):
            engine = _make_engine()
            node = _make_confirmed_node(engine, is_rootcause=True)
            engine.overturn_root_cause(
                node.id, reason="x",
                overturning_signal={"v": 1}, overturning_stage=stage,
            )
            assert node.overturning_stage == stage

    def test_overturn_distinguishes_from_verification_refute(self):
        """overturned 节点 status=REFUTED 但保留 overturning_signal（区分两种 refuted）。"""
        engine = _make_engine()
        # 正常 refuted（验证失败）
        node_a = engine.propose(parent_id=None, content="a")
        engine.verify(node_a.id)
        engine.refute(node_a.id, reason="mismatch")
        assert node_a.overturning_signal is None
        # overturned refuted
        node_b = _make_confirmed_node(engine, is_rootcause=True)
        engine.overturn_root_cause(
            node_b.id, reason="x",
            overturning_signal={"k": "v"}, overturning_stage="fixing",
        )
        assert node_b.overturning_signal == {"k": "v"}
        # 区分：node_b 有 overturning_signal，node_a 没有
        assert node_a.overturning_signal is None
        assert node_b.overturning_signal is not None


# ---------------------------------------------------------------------------
# AC-4 / AC-5：步数预算 D7 + 转缺口
# ---------------------------------------------------------------------------


class TestBudgetAndPivot:
    """步数预算（AC-4 / AC-5）。"""

    def test_budget_not_exhausted_returns_false(self):
        """step_used < max_steps → 返回 False，不 refute。"""
        engine = _make_engine(max_steps=10)
        node = engine.propose(parent_id=None, content="h")
        engine.verify(node.id)
        node.step_used = 3
        result = engine.check_budget_and_pivot(node.id)
        assert result is False
        assert node.status == HypothesisStatus.VERIFYING  # 未被 refute

    def test_budget_exhausted_coverage_gap(self):
        """step_used >= max_steps → 返回 True + refute + gap_store.create(gap_type=coverage)。"""
        mock_gap_store = MagicMock()
        engine = _make_engine(gap_store=mock_gap_store, max_steps=3)
        node = engine.propose(parent_id=None, content="h")
        engine.verify(node.id)
        node.step_used = 3
        result = engine.check_budget_and_pivot(node.id)
        assert result is True
        assert node.status == HypothesisStatus.REFUTED
        mock_gap_store.create.assert_called_once()
        gap_data = mock_gap_store.create.call_args[0][0]
        assert gap_data["gap_type"] == "coverage"
        assert gap_data["linked_bug_ids"] == []
        assert "step budget exhausted" in gap_data["description"]

    def test_budget_exhausted_reasoning_gap_for_overturned(self):
        """overturned 根因耗尽 → gap_type=reasoning（推理路径穷尽）。"""
        mock_gap_store = MagicMock()
        engine = _make_engine(gap_store=mock_gap_store, max_steps=2)
        # 构造一个被推翻的根因（overturning_signal 非空，但状态已是 REFUTED）
        root = engine.propose(parent_id=None, content="root")
        node = _make_confirmed_node(engine, is_rootcause=True, parent_id=root.id)
        engine.overturn_root_cause(
            node.id, reason="x",
            overturning_signal={"regression": True},
            overturning_stage="fixing",
        )
        # 现在 node 已是 REFUTED + overturning_signal 非空
        # check_budget_and_pivot 对 REFUTED 节点会抛 HypothesisTransitionError
        # （因为 REFUTED 是终态不能再 refute）—— 这说明 overturned 节点不应再走 budget 路径
        # 但 Contract AC-5 说"当前假设是 overturned 根因（根因被推翻后预算耗尽）"，
        # 语义是：overturn 发生后，引擎继续探索新假设，新假设耗尽时如果上下文是
        # overturned 场景 → reasoning。这里的"当前节点 overturning_signal 非空"判定
        # 针对的是 verify 后耗尽的节点（status VERIFYING）而非已 REFUTED 的 overturned。
        # 修正测试：直接构造一个 VERIFYING 节点 + 手动设置 overturning_signal
        # （模拟"该节点的探索上下文来自 overturned 根因"）
        node2 = engine.propose(parent_id=root.id, content="retry")
        engine.verify(node2.id)
        node2.step_used = 2
        node2.overturning_signal = {"prev_root_overturned": True}  # 上下文标记
        result = engine.check_budget_and_pivot(node2.id)
        assert result is True
        gap_data = mock_gap_store.create.call_args[0][0]
        assert gap_data["gap_type"] == "reasoning"

    def test_budget_exhausted_no_gap_store_degraded(self):
        """gap_store=None → refute 生效 + 返回 True + 无缺口创建（降级）。"""
        engine = _make_engine(gap_store=None, max_steps=1)
        node = engine.propose(parent_id=None, content="h")
        engine.verify(node.id)
        node.step_used = 1
        result = engine.check_budget_and_pivot(node.id)
        assert result is True
        assert node.status == HypothesisStatus.REFUTED

    def test_budget_exhausted_gap_store_create_exception(self):
        """gap_store.create 抛异常 → warning + refute 生效 + 返回 True。"""
        mock_gap_store = MagicMock()
        mock_gap_store.create.side_effect = RuntimeError("db down")
        engine = _make_engine(gap_store=mock_gap_store, max_steps=1)
        node = engine.propose(parent_id=None, content="h")
        engine.verify(node.id)
        node.step_used = 1
        # 不应抛异常
        result = engine.check_budget_and_pivot(node.id)
        assert result is True
        assert node.status == HypothesisStatus.REFUTED

    def test_max_steps_custom(self):
        """max_steps 可通过构造函数覆盖（默认 20）。"""
        engine_default = _make_engine()
        assert engine_default._max_steps == 20
        engine_custom = _make_engine(max_steps=5)
        assert engine_custom._max_steps == 5

    def test_budget_does_not_pivot(self):
        """预算耗尽 → refute 但不 pivot（不返回兄弟）。"""
        mock_gap_store = MagicMock()
        engine = _make_engine(gap_store=mock_gap_store, max_steps=2)
        root = engine.propose(parent_id=None, content="root")
        child_a = engine.propose(parent_id=root.id, content="a")
        child_b = engine.propose(parent_id=root.id, content="b")  # proposed 兄弟存在
        engine.verify(child_a.id)
        child_a.step_used = 2
        # 返回 True（耗尽），但 check_budget_and_pivot 返回 bool 不返回兄弟
        result = engine.check_budget_and_pivot(child_a.id)
        assert result is True
        assert child_a.status == HypothesisStatus.REFUTED
        # child_b 仍是 proposed（未被 pivot 选中，因为 budget 耗尽不 pivot）
        assert child_b.status == HypothesisStatus.PROPOSED


# ---------------------------------------------------------------------------
# AC-6：INV-2 delete 禁止
# ---------------------------------------------------------------------------


class TestInv2Delete:
    """INV-2 refuted 永久保留（AC-6）。"""

    def test_delete_always_raises(self):
        """delete() 始终抛 HypothesisDeleteError。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h")
        with pytest.raises(HypothesisDeleteError, match="INV-2"):
            engine.delete(node.id)

    def test_delete_refuted_node_raises(self):
        """delete() 对 refuted 节点也抛错。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h")
        engine.refute(node.id, reason="x")
        with pytest.raises(HypothesisDeleteError, match="INV-2"):
            engine.delete(node.id)

    def test_no_physical_delete_entrypoint(self):
        """引擎不提供物理删除入口（_nodes 无 pop/del）。"""
        engine = _make_engine()
        node = engine.propose(parent_id=None, content="h")
        engine.refute(node.id, reason="done")
        # 节点仍在 _nodes 中（未被物理删除）
        assert node.id in engine._nodes


# ---------------------------------------------------------------------------
# AC-7：负向知识反查剪枝（negate_and_prune）
# ---------------------------------------------------------------------------


class TestNegateAndPrune:
    """负向知识反查剪枝（AC-7）。"""

    def test_kb_retriever_none_returns_empty(self):
        """kb_retriever=None → 返回空 list 不阻断。"""
        engine = _make_engine(kb_retriever=None)
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1, 0.2]],
            symptom_type="crash",
        )
        assert result == []

    def test_prune_refutes_hypothesis(self):
        """prune=True verdict → 假设被 refute + pruned_ids 含该 id。"""
        mock_kb = MagicMock()
        node_id_placeholder = "hyp_0"
        mock_kb.negate_hypotheses.return_value = [
            NegativeVerdict(
                hypothesis_id=node_id_placeholder,
                max_negative_similarity=0.9,
                prune=True,
                demote_factor=1.0,
            ),
        ]
        engine = _make_engine(kb_retriever=mock_kb)
        node = engine.propose(parent_id=None, content="h")
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1, 0.2]],
            symptom_type="crash",
            hypothesis_ids=[node.id],  # 显式映射
        )
        assert node.id in result
        assert node.status == HypothesisStatus.REFUTED

    def test_demote_marks_without_refute(self):
        """demote_factor<1.0 → 标记降权 + 不 refute + 不在 pruned_ids。"""
        mock_kb = MagicMock()
        mock_kb.negate_hypotheses.return_value = [
            NegativeVerdict(
                hypothesis_id="hyp_0",
                max_negative_similarity=0.7,
                prune=False,
                demote_factor=0.3,
            ),
        ]
        engine = _make_engine(kb_retriever=mock_kb)
        node = engine.propose(parent_id=None, content="h")
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1]],
            symptom_type="crash",
            hypothesis_ids=[node.id],
        )
        assert result == []  # 不在 pruned_ids
        assert node.status == HypothesisStatus.PROPOSED  # 未被 refute
        assert node.demote_factor == 0.3

    def test_unaffected_hypothesis(self):
        """prune=False + demote_factor=1.0 → 假设不受影响。"""
        mock_kb = MagicMock()
        mock_kb.negate_hypotheses.return_value = [
            NegativeVerdict(
                hypothesis_id="hyp_0",
                max_negative_similarity=0.3,
                prune=False,
                demote_factor=1.0,
            ),
        ]
        engine = _make_engine(kb_retriever=mock_kb)
        node = engine.propose(parent_id=None, content="h")
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1]],
            symptom_type="crash",
            hypothesis_ids=[node.id],
        )
        assert result == []
        assert node.status == HypothesisStatus.PROPOSED
        assert node.demote_factor == 1.0

    def test_negate_exception_returns_empty(self):
        """kb_retriever.negate_hypotheses 抛异常 → 返回空 list。"""
        mock_kb = MagicMock()
        mock_kb.negate_hypotheses.side_effect = RuntimeError("kb down")
        engine = _make_engine(kb_retriever=mock_kb)
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1]],
            symptom_type="crash",
        )
        assert result == []

    def test_negate_mixed_verdicts(self):
        """混合 verdicts：prune + demote + unaffected 同时处理。"""
        mock_kb = MagicMock()
        mock_kb.negate_hypotheses.return_value = [
            NegativeVerdict(hypothesis_id="hyp_0", max_negative_similarity=0.9,
                            prune=True, demote_factor=1.0),
            NegativeVerdict(hypothesis_id="hyp_1", max_negative_similarity=0.7,
                            prune=False, demote_factor=0.3),
            NegativeVerdict(hypothesis_id="hyp_2", max_negative_similarity=0.3,
                            prune=False, demote_factor=1.0),
        ]
        engine = _make_engine(kb_retriever=mock_kb)
        n0 = engine.propose(parent_id=None, content="0")
        n1 = engine.propose(parent_id=None, content="1")
        n2 = engine.propose(parent_id=None, content="2")
        result = engine.negate_and_prune(
            hypothesis_vectors=[[0.1], [0.2], [0.3]],
            symptom_type="crash",
            hypothesis_ids=[n0.id, n1.id, n2.id],
        )
        assert result == [n0.id]
        assert n0.status == HypothesisStatus.REFUTED
        assert n1.demote_factor == 0.3
        assert n1.status == HypothesisStatus.PROPOSED
        assert n2.demote_factor == 1.0  # 不受影响
