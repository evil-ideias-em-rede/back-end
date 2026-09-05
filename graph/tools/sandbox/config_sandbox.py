from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "sandbox_files"


def _montar_comando_sandboxed(comando: str, work_dir: str) -> list:
    """
    Monta o comando real a ser executado, envolto em bubblewrap.
    O processo dentro do sandbox só enxerga:
      - /usr, /usr/local, /lib, /lib64, /bin (somente leitura)
      - work_dir montado como /workspace, com escrita liberada
    Sem rede, sem acesso ao resto do filesystem do host.
    """
    comando_com_limites = f"ulimit -u 64 -v 2097152 -f 20480; {comando}"
    montagem_skills = []
    if SKILLS_DIR.is_dir():
        montagem_skills = ["--ro-bind", str(SKILLS_DIR), "/skills"]
    
    return [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/usr/local", "/usr/local",
        *montagem_skills,
        "--bind", work_dir, "/workspace",
        "--chdir", "/workspace",
        "--unshare-all",          # rede + user + ipc + uts, tudo isolado
        "--die-with-parent",
        "--new-session",          # mitiga TIOCSTI injection
        "--proc", "/proc",
        "--dev", "/dev",
        "--clearenv",             # não herda env do host
        "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
        "--setenv", "HOME", "/workspace",
        "--setenv", "PYTHONPATH", "/skills",
        "--cap-drop", "ALL",
        "--uid", "65534", "--gid", "65534",   # nobody, não root
        "bash", "-c", comando_com_limites,
    ]