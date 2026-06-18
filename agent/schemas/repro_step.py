"""ReproStep Schema（R001-SCH02，复现序列单元）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 ReproStep 表（第 667-677 行）
- 任务包 R001-SCH02（BF002 产出 / BB008 回归复用）

设计要点：
1. **BF002 复现序列产出**：每个 step 描述一次 UI 动作 + 预期/实际信号对照。
2. **BB008 回归复用**：回归时直接 replay 已有 ReproStep 序列，无需重新生成。
3. **actual_signal 为 JSON 类型**（design 第 677 行）：实际采集到的信号结构，
   内部可引用 Signal schema 的字段结构（signal_type / pattern / severity 等），
   但不强制 FK——采集侧把匹配到的 Signal 配置快照嵌入 JSON，避免回放时 Signal 表
   变更影响历史复现序列。
4. **expected_signal 同为 JSON**（design 第 675 行）：预期信号，复现脚本静态预期。
5. 字段一一对应 design 4.1 ReproStep 表。
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class ReproStep(Base):
    """ReproStep（复现序列单元，design 4.1 第 667-677 行）。

    一条 BugReport / Trajectory 关联一个有序的 ReproStep 序列，
    BF002 产出后供 BB008 回归时直接 replay。
    """

    __tablename__ = "repro_steps"

    # 主键（design: str(PK)）
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 关联排查轨迹（design 第 671 行）
    trajectory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("trajectories.id"), nullable=True
    )

    # 序号（design 第 672 行）
    step_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # tap / swipe / input / back / wait（design 第 673 行）
    action: Mapped[str | None] = mapped_column(String, nullable=True)

    # 动作目标坐标（design 第 674 行：target_coords / target_text 二选一或并存）
    target_coords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 动作目标文字（输入框场景）
    target_text: Mapped[str | None] = mapped_column(String, nullable=True)

    # 预期信号（design 第 675 行：json，复现脚本静态预期）
    expected_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 截图引用（design 第 676 行）
    screenshot_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    # 实际采集信号（design 第 677 行：json）
    # 内部可嵌入匹配到的 Signal 快照（signal_type / pattern / severity），
    # 不做 FK，避免 Signal 表后续变更影响历史复现序列。
    actual_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)


__all__ = ["ReproStep"]
