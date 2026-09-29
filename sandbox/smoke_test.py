"""Teste do microsandbox sem depender do agente ou do banco de dados."""

import asyncio
import tempfile
from pathlib import Path

from graph.tools.sandbox.microsandbox_runtime import run_in_microsandbox


async def main() -> None:
    workdirs_root = Path("/app/workdirs")
    workdirs_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="contraponto-smoke-",
        dir=workdirs_root,
    ) as temporary:
        workspace = Path(temporary)
        (workspace / "planning.json").write_text("[]\n", encoding="utf-8")

        first = await run_in_microsandbox(
            "printf '[{\"id\": \"teste\"}]\\n' > planning.json && "
            "python3 -c 'import pymupdf; print(\"python-ok\")'",
            workspace,
        )
        assert first.returncode == 0, first.stderr.decode(errors="replace")
        assert b"python-ok" in first.stdout
        assert "teste" in (workspace / "planning.json").read_text(encoding="utf-8")

        second = await run_in_microsandbox(
            "test -s planning.json && "
            "python3 - <<'PY'\n"
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
            "except OSError:\n"
            "    print('rede-bloqueada')\n"
            "else:\n"
            "    raise SystemExit(1)\n"
            "PY",
            workspace,
        )
        assert second.returncode == 0, second.stderr.decode(errors="replace")
        assert b"rede-bloqueada" in second.stdout

    print("Smoke test do microsandbox passou.")


if __name__ == "__main__":
    if not Path("/dev/kvm").exists():
        raise SystemExit("/dev/kvm não está disponível")
    asyncio.run(main())
