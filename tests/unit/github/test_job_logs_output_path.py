"""output_path combined with selection (#336) and save_to_disk (#337) for github_get_job_logs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github.api import github_get_job_logs
from mcp_server_git.utils.log_paths import sanitize_component

LOG_TEXT = "\n".join(f"Line {i}" for i in range(50)) + "\nERROR boom\nLine tail"


def _client(log_text: str) -> MagicMock:
    client = MagicMock()
    job = AsyncMock()
    job.status = 200
    job.json = AsyncMock(return_value={"id": 12345, "name": "J", "status": "completed"})
    logs = AsyncMock()
    logs.status = 200
    logs.text = AsyncMock(return_value=log_text)
    client.get = AsyncMock(side_effect=[job, logs])
    return client


async def _run(*args, **kwargs) -> str:
    with patch("mcp_server_git.github.ci_logs.github_client_context") as ctx:
        ctx.return_value.__aenter__ = AsyncMock(return_value=_client(LOG_TEXT))
        ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        return await github_get_job_logs(*args, **kwargs)


@pytest.mark.asyncio
async def test_job_logs_output_path_with_grep_returns_matches_when_file_written(
    tmp_path,
):
    target = tmp_path / "full.log"
    result = await _run("o", "r", 12345, output_path=str(target), grep="ERROR")
    assert target.read_text(encoding="utf-8") == LOG_TEXT
    assert "💾 Full log written to" in result
    assert "ERROR boom" in result
    assert "Line 3\n" not in result


@pytest.mark.asyncio
async def test_job_logs_output_path_with_tail_lines_returns_last_lines_when_set(
    tmp_path,
):
    target = tmp_path / "full.log"
    result = await _run("o", "r", 12345, output_path=str(target), tail_lines=2)
    assert target.read_text(encoding="utf-8") == LOG_TEXT
    assert "ERROR boom" in result
    assert "Line tail" in result
    assert "Line 10\n" not in result


@pytest.mark.asyncio
async def test_job_logs_output_path_alone_returns_metadata_only_when_no_selection(
    tmp_path,
):
    result = await _run("o", "r", 12345, output_path=str(tmp_path / "f.log"))
    assert "written to" in result
    assert "Line tail" not in result
    assert "📋" not in result


@pytest.mark.asyncio
async def test_job_logs_output_path_with_full_log_returns_metadata_only_when_set(
    tmp_path,
):
    result = await _run(
        "o", "r", 12345, output_path=str(tmp_path / "f.log"), full_log=True
    )
    assert "Line tail" not in result


@pytest.mark.asyncio
async def test_job_logs_output_path_with_bad_regex_returns_failure_when_grep_invalid(
    tmp_path,
):
    result = await _run("o", "r", 12345, output_path=str(tmp_path / "f.log"), grep="(")
    assert result.startswith("❌ ")


@pytest.mark.asyncio
async def test_job_logs_save_to_disk_writes_expected_file_when_log_dir_set(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MCP_GIT_LOG_DIR", str(tmp_path / "logs"))
    result = await _run("own er", "re/po", 12345, save_to_disk=True)
    expected = tmp_path / "logs" / "github-own_er-re_po-job-12345.log"
    assert expected.read_text(encoding="utf-8") == LOG_TEXT
    assert str(expected.resolve()) in result


@pytest.mark.asyncio
async def test_job_logs_explicit_output_path_beats_save_to_disk_when_both_given(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MCP_GIT_LOG_DIR", str(tmp_path / "logs"))
    target = tmp_path / "explicit.log"
    await _run("o", "r", 12345, output_path=str(target), save_to_disk=True)
    assert target.exists()
    assert not (tmp_path / "logs").exists()


def test_sanitize_component_replaces_unsafe_chars_when_name_is_odd():
    assert sanitize_component("a/b c:d..e-f_g") == "a_b_c_d..e-f_g"
