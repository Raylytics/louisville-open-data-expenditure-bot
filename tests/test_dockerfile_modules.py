"""Both images copy the app's modules by name, so a new module must be added
to their COPY lines by hand. Nothing else notices when it is not: the test
suite imports from the repo, and the image fails only at boot. Seen twice:
the self-hosted image never got state_store.py, and claude_provider.py
reached neither image until the 2026-10-14 preview refused to start."""

import ast
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _local_imports(entry="app.py") -> set:
    """Every repo-root module reachable from `entry` through module-level imports."""
    seen, todo = set(), [entry]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        tree = ast.parse(open(os.path.join(REPO, f)).read())
        for node in tree.body:   # module level only: lazy imports are optional deps
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            for n in names:
                if os.path.isfile(os.path.join(REPO, f"{n}.py")):
                    todo.append(f"{n}.py")
    return seen


def _copied(dockerfile: str) -> set:
    text = open(os.path.join(REPO, dockerfile)).read()
    out = set()
    for line in re.findall(r"^COPY (?!--from)(.+)$", text, re.M):
        out.update(p for p in line.split()[:-1] if p.endswith(".py"))
    return out


@pytest.mark.parametrize("dockerfile", ["Dockerfile", "Dockerfile.lambda"])
def test_image_ships_every_module_the_app_imports(dockerfile):
    missing = _local_imports() - _copied(dockerfile)
    assert not missing, f"{dockerfile} does not COPY {sorted(missing)}"
