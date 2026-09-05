import os
from functools import lru_cache

from langchain_openai import ChatOpenAI

from config import OPENAI_MODEL_NAME



@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    """Cria o cliente apenas quando um turno de agente for executado."""
    return ChatOpenAI(
        model=OPENAI_MODEL_NAME,
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    )
