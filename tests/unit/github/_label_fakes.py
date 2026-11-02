"""HTTP fakes for the label tool tests (#327): adds PATCH and DELETE."""

from ._actions_fakes import FakeClient, FakeResponse, call

__all__ = ["FakeClient", "FakeResponse", "LabelClient", "call"]


class LabelClient(FakeClient):
    async def patch(self, endpoint, **kwargs):
        return await self._send("PATCH", endpoint, kwargs)

    async def delete(self, endpoint, **kwargs):
        return await self._send("DELETE", endpoint, kwargs)


class _Svc:
    def __getattr__(self, name):
        return lambda **kw: {}


def build_interface():
    from mcp_server_git.lean.interface import GitLeanInterface

    return GitLeanInterface(
        git_service=_Svc(), github_service=_Svc(), azure_service=_Svc()
    )
