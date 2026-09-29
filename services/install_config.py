"""Validação de instalação; mensagens nunca incluem valores de credenciais."""
import os
from urllib.parse import urlsplit

from services.llm import get_llm_config


def validate_install_config(environ=None) -> None:
    env = os.environ if environ is None else environ
    if env.get("APP_ENV") != "installation":
        return  # Compatibilidade com o ambiente de desenvolvimento existente.
    required = ("DATABASE_URL", "JWT_SECRET", "OPENAI_API_KEY")  # Embeddings permanecem OpenAI.
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise ValueError("Preencha as configurações obrigatórias: " + ", ".join(missing))
    get_llm_config(env)  # Exige somente chave/modelo do provedor de geração selecionado.
    secret = env["JWT_SECRET"]
    if len(secret) < 32 or any(word in secret.lower() for word in ("generate_", "change-this", "troque", "dev-only")):
        raise ValueError("JWT_SECRET precisa ser um segredo exclusivo com pelo menos 32 caracteres; use scripts/install.sh.")
    try:
        database = urlsplit(env["DATABASE_URL"])
        valid_database = database.scheme in {"postgres", "postgresql"} and database.hostname and database.password
    except ValueError:
        valid_database = False
    if not valid_database:
        raise ValueError("DATABASE_URL precisa apontar para um PostgreSQL com autenticação.")
    if env.get("JWT_ALGORITHM", "HS256") != "HS256":
        raise ValueError("A instalação padrão utiliza JWT_ALGORITHM=HS256.")


if __name__ == "__main__":
    try:
        validate_install_config()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
