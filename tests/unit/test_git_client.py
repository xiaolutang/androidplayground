"""git_client 单元测试。

使用 tmp_path + subprocess 真实初始化临时 git 仓库（非 mock），
覆盖 blame/grep/branch/commit/push 全路径，以及 BB009 push 拒绝场景。
"""
from __future__ import annotations

import subprocess
import unittest.mock as mock
from pathlib import Path

import pytest

from agent.infra.git_client import (
    BlameLine,
    GitClient,
    GitCommandError,
    GitError,
    GitPushRejectedError,
    GrepMatch,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """初始化临时 git 仓库，含一个 commit。"""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "commit.gpgsign", "false"],
        check=True,
    )
    (repo / "hello.py").write_text("def hello():\n    return 'world'\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "initial"],
        check=True,
    )
    return repo


# ---------------------------------------------------------------------------
# blame
# ---------------------------------------------------------------------------


def test_blame_returns_correct_lines(git_repo: Path):
    c = GitClient(git_repo)
    blames = c.blame("hello.py")
    assert len(blames) == 2
    assert blames[0].line_no == 1
    assert "def hello" in blames[0].content
    assert blames[1].line_no == 2
    assert "return 'world'" in blames[1].content


def test_blame_fields_populated(git_repo: Path):
    c = GitClient(git_repo)
    blames = c.blame("hello.py")
    first = blames[0]
    assert first.commit  # 非空 sha
    assert first.author == "Test User"
    assert "test@example.com" in first.author_mail
    assert first.summary == "initial"
    assert first.author_time  # ISO 时间非空


def test_blame_with_line_range(git_repo: Path):
    c = GitClient(git_repo)
    blames = c.blame("hello.py", start=1, end=1)
    assert len(blames) == 1
    assert blames[0].line_no == 1


def test_blame_line_range_second_line(git_repo: Path):
    c = GitClient(git_repo)
    blames = c.blame("hello.py", start=2, end=2)
    assert len(blames) == 1
    assert blames[0].line_no == 2


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


def test_grep_returns_matches(git_repo: Path):
    c = GitClient(git_repo)
    matches = c.grep("hello")
    assert len(matches) >= 1
    assert any(m.file == "hello.py" for m in matches)


def test_grep_match_fields(git_repo: Path):
    c = GitClient(git_repo)
    matches = c.grep("hello")
    m = next(x for x in matches if x.file == "hello.py")
    assert m.line_no >= 1
    assert "hello" in m.content


def test_grep_no_match_returns_empty(git_repo: Path):
    c = GitClient(git_repo)
    matches = c.grep("nonexistent_pattern_xyz")
    assert matches == []


def test_grep_with_file_pattern(git_repo: Path):
    c = GitClient(git_repo)
    matches = c.grep("def", file_pattern="hello.py")
    assert len(matches) == 1
    assert matches[0].file == "hello.py"


# ---------------------------------------------------------------------------
# branch / commit
# ---------------------------------------------------------------------------


def test_create_branch(git_repo: Path):
    c = GitClient(git_repo)
    original = c.get_current_branch()
    c.create_branch("fix/bug-1")
    assert c.get_current_branch() == "fix/bug-1"
    branches_result = subprocess.run(
        ["git", "-C", str(git_repo), "branch", "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        original in branches_result.stdout
        or "main" in branches_result.stdout
        or "master" in branches_result.stdout
    )


def test_commit_returns_sha(git_repo: Path):
    c = GitClient(git_repo)
    (git_repo / "new.txt").write_text("content")
    sha = c.commit("add new file")
    assert len(sha) == 40  # 完整 sha


def test_commit_without_add_all(git_repo: Path):
    c = GitClient(git_repo)
    f = git_repo / "manual.txt"
    f.write_text("manual")
    subprocess.run(
        ["git", "-C", str(git_repo), "add", "manual.txt"], check=True
    )
    sha = c.commit("manual add", add_all=False)
    assert len(sha) == 40


def test_is_clean(git_repo: Path):
    c = GitClient(git_repo)
    assert c.is_clean() is True
    (git_repo / "dirty.txt").write_text("dirty")
    assert c.is_clean() is False


def test_get_current_branch(git_repo: Path):
    c = GitClient(git_repo)
    branch = c.get_current_branch()
    assert branch in ("main", "master")


# ---------------------------------------------------------------------------
# push 拒绝 / 失败 / 不破坏状态（BB009 关键契约）
# ---------------------------------------------------------------------------


def test_push_to_nonexistent_remote_raises(git_repo: Path):
    """push 到不存在的 remote：抛 GitError 子类。"""
    c = GitClient(git_repo)
    with pytest.raises(GitError):
        c.push(remote="nonexistent-remote")


def _make_push_only_mock(fake_proc: subprocess.CompletedProcess):
    """返回 side_effect 函数：仅当 args 包含 'push' 时返回 fake_proc，
    其余调用走真实 subprocess.run。

    避免拦截 push 内部的前置命令（rev-parse 获取当前分支）。
    """

    real_run = subprocess.run

    def _side_effect(args, *a, **kw):
        if isinstance(args, list) and "push" in args:
            return fake_proc
        kw.pop("check", None)  # 真实 run 用 check=False
        return real_run(args, *a, check=False, **kw)

    return _side_effect


def test_push_rejected_raises_push_rejected_error(git_repo: Path):
    """push 403 拒绝：抛 GitPushRejectedError，不破坏仓库状态。"""
    c = GitClient(git_repo)
    fake_proc = subprocess.CompletedProcess(
        args=["git", "push"],
        returncode=1,
        stdout="",
        stderr="fatal: unable to access: 403 Permission denied",
    )
    with mock.patch(
        "subprocess.run", side_effect=_make_push_only_mock(fake_proc)
    ):
        with pytest.raises(GitPushRejectedError):
            c.push(remote="origin")
    # 仓库状态完整：有当前分支、commit 还在
    assert c.get_current_branch()
    sha_result = subprocess.run(
        ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(sha_result.stdout.strip()) == 40


def test_push_401_rejected_raises_push_rejected_error(git_repo: Path):
    """push 401：同样抛 GitPushRejectedError。"""
    c = GitClient(git_repo)
    fake_proc = subprocess.CompletedProcess(
        args=["git", "push"],
        returncode=1,
        stdout="",
        stderr="fatal: Authentication failed: 401 Unauthorized",
    )
    with mock.patch(
        "subprocess.run", side_effect=_make_push_only_mock(fake_proc)
    ):
        with pytest.raises(GitPushRejectedError):
            c.push(remote="origin")


def test_push_permission_denied_raises_push_rejected_error(git_repo: Path):
    """permission denied：抛 GitPushRejectedError。"""
    c = GitClient(git_repo)
    fake_proc = subprocess.CompletedProcess(
        args=["git", "push"],
        returncode=1,
        stdout="",
        stderr="remote: Permission denied. Repository access denied.",
    )
    with mock.patch(
        "subprocess.run", side_effect=_make_push_only_mock(fake_proc)
    ):
        with pytest.raises(GitPushRejectedError):
            c.push(remote="origin")


def test_push_does_not_break_repo_on_failure(git_repo: Path):
    """push 失败后本地 HEAD 不变（commit 完整保留）。"""
    c = GitClient(git_repo)
    (git_repo / "v2.txt").write_text("v2")
    c.commit("v2")
    sha_before = subprocess.run(
        ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with pytest.raises(GitError):
        c.push(remote="nonexistent")
    sha_after = subprocess.run(
        ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sha_before == sha_after


def test_push_rejected_error_is_subclass_of_git_error():
    """GitPushRejectedError 必须是 GitError 子类（BB009 捕获基类）。"""
    assert issubclass(GitPushRejectedError, GitError)
    assert issubclass(GitCommandError, GitError)


def test_push_non_permission_error_raises_command_error(git_repo: Path):
    """push 失败但非权限问题（如 rejected non-fast-forward）：GitCommandError。"""
    c = GitClient(git_repo)
    fake_proc = subprocess.CompletedProcess(
        args=["git", "push"],
        returncode=1,
        stdout="",
        stderr="! [rejected] main -> main (non-fast-forward)",
    )
    with mock.patch(
        "subprocess.run", side_effect=_make_push_only_mock(fake_proc)
    ):
        with pytest.raises(GitCommandError) as exc_info:
            c.push(remote="origin")
    # 不是 PushRejected
    assert not isinstance(exc_info.value, GitPushRejectedError)


# ---------------------------------------------------------------------------
# 异常分类
# ---------------------------------------------------------------------------


def test_git_binary_missing_raises_git_error(tmp_path: Path):
    """git 二进制找不到（FileNotFoundError）→ GitError。"""
    c = GitClient(tmp_path)
    with mock.patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
        with pytest.raises(GitError) as exc_info:
            c.blame("x")
    # 不是 CommandError（命令没执行）
    assert not isinstance(exc_info.value, GitCommandError)


def test_command_error_raises_git_command_error(git_repo: Path):
    c = GitClient(git_repo)
    with pytest.raises(GitCommandError):
        c._run(["log", "--nonexistent-option"])


def test_command_error_message_contains_exit_code(git_repo: Path):
    c = GitClient(git_repo)
    with pytest.raises(GitCommandError, match="code="):
        c._run(["log", "--nonexistent-option"])


def test_dataclasses_are_frozen():
    """BlameLine / GrepMatch 是 frozen dataclass。"""
    b = BlameLine(
        commit="abc",
        author="a",
        author_mail="m",
        author_time="t",
        summary="s",
        line_no=1,
        content="c",
    )
    g = GrepMatch(file="f", line_no=1, content="c")
    with pytest.raises((AttributeError, Exception)):
        b.commit = "x"  # type: ignore[misc]
    with pytest.raises((AttributeError, Exception)):
        g.file = "x"  # type: ignore[misc]
