from .base import run_agent
from .prompts.generic_activity_prompt import ATIVIDADE_GENERICA_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def generic_activity_node(state, config=None):
    remover_planning_json(state)
    print(f"Generic activity is executing for {state.get('agent_name')}...")
    return await run_agent(state, ATIVIDADE_GENERICA_PROMPT, config)
