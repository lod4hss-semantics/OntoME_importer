import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase0_contracts_are_valid():
    result = subprocess.run(
        [sys.executable, "tools/validate_phase0.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Phase 0 contracts are valid."
