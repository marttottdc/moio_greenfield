"""Utilities for materialising flow outputs into git branches."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Mapping

from django.utils import timezone


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BranchWriterConfig:
    repo_path: str = "."
    base_branch: str = "main"
    branch_prefix: str = "agent"
    auto_push: bool = False
    dry_run: bool = False
    user_name: str | None = None
    user_email: str | None = None


class BranchWriter:
    """Utility that materialises agent outputs as git commits."""

    def __init__(self, config: BranchWriterConfig) -> None:
        self.config = config
        self.repo_path = Path(config.repo_path).resolve()
        self._last_commit: str | None = None
        self._last_branch: str | None = None

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        logger.debug("[branch-writer] git %s", " ".join(args))
        return subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=self.repo_path,
            check=check,
            text=True,
            capture_output=True,
        )

    def _ensure_identity(self) -> None:
        if self.config.dry_run:
            return

        def _ensure(key: str, value: str) -> None:
            current = self._run_git("config", "--get", key, check=False)
            if current.returncode != 0 or not current.stdout.strip():
                self._run_git("config", key, value)

        if self.config.user_name:
            _ensure("user.name", self.config.user_name)
        if self.config.user_email:
            _ensure("user.email", self.config.user_email)

    def _branch_exists(self, branch: str) -> bool:
        result = self._run_git("rev-parse", "--verify", branch, check=False)
        return result.returncode == 0

    def _current_branch(self) -> str | None:
        result = self._run_git("branch", "--show-current", check=False)
        return result.stdout.strip() or None

    def _checkout(self, branch: str, create: bool = False) -> None:
        if self.config.dry_run:
            return
        if create:
            self._run_git("checkout", "-b", branch)
        else:
            self._run_git("checkout", branch)

    def _switch_branch(self, branch: str) -> None:
        if self.config.dry_run:
            return
        exists = self._branch_exists(branch)
        if not exists:
            self._checkout(self.config.base_branch)
            self._checkout(branch, create=True)
        else:
            self._checkout(branch)

    def apply_plan(self, plan: Mapping[str, Any]) -> Dict[str, Any]:
        files = plan.get("files") or plan.get("changes")
        if not files:
            raise ValueError("Branch plan must include a non-empty 'files' collection")

        branch_name = plan.get("branch_name")
        if not branch_name:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            branch_name = f"{self.config.branch_prefix}/{timestamp}"

        commit_message = plan.get("commit_message") or "Flow agent update"

        self._last_branch = branch_name
        previous_branch = self._current_branch()

        if not self.config.dry_run:
            self._ensure_identity()
            self._switch_branch(branch_name)

        staged_paths: List[Path] = []
        for entry in files:
            if not isinstance(entry, Mapping):
                raise ValueError("Each file entry must be a mapping with 'path' and 'content'")
            path_value = entry.get("path")
            content_value = entry.get("content")
            if not path_value:
                raise ValueError("File entry missing 'path'")

            repo_file = self.repo_path / Path(path_value)
            repo_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.config.dry_run:
                text = content_value if isinstance(content_value, str) else json.dumps(content_value, indent=2)
                repo_file.write_text(text)
            staged_paths.append(repo_file.relative_to(self.repo_path))

        if not self.config.dry_run:
            self._run_git("add", *[str(path) for path in staged_paths])
            status = self._run_git("status", "--porcelain")
            if status.stdout.strip():
                self._run_git("commit", "-m", commit_message)
                self._last_commit = self._run_git("rev-parse", "HEAD").stdout.strip() or None
                if self.config.auto_push:
                    self._run_git("push", "-u", "origin", branch_name)
            else:
                logger.info("No changes detected for branch plan, skipping commit")
        else:
            logger.info("Dry-run branch plan for %s: %s", branch_name, staged_paths)

        if previous_branch and not self.config.dry_run:
            self._checkout(previous_branch)

        return {
            "branch": branch_name,
            "commit": self._last_commit,
            "files": [str(path) for path in staged_paths],
        }


__all__ = ["BranchWriter", "BranchWriterConfig"]
