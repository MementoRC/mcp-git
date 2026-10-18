"""404 from the job-log endpoint: in-progress jobs vs deleted logs (issue #301)."""

import pytest

from mcp_server_git.github.ci_logs import _check_logs_response


class _Resp:
    def __init__(self, status):
        self.status = status


@pytest.mark.parametrize("status", ["in_progress", "queued", "waiting"])
def test_check_logs_response_says_after_completion_when_job_not_finished(status):
    message = _check_logs_response(_Resp(404), {"status": status})

    assert "available only after the job completes" in message
    assert "deleted" not in message


def test_check_logs_response_says_deleted_when_job_completed():
    message = _check_logs_response(_Resp(404), {"status": "completed"})

    assert "may have been deleted" in message


def test_check_logs_response_says_deleted_when_job_data_is_none():
    message = _check_logs_response(_Resp(404), None)

    assert "may have been deleted" in message
