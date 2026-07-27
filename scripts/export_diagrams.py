"""Render the PLAN.md diagrams to images (T-2222, T-2223).

    uv run python scripts/export_diagrams.py

GitHub renders Mermaid inline, so the diagrams are already readable in the repo.
This exists because a PDF or a printed report cannot run a renderer, and because
the guidelines ask for committed image files rather than only source.

The Mermaid blocks in `docs/PLAN.md` stay the single source of truth — the
images are derived and can be regenerated at any time. Editing an exported PNG
instead of the block it came from would put a diagram in the report that no
longer describes the system.

Requires `npx` (Node). The renderer is fetched on first use; if it is
unavailable the script says so and exits non-zero rather than leaving stale
images in place and reporting success.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs/PLAN.md"
ASSETS = ROOT / "assets"
RENDERER = "@mermaid-js/mermaid-cli@11"

# Heading fragment -> exported file stem. Order follows the document.
NAMES = {
    "C4 Level 1": "c4-context",
    "C4 Level 2": "c4-container",
    "C4 Level 3": "c4-component",
    "Deployment diagram": "deployment",
    "Game FSM": "uml-game-fsm",
    "Turn sequence": "uml-turn-sequence",
    "Match lifecycle": "uml-match-lifecycle",
}
BLOCK = re.compile(r"^(#{2,4} .*?)$|^```mermaid\n(.*?)^```", re.M | re.S)


def blocks(markdown: str) -> list[tuple[str, str]]:
    """Pair every mermaid block with the heading above it."""
    found, heading = [], "diagram"
    for match in BLOCK.finditer(markdown):
        if match.group(1) is not None:
            heading = match.group(1)
        elif match.group(2) is not None:
            found.append((heading, match.group(2)))
    return found


def stem_for(heading: str, index: int) -> str:
    """The output name for a heading, or a numbered fallback."""
    for fragment, stem in NAMES.items():
        if fragment in heading:
            return stem
    return f"diagram-{index:02d}"


def render(source: str, target: Path, scratch: Path) -> bool:
    """Render one block; return whether it produced an image."""
    scratch.write_text(source, encoding="utf-8")
    result = subprocess.run(
        ["npx", "-y", RENDERER, "-i", str(scratch), "-o", str(target),
         "-b", "white", "-s", "2"],
        capture_output=True, text=True, check=False, cwd=ROOT,
    )
    if result.returncode != 0 or not target.exists():
        print(f"  FAILED {target.name}: {(result.stderr or result.stdout).strip()[-300:]}")
        return False
    return True


def main() -> int:
    """Export every diagram, reporting one verdict."""
    ASSETS.mkdir(exist_ok=True)
    scratch = ASSETS / "_diagram.mmd"
    found = blocks(PLAN.read_text(encoding="utf-8"))
    if not found:
        print(f"no mermaid blocks in {PLAN}")
        return 1

    failures = []
    try:
        for index, (heading, source) in enumerate(found, start=1):
            target = ASSETS / f"{stem_for(heading, index)}.png"
            print(f"  {target.name:26} <- {heading.lstrip('# ')[:48]}")
            if not render(source, target, scratch):
                failures.append(target.name)
    finally:
        scratch.unlink(missing_ok=True)

    print("-" * 60)
    if failures:
        print(f"EXPORT FAILED for {len(failures)}: {', '.join(failures)}")
        return 1
    print(f"exported {len(found)} diagrams to {ASSETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
