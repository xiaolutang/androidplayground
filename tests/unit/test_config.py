"""R001-INF02 config 单元测试。

覆盖 test_tasks 三个场景：
1. 默认值校验（不设环境变量时 == 骨架默认值）
2. 环境变量覆盖优先级（monkeypatch 后 get_settings() 拿到环境变量值；含 int/float 转换）
3. LLM model 路由映射（prompt_type="text"→glm-5.1，"vision"→GLM-5V-Turbo）

环境变量读取策略：get_settings() 每次重新读环境变量，测试通过 monkeypatch
直接改 os.environ，再调用 get_settings() 拿到新快照，无需 reload 模块。
"""
import pytest

from agent.infra import config as cfg
from agent.infra.config import Settings, get_llm_model, get_settings


# test_tasks #1：默认值校验 -----------------------------------------------
def test_defaults_match_skeleton(monkeypatch):
    """不设环境变量时，各参数 == 骨架默认值（D7 + D2 + D6/D9 + D10 + D4）。"""
    # 清空所有相关环境变量，确保读到的是代码默认值
    env_keys = [
        "NEW_API_BASE_URL",
        "LLM_TEXT_MODEL",
        "LLM_VISION_MODEL",
        "DATABASE_URL",
        "SINGLE_HYPOTHESIS_STEP_BUDGET",
        "GLOBAL_STEP_BUDGET",
        "TOKEN_BUDGET_PER_BUG",
        "FIX_RETRY_MAX",
        "KB_SIMILARITY_FLOOR",
        "KB_NEGATIVE_PRUNE",
        "KB_NEGATIVE_DEMOTE",
        "KB_STALE_DEMOTE",
        "KB_COLD_START_N",
        "ADB_HOST",
        "ADB_PORT",
    ]
    for k in env_keys:
        monkeypatch.delenv(k, raising=False)

    s = get_settings()

    # 步数 / token 预算（D7）
    assert s.SINGLE_HYPOTHESIS_STEP_BUDGET == 5
    assert s.GLOBAL_STEP_BUDGET == 30
    assert s.TOKEN_BUDGET_PER_BUG == 50000
    assert s.FIX_RETRY_MAX == 3

    # LLM（D2）
    assert s.LLM_BASE_URL == ""
    assert s.LLM_TEXT_MODEL == "glm-5.1"
    assert s.LLM_VISION_MODEL == "GLM-5V-Turbo"

    # KB 阈值（D6/D9）
    assert s.KB_SIMILARITY_FLOOR == 0.5
    assert s.KB_NEGATIVE_PRUNE == 0.85
    assert s.KB_NEGATIVE_DEMOTE == 0.6
    assert s.KB_STALE_DEMOTE == 0.5
    assert s.KB_COLD_START_N == 10

    # ADB 网络桥（D10）
    assert s.ADB_HOST == "host.docker.internal"
    assert s.ADB_PORT == 5037

    # DB（D4）
    assert s.DATABASE_URL == "postgresql+psycopg://localhost:5432/bugfix_agent"


def test_settings_is_frozen():
    """frozen=True 防运行期误改。"""
    s = get_settings()
    with pytest.raises(Exception):
        s.GLOBAL_STEP_BUDGET = 999  # type: ignore[misc]


# test_tasks #2：环境变量覆盖优先级 ---------------------------------------
def test_env_overrides_step_budget(monkeypatch):
    """int 型：环境变量覆盖步数 / token 预算。"""
    monkeypatch.setenv("SINGLE_HYPOTHESIS_STEP_BUDGET", "8")
    monkeypatch.setenv("GLOBAL_STEP_BUDGET", "50")
    monkeypatch.setenv("TOKEN_BUDGET_PER_BUG", "120000")
    monkeypatch.setenv("FIX_RETRY_MAX", "5")
    s = get_settings()
    assert s.SINGLE_HYPOTHESIS_STEP_BUDGET == 8
    assert s.GLOBAL_STEP_BUDGET == 50
    assert s.TOKEN_BUDGET_PER_BUG == 120000
    assert s.FIX_RETRY_MAX == 5
    # 类型必须正确（int，不是 str）
    assert isinstance(s.SINGLE_HYPOTHESIS_STEP_BUDGET, int)
    assert isinstance(s.GLOBAL_STEP_BUDGET, int)
    assert isinstance(s.TOKEN_BUDGET_PER_BUG, int)
    assert isinstance(s.FIX_RETRY_MAX, int)


def test_env_overrides_kb_thresholds(monkeypatch):
    """float 型：环境变量覆盖 KB 阈值（含小数）。"""
    monkeypatch.setenv("KB_SIMILARITY_FLOOR", "0.65")
    monkeypatch.setenv("KB_NEGATIVE_PRUNE", "0.9")
    monkeypatch.setenv("KB_NEGATIVE_DEMOTE", "0.7")
    monkeypatch.setenv("KB_STALE_DEMOTE", "0.4")
    monkeypatch.setenv("KB_COLD_START_N", "20")
    s = get_settings()
    assert s.KB_SIMILARITY_FLOOR == pytest.approx(0.65)
    assert s.KB_NEGATIVE_PRUNE == pytest.approx(0.9)
    assert s.KB_NEGATIVE_DEMOTE == pytest.approx(0.7)
    assert s.KB_STALE_DEMOTE == pytest.approx(0.4)
    assert s.KB_COLD_START_N == 20
    # 类型校验
    assert isinstance(s.KB_SIMILARITY_FLOOR, float)
    assert isinstance(s.KB_NEGATIVE_PRUNE, float)
    assert isinstance(s.KB_NEGATIVE_DEMOTE, float)
    assert isinstance(s.KB_STALE_DEMOTE, float)
    assert isinstance(s.KB_COLD_START_N, int)


def test_env_overrides_llm_and_db(monkeypatch):
    """str 型：环境变量覆盖 LLM base_url / model / DB url / ADB。"""
    monkeypatch.setenv("NEW_API_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("LLM_TEXT_MODEL", "custom-text-model")
    monkeypatch.setenv("LLM_VISION_MODEL", "custom-vision-model")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://prod:5432/db")
    monkeypatch.setenv("ADB_HOST", "10.0.0.1")
    monkeypatch.setenv("ADB_PORT", "6037")
    s = get_settings()
    assert s.LLM_BASE_URL == "https://gw.example.com/v1"
    assert s.LLM_TEXT_MODEL == "custom-text-model"
    assert s.LLM_VISION_MODEL == "custom-vision-model"
    assert s.DATABASE_URL == "postgresql+psycopg://prod:5432/db"
    assert s.ADB_HOST == "10.0.0.1"
    assert s.ADB_PORT == 6037


def test_env_invalid_int_falls_back_to_default(monkeypatch):
    """非法 int 环境变量应回退默认，不崩启动（config 模块容错）。"""
    monkeypatch.setenv("GLOBAL_STEP_BUDGET", "not-a-number")
    monkeypatch.setenv("KB_COLD_START_N", "")
    s = get_settings()
    assert s.GLOBAL_STEP_BUDGET == 30
    assert s.KB_COLD_START_N == 10


def test_env_invalid_float_falls_back_to_default(monkeypatch):
    """非法 float 环境变量回退默认。"""
    monkeypatch.setenv("KB_SIMILARITY_FLOOR", "NaN-bad")
    s = get_settings()
    assert s.KB_SIMILARITY_FLOOR == pytest.approx(0.5)


def test_get_settings_reads_fresh_each_call(monkeypatch):
    """get_settings() 每次都重新读环境变量（验证 reload-free 测试可行性）。"""
    s1 = get_settings()
    monkeypatch.setenv("GLOBAL_STEP_BUDGET", "99")
    s2 = get_settings()
    assert s1.GLOBAL_STEP_BUDGET == 30
    assert s2.GLOBAL_STEP_BUDGET == 99


# test_tasks #3：LLM model 路由（D2） -------------------------------------
def test_llm_model_routing_text():
    """prompt_type='text' → glm-5.1（默认 settings）。"""
    assert get_llm_model("text") == "glm-5.1"


def test_llm_model_routing_vision():
    """prompt_type='vision' → GLM-5V-Turbo（默认 settings）。"""
    assert get_llm_model("vision") == "GLM-5V-Turbo"


def test_llm_model_routing_case_insensitive():
    """大小写无关（'TEXT' / 'Vision' 也认）。"""
    assert get_llm_model("TEXT") == "glm-5.1"
    assert get_llm_model("Vision") == "GLM-5V-Turbo"


def test_llm_model_routing_invalid_raises():
    """非法 prompt_type fail-fast，避免静默用错 model。"""
    with pytest.raises(ValueError, match="unsupported prompt_type"):
        get_llm_model("audio")
    with pytest.raises(ValueError):
        get_llm_model("")


def test_llm_model_routing_respects_env_override(monkeypatch):
    """环境变量覆盖 model 后，路由返回新 model（环境变量优先级与路由联动）。"""
    monkeypatch.setenv("LLM_TEXT_MODEL", "text-override")
    monkeypatch.setenv("LLM_VISION_MODEL", "vision-override")
    # 注入新 Settings 给路由函数，避免依赖 import-time 模块级快照
    s = get_settings()
    assert get_llm_model("text", s) == "text-override"
    assert get_llm_model("vision", s) == "vision-override"


# 模块级常量镜像可用性 ------------------------------------------------------
def test_module_level_constants_match_settings():
    """模块级常量与 settings 快照一致（兼容两种 import 风格）。"""
    assert cfg.SINGLE_HYPOTHESIS_STEP_BUDGET == cfg.settings.SINGLE_HYPOTHESIS_STEP_BUDGET
    assert cfg.LLM_TEXT_MODEL == cfg.settings.LLM_TEXT_MODEL
    assert cfg.KB_SIMILARITY_FLOOR == cfg.settings.KB_SIMILARITY_FLOOR
    assert cfg.ADB_PORT == cfg.settings.ADB_PORT
    assert cfg.DATABASE_URL == cfg.settings.DATABASE_URL
