"""Signal Schema（R001-SCH02，BF004 四类信号配置）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表（第 679-687 行）
- 任务包 R001-SCH02（signal_type ∈ {logcat, flutter_error, process, visual}）

设计要点：
1. **signal_type 四类枚举**（design 第 684 行）：
   - logcat：Android logcat 信号
   - flutter_error：Flutter error channel 信号
   - process：进程级信号（ANR / 内存 / CPU 等）
   - visual：视觉信号（UI 对照 / 截图差异）
2. **pattern 为 JSON**（design 第 685 行）：匹配规则，内部结构随 signal_type 变化
   （正则 / 关键字 / 视觉特征描述）。
3. **severity 四档**（design 第 686 行）：crash / error / warn / info。
4. **source_config 为 JSON**（design 第 687 行）：监听源配置，结构随 signal_type 变化：
   - logcat → {tag: ..., priority: ...}
   - flutter_error → {channel: ...}
   - process → {metric: ..., threshold: ...}
   - visual → {anchor_id: ...}
5. 模块文件名 signal.py 位于 agent.schemas 包内（agent.schemas.signal），
   不会与 stdlib signal 冲突（stdlib 是顶层包）。保持文件名以对齐 design 命名。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class SignalType(str, Enum):
    """Signal 类型四类枚举（design 4.1 第 684 行）。"""

    LOGCAT = "logcat"
    FLUTTER_ERROR = "flutter_error"
    PROCESS = "process"
    VISUAL = "visual"


class SignalSeverity(str, Enum):
    """Signal 严重级别四档（design 4.1 第 686 行）。"""

    CRASH = "crash"
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


class Signal(Base):
    """Signal（BF004 四类信号配置，design 4.1 第 679-687 行）。

    描述如何监听一类信号：signal_type 决定 source_config 结构，
    pattern 定义匹配规则，severity 分级。
    """

    __tablename__ = "signals"

    # 主键（design: str(PK)）
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 四类（logcat / flutter_error / process / visual）
    signal_type: Mapped[str] = mapped_column(String, nullable=False)

    # 匹配规则（正则 / 关键字 / 视觉特征，内部结构随 signal_type 变化）
    pattern: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # crash / error / warn / info
    severity: Mapped[str | None] = mapped_column(String, nullable=True)

    # 监听源配置（结构随 signal_type 变化，见模块 docstring）
    source_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)


__all__ = ["Signal", "SignalType", "SignalSeverity"]
