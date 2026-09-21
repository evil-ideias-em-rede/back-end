from .base import run_agent
from .prompts.audiencias_sugeridas.lesson_plan_prompt import PLANO_DE_AULA_PROMPT
from .prompts.editor.lesson_plan_prompt import EDITOR_LESSON_PLAN_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def lesson_plan_node(state, config=None):
    #remover_planning_json(state)
    print(f"Lesson plan is executing for {state.get('agent_name')}...")
    prompt = EDITOR_LESSON_PLAN_PROMPT if state.get("editor_mode") else PLANO_DE_AULA_PROMPT
    return await run_agent(state, prompt, config)
