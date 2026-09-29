from .base import run_agent
from .prompts.audiencias_sugeridas.brain_storm_prompt import BRAINSTORM_PROMPT
from graph.tools.sandbox.brainstorm_files import execute_brainstorm_planning
from graph.tools.retrieval.audiencias import consultar_audiencia_por_id
from graph.tools.retrieval.tool_buscar_audiencias import buscar_audiencias
from graph.tools.retrieval.tool_consultar_audiencias_sql import consultar_audiencias_sql
from graph.tools.retrieval.tool_consultar_bncc import consultar_bncc

execute_planning_bash = execute_brainstorm_planning


async def brainstorm_node(state, config=None):
    agent_name = state.get('agent_name')
    print(f"Brain storm is executing for {agent_name}...")
    restricted_prompt = BRAINSTORM_PROMPT.replace("execute_bash", execute_planning_bash.name)
    return await run_agent(
        state,
        restricted_prompt,
        config,
        tools=[
            execute_planning_bash,
            consultar_audiencia_por_id,
            buscar_audiencias,
            consultar_audiencias_sql,
            consultar_bncc,
        ],
    )
