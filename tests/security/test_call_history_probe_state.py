"""Temporary probe credentials remain private even when a state file exists."""

import runpy
import stat
from pathlib import Path


def test_history_probe_tightens_existing_state_file_permissions(tmp_path: Path) -> None:
    probe = runpy.run_path("tests/e2e/asterisk/live-call-history-probe.py")
    path = tmp_path / "probe-state.json"
    path.write_text("{}")
    path.chmod(0o644)
    probe["save"](path, {"keys": []})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == '{"keys": []}'
