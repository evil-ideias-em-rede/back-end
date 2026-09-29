import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.install_config import validate_install_config
from services.install_index import REQUIRED_TABLES, check_digest, compatible_index, ensure_index


def create_index(path):
    with sqlite3.connect(path) as conn:
        for name in REQUIRED_TABLES:
            conn.execute(f'CREATE TABLE "{name}" (id TEXT)')


class InstallationTest(unittest.TestCase):
    def config(self):
        return {"APP_ENV": "installation", "DATABASE_URL": "postgresql://app:random@db/app",
                "JWT_SECRET": "a" * 64, "OPENAI_API_KEY": "test-not-a-real-key", "OPENAI_MODEL_NAME": "test-model"}

    def test_required_settings_and_secret_safety(self):
        validate_install_config(self.config())
        for key in ("DATABASE_URL", "JWT_SECRET", "OPENAI_API_KEY", "OPENAI_MODEL_NAME"):
            env = self.config()
            env.pop(key)
            with self.assertRaisesRegex(ValueError, key):
                validate_install_config(env)
        env = self.config()
        env["JWT_SECRET"] = "dev-only-change-this-secret"
        with self.assertRaises(ValueError) as caught:
            validate_install_config(env)
        self.assertNotIn(env["JWT_SECRET"], str(caught.exception))
        validate_install_config({"APP_ENV": "development"})

    def test_valid_index_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "indice_busca.sqlite"
            create_index(path)
            with patch("services.install_index.subprocess.run") as download:
                self.assertEqual(ensure_index(Path(folder), expected=""), path)
                download.assert_not_called()

    def test_missing_or_invalid_download_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "indice_busca.sqlite"
            path.write_bytes(b"invalid but preserve")
            with patch("services.install_index.subprocess.run"):
                with self.assertRaises(ValueError):
                    ensure_index(Path(folder), "https://example.test/index.sqlite", "")
            self.assertEqual(path.read_bytes(), b"invalid but preserve")
            self.assertFalse(compatible_index(path))

    def test_folder_download_and_atomic_install(self):
        with tempfile.TemporaryDirectory() as folder:
            def download(args, **kwargs):
                self.assertIn("--no-cookies", args)
                self.assertIn("--folder", args)
                destination = Path(args[args.index("--output") + 1]) / "subfolder"
                destination.mkdir()
                create_index(destination / "indice_busca.sqlite")
            with patch("services.install_index.subprocess.run", side_effect=download):
                result = ensure_index(Path(folder), "https://drive.google.com/drive/folders/test", "")
            self.assertTrue(compatible_index(result))
            self.assertEqual(list(Path(folder).iterdir()), [result])

    def test_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index"
            path.write_bytes(b"index")
            check_digest(path, hashlib.sha256(b"index").hexdigest())
            for digest in ("0" * 64, "invalid"):
                with self.assertRaises(ValueError):
                    check_digest(path, digest)
