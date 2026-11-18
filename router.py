"""Header binario de actividad 6: creación e interpretación de paquetes."""
import argparse
import ipaddress
import socket
import struct


# IPv4 (4), puerto (2), TTL (1), ID (4), offset (4), tamaño (4), flag (1).
HEADER = struct.Struct("!4sHBIIIB")
HEADER_SIZE = HEADER.size


def parse_packet(IP_packet):
    if len(IP_packet) < HEADER_SIZE:
        raise ValueError("Header incompleto")
    ip, puerto, ttl, identifier, offset, size, flag = HEADER.unpack_from(IP_packet)
    mensaje = IP_packet[HEADER_SIZE:]
    if size != len(mensaje):
        raise ValueError("Tamaño declarado distinto del payload recibido")
    if flag not in (0, 1):
        raise ValueError("FLAG debe ser 0 o 1")
    return dict(ip=socket.inet_ntoa(ip), puerto=puerto, ttl=ttl,
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
        header = HEADER.pack(socket.inet_aton(packet["ip"]), packet["puerto"],
                             packet["ttl"], packet["id"], packet["offset"],
                             len(mensaje), packet["flag"])
    except (struct.error, OSError) as error:
        raise ValueError(f"Campos inválidos: {error}") from error
    return header + mensaje


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
    counters = {}
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
                    print(packet["mensaje"].decode("utf-8", errors="replace"), flush=True)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("router_IP")
    parser.add_argument("router_puerto", type=int)
    parser.add_argument("router_rutas")
    args = parser.parse_args()
    run_router(args.router_IP, args.router_puerto, args.router_rutas)
