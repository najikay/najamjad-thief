"""Tunables live in config, never in source (T-0321, guidelines §7.1).

The guidelines put hardcoded values at **threshold zero**, and the reason is
concrete rather than stylistic: a value baked into a module cannot be changed
for one opponent, cannot differ between the two repos, and cannot be reviewed
without reading code.

The hardest instances to spot are not literals — they are lookups whose default
is the only value they ever return. `manager.get("ui.port", 8000)` looked like
configuration for weeks while no config file declared `[ui]`, so 8000 was as
hardcoded as if it had been written inline.

What is deliberately allowed: physical and mathematical constants, values in
`constants.py`, enum members, and the defaults on a dataclass field that a
sweep varies — those are the *shipped* value of a tunable, which is a different
thing from a value with nowhere else to live.
"""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/najamjad_agent"
CONFIG = ROOT / "config"
DATA = ROOT / "data"

#: Modules whose whole job is to hold or read configuration.
CONFIG_MODULES = {"constants.py", "config.py", "app_config.py", "version.py",
                  "rate_limits.py", "params.py", "logging_setup.py"}
URL = re.compile(r"https?://(?!example\.invalid|localhost|127\.0\.0\.1)[\w.-]+")
#: OAuth scope identifiers are URLs by spelling and constants by nature. Rule 30
#: *fixes* our Gmail scope at `gmail.send`; moving it to config would let someone
#: widen our mailbox access by editing a file, which is the thing the rule
#: exists to prevent. The exception is narrow and named rather than waived.
FIXED_IDENTIFIERS = ("https://www.googleapis.com/auth/gmail.send",)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def source_files() -> list[Path]:
    """Every shipped module except the ones that exist to hold settings."""
    return [path for path in SRC.rglob("*.py") if path.name not in CONFIG_MODULES]


def test_no_live_url_is_written_into_a_module():
    """A URL in source cannot be pointed at a different opponent."""
    offenders = []
    for path in source_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(fixed in code for fixed in FIXED_IDENTIFIERS):
                continue
            if URL.search(code) and "docs" not in str(path):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert not offenders, f"live URLs in source: {offenders}"


def test_no_email_address_is_written_into_a_module():
    """The result recipient is fixed by Appendix F and belongs in config."""
    offenders = [
        f"{path.relative_to(ROOT)}"
        for path in source_files()
        if EMAIL.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"email addresses in source: {offenders}"


def test_every_config_default_the_code_reads_is_declared_somewhere():
    """The lookup-with-a-default trap.

    A key nothing declares means the default is the only value it can return.
    Every dotted key the code asks for must exist in one of the shipped config
    files, or be a documented game term.
    """
    declared: set[str] = set()

    def walk(node: object, prefix: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.startswith("_"):
                    continue
                path = f"{prefix}{key}"
                declared.add(path)
                walk(value, f"{path}.")

    for path in list(CONFIG.rglob("*.json")) + list(CONFIG.rglob("*.toml")):
        if path.suffix == ".json":
            try:
                walk(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                head = line.split("=", 1)[0].strip()
                if head and not head.startswith(("#", "[")):
                    declared.add(head)
            declared.update(
                section.strip("[]") for section in re.findall(r"^\[[\w.]+\]",
                path.read_text(encoding="utf-8"), re.M)
            )

    asked: set[str] = set()
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        asked.update(re.findall(r'\.get\(\s*"([\w]+\.[\w.]+)"', text))
        asked.update(re.findall(r'\.require\(\s*"([\w]+\.[\w.]+)"', text))
        asked.update(re.findall(r'setting\([^,]+,\s*"([\w]+\.[\w.]+)"', text))

    def known(dotted: str) -> bool:
        leaf = dotted.split(".")[-1]
        return dotted in declared or leaf in declared or any(
            key.endswith("." + leaf) for key in declared
        )

    missing = sorted(key for key in asked if not known(key))
    assert not missing, f"config keys the code reads that nothing declares: {missing}"


def test_content_tables_live_in_data_not_in_source():
    """Adding a city should be a content change, not a code change."""
    assert (DATA / "map_areas.json").exists()
    raw = json.loads((DATA / "map_areas.json").read_text(encoding="utf-8"))
    assert raw["version"] == "1.00"
    assert len(raw["areas"]) >= 4


def test_the_landmark_table_is_actually_read_from_data():
    """A data file nothing loads is decoration."""
    from najamjad_agent.llm.template_provider import LANDMARKS, load_landmarks

    assert "New York" in LANDMARKS
    assert load_landmarks() == LANDMARKS


def test_a_missing_data_file_costs_flavour_not_a_turn(tmp_path):
    """A hint is mandatory (rule 26); losing the vocabulary must not lose it."""
    from najamjad_agent.llm.template_provider import FALLBACK_LANDMARKS, load_landmarks

    assert load_landmarks(tmp_path / "absent.json") == FALLBACK_LANDMARKS


@pytest.mark.parametrize("module", sorted(path.name for path in SRC.rglob("*.py")))
def test_every_module_parses(module: str):
    """A cheap guard that the meta-tests above are reading real source."""
    matches = list(SRC.rglob(module))
    for path in matches:
        ast.parse(path.read_text(encoding="utf-8"))
