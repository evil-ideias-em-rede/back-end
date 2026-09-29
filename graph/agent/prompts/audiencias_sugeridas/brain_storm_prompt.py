from ..loader import render_for_agent
from ..brainstorm_rules import BRAINSTORM_SCOPE
from .rules import PLANNING_RULES, _NEUTRALITY_BLOCK


BRAINSTORM_PROMPT = "\n\n".join((
    render_for_agent("18-brainstorm"),
    _NEUTRALITY_BLOCK,
    PLANNING_RULES,
    BRAINSTORM_SCOPE,
))
