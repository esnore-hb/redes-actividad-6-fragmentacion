"""Pruebas de la interfaz real del emisor y su datagrama UDP."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest

from router import parse_packet


ROOT = Path(__file__).resolve().parent


class SenderTests(unittest.TestCase):
    def run_sender(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "enviar.py"), *arguments],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_cli_preserves_final_destination_utf8_and_total_size(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(5)
            entry_port = receiver.getsockname()[1]
            message = "hola ñ 🐶"
            result = self.run_sender("127.0.0.1", "8885", message,
                "127.0.0.1", str(entry_port), "10", "--id", "347", "--total", "150")
            self.assertEqual(result.returncode, 0, result.stderr)
            raw, _ = receiver.recvfrom(65535)
            self.assertEqual(len(raw), 150)
            self.assertEqual(parse_packet(raw), dict(ip="127.0.0.1", puerto=8885,
                ttl=10, id=347, offset=0, tamano=130, flag=0,
                mensaje=message.encode("utf-8").ljust(130, b".")))
            result = self.run_sender("127.0.0.1", "8885", "sin relleno",
                "127.0.0.1", str(entry_port), "10")
            self.assertEqual(result.returncode, 0, result.stderr)
            raw, _ = receiver.recvfrom(65535)
            packet = parse_packet(raw)
            self.assertEqual(packet["mensaje"], b"sin relleno")
            self.assertGreaterEqual(packet["id"], 0)
            self.assertLess(packet["id"], 2**32)

    def test_invalid_arguments_are_rejected(self):
        base = ["127.0.0.1", "8885", "hola", "127.0.0.1", "8881", "10"]
        invalid = [base[:-1] + [ttl] for ttl in ("0", "-1", "256")]
        invalid += [base + ["--id", "4294967296"], base + ["--total", "23"],
                    base + ["--total", "65508"], ["no-es-ip"] + base[1:]]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                result = self.run_sender(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
