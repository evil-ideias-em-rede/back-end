from .base import run_agent
from .prompts.lesson_plan_prompt import PLANO_DE_AULA_PROMPT


async def lesson_plan_node(state, config=None):
    print("Lesson plan is executing...")
    return await run_agent(state, PLANO_DE_AULA_PROMPT, config)
