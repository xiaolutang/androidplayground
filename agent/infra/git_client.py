"""git 客户端封装：subprocess 调 git，提供 blame/grep/branch/commit/push。

纯标准库实现（不引 GitPython），为 BB009（push 拒绝场景）提供：
- push 被远端拒绝（403/401/权限）→ GitPushRejectedError，不破坏本地仓库状态。
"""
from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """git 操作异常基类。"""


class GitCommandError(GitError):
    """git 命令失败（非零退出码）。"""


class GitPushRejectedError(GitError):
    """push 被远端拒绝（403/401/权限不足）。

    BB009 监听此异常类型，触发"push 拒绝"事件，
    BugReport 状态保持不变（不破坏）。
    """


@dataclass(frozen=True)
class BlameLine:
    """git blame 单行结果。"""

    commit: str  # commit sha（短）
    author: str
    author_mail: str
    author_time: str  # ISO 时间
    summary: str  # commit summary
    line_no: int
    content: str


@dataclass(frozen=True)
class GrepMatch:
    """git grep 单个匹配。"""

    file: str
    line_no: int
    content: str


# push 拒绝关键词（小写匹配）。覆盖 403/401/权限不足/认证失败等场景。
_PUSH_REJECT_KEYWORDS = (
    "403",
    "401",
    "permission denied",
    "access denied",
    "could not read username",
    "fatal: could not read",
    "operation not permitted",
    "unauthorized",
    "authentication required",
    "not authorized",
)


class GitClient:
    """subprocess 调 git，封装 blame/grep/branch/commit/push。"""

    def __init__(self, repo_path: str | Path):
        self._repo = Path(repo_path).resolve()

    def _run(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """运行 git 命令。失败抛 GitCommandError。"""
        cmd = ["git", "-C", str(self._repo), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise GitError("git binary not found") from e
        if check and result.returncode != 0:
            raise GitCommandError(
                f"git {' '.join(args)} failed (code={result.returncode}): "
                f"{result.stderr.strip()}"
            )
        return result

    def blame(
        self,
        file_path: str,
        *,
        start: int | None = None,
        end: int | None = None,
    ) -> list[BlameLine]:
        """git blame，返回逐行结果。可选行号范围（闭区间）。"""
        args = ["blame", "--line-porcelain", file_path]
        if start is not None and end is not None:
            args += ["-L", f"{start},{end}"]
        result = self._run(args)
        return self._parse_blame_porcelain(result.stdout)

    @staticmethod
    def _parse_blame_porcelain(text: str) -> list[BlameLine]:
        """解析 --line-porcelain 输出。

        --line-porcelain 格式：每个 chunk 以 header 行开头
        （sha orig_lineno final_lineno [group...]），
        随后若干键值行（author / author-mail / author-time / summary ...），
        以一个 tab 开头的行结尾（该行内容）。
        """
        lines = text.split("\n")
        results: list[BlameLine] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            # header 行：非 tab、非空、非空格开头
            if line and not line.startswith("\t") and not line.startswith(" "):
                parts = line.split(" ")
                if len(parts) >= 2:
                    commit = parts[0]
                    # 标准 --line-porcelain：<sha> <orig-lineno> <final-lineno>
                    try:
                        if len(parts) >= 3:
                            line_no = int(parts[2])
                        else:
                            line_no = int(parts[1])
                    except ValueError:
                        line_no = int(parts[1]) if parts[1].isdigit() else 0
                    author = ""
                    author_mail = ""
                    author_time = ""
                    summary = ""
                    content = ""
                    j = i + 1
                    while j < n:
                        sub = lines[j]
                        if sub.startswith("\t"):
                            content = sub[1:]
                            j += 1
                            break
                        if sub.startswith("author "):
                            author = sub[len("author ") :]
                        elif sub.startswith("author-mail "):
                            author_mail = sub[len("author-mail ") :]
                        elif sub.startswith("author-time "):
                            ts_raw = sub[len("author-time ") :]
                            try:
                                ts = int(ts_raw)
                                author_time = datetime.datetime.fromtimestamp(
                                    ts, datetime.UTC
                                ).isoformat()
                            except ValueError:
                                author_time = ts_raw
                        elif sub.startswith("summary "):
                            summary = sub[len("summary ") :]
                        j += 1
                    results.append(
                        BlameLine(
                            commit=commit,
                            author=author,
                            author_mail=author_mail,
                            author_time=author_time,
                            summary=summary,
                            line_no=line_no,
                            content=content,
                        )
                    )
                    i = j
                    continue
            i += 1
        return results

    def grep(
        self,
        pattern: str,
        *,
        file_pattern: str | None = None,
        ref: str = "HEAD",
    ) -> list[GrepMatch]:
        """git grep，在 ref 中搜索 pattern（扩展正则）。

        返回约定：returncode=0 有匹配，=1 无匹配（返回 []），其他抛错。
        """
        args = ["grep", "-n", "-E", pattern, ref]
        if file_pattern:
            args += ["--", file_pattern]
        result = self._run(args, check=False)
        if result.returncode == 1:  # grep 无匹配
            return []
        if result.returncode != 0:
            raise GitCommandError(f"git grep failed: {result.stderr.strip()}")
        matches: list[GrepMatch] = []
        for raw in result.stdout.splitlines():
            # 格式（带 ref）：HEAD:path:lineno:content
            # 或：path:lineno:content
            parts = raw.split(":", 3)
            if len(parts) >= 4 and parts[0] == ref:
                matches.append(
                    GrepMatch(
                        file=parts[1],
                        line_no=int(parts[2]),
                        content=parts[3],
                    )
                )
            elif len(parts) >= 3:
                try:
                    matches.append(
                        GrepMatch(
                            file=parts[0],
                            line_no=int(parts[1]),
                            content=parts[2],
                        )
                    )
                except ValueError:
                    pass
        return matches

    def create_branch(self, branch_name: str, *, from_ref: str = "HEAD") -> None:
        """git checkout -b（从 from_ref 创建并切换）。"""
        self._run(["checkout", "-b", branch_name, from_ref])

    def commit(
        self,
        message: str,
        *,
        allow_empty: bool = False,
        add_all: bool = True,
    ) -> str:
        """git add（可选）+ git commit。返回 commit sha（完整 40 位）。"""
        if add_all:
            self._run(["add", "-A"])
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        self._run(args)
        result = self._run(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def push(
        self,
        *,
        remote: str = "origin",
        refspec: str | None = None,
        timeout: int = 30,
    ) -> None:
        """git push。push 被拒绝（403/401/权限）抛 GitPushRejectedError。

        关键契约：push 失败时不破坏本地仓库状态（分支/commit 都保留）。
        push 是远程操作，本地 HEAD/分支引用不受其影响——失败仅抛异常。
        """
        current_branch_result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        current_branch = current_branch_result.stdout.strip()
        refspec = refspec or current_branch
        cmd = ["git", "-C", str(self._repo), "push", remote, refspec]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise GitError(f"git push timeout after {timeout}s") from e
        except FileNotFoundError as e:
            raise GitError("git binary not found") from e
        if proc.returncode != 0:
            stderr_lower = proc.stderr.lower()
            if any(kw in stderr_lower for kw in _PUSH_REJECT_KEYWORDS):
                raise GitPushRejectedError(
                    f"git push rejected (permission denied): {proc.stderr.strip()}"
                )
            raise GitCommandError(
                f"git push failed (code={proc.returncode}): {proc.stderr.strip()}"
            )

    def get_current_branch(self) -> str:
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def is_clean(self) -> bool:
        """工作区是否干净（无未提交改动）。"""
        result = self._run(["status", "--porcelain"], check=False)
        return result.stdout.strip() == ""
