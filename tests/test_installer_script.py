"""Valida geração local de configuração sem criar containers nem usar chaves."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64" and Path("/dev/kvm").exists(), "pré-requisito Linux/KVM ausente")
class InstallerScriptTest(unittest.TestCase):
    @unittest.skipUnless((ROOT / ".env.install.example").is_file(), "teste do host: exemplo de instalação não é distribuído na imagem")
    def test_private_unique_config_and_no_overwrite(self):
        secrets = []
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            binary = base / "bin"
            binary.mkdir()
            docker = binary / "docker"
            docker.write_text("#!/bin/sh\nexit 0\n")
            docker.chmod(0o755)
            env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
            for number in range(2):
                project = base / str(number)
                backend = project / "back-end"
                (backend / "scripts").mkdir(parents=True)
                (project / "front-end").mkdir()
                (project / "front-end/package-lock.json").write_text("{}")
                for name in (
                    "graph/tools/retrieval/public_hearing/PublicHearingBR_LDS.jsonl",
                    "graph/tools/retrieval/dados_camara/resultados_mimo_corpus/resultados_mimo_corpus.csv.gz",
                ):
                    target = backend / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"fixture: preflight checks existence only")
                shutil.copy2(ROOT / "scripts/install.sh", backend / "scripts/install.sh")
                shutil.copy2(ROOT / ".env.install.example", backend / ".env.install.example")
                command = ["bash", str(backend / "scripts/install.sh")]
                subprocess.run(command + ["--check"], env=env, check=True, capture_output=True)
                self.assertFalse((backend / ".env.install").exists())
                subprocess.run(command, env=env, check=True, capture_output=True)
                config = backend / ".env.install"
                first = config.read_bytes()
                secrets.append(first)
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(b"GENERATE_", first)
                subprocess.run(command, env=env, check=True, capture_output=True)
                self.assertEqual(first, config.read_bytes())
        self.assertNotEqual(secrets[0], secrets[1])
