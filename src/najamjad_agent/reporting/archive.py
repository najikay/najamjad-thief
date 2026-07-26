"""Bundle a finished match into one file worth keeping.

After a match the evidence is scattered: artifacts in the workspace, the event
stream in a JSONL file, screenshots elsewhere. Rule 19 disputes and grading both
depend on that evidence still existing weeks later, and "it was on my laptop" is
not a defence — so this collects it into a single archive with a manifest of
what went in.

Secrets are never bundled. The refusal is by pattern rather than by listing what
is safe, because the failure mode here is one-directional: a missing log is an
inconvenience, a `token.json` inside a zip that gets emailed to an opponent is
an incident (guidelines §7.4, book rules 39-40).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..protocol.canonical import canonical_json

# Never archived, whatever directory they are found in.
SECRET_NAMES = frozenset({"credentials.json", "token.json", ".env"})
SECRET_SUFFIXES = frozenset({".pem", ".key"})
SKIP_PARTS = frozenset({"__pycache__", ".git", ".venv"})


def is_secret(path: Path) -> bool:
    """Whether a file must never be placed in an archive."""
    return path.name in SECRET_NAMES or path.suffix in SECRET_SUFFIXES


@dataclass
class ArchiveReport:
    """What the bundle contains, and what was deliberately left out."""

    path: Path
    included: list[str] = field(default_factory=list)
    excluded_secrets: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        """How many files made it in."""
        return len(self.included)

    def manifest(self) -> dict[str, Any]:
        """The index written into the archive itself."""
        return {
            "archive": self.path.name,
            "file_count": self.file_count,
            "files": sorted(self.included),
            "excluded_secrets": sorted(self.excluded_secrets),
            "missing_sources": sorted(self.missing_sources),
        }


def _collect(source: Path) -> list[Path]:
    """Every archivable file under one source path."""
    if source.is_file():
        return [source]
    return [
        path
        for path in sorted(source.rglob("*"))
        if path.is_file() and not SKIP_PARTS & set(path.parts)
    ]


def build_archive(destination: Path, sources: dict[str, Path]) -> ArchiveReport:
    """Zip every source under its own folder name; skip secrets and note them.

    A source that does not exist is recorded rather than raised: archiving a
    match that never produced screenshots should still produce an archive.
    """
    report = ArchiveReport(path=destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
        for label, source in sorted(sources.items()):
            if not source.exists():
                report.missing_sources.append(label)
                continue
            for path in _collect(source):
                relative = path.name if source.is_file() else path.relative_to(source)
                entry = f"{label}/{relative}"
                if is_secret(path):
                    report.excluded_secrets.append(entry)
                    continue
                bundle.write(path, entry)
                report.included.append(entry)
        bundle.writestr("manifest.json", canonical_json(report.manifest()))
    return report
