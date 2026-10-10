"""Convention guard: systemd unit files at the repo root (issue #252).

systemd only honours StartLimit* settings in [Unit]; in [Service] they are
silently ignored, so the restart limit never applies.
"""

import configparser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SERVICE_FILES = sorted(REPO_ROOT.glob("*.service"))
START_LIMIT_KEYS = (
    "StartLimitIntervalSec",
    "StartLimitInterval",
    "StartLimitBurst",
    "StartLimitAction",
)


def _parse(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read(path, encoding="utf-8")
    return parser


def test_service_files_returns_nonempty_when_repo_root_scanned() -> None:
    assert SERVICE_FILES, f"no *.service files found in {REPO_ROOT}"


@pytest.mark.parametrize("path", SERVICE_FILES, ids=lambda p: p.name)
def test_service_section_has_no_start_limit_keys_when_unit_file_parsed(
    path: Path,
) -> None:
    parser = _parse(path)
    misplaced = [key for key in START_LIMIT_KEYS if parser.has_option("Service", key)]
    assert not misplaced, f"{path.name}: {misplaced} must be in [Unit], not [Service]"


def test_unit_section_has_start_limit_values_when_http_unit_parsed() -> None:
    parser = _parse(REPO_ROOT / "mcp-git-http.service")
    assert parser.get("Unit", "StartLimitIntervalSec") == "60"
    assert parser.get("Unit", "StartLimitBurst") == "3"
