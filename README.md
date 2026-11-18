# Actividad 6: Fragmentación

Python 3, sin dependencias externas para ejecutar routers y pruebas.
Protocolo propio de la actividad: datagramas UDP con header binario de 20 bytes.

## Ejecutar

Desde esta carpeta, abrir cinco terminales y ejecutar una línea en cada una:

```powershell
python router.py 127.0.0.1 8881 rutas_R1_v3_mtu.txt
python router.py 127.0.0.1 8882 rutas_R2_v3_mtu.txt
python router.py 127.0.0.1 8883 rutas_R3_v3_mtu.txt
python router.py 127.0.0.1 8884 rutas_R4_v3_mtu.txt
python router.py 127.0.0.1 8885 rutas_R5_v3_mtu.txt
```

Desde otra terminal:

```powershell
python enviar.py 127.0.0.1 8885 'hola!' 127.0.0.1 8881 10 --id 347
python enviar.py 127.0.0.1 8885 'mensaje de prueba' 127.0.0.1 8881 30 --total 150 --id 348
```

Usar un ID nuevo por datagrama en vuelo. No enviar un header textual con netcat:
el emisor construye los campos binarios y calcula el tamaño del payload en bytes.
El receptor imprime el mensaje completo solo después de reensamblarlo.
Las líneas FORWARD y DESCARTE son diagnósticos.
La interfaz conserva el orden de argumentos de actividad 5:
`IP_final puerto_final mensaje IP_envio puerto_envio TTL`; se agregan `--id`
(opcional, aleatorio de 32 bits por defecto) y `--total` (relleno con puntos).

## Verificación

```powershell
python -m unittest -v
python prueba_red.py
```

La segunda prueba inicia y cierra sus cinco procesos en puertos 28881-28885,
traduce las tablas conservando su topología y genera `evidencia-red.txt`.
Requiere esos puertos disponibles. No modifica los archivos originales de rutas.
La suite de `unittest` contiene 15 pruebas: 12 de funciones, una de recepción UDP
y dos de la interfaz del emisor. La prueba de cinco routers se ejecuta aparte.

## Contrato binario

Orden de red (big-endian), formato struct `!4sHBIIIB`:

| Campo | Bytes | Uso |
| --- | ---: | --- |
| IP | 4 | IPv4 destino |
| Puerto | 2 | Router destino |
| TTL | 1 | Disminuye una vez por forwarding |
| ID | 4 | Identificador del datagrama |
| Offset | 4 | Inicio del payload respecto del original, en bytes |
| Tamaño | 4 | Solo payload, en bytes |
| FLAG | 1 | 1: hay datos posteriores; 0: último fragmento |

`parse_packet` retorna un diccionario con `ip`, `puerto`, `ttl`, `id`,
`offset`, `tamano`, `flag` y `mensaje` (bytes). `create_packet` realiza la operación
inversa. `fragment_IP_packet` y `reassemble_IP_packet` trabajan con bytes completos.
El reensamblaje devuelve `None` si faltan datos o los fragmentos son incompatibles.
Conserva el TTL mínimo de los fragmentos; no restituye el TTL anterior al tránsito.

`load_routes` carga las tablas; `check_routes(archivo_rutas, (ip, puerto), turnos)`
retorna `(next_hop, mtu)` o `None`. Pasar siempre el mismo diccionario `turnos`
para conservar round-robin por área `(red, puerto_inicial, puerto_final)`.
Se respeta la primera área coincidente de la tabla, como en actividad 5;
destinos distintos dentro de la misma área comparten turno y áreas distintas
mantienen turnos independientes. Cada paquete o fragmento recibido elige
una ruta; todos los subfragmentos producidos en esa operación usan esa ruta.

## Alcance

Esta versión se contrastó con `router.py` y `enviar.py` finales de actividad 5.
Conserva la interfaz de `check_routes`, su selección por área y el comportamiento
de TTL: solo se procesan valores mayores que cero y se resta uno al reenviar.
Un TTL 1 sale como TTL 0 y se descarta al llegar al siguiente router.
Se extiende el header de 7 a 20 bytes y se añade MTU a las rutas.
Las tablas se transcriben del enunciado; R5 conserva la dirección sin prefijo,
interpretada como /32 por `ipaddress`, suficiente para el destino 127.0.0.1.

No se implementan retransmisión UDP ni expiración de buffers incompletos.
Los IDs deben ser únicos entre datagramas simultáneos hacia un mismo router.
Un fragmento perdido impide imprimir el mensaje. Duplicados idénticos durante
el reensamblaje se toleran; no hay supresión de duplicados tras una entrega completa.

El [informe](informe.md) describe las decisiones de implementación y las
observaciones obtenidas en [la ejecución de cinco routers](evidencia-red.txt).
