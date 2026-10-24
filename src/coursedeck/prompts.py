"""Versioned prompts: prompts/<task>/<version>.md, changes recorded in prompts/<task>/CHANGELOG.md."""

import hashlib
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"  # repo root/prompts


def load_prompt(task: str, version: str) -> str:
    path = PROMPTS_DIR / task / f"{version}.md"
    if not path.exists():
        raise ValueError(f"unknown prompt {task}/{version}; available: {prompt_versions(task)}")
    return path.read_text("utf-8").strip()


def prompt_versions(task: str) -> list[str]:
    return sorted(p.stem for p in (PROMPTS_DIR / task).glob("v*.md"))


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]
