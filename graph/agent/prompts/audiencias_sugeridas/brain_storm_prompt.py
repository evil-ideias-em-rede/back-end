from ..loader import render
from .rules import PLANNING_RULES, _NEUTRALITY_BLOCK


BRAINSTORM_PROMPT = f"""
{render("18-brainstorm")}

{_NEUTRALITY_BLOCK}

{PLANNING_RULES}
""".strip()
