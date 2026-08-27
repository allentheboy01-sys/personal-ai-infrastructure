#!/usr/bin/env python3
"""Validate repository-local links in tracked Markdown documents."""

from __future__ import annotations

import re
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)


def tracked_markdown_files() -> tuple[Path, ...]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "*.md",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        ROOT / line
        for line in completed.stdout.splitlines()
        if line.strip() and (ROOT / line).is_file()
    )


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("#", "mailto:")):
        return None
    return unquote(parsed.path)


def main() -> int:
    broken: list[str] = []
    checked = 0
    for document in tracked_markdown_files():
        text = document.read_text(encoding="utf-8")
        targets = INLINE_LINK.findall(text) + REFERENCE_LINK.findall(text)
        for raw_target in targets:
            relative = local_target(raw_target)
            if not relative:
                continue
            checked += 1
            resolved = (document.parent / relative).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                broken.append(f"{document.relative_to(ROOT)} -> {raw_target}")
                continue
            if not resolved.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {raw_target}")

    if broken:
        print("Broken repository-local Markdown links:")
        for item in broken:
            print(f"- {item}")
        return 1

    print(f"Validated {checked} repository-local Markdown links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
