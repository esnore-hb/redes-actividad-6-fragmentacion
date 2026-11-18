"""Prueba reproducible de cinco procesos UDP; no usa los puertos de actividad 5."""
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
from router import create_packet, fragment_IP_packet, parse_packet


ROOT = Path(__file__).resolve().parent


def main():
    events = queue.Queue()
    logs, processes = [], []
    ports = list(range(28881, 28886))

    def read_output(index, process):
        for line in process.stdout:
            events.put((index, line.rstrip()))

    def wait_for(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty:
                break
            logs.append(f"R{event[0]} {event[1]}")
            if predicate(event):
                return
        raise AssertionError("No se recibió el evento esperado; revisar evidencia-red.txt")

    def make_packet(identifier, payload, ttl=30):
        return create_packet(dict(ip="127.0.0.1", puerto=ports[4], ttl=ttl,
            id=identifier, offset=0, flag=0, mensaje=payload))

    try:
        # Verificar disponibilidad antes de lanzar procesos (también se comprueba LISTO).
        reserved = []
        try:
            for port in ports:
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                reserved.append(probe)
                probe.bind(("127.0.0.1", port))
        finally:
            for probe in reserved:
                probe.close()
        with tempfile.TemporaryDirectory() as directory:
            for index, port in enumerate(ports, 1):
                text = (ROOT / f"rutas_R{index}_v3_mtu.txt").read_text()
                for original, replacement in zip(range(8881, 8886), ports):
                    text = text.replace(str(original), str(replacement))
                route_file = Path(directory) / f"R{index}.txt"
                route_file.write_text(text)
                process = subprocess.Popen([sys.executable, "-u", str(ROOT / "router.py"),
                    "127.0.0.1", str(port), str(route_file)], stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                processes.append(process)
                threading.Thread(target=read_output, args=(index, process), daemon=True).start()
                wait_for(lambda event, i=index: event[0] == i and event[1].startswith("LISTO"))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for number in range(4):
                    payload = b"hola!" if number == 0 else f"hola{number}".encode()
                    sender.sendto(make_packet(347 + number, payload, ttl=10), ("127.0.0.1", ports[0]))
                    wait_for(lambda event, p=payload: event == (5, p.decode()))
                for source in (1, 1, 2, 3, 4, 1):
                    identifier = 1000 + len([line for line in logs if line.startswith("CASO")])
                    payload = f"desde-R{source}-id{identifier}:".encode().ljust(130, b"x")
                    logs.append(f"CASO id={identifier} origen=R{source} total=150 payload=130")
                    sender.sendto(make_packet(identifier, payload), ("127.0.0.1", ports[source - 1]))
                    wait_for(lambda event, p=payload: event == (5, p.decode()))
                expired = make_packet(2000, b"NO DEBE ENTREGARSE")
                expired = create_packet({**parse_packet(expired), "ttl": 1})
                sender.sendto(expired, ("127.0.0.1", ports[0]))
                wait_for(lambda event: event[0] == 2 and "DESCARTE TTL id=2000" in event[1])
                sender.sendto(make_packet(2001, b"f" * 130, ttl=1), ("127.0.0.1", ports[0]))
                for offset in (0, 80):
                    wait_for(lambda event, off=offset: event ==
                             (2, f"DESCARTE TTL id=2001 offset={off}"))
                sender.sendto(make_packet(2002, b"TTL CERO NO SE IMPRIME", ttl=0),
                              ("127.0.0.1", ports[4]))
                wait_for(lambda event: event == (5, "DESCARTE TTL id=2002 offset=0"))
                missing = create_packet({**parse_packet(make_packet(2003, b"sin ruta")),
                                         "ip": "192.0.2.1"})
                sender.sendto(missing, ("127.0.0.1", ports[0]))
                wait_for(lambda event: event == (1, "DESCARTE SIN RUTA id=2003"))
                messages = [b"ordenado:" + b"a" * 100,
                            b"desordenado:" + b"b" * 100,
                            b"intercalado:" + b"c" * 100]
                ordered = fragment_IP_packet(make_packet(3000, messages[0]), 50)
                for fragment in ordered:
                    sender.sendto(fragment, ("127.0.0.1", ports[4]))
                wait_for(lambda event: event == (5, messages[0].decode()))
                groups = [fragment_IP_packet(make_packet(3001 + i, payload), 50)[::-1]
                          for i, payload in enumerate(messages[1:])]
                for pair in zip(*groups):
                    for fragment in pair:
                        sender.sendto(fragment, ("127.0.0.1", ports[4]))
                remaining = {payload.decode() for payload in messages[1:]}
                while remaining:
                    def received(event):
                        if event[0] == 5 and event[1] in remaining:
                            remaining.remove(event[1])
                            return True
                        return False
                    wait_for(received)
                # Ejecutar también la interfaz de consola heredada de actividad 5.
                cli = subprocess.run([sys.executable, str(ROOT / "enviar.py"),
                    "127.0.0.1", str(ports[4]), "desde-emisor:", "127.0.0.1",
                    str(ports[0]), "30", "--id", "4000", "--total", "150"],
                    capture_output=True, text=True, encoding="utf-8", timeout=8,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                assert cli.returncode == 0, cli.stderr
                logs.append("EMISOR " + cli.stdout.strip())
                wait_for(lambda event: event == (5, "desde-emisor:".ljust(130, ".")))
            forwards = [line for line in logs if "FORWARD" in line]
            for line in forwards:
                fields = dict(field.split("=", 1) for field in line.split() if "=" in field)
                assert int(fields["size"]) <= int(fields["mtu"]), line
            assert any("offset=30 " in line for line in forwards), "Falta refragmentación"
            small_r2 = [line for line in forwards if line.startswith("R2 ") and
                        any(f"id={i} " in line for i in range(347, 351))]
            assert [int(line.split("next=")[1].split()[0]) for line in small_r2[:4]] == [ports[2], ports[3]] * 2
            small = [line for line in forwards if any(f"id={i} " in line for i in range(347, 351))]
            assert all("size=25 " in line and "offset=0 " in line and "flag=0 " in line
                       for line in small)
            assert all("ttl=9 " in line for line in small if line.startswith("R1 "))
            assert any("id=2000 " in line and "ttl=0 " in line for line in forwards)
            assert len([line for line in forwards if "id=2001 " in line]) == 2
            assert not any(line == "R5 NO DEBE ENTREGARSE" for line in logs)
            logs.append("RESULTADO: OK; 4 pequeños, 6 de 150 bytes, TTL de paquete y fragmentos, "
                        "TTL 0 en destino, sin ruta, 3 reensamblajes directos y emisor CLI de 150 bytes.")
            print(logs[-1])
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=5)
        (ROOT / "evidencia-red.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
