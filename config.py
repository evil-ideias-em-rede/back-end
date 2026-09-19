import os

from dotenv import load_dotenv


load_dotenv(override=False)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)

# Dentro do container, ``localhost`` aponta para o próprio backend. O banco
# local fica no host e é exposto pelo Docker em ``host.docker.internal``.
if os.path.exists("/.dockerenv"):
    DATABASE_URL = DATABASE_URL.replace("@localhost:", "@host.docker.internal:")
    DATABASE_URL = DATABASE_URL.replace("@127.0.0.1:", "@host.docker.internal:")
