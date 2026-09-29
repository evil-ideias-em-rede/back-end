"""Seleção única do provedor de geração; embeddings têm configuração separada."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str


def get_llm_config(environ: Mapping[str, str] | None = None, *, model: str | None = None) -> LLMConfig:
    env = os.environ if environ is None else environ
    provider = env.get("LLM_PROVIDER", "openai").strip().lower()
    if provider not in {"openai", "deepinfra"}:
        raise ValueError("LLM_PROVIDER deve ser openai ou deepinfra.")
    prefix = provider.upper()
    model_key = "OPENAI_MODEL_NAME" if provider == "openai" else "DEEPINFRA_MODEL"
    selected_model = model or env.get(model_key, "").strip()
    if not selected_model and provider == "openai":
        selected_model = env.get("OPENAI_MODEL", "").strip()  # Compatibilidade legada.
    api_key = env.get(f"{prefix}_API_KEY", "").strip()
    missing = ([] if selected_model else [model_key]) + ([] if api_key else [f"{prefix}_API_KEY"])
    if missing:
        raise ValueError("Preencha as configurações obrigatórias: " + ", ".join(missing))
    # URLs explícitas impedem que OPENAI_BASE_URL redirecione a chave DeepInfra.
    base_url = (
        "https://api.deepinfra.com/v1/openai"
        if provider == "deepinfra"
        else env.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1"
    )
    return LLMConfig(provider, selected_model, api_key, base_url)


def create_chat_model(model: str | None = None, **kwargs) -> ChatOpenAI:
    config = get_llm_config(model=model)
    return ChatOpenAI(
        **kwargs,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        use_responses_api=config.provider == "openai",
    )


def create_structured_model(schema, model: str | None = None):
    config = get_llm_config(model=model)
    # Function calling é aceito pela API compatível da DeepInfra; não enviar
    # parâmetros exclusivos de Structured Outputs/Responses da OpenAI.
    method = "function_calling" if config.provider == "deepinfra" else "json_schema"
    return create_chat_model(model=config.model, temperature=0).with_structured_output(
        schema, method=method
    )


def generate_text(prompt: str, model: str | None = None) -> str:
    """Normaliza Chat Completions (str) e Responses (blocos de texto)."""
    response = create_chat_model(model=model).invoke(prompt)
    if isinstance(response.content, str):
        text = response.content
    else:
        text = "".join(
            block.get("text", "")
            for block in response.content
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
        )
    if not text.strip():
        raise ValueError("O provedor de IA retornou uma resposta sem texto.")
    return text
