from ..loader import render_for_agent
from ..material_rules import material_rules
from .rules import (
    ACERVO_PEDAGOGICO,
    LEITURA_DO_PLANEJAMENTO,
    PONTE_ARTEFATO,
    _NEUTRALITY_BLOCK,
    _SANDBOX_FLOW_PLANNING,
)


SLIDES_PROMPT = f"""
{render_for_agent("23-slides")}

{material_rules("slides")}

{ACERVO_PEDAGOGICO}

{_NEUTRALITY_BLOCK}

{LEITURA_DO_PLANEJAMENTO}

{PONTE_ARTEFATO}

{_SANDBOX_FLOW_PLANNING}
""".strip()
