"""Golden 测试 pytest 配置（R001-INT04 AC-5）。

注册 ``golden`` marker + ``--run-golden`` 选项。

行为：
- 默认（无 ``--run-golden``）：所有 ``@pytest.mark.golden`` 测试 skip。
- ``--run-golden``：golden 测试正常执行。

放在 ``tests/golden/conftest.py``（而非仓库根 ``tests/conftest.py``）：
- 仅对 golden 子目录生效，不影响主 CI 测试收集。
- 避免给 unit / integration 目录引入不必要的 marker 校验逻辑。
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册 ``--run-golden`` 命令行选项。"""
    parser.addoption(
        "--run-golden",
        action="store_true",
        default=False,
        help="Run golden set tests (default: skip)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """注册 golden marker（避免 unknown marker warning）。"""
    config.addinivalue_line(
        "markers",
        "golden: golden set test (deselected unless --run-golden given)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """未传 ``--run-golden`` 时，所有 golden 标记的测试 skip。"""
    if config.getoption("--run-golden"):
        return
    skip_golden = pytest.mark.skip(
        reason="golden test needs --run-golden option to run"
    )
    for item in items:
        if "golden" in item.keywords:
            item.add_marker(skip_golden)
