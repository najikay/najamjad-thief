"""Every test cited by the docs must exist (T-2229).

`docs/edge-cases.md` is only worth reading if its citations resolve. A table of
`file::test_name` references is exactly the kind of document that rots silently:
a test gets renamed, the doc keeps naming the old one, and a reader who tries to
check a claim finds nothing — which is worse than not having cited anything.

This is cheap to enforce and impossible to maintain by hand, so it is enforced.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
#: Both edge-case documents. The domain one cites the property tests, whose
#: names are the least memorable in the suite and so the likeliest to rot.
DOCS = (ROOT / "docs/edge-cases.md", ROOT / "docs/edge-cases-domain.md")
TESTS = ROOT / "tests"

# `test_domain/test_capture.py::test_something` — optionally with a directory
# prefix, since the doc cites some files by name alone.
CITATION = re.compile(r"`((?:[\w/]+/)?test_\w+\.py)::(test_\w+)`")


def citations() -> list[tuple[str, str]]:
    """Every (file, test) pair either document names."""
    found: list[tuple[str, str]] = []
    for doc in DOCS:
        found.extend(CITATION.findall(doc.read_text(encoding="utf-8")))
    return found


def test_the_document_actually_cites_things():
    """A regex that silently matches nothing would make every test below pass."""
    assert len(citations()) >= 55, "the edge-case docs should cite most of their claims"


@pytest.mark.parametrize("filename,test_name", citations())
def test_every_cited_test_exists(filename: str, test_name: str):
    """The cited file exists and defines the cited test."""
    matches = list(TESTS.rglob(Path(filename).name))
    assert matches, f"{filename} is cited by an edge-case document but does not exist"

    # A citation with a directory prefix must resolve to that directory.
    if "/" in filename:
        matches = [path for path in matches if str(path).replace("\\", "/").endswith(filename)]
        assert matches, f"no test file at the cited path {filename}"

    defined = any(
        re.search(rf"^(async )?def {re.escape(test_name)}\b", path.read_text(encoding="utf-8"), re.M)
        for path in matches
    )
    assert defined, f"{filename} does not define {test_name} (cited by an edge-case document)"
