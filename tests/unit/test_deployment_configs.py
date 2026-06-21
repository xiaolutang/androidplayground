"""R001-DEP01：部署配置文件结构校验（纯静态，无需 Docker）。

依据：
- Sprint Contract R001-DEP01（mode: direct, acceptance_criteria）
- 质量门：`pytest tests/unit/test_deployment_configs.py -q` 全过

覆盖：
1. docker-compose.yml 语法（yaml.safe_load）
2. 三服务定义存在（postgres / agent / frontend）
3. agent 服务有 host.docker.internal 映射（D10）
4. Dockerfile 存在且基础镜像正确
5. Makefile 有 up/down/logs/test 目标
6. .dockerignore 排除敏感目录

注意：不需要真正运行 docker（CI 环境可能无 Docker），
只验证配置文件的语法和结构。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# 路径定位：仓库根（tests/unit/ → ../../）
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def compose_yaml() -> dict:
    """加载 docker-compose.yml 并解析为 dict。"""
    if not COMPOSE_PATH.exists():
        pytest.skip(f"docker-compose.yml not found at {COMPOSE_PATH}")
    with COMPOSE_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "docker-compose.yml root must be a mapping"
    return data


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    if not DOCKERFILE_PATH.exists():
        pytest.skip(f"Dockerfile not found at {DOCKERFILE_PATH}")
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def makefile_text() -> str:
    if not MAKEFILE_PATH.exists():
        pytest.skip(f"Makefile not found at {MAKEFILE_PATH}")
    return MAKEFILE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerignore_text() -> str:
    if not DOCKERIGNORE_PATH.exists():
        pytest.skip(f".dockerignore not found at {DOCKERIGNORE_PATH}")
    return DOCKERIGNORE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-1：docker-compose.yml 语法合法
# ---------------------------------------------------------------------------
class TestComposeSyntax:
    """验证 docker-compose.yml 顶层结构。"""

    def test_compose_file_exists(self) -> None:
        assert COMPOSE_PATH.exists(), f"docker-compose.yml missing at {COMPOSE_ROOT_parent()}"

    def test_compose_top_level_keys(self, compose_yaml: dict) -> None:
        # Compose 规范允许 services / volumes / networks 等顶层 key
        assert "services" in compose_yaml, "compose must define 'services'"
        services = compose_yaml["services"]
        assert isinstance(services, dict) and services, "services must be non-empty mapping"

    def test_compose_version_or_services(self, compose_yaml: dict) -> None:
        # 现代 compose 不强制 version 字段（compose spec），但 services 必须存在
        assert "services" in compose_yaml


# ---------------------------------------------------------------------------
# AC-2：三服务定义存在（postgres / agent / frontend）
# ---------------------------------------------------------------------------
class TestThreeServices:
    REQUIRED_SERVICES = ("postgres", "agent", "frontend")

    def test_all_services_present(self, compose_yaml: dict) -> None:
        services = compose_yaml.get("services", {})
        missing = [s for s in self.REQUIRED_SERVICES if s not in services]
        assert not missing, f"missing services: {missing}"

    def test_postgres_image_is_pgvector(self, compose_yaml: dict) -> None:
        pg = compose_yaml["services"]["postgres"]
        image = pg.get("image", "")
        assert "pgvector" in image, f"postgres image must be pgvector/*, got {image!r}"
        assert "pg16" in image, f"postgres image must target pg16, got {image!r}"

    def test_postgres_has_healthcheck(self, compose_yaml: dict) -> None:
        pg = compose_yaml["services"]["postgres"]
        assert "healthcheck" in pg, "postgres must define healthcheck"
        hc = pg["healthcheck"]
        assert "test" in hc, "healthcheck must define 'test'"

    def test_postgres_env_set(self, compose_yaml: dict) -> None:
        pg = compose_yaml["services"]["postgres"]
        env = pg.get("environment", {})
        assert env.get("POSTGRES_USER"), "POSTGRES_USER must be set"
        assert env.get("POSTGRES_PASSWORD"), "POSTGRES_PASSWORD must be set"
        assert env.get("POSTGRES_DB"), "POSTGRES_DB must be set"

    def test_postgres_volume_persist(self, compose_yaml: dict) -> None:
        pg = compose_yaml["services"]["postgres"]
        vols = pg.get("volumes", [])
        assert any("postgres" in str(v) for v in vols), \
            "postgres must mount a named volume for persistence"

    def test_agent_build_from_dockerfile(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        build = agent.get("build", {})
        if isinstance(build, dict):
            assert build.get("dockerfile", "").lower() == "dockerfile" or \
                "context" in build, "agent must build from Dockerfile"
        else:
            pytest.fail("agent.build must be a mapping")

    def test_agent_depends_on_postgres_healthy(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        dep = agent.get("depends_on", {})
        if isinstance(dep, dict):
            assert "postgres" in dep, "agent must depend_on postgres"
            pg_dep = dep["postgres"]
            assert isinstance(pg_dep, dict)
            assert pg_dep.get("condition") == "service_healthy", \
                "agent must wait for postgres healthy"
        else:
            pytest.fail("depends_on must be a mapping with condition")

    def test_agent_port_8000(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        ports = agent.get("ports", [])
        assert any("8000" in str(p) for p in ports), \
            "agent must expose port 8000"

    def test_agent_database_url_points_to_postgres(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        env = agent.get("environment", {})
        db_url = env.get("DATABASE_URL", "")
        assert "postgres" in db_url and "5432" in db_url, \
            f"agent DATABASE_URL must point to postgres service: {db_url!r}"

    def test_frontend_service_minimal(self, compose_yaml: dict) -> None:
        fe = compose_yaml["services"]["frontend"]
        # 占位要求：要么有 image，要么有 build
        assert fe.get("image") or fe.get("build"), \
            "frontend service must define image or build"


# ---------------------------------------------------------------------------
# AC-3：agent 有 host.docker.internal 映射（D10）
# ---------------------------------------------------------------------------
class TestAdbBridge:
    """D10：容器经 host.docker.internal:5037 连宿主 adb server。"""

    def test_agent_has_extra_hosts(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        extra_hosts = agent.get("extra_hosts", [])
        found = False
        for entry in extra_hosts:
            # entry 可以是 "host.docker.internal:host-gateway" 或 dict（compose 长语法）
            if isinstance(entry, str) and "host.docker.internal" in entry:
                found = True
                assert "host-gateway" in entry, \
                    f"extra_hosts must map host.docker.internal to host-gateway, got {entry!r}"
            elif isinstance(entry, dict) and "host.docker.internal" in entry:
                found = True
        assert found, "agent.extra_hosts must define host.docker.internal"

    def test_agent_adb_env(self, compose_yaml: dict) -> None:
        agent = compose_yaml["services"]["agent"]
        env = agent.get("environment", {})
        adb_host = env.get("ADB_HOST", "")
        adb_port = env.get("ADB_PORT", "")
        assert "host.docker.internal" in str(adb_host) or adb_host == "", \
            f"ADB_HOST should allow host.docker.internal, got {adb_host!r}"
        # ADB_PORT 可被用户覆盖，但默认或显式必须是 5037
        assert str(adb_port) in ("5037", ""), \
            f"ADB_PORT default should be 5037, got {adb_port!r}"


# ---------------------------------------------------------------------------
# AC-4：Dockerfile 存在且基础镜像正确
# ---------------------------------------------------------------------------
class TestDockerfile:
    def test_dockerfile_exists(self) -> None:
        assert DOCKERFILE_PATH.exists(), f"Dockerfile missing at {DOCKERFILE_PATH}"

    def test_base_image_python313(self, dockerfile_text: str) -> None:
        # 匹配 FROM python:3.13* （允许 python:3.13 / python:3.13-slim / python:3.13.x-slim）
        from_line = next(
            (ln for ln in dockerfile_text.splitlines() if ln.strip().upper().startswith("FROM ")),
            None,
        )
        assert from_line is not None, "Dockerfile must have FROM instruction"
        assert re.search(r"python:3\.13", from_line), \
            f"base image must be python:3.13*, got {from_line!r}"

    def test_dockerfile_installs_adb(self, dockerfile_text: str) -> None:
        # 必须安装 adb（android-tools-adb 或 platform-tools）
        lower = dockerfile_text.lower()
        assert ("android-tools-adb" in lower) or ("platform-tools" in lower), \
            "Dockerfile must install adb (android-tools-adb or platform-tools)"

    def test_dockerfile_copies_pyproject_first(self, dockerfile_text: str) -> None:
        """层缓存优化：先 COPY pyproject.toml 再 COPY 业务代码。"""
        lines = dockerfile_text.splitlines()
        # 找 pyproject.toml COPY 的行号
        pyproject_line_idx = next(
            (i for i, ln in enumerate(lines) if "pyproject.toml" in ln and "COPY" in ln.upper()),
            None,
        )
        assert pyproject_line_idx is not None, \
            "Dockerfile must COPY pyproject.toml before code (layer cache optimization)"
        # 找 agent/ COPY 的第一个行号
        agent_copy_idx = next(
            (i for i, ln in enumerate(lines)
             if "COPY" in ln.upper() and "agent/" in ln and "pyproject.toml" not in ln),
            None,
        )
        assert agent_copy_idx is not None, "Dockerfile must COPY agent/ source"
        assert pyproject_line_idx < agent_copy_idx, \
            "pyproject.toml must be COPYed before agent/ code (layer cache)"

    def test_dockerfile_cmd_uvicorn(self, dockerfile_text: str) -> None:
        lower = dockerfile_text.lower()
        assert "uvicorn" in lower, "Dockerfile CMD must use uvicorn"
        assert "agent.main:app" in dockerfile_text, \
            "Dockerfile CMD must start agent.main:app"

    def test_dockerfile_exposes_8000(self, dockerfile_text: str) -> None:
        assert "EXPOSE 8000" in dockerfile_text, "Dockerfile must EXPOSE 8000"


# ---------------------------------------------------------------------------
# AC-5：Makefile 有 up/down/logs/test 目标
# ---------------------------------------------------------------------------
class TestMakefile:
    REQUIRED_TARGETS = ("up", "down", "logs", "test", "shell", "adb-devices")

    def test_makefile_exists(self) -> None:
        assert MAKEFILE_PATH.exists(), f"Makefile missing at {MAKEFILE_PATH}"

    @pytest.mark.parametrize("target", REQUIRED_TARGETS)
    def test_target_exists(self, makefile_text: str, target: str) -> None:
        # Makefile 目标语法：行首 + 目标名 + ':' (可能后跟依赖)
        pattern = rf"^{re.escape(target)}\s*:"
        assert re.search(pattern, makefile_text, re.MULTILINE), \
            f"Makefile must define target '{target}:'"

    def test_up_target_runs_docker_compose(self, makefile_text: str) -> None:
        # `up` 目标必须调用 docker compose up
        # 找 up: 后到下一个目标之间的内容
        match = re.search(r"^up\s*:.*?(?=^\S|\Z)", makefile_text, re.MULTILINE | re.DOTALL)
        assert match, "Makefile must have 'up' target"
        body = match.group(0)
        assert "docker compose up" in body, "'up' must call docker compose up"

    def test_up_target_starts_adb(self, makefile_text: str) -> None:
        match = re.search(r"^up\s*:.*?(?=^\S|\Z)", makefile_text, re.MULTILINE | re.DOTALL)
        assert match
        body = match.group(0)
        assert "adb" in body.lower(), "'up' must reference adb (start-server)"

    def test_down_target(self, makefile_text: str) -> None:
        match = re.search(r"^down\s*:.*?(?=^\S|\Z)", makefile_text, re.MULTILINE | re.DOTALL)
        assert match
        body = match.group(0)
        assert "docker compose down" in body

    def test_adb_devices_target_uses_host_docker_internal(
        self, makefile_text: str
    ) -> None:
        match = re.search(
            r"^adb-devices\s*:.*?(?=^\S|\Z)", makefile_text, re.MULTILINE | re.DOTALL
        )
        assert match
        body = match.group(0)
        assert "host.docker.internal" in body, \
            "'adb-devices' must use host.docker.internal (D10)"


# ---------------------------------------------------------------------------
# AC-6：.dockerignore 排除敏感目录
# ---------------------------------------------------------------------------
class TestDockerignore:
    MUST_EXCLUDE = (".git", "agent/.env", "__pycache__", ".venv", ".dev-flow")

    def test_dockerignore_exists(self) -> None:
        assert DOCKERIGNORE_PATH.exists(), \
            f".dockerignore missing at {DOCKERIGNORE_PATH}"

    @pytest.mark.parametrize("pattern", MUST_EXCLUDE)
    def test_excludes_sensitive(self, dockerignore_text: str, pattern: str) -> None:
        lines = [ln.strip() for ln in dockerignore_text.splitlines()]
        # 支持 agent/.env 出现或 .env 被 *.env 匹配
        found = pattern in lines or any(pattern in ln for ln in lines)
        assert found, f".dockerignore must exclude {pattern!r}"

    def test_does_not_exclude_agent_source(self, dockerignore_text: str) -> None:
        """安全检查：不能排除 agent/ 源码本身（否则镜像构建后无代码）。"""
        lines = [ln.strip() for ln in dockerignore_text.splitlines() if ln.strip()]
        for ln in lines:
            if ln.startswith("#"):
                continue
            # agent/ 单独成行（精确排除整个包）不可接受
            assert ln != "agent/", \
                f".dockerignore must NOT exclude entire agent/ source: {ln!r}"

    def test_excludes_pytest_cache(self, dockerignore_text: str) -> None:
        assert ".pytest_cache" in dockerignore_text, \
            ".dockerignore should exclude .pytest_cache"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def COMPOSE_ROOT_parent() -> str:
    return str(COMPOSE_PATH.parent)
