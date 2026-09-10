from .base import run_agent
from .prompts.political_leteracy_prompt import LETRAMENTO_POLITICO_PROMPT


async def political_leteracy_node(state, config=None):
    print(f"Political leteracy is executing for {state.get('agent_name')}...")
    return await run_agent(state, LETRAMENTO_POLITICO_PROMPT, config)
