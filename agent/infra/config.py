"""全局配置参数（R001-INF02）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md
- 技术决策 D2（LLM provider）/ D7（步数 token 预算）/ D9（KB 冲突，含 D6 阈值）
- 任务包 R001-INF02 参数骨架

设计要点：
1. 所有参数既给代码默认值，又支持环境变量覆盖（环境变量优先）。
2. 为便于测试注入与 reload，封装为 `get_settings()` 返回只读 Settings 实例；
   模块级常量 `settings` 作为 import-time 快照（保持 `from agent.infra.config import XXX` 风格可用）。
3. 环境变量命名规范：大写 + 业务前缀（与参数同名或语义前缀，如 NEW_API_BASE_URL /
   SINGLE_HYPOTHESIS_STEP_BUDGET / KB_SIMILARITY_FLOOR / ADB_HOST 等）。
4. LLM model 路由（D2）：按 prompt_type（text / vision）返回对应 model 名。
5. 不在此模块发起任何真实 LLM/DB 连接，仅做配置读取。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# 加载 agent/.env（显式指定绝对路径，避免工作目录差异导致找不到文件）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# prompt_type → model 默认路由（D2）
_DEFAULT_LLM_TEXT_MODEL: Final[str] = "glm-5.1"
_DEFAULT_LLM_VISION_MODEL: Final[str] = "GLM-5V-Turbo"

# 环境变量名常量集中声明，便于测试 monkeypatch 与文档化
_ENV_NEW_API_BASE_URL = "NEW_API_BASE_URL"
_ENV_LLM_TEXT_MODEL = "LLM_TEXT_MODEL"
_ENV_LLM_VISION_MODEL = "LLM_VISION_MODEL"
_ENV_DATABASE_URL = "DATABASE_URL"

_ENV_SINGLE_HYPOTHESIS_STEP_BUDGET = "SINGLE_HYPOTHESIS_STEP_BUDGET"
_ENV_GLOBAL_STEP_BUDGET = "GLOBAL_STEP_BUDGET"
_ENV_TOKEN_BUDGET_PER_BUG = "TOKEN_BUDGET_PER_BUG"
_ENV_FIX_RETRY_MAX = "FIX_RETRY_MAX"

_ENV_KB_SIMILARITY_FLOOR = "KB_SIMILARITY_FLOOR"
_ENV_KB_NEGATIVE_PRUNE = "KB_NEGATIVE_PRUNE"
_ENV_KB_NEGATIVE_DEMOTE = "KB_NEGATIVE_DEMOTE"
_ENV_KB_STALE_DEMOTE = "KB_STALE_DEMOTE"
_ENV_KB_COLD_START_N = "KB_COLD_START_N"

_ENV_ADB_HOST = "ADB_HOST"
_ENV_ADB_PORT = "ADB_PORT"
_ENV_ADB_BIN = "ADB_BIN"
_ENV_ADB_ACTION_TIMEOUT = "ADB_ACTION_TIMEOUT"
_ENV_ADB_RETRY_MAX = "ADB_RETRY_MAX"

_ENV_EMULATOR_BOOT_TIMEOUT = "EMULATOR_BOOT_TIMEOUT"
_ENV_EMULATOR_BIN = "EMULATOR_BIN"
_ENV_SCREENSHOT_FORMAT = "SCREENSHOT_FORMAT"


def _get_int(env_key: str, default: int) -> int:
    """读取环境变量为 int，失败回退 default（容忍空白与非法值）。"""
    raw = os.getenv(env_key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        # 非法值视为未设置，回退默认，避免启动崩溃（config 模块不应抛异常）
        return default


def _get_float(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _get_str(env_key: str, default: str) -> str:
    raw = os.getenv(env_key)
    if raw is None or raw.strip() == "":
        return default
    return raw


@dataclass(frozen=True)
class Settings:
    """运行时配置快照（只读，frozen 防止运行期误改）。

    所有字段在 get_settings() 调用时点从环境变量读取一次；测试可通过
    monkeypatch 环境变量后重新调用 get_settings() 拿到新快照。
    """

    # ---- 步数 / token 预算（D7，待校准）----
    SINGLE_HYPOTHESIS_STEP_BUDGET: int = 5
    GLOBAL_STEP_BUDGET: int = 30
    TOKEN_BUDGET_PER_BUG: int = 50000
    FIX_RETRY_MAX: int = 3

    # ---- LLM（D2，New API 网关）----
    LLM_BASE_URL: str = ""  # 从 NEW_API_BASE_URL 读，默认空串便于本地 fail-fast
    LLM_TEXT_MODEL: str = _DEFAULT_LLM_TEXT_MODEL
    LLM_VISION_MODEL: str = _DEFAULT_LLM_VISION_MODEL

    # ---- KB 阈值（D6/D9，待校准）----
    KB_SIMILARITY_FLOOR: float = 0.5
    KB_NEGATIVE_PRUNE: float = 0.85
    KB_NEGATIVE_DEMOTE: float = 0.6
    KB_STALE_DEMOTE: float = 0.5
    KB_COLD_START_N: int = 10

    # ---- ADB 网络桥（D10）----
    # ADB_HOST="" 表示本地直跑（不加 -H/-P）；非空走网络桥（容器经 host.docker.internal）
    ADB_HOST: str = ""
    ADB_PORT: int = 5037
    # ADB 二进制路径（空表示走三段式解析：env → which → 平台固定路径）
    ADB_BIN: str = ""
    # ADB 动作默认超时（秒），env 可覆盖
    ADB_ACTION_TIMEOUT: int = 10
    # ADB 重试上限（连接错不重试，命令错/超时重试）
    ADB_RETRY_MAX: int = 2

    # ---- Emulator（BF002）----
    # emulator boot 完成超时（秒），env 可覆盖
    EMULATOR_BOOT_TIMEOUT: int = 120
    # emulator 二进制路径（空表示走解析：env → SDK 固定路径 → which）
    EMULATOR_BIN: str = ""
    # 截图产出格式（data_url / file_url），控制 screenshot_collector 产出形态
    SCREENSHOT_FORMAT: str = "data_url"

    # ---- DB（D4 同库 PG+pgvector）----
    DATABASE_URL: str = "postgresql+psycopg://localhost:5432/bugfix_agent"


def get_settings() -> Settings:
    """从环境变量读取一份 Settings 快照。

    每次调用都重新读取（便于测试 monkeypatch 后取最新值）；生产路径可在
    启动期调用一次缓存到模块级 `settings`。
    """
    return Settings(
        # 步数 / token 预算
        SINGLE_HYPOTHESIS_STEP_BUDGET=_get_int(
            _ENV_SINGLE_HYPOTHESIS_STEP_BUDGET, 5
        ),
        GLOBAL_STEP_BUDGET=_get_int(_ENV_GLOBAL_STEP_BUDGET, 30),
        TOKEN_BUDGET_PER_BUG=_get_int(_ENV_TOKEN_BUDGET_PER_BUG, 50000),
        FIX_RETRY_MAX=_get_int(_ENV_FIX_RETRY_MAX, 3),
        # LLM
        LLM_BASE_URL=_get_str(_ENV_NEW_API_BASE_URL, ""),
        LLM_TEXT_MODEL=_get_str(_ENV_LLM_TEXT_MODEL, _DEFAULT_LLM_TEXT_MODEL),
        LLM_VISION_MODEL=_get_str(
            _ENV_LLM_VISION_MODEL, _DEFAULT_LLM_VISION_MODEL
        ),
        # KB
        KB_SIMILARITY_FLOOR=_get_float(_ENV_KB_SIMILARITY_FLOOR, 0.5),
        KB_NEGATIVE_PRUNE=_get_float(_ENV_KB_NEGATIVE_PRUNE, 0.85),
        KB_NEGATIVE_DEMOTE=_get_float(_ENV_KB_NEGATIVE_DEMOTE, 0.6),
        KB_STALE_DEMOTE=_get_float(_ENV_KB_STALE_DEMOTE, 0.5),
        KB_COLD_START_N=_get_int(_ENV_KB_COLD_START_N, 10),
        # ADB
        ADB_HOST=_get_str(_ENV_ADB_HOST, ""),
        ADB_PORT=_get_int(_ENV_ADB_PORT, 5037),
        ADB_BIN=_get_str(_ENV_ADB_BIN, ""),
        ADB_ACTION_TIMEOUT=_get_int(_ENV_ADB_ACTION_TIMEOUT, 10),
        ADB_RETRY_MAX=_get_int(_ENV_ADB_RETRY_MAX, 2),
        # Emulator
        EMULATOR_BOOT_TIMEOUT=_get_int(_ENV_EMULATOR_BOOT_TIMEOUT, 120),
        EMULATOR_BIN=_get_str(_ENV_EMULATOR_BIN, ""),
        SCREENSHOT_FORMAT=_get_str(_ENV_SCREENSHOT_FORMAT, "data_url"),
        # DB
        DATABASE_URL=_get_str(
            _ENV_DATABASE_URL,
            "postgresql+psycopg://localhost:5432/bugfix_agent",
        ),
    )


# LLM model 路由（D2）--------------------------------------------------------
# prompt_type ∈ {"text", "vision"} → 返回对应 model 名。
# 路由表在调用时按当前 Settings 解析，保证环境变量覆盖 model 后路由同步生效。
def get_llm_model(prompt_type: str, s: "Settings | None" = None) -> str:
    """按 prompt_type 路由到对应 LLM model（D2）。

    Args:
        prompt_type: "text"（BB002/BB004/BB007/BB013）或 "vision"（BF003）。
        s: 可选 Settings 注入（测试用）；None 时用模块级 settings 快照。

    Returns:
        model 名字符串。

    Raises:
        ValueError: prompt_type 非法时（fail-fast，避免静默用错 model）。
    """
    cur = s if s is not None else settings
    key = (prompt_type or "").strip().lower()
    if key == "text":
        return cur.LLM_TEXT_MODEL
    if key == "vision":
        return cur.LLM_VISION_MODEL
    raise ValueError(
        f"unsupported prompt_type={prompt_type!r} (expected 'text' or 'vision')"
    )


# 模块级 import-time 快照（兼容 `from agent.infra.config import settings` 用法）
settings: Settings = get_settings()

# 模块级常量镜像（兼容 `from agent.infra.config import SINGLE_HYPOTHESIS_STEP_BUDGET` 风格）
# 注意：这些值是 import 时点快照，测试环境变量覆盖优先级请改用 get_settings()。
SINGLE_HYPOTHESIS_STEP_BUDGET: int = settings.SINGLE_HYPOTHESIS_STEP_BUDGET
GLOBAL_STEP_BUDGET: int = settings.GLOBAL_STEP_BUDGET
TOKEN_BUDGET_PER_BUG: int = settings.TOKEN_BUDGET_PER_BUG
FIX_RETRY_MAX: int = settings.FIX_RETRY_MAX

LLM_BASE_URL: str = settings.LLM_BASE_URL
LLM_TEXT_MODEL: str = settings.LLM_TEXT_MODEL
LLM_VISION_MODEL: str = settings.LLM_VISION_MODEL

KB_SIMILARITY_FLOOR: float = settings.KB_SIMILARITY_FLOOR
KB_NEGATIVE_PRUNE: float = settings.KB_NEGATIVE_PRUNE
KB_NEGATIVE_DEMOTE: float = settings.KB_NEGATIVE_DEMOTE
KB_STALE_DEMOTE: float = settings.KB_STALE_DEMOTE
KB_COLD_START_N: int = settings.KB_COLD_START_N

ADB_HOST: str = settings.ADB_HOST
ADB_PORT: int = settings.ADB_PORT
ADB_BIN: str = settings.ADB_BIN
ADB_ACTION_TIMEOUT: int = settings.ADB_ACTION_TIMEOUT
ADB_RETRY_MAX: int = settings.ADB_RETRY_MAX

EMULATOR_BOOT_TIMEOUT: int = settings.EMULATOR_BOOT_TIMEOUT
EMULATOR_BIN: str = settings.EMULATOR_BIN
SCREENSHOT_FORMAT: str = settings.SCREENSHOT_FORMAT

DATABASE_URL: str = settings.DATABASE_URL


__all__ = [
    "Settings",
    "get_settings",
    "get_llm_model",
    "settings",
    # 模块级常量镜像
    "SINGLE_HYPOTHESIS_STEP_BUDGET",
    "GLOBAL_STEP_BUDGET",
    "TOKEN_BUDGET_PER_BUG",
    "FIX_RETRY_MAX",
    "LLM_BASE_URL",
    "LLM_TEXT_MODEL",
    "LLM_VISION_MODEL",
    "KB_SIMILARITY_FLOOR",
    "KB_NEGATIVE_PRUNE",
    "KB_NEGATIVE_DEMOTE",
    "KB_STALE_DEMOTE",
    "KB_COLD_START_N",
    "ADB_HOST",
    "ADB_PORT",
    "ADB_BIN",
    "ADB_ACTION_TIMEOUT",
    "ADB_RETRY_MAX",
    "EMULATOR_BOOT_TIMEOUT",
    "EMULATOR_BIN",
    "SCREENSHOT_FORMAT",
    "DATABASE_URL",
]
