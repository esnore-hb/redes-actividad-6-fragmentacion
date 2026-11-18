"""Verifica por UDP que el destino imprime solo datagramas completos."""
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from router import create_packet, fragment_IP_packet


class DestinationTests(unittest.TestCase):
    def test_ordered_reversed_and_interleaved_fragments(self):
        root = Path(__file__).resolve().parent
        output = queue.Queue()
        with tempfile.TemporaryDirectory() as directory:
            routes = Path(directory) / "rutas.txt"
            routes.write_text("", encoding="utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen(
                [sys.executable, "-u", str(root / "router.py"),
                 "127.0.0.1", str(port), str(routes)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            def read_output():
                for line in process.stdout:
                    output.put(line.rstrip("\r\n"))

            threading.Thread(target=read_output, daemon=True).start()

            def fragments(identifier, text):
                raw = create_packet(dict(ip="127.0.0.1", puerto=port, ttl=10,
                    id=identifier, offset=0, flag=0, mensaje=text.encode("utf-8")))
                return fragment_IP_packet(raw, 50)

            def assert_waiting():
                with self.assertRaises(queue.Empty):
                    output.get(timeout=0.15)
                self.assertIsNone(process.poll())

            try:
                self.assertEqual(output.get(timeout=5), f"LISTO 127.0.0.1:{port}")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    def send(group):
                        for fragment in group:
                            sender.sendto(fragment, ("127.0.0.1", port))

                    ordered = "en orden: " + "a" * 120
                    group = fragments(100, ordered)
                    send(group[:-1])
                    send(group[:1])  # Duplicado mientras está pendiente.
                    assert_waiting()
                    send(group[-1:])
                    self.assertEqual(output.get(timeout=5), ordered)

                    reversed_text = "desordenado: " + "á🐶" * 25
                    group = fragments(101, reversed_text)[::-1]
                    send(group[:1])  # Llega primero el fragmento con FLAG 0.
                    assert_waiting()
                    send(group[1:])
                    self.assertEqual(output.get(timeout=5), reversed_text)

                    texts = ["ID A: " + "b" * 124, "ID B: " + "c" * 124]
                    groups = [fragments(102 + i, text) for i, text in enumerate(texts)]
                    for pair in zip(groups[0][:-1], groups[1][:-1]):
                        send(pair)
                    assert_waiting()
                    send(groups[1][-1:])
                    self.assertEqual(output.get(timeout=5), texts[1])
                    assert_waiting()  # Completar B no completa A.
                    send(groups[0][-1:])
                    self.assertEqual(output.get(timeout=5), texts[0])
                    assert_waiting()
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
