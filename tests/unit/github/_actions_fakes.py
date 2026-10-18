"""Hand-written HTTP fakes shared by the workflow-action tests (#301, #309).

Only the ``github_client_context`` boundary is faked; routes are keyed by
``(METHOD, endpoint)`` and every call is recorded.
"""

from unittest.mock import patch

from mcp_server_git.github import workflow_actions

RUN = "/repos/o/r/actions/runs"
JOB = "/repos/o/r/actions/jobs"
CHECK = "/repos/o/r/check-runs"

RUN_PAYLOAD = {
    "id": 9,
    "name": "CI",
    "status": "queued",
    "conclusion": None,
    "run_attempt": 2,
    "html_url": "https://github.com/o/r/actions/runs/9",
}


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class FakeClient:
    """Routes by (method, endpoint); a list value is consumed in order."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def _send(self, method, endpoint, kwargs):
        self.calls.append((method, endpoint, kwargs))
        value = self.routes[(method, endpoint)]
        return value.pop(0) if isinstance(value, list) else value

    async def get(self, endpoint, **kwargs):
        return await self._send("GET", endpoint, kwargs)

    async def post(self, endpoint, **kwargs):
        return await self._send("POST", endpoint, kwargs)

    def posts(self):
        return [(ep, kw) for m, ep, kw in self.calls if m == "POST"]


async def call(op, client, *args, **kwargs):
    with patch.object(workflow_actions, "github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        return await op(*args, **kwargs)
