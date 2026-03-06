from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flows.core.branching import BranchWriter, BranchWriterConfig


def _init_repo(tmpdir: Path) -> Path:
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, check=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, check=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmpdir, check=True, text=True)
    (tmpdir / "README.md").write_text("initial\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmpdir, check=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, check=True, text=True)
    return tmpdir


def test_branch_writer_creates_branch(tmp_path):
    repo = _init_repo(tmp_path)
    config = BranchWriterConfig(
        repo_path=str(repo),
        base_branch="main",
        branch_prefix="agent/demo",
        auto_push=False,
    )

    writer = BranchWriter(config)
    plan = {
        "files": [
            {"path": "src/example.txt", "content": "hello world"},
            {"path": "meta/data.json", "content": {"foo": "bar"}},
        ],
        "commit_message": "Add example file",
    }

    result = writer.apply_plan(plan)

    assert result["branch"].startswith("agent/demo/")
    file_content = subprocess.run(
        ["git", "show", f"{result['branch']}:src/example.txt"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert file_content == "hello world"

    json_content = subprocess.run(
        ["git", "show", f"{result['branch']}:meta/data.json"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert json.loads(json_content) == {"foo": "bar"}

    branch_name = result["branch"]
    rev = subprocess.run(
        ["git", "rev-parse", branch_name], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()
    assert rev == result["commit"]


def test_branch_writer_skips_when_no_changes(tmp_path):
    repo = _init_repo(tmp_path)
    config = BranchWriterConfig(
        repo_path=str(repo),
        base_branch="main",
        branch_prefix="agent/demo",
        auto_push=False,
    )

    writer = BranchWriter(config)
    plan = {
        "files": [{"path": "README.md", "content": "initial\n"}],
        "commit_message": "No change",
        "branch_name": "agent/demo/static",
    }

    result = writer.apply_plan(plan)
    assert result["branch"] == "agent/demo/static"
    assert result["commit"] is None

