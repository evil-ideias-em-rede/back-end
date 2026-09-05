from .base import run_agent
from .prompts.brain_storm_prompt import BRAINSTORM_PROMPT


async def brain_storm_node(state, config=None):
    print("Brain storm is executing...")
    return await run_agent(state, BRAINSTORM_PROMPT, config)
