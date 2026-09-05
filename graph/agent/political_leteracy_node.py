from .base import run_agent
from .prompts.political_leteracy_prompt import LETRAMENTO_POLITICO_PROMPT


async def political_leteracy_node(state, config=None):
    print("Political leteracy is executing...")
    return await run_agent(state, LETRAMENTO_POLITICO_PROMPT, config)
