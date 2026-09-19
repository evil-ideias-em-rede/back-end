from .base import run_agent
from .prompts.lesson_plan_prompt import PLANO_DE_AULA_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def lesson_plan_node(state, config=None):
    remover_planning_json(state)
    print(f"Lesson plan is executing for {state.get('agent_name')}...")
    return await run_agent(state, PLANO_DE_AULA_PROMPT, config)
