# R001-DEP01：agent 镜像（Python 3.13 + adb platform-tools）
#
# 依据：
# - Sprint Contract R001-DEP01（mode: direct）
# - 技术决策 D10（容器经 host.docker.internal:5037 连宿主 adb server）
# - pyproject.toml 位于 agent/ 目录（package-dir 上指 ..）
#
# 层缓存优化：
# - 先 COPY pyproject.toml + pip install，再 COPY 业务代码
# - 代码变动只重建最后一层，依赖层稳定缓存

FROM python:3.13-slim

# 元数据
LABEL org.opencontainers.image.title="bugfix-agent" \
      org.opencontainers.image.description="Client Bug Fix Agent (FastAPI + LangGraph)" \
      org.opencontainers.image.source="https://github.com/androidplayground/androidplayground"

# 安装 adb（Debian 仓库的 android-tools-adb 即 platform-tools 中 adb）+ tini 作为 init
# tini：处理信号转发，避免僵尸进程（uvicorn 子进程场景）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        android-tools-adb \
        tini \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖描述文件（层缓存优化：依赖变动少时跳过后续 pip install）
COPY agent/pyproject.toml /app/agent/pyproject.toml

# 安装 Python 依赖
# --no-cache-dir：避免 pip 缓存占用镜像体积
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e "/app/agent[test]"

# 复制业务代码
COPY agent/ /app/agent/

# 默认环境变量（容器内 adb 走 host.docker.internal，详见 docker-compose.yml）
ENV ADB_HOST=host.docker.internal \
    ADB_PORT=5037 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 健康检查：FastAPI /health 端点
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000

# tini 转发信号，uvicorn 以 1 worker 起步（开发期）
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
