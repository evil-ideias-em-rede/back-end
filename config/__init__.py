"""Configuração central do backend.

As variáveis podem ser fornecidas pelo ambiente. Valores de desenvolvimento
mantêm os módulos importáveis e tornam os erros de configuração explícitos no
momento em que um recurso externo é usado.
"""

import os

from dotenv import load_dotenv


# Damos prioridade às variáveis já exportadas pelo ambiente. O arquivo local
# é apenas um fallback de desenvolvimento.
dotenv_file = os.getenv("BACKEND_DOTENV_FILE", ".env")
load_dotenv(dotenv_file, override=False)


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-this-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
