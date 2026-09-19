from .base import run_agent
from .prompts.political_leteracy_prompt import LETRAMENTO_POLITICO_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def political_leteracy_node(state, config=None):
    remover_planning_json(state)
    print(f"Political leteracy is executing for {state.get('agent_name')}...")
    return await run_agent(state, LETRAMENTO_POLITICO_PROMPT, config)
