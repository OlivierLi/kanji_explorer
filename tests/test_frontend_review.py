"""Execute the browser's actual request/navigation functions with controlled I/O."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_review_regressions():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend regression checks')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, 'tests/frontend_review.cjs'], cwd=root, check=True)
