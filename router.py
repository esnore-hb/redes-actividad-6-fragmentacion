"""Header binario de actividad 6: creación e interpretación de paquetes."""
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
