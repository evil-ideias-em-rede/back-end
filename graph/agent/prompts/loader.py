"""Carrega os prompts versionados em `library/`.

Cada arquivo da biblioteca tem front-matter YAML simples, um bloco `## SYSTEM`
e, exceto o global, um bloco `## USER`. As variáveis aparecem como
`{{NOME}}` e são substituídas aqui.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

LIBRARY_DIR = Path(__file__).resolve().parent / "library"
COMPONENTS_DIR = LIBRARY_DIR / "componentes"

# Variáveis preenchidas pelo próprio loader a partir de outros arquivos.
COMPONENT_VARIABLES = {
    "SYSTEM_GLOBAL": ("00-system-global", None),
    "PEDAGOGICAL_PRINCIPLES": ("componentes/principios-pedagogicos", "pedagogical_principles"),
    "SOURCE_RULES": ("componentes/regras-de-uso-da-fonte", "source_rules"),
    "LEGISLATIVE_GLOSSARY": ("componentes/vocabulario-legislativo", "legislative_glossary"),
    "THEORY_USAGE": ("componentes/teorias-da-aprendizagem", "theory_usage"),
}

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_VARIABLE = re.compile(r"\{\{([A-Z_]+)\}\}")


class PromptNotFound(LookupError):
    pass


def _read(prompt_id: str) -> str:
    path = LIBRARY_DIR / f"{prompt_id}.md"
    if not path.is_file():
        raise PromptNotFound(f"prompt '{prompt_id}' não existe em {LIBRARY_DIR}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _parse(prompt_id: str) -> dict:
    raw = _read(prompt_id)
    front = {}
    match = _FRONT_MATTER.match(raw)
    body = raw
    if match:
        body = raw[match.end():]
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            front[key.strip()] = value

    sections = {"system": "", "user": ""}
    current = None
    buffer: list[str] = []
    for line in body.splitlines():
        heading = line.strip().lower()
        if heading in {"## system", "## user"}:
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = heading.split()[1]
            buffer = []
            continue
        if current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    if not sections["system"]:
        sections["system"] = body.strip()

    return {
        "id": front.get("id", prompt_id),
        "inputs": front.get("inputs", []),
        "system": sections["system"],
        "user": sections["user"],
    }


@lru_cache(maxsize=None)
def _component(name: str, tag: str | None) -> str:
    text = (LIBRARY_DIR / f"{name}.md").read_text(encoding="utf-8")
    text = _FRONT_MATTER.sub("", text).strip()
    if tag:
        found = re.search(rf"(<{tag}>.*?</{tag}>)", text, re.S)
        if found:
            return found.group(1).strip()
    return text


def _drop_unfilled(text: str) -> str:
    """Remove o bloco XML que envolve uma variável sem valor."""
    for name in set(_VARIABLE.findall(text)):
        wrapped = re.compile(
            rf"[ \t]*<([a-z_]+)>\s*\{{\{{{name}\}}\}}\s*</\1>[ \t]*\n?", re.S
        )
        text = wrapped.sub("", text)
        text = re.sub(rf"^[ \t]*\{{\{{{name}\}}\}}[ \t]*\n?", "", text, flags=re.M)
        text = text.replace(f"{{{{{name}}}}}", "")
    return re.sub(r"\n{3,}", "\n\n", text)


def render(prompt_id: str, values: dict | None = None, *, drop_missing: bool = True) -> str:
    """Devolve o texto do prompt com as variáveis substituídas.

    Os blocos SYSTEM e USER são concatenados: o corpo do USER contém as
    instruções, os exemplos e o contrato de saída, que precisam chegar ao
    modelo junto com o papel definido no SYSTEM.
    """
    parsed = _parse(prompt_id)
    resolved = dict(values or {})

    for name, (source, tag) in COMPONENT_VARIABLES.items():
        if name in resolved:
            continue
        resolved[name] = _parse(source)["system"] if tag is None else _component(source, tag)

    text = parsed["system"]
    if parsed["user"]:
        text = f"{text}\n\n{parsed['user']}"

    def replace(match: re.Match) -> str:
        value = resolved.get(match.group(1))
        return "" if value is None else str(value)

    filled = _VARIABLE.sub(lambda m: replace(m) if m.group(1) in resolved else m.group(0), text)
    if drop_missing:
        filled = _drop_unfilled(filled)
    return filled.strip()


def inputs(prompt_id: str) -> list[str]:
    return list(_parse(prompt_id)["inputs"])


def available() -> list[str]:
    return sorted(path.stem for path in LIBRARY_DIR.glob("*.md"))
