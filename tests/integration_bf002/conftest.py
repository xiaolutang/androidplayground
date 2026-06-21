"""BF002 模拟器集成测试 pytest 配置（R001-INT03）。

注册 ``emulator`` marker + ``--run-emulator`` 选项。

行为：
- 默认（无 ``--run-emulator``）：所有 ``@pytest.mark.emulator`` 测试 skip。
- ``--run-emulator``：emulator 测试正常执行。

放在 ``tests/integration_bf002/conftest.py``（而非仓库根 ``tests/conftest.py``）：
- 仅对 integration_bf002 子目录生效，不影响主 CI 测试收集。
- 避免给 unit / integration / golden 目录引入不必要的 marker 校验逻辑。

与 ``tests/golden/conftest.py`` 的 ``--run-golden`` 模式完全一致。
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册 ``--run-emulator`` 命令行选项。"""
    parser.addoption(
        "--run-emulator",
        action="store_true",
        default=False,
        help="Run BF002 emulator integration tests (default: skip)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """注册 emulator marker（避免 unknown marker warning）。"""
    config.addinivalue_line(
        "markers",
        "emulator: BF002 emulator integration test (deselected unless "
        "--run-emulator given)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """未传 ``--run-emulator`` 时，所有 emulator 标记的测试 skip。"""
    if config.getoption("--run-emulator"):
        return
    skip_emulator = pytest.mark.skip(
        reason="emulator integration test needs --run-emulator option to run"
    )
    for item in items:
        if "emulator" in item.keywords:
            item.add_marker(skip_emulator)
