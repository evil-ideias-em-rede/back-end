from .base import run_agent
from .prompts.debate_outline_prompt import ROTEIRO_DEBATE_PROMPT


async def debate_outline_node(state, config=None):
    print("Debate outline is executing...")
    return await run_agent(state, ROTEIRO_DEBATE_PROMPT, config)
