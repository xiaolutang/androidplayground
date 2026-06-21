"""PRSubmitter 单元测试（R001-BB009，AC-1 ~ AC-3 + INV-2 守护）。

覆盖：
- AC-1 Tier1 普通 PR（is_draft=False）+ pr_url 返回
- AC-2 Tier2 draft PR（is_draft=True）
- AC-3 push 失败不破坏状态（commit_sha 保留 / branch_name 保留 / 不 re-raise）
- INV-2 守护：类无 merge 方法 / available_operations 不含 merge
- 降级处理：git_client=None / 缺方法 / 各阶段异常
- 透传：commit_message / pr_title / pr_body
- 边界：多文件提交、branch 命名含 tier + timestamp
"""
from __future__ import annotations

import pytest

from agent.fix.pr_submitter import (
    PRSubmitter,
    REQUIRED_GIT_METHODS,
)


# ---------------------------------------------------------------------------
# 测试辅助：MockGitClient
# ---------------------------------------------------------------------------
class MockGitClient:
    """模拟 GitClient（满足 duck typing 的所有必需方法）。"""

    def __init__(
        self,
        *,
        branch_error: Exception | None = None,
        add_error: Exception | None = None,
        commit_error: Exception | None = None,
        push_error: Exception | None = None,
        pr_error: Exception | None = None,
        commit_sha: str = "abc123def456789012345678901234567890abcd",
        pr_url: str = "https://github.com/example/repo/pull/1",
    ) -> None:
        self.branch_error = branch_error
        self.add_error = add_error
        self.commit_error = commit_error
        self.push_error = push_error
        self.pr_error = pr_error
        self._commit_sha = commit_sha
        self._pr_url = pr_url
        # 调用记录（供测试断言透传）
        self.create_branch_calls: list[str] = []
        self.add_calls: list[tuple] = []
        self.commit_calls: list[str] = []
        self.push_calls: list[tuple] = []
        self.create_pr_calls: list[dict] = []

    def create_branch(self, branch_name: str, *, from_ref: str = "HEAD") -> None:
        if self.branch_error:
            raise self.branch_error
        self.create_branch_calls.append(branch_name)

    def add(self, *files: str) -> None:
        if self.add_error:
            raise self.add_error
        self.add_calls.append(files)

    def commit(self, message: str, *, allow_empty: bool = False) -> str:
        if self.commit_error:
            raise self.commit_error
        self.commit_calls.append(message)
        return self._commit_sha

    def push(self, *, remote: str = "origin", refspec: str | None = None) -> None:
        if self.push_error:
            raise self.push_error
        self.push_calls.append((remote, refspec))

    def create_pr(
        self,
        *,
        remote: str,
        base: str,
        head: str,
        title: str,
        body: str,
        is_draft: bool,
    ) -> str:
        if self.pr_error:
            raise self.pr_error
        self.create_pr_calls.append(
            {
                "remote": remote,
                "base": base,
                "head": head,
                "title": title,
                "body": body,
                "is_draft": is_draft,
            }
        )
        return self._pr_url


@pytest.fixture
def mock_git() -> MockGitClient:
    """默认成功的 MockGitClient。"""
    return MockGitClient()


@pytest.fixture
def submitter(mock_git: MockGitClient) -> PRSubmitter:
    """默认 PRSubmitter（注入 mock_git）。"""
    return PRSubmitter(git_client=mock_git)


def _make_kwargs(**overrides) -> dict:
    """构造 submit() 默认参数。"""
    defaults = {
        "fix_patch_content": "diff --git a/x b/x\n+new",
        "files_to_commit": ["src/x.py"],
        "commit_message": "fix: patch x",
        "tier": "tier_1",
        "pr_title": "[Auto] fix x",
        "pr_body": "auto-generated PR",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# AC-1: Tier1 普通 PR（is_draft=False）+ pr_url 返回
# ---------------------------------------------------------------------------
def test_tier1_submit_returns_normal_pr(submitter: PRSubmitter):
    """AC-1：Tier1 提交 → is_draft=False + pr_url 返回 + submitted=True。"""
    result = submitter.submit(**_make_kwargs(tier="tier_1"))

    assert result.submitted is True
    assert result.is_draft is False
    assert result.pr_url == "https://github.com/example/repo/pull/1"
    assert result.error is None
    assert result.tier == "tier_1"
    assert result.branch_name is not None
    assert result.commit_sha is not None


def test_tier1_pr_call_is_draft_false(submitter: PRSubmitter, mock_git: MockGitClient):
    """AC-1：create_pr 被调用时 is_draft=False。"""
    submitter.submit(**_make_kwargs(tier="tier_1"))

    assert len(mock_git.create_pr_calls) == 1
    assert mock_git.create_pr_calls[0]["is_draft"] is False


# ---------------------------------------------------------------------------
# AC-2: Tier2 draft PR（is_draft=True）
# ---------------------------------------------------------------------------
def test_tier2_submit_returns_draft_pr(submitter: PRSubmitter):
    """AC-2：Tier2 提交 → is_draft=True + pr_url 返回。"""
    result = submitter.submit(**_make_kwargs(tier="tier_2"))

    assert result.submitted is True
    assert result.is_draft is True
    assert result.pr_url is not None


def test_tier2_pr_call_is_draft_true(submitter: PRSubmitter, mock_git: MockGitClient):
    """AC-2：create_pr 被调用时 is_draft=True。"""
    submitter.submit(**_make_kwargs(tier="tier_2"))

    assert mock_git.create_pr_calls[0]["is_draft"] is True


# ---------------------------------------------------------------------------
# AC-3: push 失败不破坏状态
# ---------------------------------------------------------------------------
def test_push_failure_preserves_commit_sha():
    """AC-3：push 异常 → submitted=False + commit_sha 保留 + 不 re-raise。"""
    git = MockGitClient(push_error=RuntimeError("403 permission denied"))
    sub = PRSubmitter(git_client=git)

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert result.commit_sha == "abc123def456789012345678901234567890abcd"
    assert result.branch_name is not None
    assert result.error is not None
    assert "push failed" in result.error
    assert "permission denied" in result.error


def test_push_failure_does_not_call_create_pr():
    """AC-3：push 失败后不调 create_pr。"""
    git = MockGitClient(push_error=RuntimeError("network error"))
    sub = PRSubmitter(git_client=git)

    sub.submit(**_make_kwargs())

    assert len(git.create_pr_calls) == 0


# ---------------------------------------------------------------------------
# branch 命名：含 tier + timestamp
# ---------------------------------------------------------------------------
def test_branch_name_contains_tier(submitter: PRSubmitter):
    """branch 命名含 tier 字段。"""
    result = submitter.submit(**_make_kwargs(tier="tier_1"))

    assert "tier_1" in result.branch_name


def test_branch_name_contains_timestamp(submitter: PRSubmitter):
    """branch 命名含 timestamp（13 位毫秒）。"""
    result = submitter.submit(**_make_kwargs(tier="tier_2"))

    # 格式：fix/auto/tier_2/{ts}-{uuid8}（prefix 可含 /）
    last_segment = result.branch_name.split("/")[-1]
    ts_uuid = last_segment.split("-")
    # ts 是 13 位毫秒数字
    assert ts_uuid[0].isdigit()
    assert len(ts_uuid[0]) == 13


def test_branch_name_uses_custom_prefix(mock_git: MockGitClient):
    """branch_prefix 参数生效。"""
    sub = PRSubmitter(git_client=mock_git)
    result = sub.submit(**_make_kwargs(branch_prefix="fix/manual"))

    assert result.branch_name.startswith("fix/manual/tier_1/")


# ---------------------------------------------------------------------------
# create_branch 异常 → submitted=False + error 信息 + 不破坏状态
# ---------------------------------------------------------------------------
def test_create_branch_failure_returns_not_submitted():
    """create_branch 异常 → submitted=False + error 含异常信息。"""
    git = MockGitClient(branch_error=RuntimeError("branch exists"))
    sub = PRSubmitter(git_client=git)

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert result.error is not None
    assert "create_branch" in result.error or "branch exists" in result.error


# ---------------------------------------------------------------------------
# commit 异常 → submitted=False
# ---------------------------------------------------------------------------
def test_commit_failure_returns_not_submitted():
    """commit 异常 → submitted=False + error 含异常信息。"""
    git = MockGitClient(commit_error=RuntimeError("nothing to commit"))
    sub = PRSubmitter(git_client=git)

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert result.error is not None
    assert "commit" in result.error.lower() or "nothing" in result.error


# ---------------------------------------------------------------------------
# create_pr 异常 → submitted=False + branch_name 保留
# ---------------------------------------------------------------------------
def test_create_pr_failure_preserves_branch_name():
    """create_pr 异常 → submitted=False + branch_name 保留（供人工补 PR）。"""
    git = MockGitClient(pr_error=RuntimeError("API rate limit"))
    sub = PRSubmitter(git_client=git)

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert result.branch_name is not None
    assert result.commit_sha is not None  # commit + push 都成功
    assert result.error is not None
    assert "create_pr" in result.error or "rate limit" in result.error


# ---------------------------------------------------------------------------
# git_client=None → ValueError
# ---------------------------------------------------------------------------
def test_git_client_none_raises_value_error():
    """git_client=None → ValueError（无法工作）。"""
    with pytest.raises(ValueError, match="git_client is required"):
        PRSubmitter(git_client=None)


# ---------------------------------------------------------------------------
# git_client 缺方法 → submitted=False + error 含 missing method
# ---------------------------------------------------------------------------
def test_git_client_missing_method_returns_error():
    """git_client 缺 create_pr 方法 → submitted=False + error 含 missing method。"""

    class IncompleteGitClient:
        def create_branch(self, *args, **kwargs): ...
        def add(self, *args, **kwargs): ...
        def commit(self, *args, **kwargs): ...
        def push(self, *args, **kwargs): ...
        # 故意缺 create_pr

    sub = PRSubmitter(git_client=IncompleteGitClient())

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert result.error is not None
    assert "missing method" in result.error
    assert "create_pr" in result.error


def test_git_client_missing_push_returns_error():
    """git_client 缺 push 方法 → submitted=False + error 含 missing method。"""

    class MissingPush:
        def create_branch(self, *args, **kwargs): ...
        def add(self, *args, **kwargs): ...
        def commit(self, *args, **kwargs): ...
        def create_pr(self, *args, **kwargs): ...

    sub = PRSubmitter(git_client=MissingPush())

    result = sub.submit(**_make_kwargs())

    assert result.submitted is False
    assert "missing method" in result.error
    assert "push" in result.error


# ---------------------------------------------------------------------------
# 多文件提交（files_to_commit 列表）
# ---------------------------------------------------------------------------
def test_multi_file_commit_passes_to_git_add(submitter: PRSubmitter, mock_git: MockGitClient):
    """多文件提交：files_to_commit 列表全部传给 git_client.add。"""
    files = ["src/a.py", "src/b.py", "tests/test_a.py"]
    submitter.submit(**_make_kwargs(files_to_commit=files))

    assert len(mock_git.add_calls) == 1
    assert set(mock_git.add_calls[0]) == set(files)


# ---------------------------------------------------------------------------
# INV-2 守护：类无 merge 方法
# ---------------------------------------------------------------------------
def test_class_has_no_merge_method():
    """INV-2：PRSubmitter 类无 merge / merge_pr / auto_merge 方法。"""
    assert not hasattr(PRSubmitter, "merge")
    assert not hasattr(PRSubmitter, "merge_pr")
    assert not hasattr(PRSubmitter, "auto_merge")


def test_instance_has_no_merge_method(submitter: PRSubmitter):
    """INV-2：PRSubmitter 实例无 merge 方法。"""
    assert not hasattr(submitter, "merge")
    assert not hasattr(submitter, "merge_pr")


# ---------------------------------------------------------------------------
# available_operations 不含 merge
# ---------------------------------------------------------------------------
def test_available_operations_excludes_merge():
    """available_operations() 不含 merge。"""
    ops = PRSubmitter.available_operations()

    assert "merge" not in ops
    assert "merge_pr" not in ops
    assert "auto_merge" not in ops


def test_available_operations_includes_required():
    """available_operations() 含 create_branch / commit / push / create_pr。"""
    ops = PRSubmitter.available_operations()

    assert "create_branch" in ops
    assert "commit" in ops
    assert "push" in ops
    assert "create_pr" in ops


# ---------------------------------------------------------------------------
# commit_message 透传
# ---------------------------------------------------------------------------
def test_commit_message_passthrough(submitter: PRSubmitter, mock_git: MockGitClient):
    """commit_message 透传给 git_client.commit。"""
    msg = "fix(infra): resolve push rejected edge case [BB009]"
    submitter.submit(**_make_kwargs(commit_message=msg))

    assert mock_git.commit_calls[-1] == msg


# ---------------------------------------------------------------------------
# pr_title / pr_body 透传
# ---------------------------------------------------------------------------
def test_pr_title_body_passthrough(submitter: PRSubmitter, mock_git: MockGitClient):
    """pr_title / pr_body 透传给 git_client.create_pr。"""
    title = "[Auto][Tier1] Fix NPE in reproduce_runner"
    body = "## Summary\n- Fix NPE\n\n## Test Plan\n- [x] unit test"
    submitter.submit(**_make_kwargs(pr_title=title, pr_body=body))

    assert mock_git.create_pr_calls[-1]["title"] == title
    assert mock_git.create_pr_calls[-1]["body"] == body


# ---------------------------------------------------------------------------
# 补充：uncommon tier 保守降级为 draft
# ---------------------------------------------------------------------------
def test_uncommon_tier_fallbacks_to_draft(submitter: PRSubmitter):
    """非 tier_1/tier_2 的 tier → 保守降级为 draft=True。"""
    result = submitter.submit(**_make_kwargs(tier="tier_3"))

    # tier_3 走 draft（保守，避免误合）
    assert result.is_draft is True


# ---------------------------------------------------------------------------
# 补充：REQUIRED_GIT_METHODS 常量
# ---------------------------------------------------------------------------
def test_required_git_methods_constant():
    """REQUIRED_GIT_METHODS 含 5 个必需方法（不含 merge）。"""
    assert "create_branch" in REQUIRED_GIT_METHODS
    assert "add" in REQUIRED_GIT_METHODS
    assert "commit" in REQUIRED_GIT_METHODS
    assert "push" in REQUIRED_GIT_METHODS
    assert "create_pr" in REQUIRED_GIT_METHODS
    assert "merge" not in REQUIRED_GIT_METHODS
