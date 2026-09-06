import json
import os
import subprocess
import sys
from pathlib import Path


def test_fresh_bootstrap_executes_retry_batch_and_preserves_agricola_provenance(tmp_path):
    env = {key: value for key, value in os.environ.items() if not key.startswith('SCRAPER_')}
    env.update(SCRAPER_DATA_DIR=str(tmp_path), SCRAPER_COMPARISON_DECISIONS_DB_PATH=str(tmp_path / 'decisions.sqlite3'),
               SCRAPER_UPDATE_IMPORT_LEGACY='0', SCRAPER_ADDITION_IMPORT_LEGACY='0',
               SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED='0')
    result = subprocess.run([sys.executable, 'tests/modular_bootstrap_probe.py'],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['ok']
