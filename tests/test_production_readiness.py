from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_production_readiness.py"
SPEC = importlib.util.spec_from_file_location("check_production_readiness", SCRIPT_PATH)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)


def test_required_open_source_files_exist():
    checks = readiness.check_required_files()

    assert checks
    assert all(check.ok for check in checks), [check for check in checks if not check.ok]


def test_bilingual_documentation_markers_exist():
    checks = readiness.check_bilingual_docs()

    assert all(check.ok for check in checks), [check for check in checks if not check.ok]


def test_backup_restore_drill_documentation_is_actionable():
    checks = readiness.check_restore_drill_docs()

    assert all(check.ok for check in checks), [check for check in checks if not check.ok]


def test_free_local_defaults_are_configured():
    checks = readiness.check_free_local_defaults()

    assert all(check.ok for check in checks), [check for check in checks if not check.ok]


def test_production_compose_has_core_services_and_healthchecks():
    checks = readiness.check_prod_compose()

    assert all(check.ok for check in checks), [check for check in checks if not check.ok]
