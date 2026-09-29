import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from auth.dependencies import CurrentUser
from auth.workflow_access import require_workflow_access


class WorkflowAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_artifact_access(self):
        for path in ({"session_id": "807f3a76-c9ba-4e0f-afbb-f5bd3d5b47e1"}, {"sandbox_id": "a" * 64}):
            for owner, user_id, status in (("owner", None, 401), ("owner", "other", 404), ("owner", "owner", None), (None, None, None)):
                with self.subTest(path=path, owner=owner, user=user_id):
                    conn = MagicMock()
                    conn.fetchrow = AsyncMock(return_value={"owner_user_id": owner})
                    pool = MagicMock()
                    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
                    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
                    with patch("auth.workflow_access.get_pool", return_value=pool):
                        request = SimpleNamespace(path_params=path)
                        user = CurrentUser(user_id) if user_id else None
                        if status:
                            with self.assertRaises(HTTPException) as caught:
                                await require_workflow_access(request, user)
                            self.assertEqual(caught.exception.status_code, status)
                        else:
                            await require_workflow_access(request, user)
