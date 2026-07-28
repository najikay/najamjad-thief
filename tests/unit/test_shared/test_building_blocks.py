"""Building-block docstrings on the shared components (T-0428, guidelines §16).

§16 asks each building block to declare three things, and the value is in the
third: **Input** (types, valid range, dependencies), **Output** (types, format,
edge-case behaviour) and **Setup** (parameters, defaults, initialisation).

Applied to `shared/` because those are the components every other package
depends on — a wrong assumption about the gatekeeper or the event bus is a
wrong assumption everywhere. It is deliberately *not* applied to every class in
the project: the domain's value objects are described adequately by their names
and fields, and a mandated template on all of them would produce paperwork
rather than explanation.
"""

import ast
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[3] / "src/najamjad_agent/shared"
SECTIONS = ("Input:", "Output:", "Setup:")


def building_blocks() -> list[tuple[str, str, str]]:
    """Every documented component class in `shared/`, with its docstring."""
    found = []
    for path in sorted(SHARED.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not node.name.endswith("Error"):
                found.append((path.name, node.name, ast.get_docstring(node) or ""))
    return found


def test_there_are_building_blocks_to_check():
    """A discovery bug would make every check below vacuously pass."""
    assert len(building_blocks()) >= 5


@pytest.mark.parametrize(
    "module,name,doc", building_blocks(), ids=[f"{m}:{n}" for m, n, _ in building_blocks()]
)
def test_every_shared_component_declares_input_output_and_setup(module, name, doc):
    """The three sections §16 asks for."""
    missing = [section for section in SECTIONS if section not in doc]

    assert not missing, f"{module}:{name} docstring is missing {missing}"


@pytest.mark.parametrize(
    "module,name,doc", building_blocks(), ids=[f"{m}:{n}" for m, n, _ in building_blocks()]
)
def test_the_sections_say_something(module, name, doc):
    """A heading with nothing after it satisfies a grep and no reader."""
    for section in SECTIONS:
        body = doc.split(section, 1)[1]
        for other in SECTIONS:
            body = body.split(other, 1)[0]
        assert len(body.strip()) > 15, f"{module}:{name} — {section} is empty"


def test_exceptions_are_exempt():
    """An exception class is named for what went wrong; a three-section
    template would add nothing."""
    names = {name for _module, name, _doc in building_blocks()}

    assert not any(name.endswith("Error") for name in names)
