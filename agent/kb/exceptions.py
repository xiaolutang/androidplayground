"""KB 异常定义（R001-BF005）。

KBPermissionError：
- 用于 PatternStore 写入权限校验失败（非 BB015 调用方）。
- 故意不继承内置 PermissionError，避免被上层宽泛 ``except PermissionError`` 吞掉。
"""
from __future__ import annotations


class KBPermissionError(Exception):
    """pattern_store 写入权限不足（非 BB015 调用方）。

    特意继承 ``Exception``（不继承 ``PermissionError``），避免被上层
    ``except PermissionError`` 宽泛捕获吞掉，保证权限失败能被上层明确处理。
    """


__all__ = ["KBPermissionError"]
