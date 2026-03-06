from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class SkillEntry:
    key: str
    name: str
    path: Path
    content: str
    enabled: bool


def _discover_skill_md_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    direct = root / "SKILL.md"
    if direct.exists() and direct.is_file():
        candidates.append(direct)
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if skill_file.exists() and skill_file.is_file():
            candidates.append(skill_file)
    return candidates


def load_skills(skill_dirs: Iterable[Path], enabled_keys: list[str]) -> list[SkillEntry]:
    wanted = {key.strip().lower() for key in enabled_keys if key.strip()}
    entries: list[SkillEntry] = []

    for directory in skill_dirs:
        root = directory.expanduser()
        if not root.exists() or not root.is_dir():
            continue
        for skill_file in _discover_skill_md_files(root):
            key = skill_file.parent.name.lower()
            try:
                content = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            title_line = next((line.strip() for line in content.splitlines() if line.strip().startswith("# ")), "")
            title = title_line[2:].strip() if title_line.startswith("# ") else skill_file.parent.name
            enabled = not wanted or key in wanted
            entries.append(
                SkillEntry(
                    key=key,
                    name=title,
                    path=skill_file,
                    content=content,
                    enabled=enabled,
                )
            )

    entries.sort(key=lambda item: item.key)
    return entries


def build_skills_prompt(skills: list[SkillEntry], max_chars: int) -> str:
    enabled = [skill for skill in skills if skill.enabled]
    if not enabled:
        return ""

    blocks: list[str] = []
    remaining = max_chars

    for skill in enabled:
        header = f"\n## Skill: {skill.name} ({skill.key})\n"
        body = skill.content.strip()
        block = header + body + "\n"
        if len(block) > remaining:
            if remaining <= 0:
                break
            block = block[:remaining]
        blocks.append(block)
        remaining -= len(block)
        if remaining <= 0:
            break

    if not blocks:
        return ""

    return (
        "You can use the following local skill instructions when relevant. "
        "Treat them as operational guidance:\n"
        + "\n".join(blocks)
    )
