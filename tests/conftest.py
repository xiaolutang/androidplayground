"""pytest 全局 conftest（在 collection 早期执行，早于 testcontainers import）。

作用：固化 Testcontainers 所需的本机 Docker 环境探测，避免每个开发 /
CI 任务都手动设置环境变量。

策略（方案 A：conftest.py 自动探测）：
1. ``DOCKER_HOST`` 未设且本机 colima 默认 socket 存在 → 自动指向 colima socket。
   覆盖条件：仅当用户未显式设 DOCKER_HOST（用户显式设置优先）。
2. ``TESTCONTAINERS_RYUK_DISABLED`` 未设 → 默认 true。
   原因：colima 下 ryuk 容器挂载失败；禁用 ryuk 仅放弃自动清理泄漏容器，
   开发环境可接受（CI 上若需要 ryuk 可显式设为 false）。

放在仓库根 ``tests/conftest.py``（而非 ``tests/integration/conftest.py``）：
- 根 conftest 对所有测试目录生效，SCH01 等后续任务写在 ``tests/integration/``
  也能直接复用，无需重复配置。
- conftest 在 pytest 启动早期执行，远早于 testcontainers import，
  因此 ``os.environ`` 的设置对 testcontainers 可见。
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. DOCKER_HOST 自动探测（仅当未显式设置 + colima 默认 socket 存在）
# ---------------------------------------------------------------------------
_COLIMA_DEFAULT_SOCKET = Path.home() / ".colima" / "default" / "docker.sock"

if "DOCKER_HOST" not in os.environ and _COLIMA_DEFAULT_SOCKET.exists():
    os.environ["DOCKER_HOST"] = f"unix://{_COLIMA_DEFAULT_SOCKET}"

# ---------------------------------------------------------------------------
# 2. TESTCONTAINERS_RYUK_DISABLED 默认 true（colima 下 ryuk 挂载失败）
#    仅当用户未显式设置时才设默认值（CI 可显式设 false 启用 ryuk）。
# ---------------------------------------------------------------------------
if "TESTCONTAINERS_RYUK_DISABLED" not in os.environ:
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
