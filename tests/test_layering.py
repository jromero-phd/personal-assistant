"""Architecture rules, enforced by reading imports (so they can't silently rot)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "assistant"


def imports_of(package_dir: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in (SRC / package_dir).rglob("*.py"):
        mods: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module)
        found[str(path.relative_to(SRC))] = mods
    return found


def offenders(package_dir: str, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    return [
        f"{file} imports {m}"
        for file, mods in imports_of(package_dir).items()
        for m in mods
        if m.startswith(forbidden_prefixes)
    ]


def test_core_does_not_depend_on_adapters_or_concrete_tools():
    assert offenders("core", ("assistant.adapters", "assistant.tools")) == []


def test_policies_depend_only_on_the_tool_contract():
    assert (
        offenders("policies", ("assistant.adapters", "assistant.tools", "assistant.core.runner"))
        == []
    )


def test_tools_do_not_depend_on_adapters():
    assert offenders("tools", ("assistant.adapters",)) == []


def test_only_adapters_touch_the_clock_or_environment():
    for pkg in ("core", "tools", "policies"):
        for file in imports_of(pkg):
            text = (SRC / file).read_text()
            assert "date.today(" not in text and "datetime.now(" not in text, file
            assert "os.environ" not in text, file
