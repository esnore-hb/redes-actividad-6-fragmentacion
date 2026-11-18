"""Emisor del protocolo binario de actividad 6."""
import argparse
import secrets
import socket
from router import HEADER_SIZE, create_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("IP_final")
    parser.add_argument("puerto_final", type=int)
    parser.add_argument("mensaje")
    parser.add_argument("IP_envio")
    parser.add_argument("puerto_envio", type=int)
    parser.add_argument("TTL", type=int)
    parser.add_argument("--id", type=int, default=None)
    parser.add_argument("--total", type=int, help="Tamaño total; rellena con puntos")
    args = parser.parse_args()
    if not 1 <= args.TTL <= 255:
        parser.error("El TTL inicial debe estar entre 1 y 255")
    if not (0 <= args.puerto_final <= 65535 and 1 <= args.puerto_envio <= 65535):
        parser.error("Puertos fuera de rango")
    if args.id is not None and not 0 <= args.id < 2**32:
        parser.error("ID debe estar entre 0 y 2**32 - 1")
    for address in (args.IP_final, args.IP_envio):
        try:
            socket.inet_pton(socket.AF_INET, address)
        except OSError:
            parser.error(f"Dirección IPv4 inválida: {address}")
    payload = args.mensaje.encode("utf-8")
    if args.total is not None:
        if args.total < HEADER_SIZE + len(payload):
            parser.error("El total solicitado no alcanza para header y mensaje")
        payload = payload.ljust(args.total - HEADER_SIZE, b".")
    if HEADER_SIZE + len(payload) > 65507:
        parser.error("El paquete supera el máximo de 65507 bytes del payload UDP IPv4")
    packet = create_packet(dict(ip=args.IP_final, puerto=args.puerto_final, ttl=args.TTL,
        id=args.id if args.id is not None else secrets.randbits(32), offset=0,
        flag=0, mensaje=payload))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.sendto(packet, (args.IP_envio, args.puerto_envio))
    print(f"Enviados {len(packet)} bytes (header={HEADER_SIZE}, payload={len(payload)})")


if __name__ == "__main__":
    main()
