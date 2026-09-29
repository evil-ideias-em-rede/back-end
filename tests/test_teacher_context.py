import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.teacher_context import format_teacher_context, load_teacher_context


class TeacherContextTest(unittest.IsolatedAsyncioTestCase):
    def test_relationships_and_whitelist(self):
        text = format_teacher_context(
            [{"name": "Escola A"}],
            [{"id": "t1", "school": "Escola A", "series": "6º ano",
              "id_series": "B", "disciplina": "Geografia", "student_count": 32}],
            [{"id": "p1", "title": "Plano", "turma_ids": ["t1", "outra-turma"],
              "file_content": "SEGREDO", "html_content": "<p>Não incluir</p>"}],
            [{"id": "m1", "title": "Livro", "turma_ids": ["t1"]}],
        )
        catalog = json.loads(text.split("\n")[-1])
        self.assertEqual(catalog["escolas"], ["Escola A"])
        self.assertEqual(catalog["turmas"][0]["numero_de_alunos"], 32)
        self.assertEqual(catalog["templates"][0]["turmas"], ["t1"])
        self.assertEqual(catalog["materiais_didaticos"][0]["turmas"], ["t1"])
        self.assertNotIn("SEGREDO", text)
        self.assertNotIn("<p>", text)

    async def test_anonymous_never_queries_private_data(self):
        with patch("services.teacher_context.get_pool") as pool:
            self.assertIsNone(await load_teacher_context(None, "session"))
            pool.assert_not_called()

    async def test_only_owner_private_session_receives_context(self):
        for owner in (None, "other-owner", "owner"):
            conn = MagicMock()
            conn.fetchval = AsyncMock(return_value=owner)
            conn.fetch = AsyncMock(return_value=[])
            pool = MagicMock()
            pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
            pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("services.teacher_context.get_pool", return_value=pool):
                context = await load_teacher_context("owner", "session")
            if owner != "owner":
                self.assertIsNone(context)
                conn.fetch.assert_not_called()
            else:
                self.assertIn('"turmas": []', context)
                self.assertEqual(conn.fetch.await_count, 4)
                for call in conn.fetch.await_args_list:
                    self.assertEqual(call.args[1], "owner")
                    self.assertIn("user_id=$1", call.args[0])
                    self.assertNotIn("file_content", call.args[0])

    async def test_each_message_reloads_catalog(self):
        conn = MagicMock()
        conn.fetchval = AsyncMock(return_value="owner")
        conn.fetch = AsyncMock(return_value=[])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("services.teacher_context.get_pool", return_value=pool):
            await load_teacher_context("owner", "session")
            await load_teacher_context("owner", "session")
        self.assertEqual(conn.fetch.await_count, 8)
