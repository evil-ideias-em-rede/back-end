"""Instala o índice público em volume, sem cookies, com validação e troca atômica."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
from uuid import uuid4


DEFAULT_URL = "https://drive.google.com/drive/folders/16tgqKuWKXBBUwYrAJRKuU1pj38yKPAGs"
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "graph/tools/retrieval/indice"
REQUIRED_TABLES = {"audiencias", "audiencias_vec", "documentos", "documentos_vec"}


def compatible_index(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
            return REQUIRED_TABLES <= tables
    except sqlite3.Error:
        return False


def check_digest(path: Path, expected: str) -> None:
    if not expected:
        return
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise ValueError("INDEX_SHA256 deve conter 64 caracteres hexadecimais.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected.lower():
        raise ValueError("O índice não corresponde a INDEX_SHA256. O arquivo existente foi preservado.")


def ensure_index(directory: Path = DEFAULT_DIR, url: str | None = None, expected: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "indice_busca.sqlite"
    expected = os.getenv("INDEX_SHA256", "").strip() if expected is None else expected
    if compatible_index(target):
        check_digest(target, expected)
        print("Índice existente validado; download dispensado.", flush=True)
        return target
    url = os.getenv("INDEX_DOWNLOAD_URL", DEFAULT_URL).strip() if url is None else url
    if not url:
        raise ValueError("Índice ausente/incompatível. Configure INDEX_DOWNLOAD_URL ou importe indice_busca.sqlite para o volume.")
    if not url.startswith("https://"):
        raise ValueError("INDEX_DOWNLOAD_URL deve usar HTTPS.")
    print("Instalando índice público; o primeiro download pode levar alguns minutos...", flush=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=directory) as temporary:
        staging = Path(temporary)
        is_folder = "/folders/" in url
        destination = str(staging) + "/" if is_folder else str(staging / target.name)
        args = ["gdown", "--no-cookies", "--timeout", "60", "--retries", "3"]
        if is_folder:
            args.append("--folder")
        args.extend(["--output", destination, url])
        subprocess.run(args, check=True, timeout=900)
        candidates = list(staging.rglob(target.name))
        if len(candidates) != 1 or not compatible_index(candidates[0]):
            raise ValueError("Download não contém um único índice compatível; confira o acesso público e a versão distribuída.")
        source = candidates[0]
        check_digest(source, expected)
        if target.exists():
            backup = target.with_name(f"indice_busca.previous-{uuid4().hex}.sqlite")
            shutil.copy2(target, backup)
            print(f"Índice anterior preservado em {backup.name}.", flush=True)
        os.replace(source, target)
    print("Índice instalado e validado.", flush=True)
    return target


if __name__ == "__main__":
    try:
        ensure_index()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Não imprime a URL configurada (ela pode conter parâmetros privados).
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise SystemExit("Falha ao preparar o índice: " + detail) from None
