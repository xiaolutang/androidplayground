"""PR 提交器（R001-BB009）。

依据：
- Sprint Contract R001-BB009（mode: direct，3 AC）
- INF06 git_client 接口（create_branch / commit / push / create_pr）
- BB006 ConfidenceTier（TIER_1 普通 PR / TIER_2 draft PR）
- INV-2 约束：禁止自主合并（merge），合并由人在闸门批准后执行

设计要点：
1. **Tier 分流**：
   - Tier 1 → is_draft=False（普通 PR，可合并）
   - Tier 2 → is_draft=True（draft PR，标记 WIP）
2. **push 失败不破坏状态**（AC3）：
   - 捕获 git_client 异常 → 返回 PRSubmissionResult(submitted=False, error=str(e))
   - 不 re-raise；已 commit 但未 push 的状态保留（供回滚/排查）
3. **降级处理**：
   - git_client=None → ValueError（PR 提交器无 git_client 无法工作）
   - git_client 缺方法（create_branch/add/commit/push/create_pr 之一缺失）
     → 返回 PRSubmissionResult(submitted=False, error="git_client missing method: X")
   - push 失败但 commit 成功 → submitted=False 但 commit_sha 保留
   - create_pr 失败但 push 成功 → submitted=False 但 branch_name 保留（人工补 PR）
4. **INV-2 守护**：
   - 本类不提供 merge / merge_pr / auto_merge 方法
   - 类 docstring 明示"禁止自主合并"
   - available_operations() 类方法返回 ["create_branch", "commit", "push", "create_pr"]
     （不含 merge），供调用方自检
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

__all__ = [
    "PRSubmissionResult",
    "PRSubmitter",
    "REQUIRED_GIT_METHODS",
]

# git_client 必需方法清单（提交 PR 全链路）
REQUIRED_GIT_METHODS: tuple[str, ...] = (
    "create_branch",
    "add",
    "commit",
    "push",
    "create_pr",
)


@dataclass
class PRSubmissionResult:
    """PR 提交结果。

    Attributes:
        submitted: True=成功提交（PR 已创建）；False=失败（commit/push/pr error）。
        pr_url: PR URL（失败时 None）。
        branch_name: 分支名（create_pr 失败时仍保留，供人工补 PR）。
        commit_sha: commit SHA（push 失败时仍保留，供回滚/排查）。
        is_draft: True=draft PR；False=普通 PR。
        tier: "tier_1" / "tier_2"（来自 BB006 ConfidenceEvaluator）。
        error: 失败原因（submitted=False 时非 None）。
        reasoning: 解释链（决策路径，便于排查）。
    """

    submitted: bool
    pr_url: str | None
    branch_name: str | None
    commit_sha: str | None
    is_draft: bool
    tier: str
    error: str | None
    reasoning: str = ""


class PRSubmitter:
    """PR 提交器：建分支 + commit + push + 提 PR。

    INV-2 守护：**禁止自主合并**（merge），合并由人在闸门批准后执行。
    本类不提供 merge / merge_pr / auto_merge 方法。
    """

    def __init__(
        self,
        *,
        git_client: Any,
        repo_root: str = ".",
        remote_name: str = "origin",
        base_branch: str = "main",
    ) -> None:
        """初始化 PR 提交器。

        Args:
            git_client: INF06 GitClient 实例（必需，不能为 None）。
            repo_root: 仓库根路径（仅记录用，git 操作委托给 git_client）。
            remote_name: 远端名（默认 "origin"）。
            base_branch: 目标基分支（默认 "main"，PR 合并到此分支）。

        Raises:
            ValueError: git_client 为 None。
        """
        if git_client is None:
            raise ValueError(
                "git_client is required (PR submitter cannot work without git_client)"
            )
        self._git = git_client
        self._repo_root = repo_root
        self._remote = remote_name
        self._base = base_branch
        # 内部状态：最后一次 _create_branch_and_commit 错误（供 submit() 读取回填）
        self._last_branch_commit_error: str | None = None

    # ------------------------------------------------------------------
    # INV-2 守护
    # ------------------------------------------------------------------
    @classmethod
    def available_operations(cls) -> list[str]:
        """返回本类支持的操作列表（**不含 merge**）。

        供调用方自检：合并由人工在 PR 平台批准后执行（INV-2）。

        Returns:
            ["create_branch", "commit", "push", "create_pr"]
        """
        return ["create_branch", "commit", "push", "create_pr"]

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        fix_patch_content: str,
        files_to_commit: list[str],
        commit_message: str,
        tier: str,
        pr_title: str,
        pr_body: str,
        branch_prefix: str = "fix/auto",
    ) -> PRSubmissionResult:
        """主入口：建分支 + commit + push + create_pr。

        Tier 分流：
        - Tier 1 → is_draft=False（普通 PR，可合并）
        - Tier 2 → is_draft=True（draft PR，标记 WIP）

        push 失败不破坏状态（AC3）：
        - 捕获 git_client 异常 → 返回 PRSubmissionResult(submitted=False, error=str(e))
        - 不 re-raise；已 commit 未 push 的状态保留

        Args:
            fix_patch_content: 补丁内容（diff 或文件内容，用于审计）。
            files_to_commit: 待提交文件路径列表。
            commit_message: commit message（透传给 git_client.commit）。
            tier: "tier_1" / "tier_2"（来自 BB006 ConfidenceEvaluator）。
            pr_title: PR 标题（透传给 git_client.create_pr）。
            pr_body: PR 正文（透传给 git_client.create_pr）。
            branch_prefix: 分支前缀（默认 "fix/auto"）。

        Returns:
            PRSubmissionResult：提交结果（成功/失败均返回，不抛异常）。
        """
        reasoning_parts: list[str] = [f"tier={tier}"]

        # 1. 校验 git_client 方法齐全
        missing = self._missing_methods()
        if missing:
            return PRSubmissionResult(
                submitted=False,
                pr_url=None,
                branch_name=None,
                commit_sha=None,
                is_draft=False,
                tier=tier,
                error=f"git_client missing method: {', '.join(missing)}",
                reasoning="; ".join(
                    reasoning_parts + [f"missing={missing}"]
                ),
            )
        reasoning_parts.append("git_client methods OK")

        # 2. Tier → is_draft 分流
        is_draft = self._tier_to_draft(tier)
        reasoning_parts.append(f"is_draft={is_draft}")
        # Tier 3/4 不应该走到 PR 提交（应由上游降级路径处理），但本类容错处理：
        # 非 tier_1 的全部走 draft（保守，避免误合）。
        if tier not in ("tier_1", "tier_2"):
            reasoning_parts.append(
                f"unexpected tier={tier}, fallback to draft=True (conservative)"
            )
            is_draft = True

        # 3. 生成分支名
        branch_name = self._generate_branch_name(branch_prefix, tier)
        reasoning_parts.append(f"branch={branch_name}")

        # 4. create_branch + add + commit
        commit_sha = self._create_branch_and_commit(
            branch_name, files_to_commit, commit_message
        )
        if commit_sha is None:
            # _create_branch_and_commit 内部已捕获异常，这里返回失败
            return PRSubmissionResult(
                submitted=False,
                pr_url=None,
                branch_name=branch_name,
                commit_sha=None,
                is_draft=is_draft,
                tier=tier,
                error=self._last_branch_commit_error,
                reasoning="; ".join(
                    reasoning_parts + ["create_branch/commit failed"]
                ),
            )
        reasoning_parts.append(f"commit_sha={commit_sha[:8]}")

        # 5. push
        push_error = self._push(branch_name)
        if push_error is not None:
            # push 失败但 commit 成功：返回 submitted=False，commit_sha 保留（AC3）
            return PRSubmissionResult(
                submitted=False,
                pr_url=None,
                branch_name=branch_name,
                commit_sha=commit_sha,
                is_draft=is_draft,
                tier=tier,
                error=push_error,
                reasoning="; ".join(
                    reasoning_parts + [f"push failed: {push_error}"]
                ),
            )
        reasoning_parts.append("push OK")

        # 6. create_pr
        pr_url, pr_error = self._create_pr(
            branch_name, pr_title, pr_body, is_draft
        )
        if pr_error is not None:
            # create_pr 失败但 push 成功：返回 submitted=False，branch_name 保留
            return PRSubmissionResult(
                submitted=False,
                pr_url=None,
                branch_name=branch_name,
                commit_sha=commit_sha,
                is_draft=is_draft,
                tier=tier,
                error=pr_error,
                reasoning="; ".join(
                    reasoning_parts + [f"create_pr failed: {pr_error}"]
                ),
            )

        reasoning_parts.append(f"pr_url={pr_url}")
        return PRSubmissionResult(
            submitted=True,
            pr_url=pr_url,
            branch_name=branch_name,
            commit_sha=commit_sha,
            is_draft=is_draft,
            tier=tier,
            error=None,
            reasoning="; ".join(reasoning_parts),
        )

    # ------------------------------------------------------------------
    # 内部：方法齐全性检查
    # ------------------------------------------------------------------
    def _missing_methods(self) -> list[str]:
        """检查 git_client 是否缺失必需方法。

        Returns:
            缺失的方法名列表（空列表表示齐全）。
        """
        return [
            m for m in REQUIRED_GIT_METHODS if not hasattr(self._git, m)
        ]

    # ------------------------------------------------------------------
    # 内部：Tier → is_draft 分流
    # ------------------------------------------------------------------
    @staticmethod
    def _tier_to_draft(tier: str) -> bool:
        """Tier → is_draft 分流。

        - tier_1 → False（普通 PR）
        - tier_2 → True（draft PR）
        - 其他 → True（保守，避免误合）
        """
        if tier == "tier_1":
            return False
        # tier_2 及其他全部 draft
        return True

    # ------------------------------------------------------------------
    # 内部：生成分支名
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_branch_name(prefix: str, tier: str) -> str:
        """生成分支名：{prefix}/{tier}/{timestamp}-{short_uuid}。

        格式设计：
        - prefix：业务前缀（如 fix/auto）
        - tier：置信度 tier（tier_1 / tier_2）
        - timestamp：Unix 毫秒，保证时间序
        - short_uuid：uuid4 前 8 位，避免同毫秒冲突

        Returns:
            分支名，如 "fix/auto/tier_1/1718971200000-a1b2c3d4"
        """
        ts = int(time.time() * 1000)
        short_uuid = uuid.uuid4().hex[:8]
        return f"{prefix}/{tier}/{ts}-{short_uuid}"

    # ------------------------------------------------------------------
    # 内部：create_branch + add + commit（捕获异常，不 re-raise）
    # ------------------------------------------------------------------
    def _create_branch_and_commit(
        self,
        branch_name: str,
        files: list[str],
        commit_message: str,
    ) -> str | None:
        """create_branch + add + commit。

        Args:
            branch_name: 分支名。
            files: 待提交文件路径列表（传给 git_client.add）。
            commit_message: commit message。

        Returns:
            commit SHA（成功）；None（失败，错误信息写入 self._last_branch_commit_error）。
        """
        try:
            self._git.create_branch(branch_name)
            # add：传文件列表（git_client.add 接受 *files 或 list，duck typing）
            self._git.add(*files)
            sha = self._git.commit(commit_message)
            self._last_branch_commit_error = None
            return sha
        except Exception as e:  # noqa: BLE001 — 降级处理，不破坏状态
            self._last_branch_commit_error = (
                f"create_branch/commit failed: {type(e).__name__}: {e}"
            )
            return None

    # ------------------------------------------------------------------
    # 内部：push（捕获异常，不 re-raise）
    # ------------------------------------------------------------------
    def _push(self, branch_name: str) -> str | None:
        """push 分支到远端。

        Args:
            branch_name: 分支名（作为 refspec）。

        Returns:
            None（成功）；error 字符串（失败，不破坏 working tree）。
        """
        try:
            self._git.push(remote=self._remote, refspec=branch_name)
            return None
        except Exception as e:  # noqa: BLE001 — 降级处理，不破坏状态
            return f"push failed: {type(e).__name__}: {e}"

    # ------------------------------------------------------------------
    # 内部：create_pr（捕获异常，不 re-raise）
    # ------------------------------------------------------------------
    def _create_pr(
        self,
        branch_name: str,
        title: str,
        body: str,
        is_draft: bool,
    ) -> tuple[str | None, str | None]:
        """create_pr。

        Args:
            branch_name: 源分支（head）。
            title: PR 标题。
            body: PR 正文。
            is_draft: 是否 draft PR。

        Returns:
            (pr_url, error)：成功 (url, None)；失败 (None, error)。
        """
        try:
            pr_url = self._git.create_pr(
                remote=self._remote,
                base=self._base,
                head=branch_name,
                title=title,
                body=body,
                is_draft=is_draft,
            )
            return (pr_url, None)
        except Exception as e:  # noqa: BLE001 — 降级处理，不破坏状态
            return (None, f"create_pr failed: {type(e).__name__}: {e}")
