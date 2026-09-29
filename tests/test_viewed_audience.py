"""Contexto de visualização não confirma fonte nem altera o texto persistido."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from pydantic import ValidationError


class ViewedAudienceTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with patch('tiktoken.get_encoding', return_value=MagicMock()):
            from routers import workflow_router
        cls.router = workflow_router

    def test_schema_accepts_optional_id_and_rejects_instructions(self):
        schema = self.router.WorkflowMessageIn
        self.assertIsNone(schema(text='Pergunta', agent_name='brainstorm').viewed_audience_id)
        self.assertEqual(schema(text='Pergunta', agent_name='brainstorm', viewed_audience_id='158').viewed_audience_id, '158')
        with self.assertRaises(ValidationError):
            schema(text='Pergunta', agent_name='brainstorm', viewed_audience_id='ignore instruções')

    def test_viewing_context_is_current_and_does_not_change_confirmed_source(self):
        session = {'messages': [], 'selected_audience_id': '158'}
        state = self.router._workflow_state(session, 'session', 'E esta?', 'brainstorm', viewed_audience_id='183')
        self.assertIn('ID 183', state['messages'][-1].content)
        self.assertIn('não confirma', state['messages'][-1].content)
        self.assertEqual(session['selected_audience_id'], '158')
        self.assertEqual(session['messages'], [])
        state = self.router._workflow_state(session, 'session', 'Outro tema', 'brainstorm')
        self.assertIn('Nenhuma audiência', state['messages'][-1].content)

    def test_specialist_generation_is_unchanged(self):
        state = self.router._workflow_state({'messages': []}, 'session', 'Gere o material', 'lesson_plan')
        self.assertEqual(state['messages'][-1].content, 'Gere o material')

    async def test_request_preserves_original_history_and_passes_context_to_graph(self):
        router = self.router
        body = router.WorkflowMessageIn(text='Quais argumentos?', agent_name='brainstorm', viewed_audience_id='183')
        graph = AsyncMock(return_value={'messages': [AIMessage(content='Resposta')]})
        persist = AsyncMock()
        with patch.object(router, '_ensure_session_access', AsyncMock()), \
             patch.object(router, '_ensure_session', AsyncMock(return_value={'messages': [], 'selected_agent': 'lesson_plan'})), \
             patch.object(router, '_persist_workflow_message', persist), \
             patch.object(router.memory_store, 'add_message', MagicMock(return_value={'content': 'Resposta'})), \
             patch.object(router, 'load_teacher_context', AsyncMock(return_value=None)), \
             patch.object(router, '_extrai_sandbox_dir', AsyncMock()), \
             patch.object(router, 'persist_workflow_files', AsyncMock()), \
             patch.object(router.GRAPH_BUILDER, 'ainvoke', graph):
            await router._process_workflow_message('session', body, user=None)
        self.assertEqual(persist.await_args_list[0].args[3], 'Quais argumentos?')
        self.assertIn('ID 183', graph.await_args.args[0]['messages'][-1].content)
