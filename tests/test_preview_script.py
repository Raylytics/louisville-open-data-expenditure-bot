"""infra/preview.sh `ok` against stubbed docker/curl (roborev 6026): the
health snapshot deploy.sh decides on must come from a container built from
HEAD, never from one left running at an earlier commit."""
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "infra" / "preview.sh"
HEALTH = {"status": "ok", "tables": {"expenditures": 7}, "cache_version": "cafe0001"}


def _head():
    return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()


@pytest.fixture
def ok(tmp_path):
    if (subprocess.run(["git", "-C", str(REPO), "diff", "--quiet"]).returncode != 0
            or subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode != 0):
        pytest.skip("working tree is dirty; `ok` (correctly) refuses first")
    files = [REPO / ".preview-ok", REPO / ".preview-health.json"]
    saved = {p: (p.read_text() if p.exists() else None) for p in files}
    for p in files:
        p.unlink(missing_ok=True)
    bin_ = tmp_path / "bin"; bin_.mkdir()
    (bin_ / "docker").write_text('#!/bin/sh\nprintf "%s" "$LABEL"\n')
    (bin_ / "curl").write_text(f"#!/bin/sh\nprintf '%s' '{json.dumps(HEALTH)}'\n")
    for f in bin_.iterdir():
        f.chmod(0o755)

    def run(label):
        env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", LABEL=label)
        return subprocess.run(["/bin/bash", str(SCRIPT), "ok"], env=env, capture_output=True, text=True, timeout=30)
    yield run, files
    for p, before in saved.items():
        if before is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(before)


def test_ok_records_the_snapshot_of_a_preview_built_from_head(ok):
    run, (mark, snap) = ok
    proc = run(_head())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert mark.read_text().strip() == _head()
    assert json.loads(snap.read_text()) == {"sha": _head(), "tables": HEALTH["tables"], "cache_version": "cafe0001"}


@pytest.mark.parametrize("label", ["0" * 40, "", "HEAD-dirty"])
def test_ok_refuses_a_preview_built_from_another_tree(ok, label):
    run, (mark, snap) = ok
    proc = run(_head() + "-dirty" if label == "HEAD-dirty" else label)
    assert proc.returncode == 1 and "not HEAD" in proc.stdout
    assert not mark.exists() and not snap.exists()
