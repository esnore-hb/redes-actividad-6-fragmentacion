"""Mini-router UDP con TTL, round-robin y fragmentación por enlace."""
import ipaddress
import socket
import sys


# IPv4 (4), puerto (2), TTL (1), ID (4), offset (4), tamaño (4), flag (1).
HEADER_SIZE = 20


def parse_packet(IP_packet):
    if len(IP_packet) < HEADER_SIZE:
        raise ValueError("Header incompleto")
    ip = socket.inet_ntop(socket.AF_INET, IP_packet[:4])
    puerto = int.from_bytes(IP_packet[4:6], byteorder="big")
    ttl = IP_packet[6]
    identifier = int.from_bytes(IP_packet[7:11], byteorder="big")
    offset = int.from_bytes(IP_packet[11:15], byteorder="big")
    size = int.from_bytes(IP_packet[15:19], byteorder="big")
    flag = IP_packet[19]
    mensaje = IP_packet[HEADER_SIZE:]
    if size != len(mensaje):
        raise ValueError("Tamaño declarado distinto del payload recibido")
    if flag not in (0, 1):
        raise ValueError("FLAG debe ser 0 o 1")
    return dict(ip=ip, puerto=puerto, ttl=ttl,
                id=identifier, offset=offset, tamano=size, flag=flag,
                mensaje=mensaje)


def create_packet(packet):
    mensaje = packet["mensaje"]
    if not isinstance(mensaje, bytes):
        raise ValueError("El mensaje debe estar codificado en bytes")
    if packet.get("tamano", len(mensaje)) != len(mensaje):
        raise ValueError("Tamaño declarado distinto del payload")
    if packet["flag"] not in (0, 1):
        raise ValueError("FLAG debe ser 0 o 1")
    try:
        ip = socket.inet_pton(socket.AF_INET, packet["ip"])
        puerto = packet["puerto"].to_bytes(2, byteorder="big")
        ttl = packet["ttl"].to_bytes(1, byteorder="big")
        identifier = packet["id"].to_bytes(4, byteorder="big")
        offset = packet["offset"].to_bytes(4, byteorder="big")
        size = len(mensaje).to_bytes(4, byteorder="big")
        flag = packet["flag"].to_bytes(1, byteorder="big")
    except (OverflowError, AttributeError, OSError) as error:
        raise ValueError(f"Campos inválidos: {error}") from error
    return ip + puerto + ttl + identifier + offset + size + flag + mensaje


def fragment_IP_packet(IP_packet, MTU):
    packet = parse_packet(IP_packet)
    if len(IP_packet) <= MTU:
        return [IP_packet]
    capacity = MTU - HEADER_SIZE
    if capacity <= 0:
        raise ValueError("El MTU debe permitir header y al menos un byte de datos")
    fragments = []
    for start in range(0, len(packet["mensaje"]), capacity):
        chunk = packet["mensaje"][start:start + capacity]
        more = start + len(chunk) < len(packet["mensaje"])
        fragments.append(create_packet({**packet, "mensaje": chunk,
            "tamano": len(chunk), "offset": packet["offset"] + start,
            "flag": 1 if more else packet["flag"]}))
    return fragments


def reassemble_IP_packet(fragment_list):
    if not fragment_list:
        return None
    fragments = sorted((parse_packet(raw) for raw in fragment_list),
                       key=lambda p: p["offset"])
    first = fragments[0]
    identity = (first["ip"], first["puerto"], first["id"])
    cursor, chunks, seen = 0, [], set()
    last = False
    for fragment in fragments:
        if (fragment["ip"], fragment["puerto"], fragment["id"]) != identity:
            return None
        signature = (fragment["offset"], fragment["mensaje"], fragment["flag"])
        if signature in seen:
            continue
        seen.add(signature)
        if last or fragment["offset"] != cursor:
            return None
        chunks.append(fragment["mensaje"])
        cursor += fragment["tamano"]
        last = fragment["flag"] == 0
    if not last:
        return None
    payload = b"".join(chunks)
    # Fragmentos pueden recorrer caminos con distinto número de saltos.
    return create_packet({**first, "ttl": min(p["ttl"] for p in fragments),
                          "offset": 0, "flag": 0, "tamano": len(payload),
                          "mensaje": payload})


def load_routes(filename):
    routes = []
    with open(filename, encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            fields = line.split("#", 1)[0].split()
            if not fields:
                continue
            if len(fields) != 6:
                raise ValueError(f"Línea {number}: se esperan seis campos")
            network, low, high, ip, port, mtu = fields
            route = (ipaddress.ip_network(network, strict=False), int(low),
                     int(high), (str(ipaddress.IPv4Address(ip)), int(port)), int(mtu))
            if not (0 <= route[1] <= route[2] <= 65535 and
                    0 <= route[3][1] <= 65535 and route[4] > HEADER_SIZE):
                raise ValueError(f"Línea {number}: rango, puerto o MTU inválido")
            routes.append(route)
    return routes


def check_routes(routes_file_name, destination_address, turnos):
    """Extiende actividad 5: ruta y MTU, con turnos por área de red."""
    ip, port = destination_address
    area_elegida = None
    matches = []
    for route in load_routes(routes_file_name):
        area = route[:3]
        if ipaddress.IPv4Address(ip) in route[0] and route[1] <= port <= route[2]:
            if area_elegida is None:
                area_elegida = area
            if area == area_elegida:
                matches.append(route)
    if not matches:
        return None
    key = (str(routes_file_name), area_elegida)
    index = turnos.get(key, 0)
    turnos[key] = (index + 1) % len(matches)
    chosen = matches[index % len(matches)]
    return chosen[3], chosen[4]


def run_router(ip, port, routes_file):
    load_routes(routes_file)  # Validar antes de comenzar a recibir.
    counters, pending = {}, {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.bind((ip, port))
        print(f"LISTO {ip}:{port}", flush=True)
        while True:
            raw, _ = connection.recvfrom(65535)
            try:
                packet = parse_packet(raw)
                if packet["ttl"] == 0:
                    print(f"DESCARTE TTL id={packet['id']} offset={packet['offset']}", flush=True)
                    continue
                if (packet["ip"], packet["puerto"]) == (ip, port):
                    fragments = pending.setdefault(packet["id"], [])
                    if raw not in fragments:
                        fragments.append(raw)
                    assembled = reassemble_IP_packet(fragments)
                    if assembled is not None:
                        del pending[packet["id"]]
                        print(parse_packet(assembled)["mensaje"].decode("utf-8", errors="replace"), flush=True)
                    continue
                route = check_routes(routes_file, (packet["ip"], packet["puerto"]), counters)
                if route is None:
                    print(f"DESCARTE SIN RUTA id={packet['id']}", flush=True)
                    continue
                next_hop, mtu = route
                forwarded = create_packet({**packet, "ttl": packet["ttl"] - 1})
                for fragment in fragment_IP_packet(forwarded, mtu):
                    info = parse_packet(fragment)
                    print(f"FORWARD id={info['id']} offset={info['offset']} "
                          f"size={len(fragment)} flag={info['flag']} ttl={info['ttl']} "
                          f"next={next_hop[1]} mtu={mtu}", flush=True)
                    connection.sendto(fragment, next_hop)
            except ValueError as error:
                print(f"DESCARTE INVÁLIDO: {error}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("Uso: python router.py router_IP router_puerto router_rutas.txt")
    try:
        router_puerto = int(sys.argv[2])
    except ValueError:
        sys.exit("El puerto debe ser un número entero.")
    if not 1 <= router_puerto <= 65535:
        sys.exit("El puerto del router debe estar entre 1 y 65535.")
    run_router(sys.argv[1], router_puerto, sys.argv[3])
