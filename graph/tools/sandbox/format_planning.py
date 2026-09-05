import json
from pathlib import Path


def format_planning_file(work_dir: str | Path) -> str | None:
    """Formata planning.json e retorna um erro legível sem interromper o comando."""
    planning_file = Path(work_dir) / "planning.json"
    if not planning_file.is_file():
        return None
    if planning_file.is_symlink():
        return "planning.json não pode ser um link simbólico"

    try:
        original = planning_file.read_text(encoding="utf-8")
        data = json.loads(original)
        formatted = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if original != formatted:
            planning_file.write_text(formatted, encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return str(exc)

    return None


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Formata o planning.json de um workspace")
    parser.add_argument("workspace", nargs="?", default=".")
    args = parser.parse_args()
    error = format_planning_file(args.workspace)
    if error:
        print(f"Erro ao formatar planning.json: {error}", file=sys.stderr)
        raise SystemExit(1)
    print("planning.json formatado com sucesso")
