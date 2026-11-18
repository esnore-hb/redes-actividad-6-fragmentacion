"""Emisor del protocolo binario de actividad 6."""
import socket
import sys
from router import HEADER_SIZE, create_packet


def main():
    if len(sys.argv) not in (8, 9):
        sys.exit('Uso: python enviar.py IP_final puerto_final "mensaje" '
                 'IP_envio puerto_envio TTL ID [tamano_total]')
    ip_final, ip_envio = sys.argv[1], sys.argv[4]
    try:
        puerto_final = int(sys.argv[2])
        puerto_envio = int(sys.argv[5])
        ttl = int(sys.argv[6])
        identifier = int(sys.argv[7])
        total = int(sys.argv[8]) if len(sys.argv) == 9 else None
    except ValueError:
        sys.exit("Los puertos, TTL, ID y tamaño total deben ser números enteros.")
    if not 1 <= ttl <= 255:
        sys.exit("El TTL inicial debe estar entre 1 y 255")
    if not (0 <= puerto_final <= 65535 and 1 <= puerto_envio <= 65535):
        sys.exit("Puertos fuera de rango")
    if not 0 <= identifier < 2**32:
        sys.exit("ID debe estar entre 0 y 2**32 - 1")
    for address in (ip_final, ip_envio):
        try:
            socket.inet_pton(socket.AF_INET, address)
        except OSError:
            sys.exit(f"Dirección IPv4 inválida: {address}")
    payload = sys.argv[3].encode("utf-8")
    if HEADER_SIZE + len(payload) > 65507 or (total is not None and total > 65507):
        sys.exit("El paquete supera el máximo de 65507 bytes del payload UDP IPv4")
    if total is not None:
        if total < HEADER_SIZE + len(payload):
            sys.exit("El total solicitado no alcanza para header y mensaje")
        payload = payload.ljust(total - HEADER_SIZE, b".")
    packet = create_packet(dict(ip=ip_final, puerto=puerto_final, ttl=ttl,
        id=identifier, offset=0,
        flag=0, mensaje=payload))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.sendto(packet, (ip_envio, puerto_envio))
    print(f"Enviados {len(packet)} bytes (header={HEADER_SIZE}, payload={len(payload)})")


if __name__ == "__main__":
    main()
