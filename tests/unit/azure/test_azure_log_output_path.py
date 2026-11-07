"""output_path combined with selection (#336) and save_to_disk (#337) for azure_get_build_logs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.azure.api import azure_get_build_logs

LOG_LINES = [f"Line {i}" for i in range(50)] + ["ERROR boom", "Line tail"]


async def _run(**kwargs) -> str:
    client = MagicMock()
    response = AsyncMock()
    response.status = 200
    response.headers = {"Content-Type": "application/json"}
    response.json = AsyncMock(return_value={"value": LOG_LINES})
    client.get = AsyncMock(return_value=response)
    with patch("mcp_server_git.azure.api.azure_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        return await azure_get_build_logs(build_id=123, log_id=7, **kwargs)


@pytest.mark.asyncio
async def test_build_logs_output_path_with_grep_returns_matches_when_file_written(
    tmp_path,
):
    target = tmp_path / "full.log"
    result = await _run(project="p", output_path=str(target), grep="ERROR")
    assert target.read_text(encoding="utf-8") == "\n".join(LOG_LINES)
    assert "ERROR boom" in result
    assert "Line 3\n" not in result


@pytest.mark.asyncio
async def test_build_logs_output_path_with_tail_lines_returns_last_lines_when_set(
    tmp_path,
):
    result = await _run(project="p", output_path=str(tmp_path / "f.log"), tail_lines=2)
    assert "Line tail" in result
    assert "Line 10\n" not in result


@pytest.mark.asyncio
async def test_build_logs_output_path_alone_returns_metadata_only_when_no_selection(
    tmp_path,
):
    result = await _run(project="p", output_path=str(tmp_path / "f.log"))
    assert "written to" in result
    assert "Line tail" not in result


@pytest.mark.asyncio
async def test_build_logs_save_to_disk_writes_sanitized_name_when_log_dir_set(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MCP_GIT_LOG_DIR", str(tmp_path / "logs"))
    result = await _run(project="my proj/x", save_to_disk=True)
    expected = tmp_path / "logs" / "azure-my_proj_x-build-123-log-7.log"
    assert expected.read_text(encoding="utf-8") == "\n".join(LOG_LINES)
    assert str(expected.resolve()) in result


@pytest.mark.asyncio
async def test_build_logs_explicit_output_path_beats_save_to_disk_when_both_given(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MCP_GIT_LOG_DIR", str(tmp_path / "logs"))
    target = tmp_path / "explicit.log"
    await _run(project="p", output_path=str(target), save_to_disk=True)
    assert target.exists()
    assert not (tmp_path / "logs").exists()
