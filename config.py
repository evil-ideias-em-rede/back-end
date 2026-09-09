import os

from dotenv import load_dotenv


load_dotenv(override=False)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
