# Actividad 6: Fragmentación de datagramas

Pruebas locales realizadas el 18 de noviembre de 2026 con Python y sockets UDP.

## Implementación

El header ocupa 20 bytes: IP (4), puerto (2), TTL (1), ID (4), offset (4), tamaño (4) y FLAG (1). Los enteros se codifican en big-endian. Tamaño cuenta exclusivamente bytes del payload; offset también se mide en bytes. El parseo rechaza headers truncados, tamaños incoherentes y flags distintos de 0 y 1.

Se extendió la versión final de actividad 5: las funciones parse_packet y create_packet agregan los campos de fragmentación; check_routes conserva sus argumentos y retorna ahora siguiente salto junto con MTU. También se conserva el orden de argumentos del emisor, agregando opciones para ID y tamaño total.

Cada tabla indica red, rango de puertos destino, siguiente salto y MTU. Se respeta la primera área coincidente y se alternan sus rutas con round-robin por área (red y rango de puertos), como en actividad 5. Cada recepción reenviada elige una ruta; sus subfragmentos comparten siguiente salto y MTU. El TTL disminuye una vez antes de reenviar. TTL 0 se descarta incluso en destino; TTL 1 puede entregarse localmente o reenviarse como TTL 0, que el siguiente router descarta.

Si el paquete completo supera el MTU, cada fragmento transporta hasta MTU - 20 bytes de datos. Su offset suma el desplazamiento dentro del padre al offset del padre. Todos los subfragmentos salvo el último llevan FLAG 1; el último conserva el FLAG del padre. Así, refragmentar un fragmento intermedio no lo convierte erróneamente en el final del datagrama.

En destino se almacenan listas por ID. Después de cada recepción se ordenan por offset, se verifica cobertura continua desde cero y se exige un último fragmento con FLAG 0. Solo entonces se imprime el payload y se elimina la lista. El TTL del paquete rearmado corresponde al mínimo recibido. La comparación binaria con el original se prueba sin tránsito; durante el tránsito el TTL cambia legítimamente.

## Pruebas y observaciones

Se ejecutaron 15 pruebas con resultado OK: 12 pruebas de funciones, una de recepción UDP con un proceso router real y dos de la interfaz del emisor. Cubren ida y vuelta de bytes construidos manualmente, validación de paquetes, límites de MTU, refragmentación, reensamblaje de un datagrama refragmentado, fragmentos faltantes o duplicados e IDs intercalados, solapamientos, payload vacío, TTL diferentes y selección de rutas con MTU. Se verificó round-robin con tres alternativas, turnos compartidos por área e independencia entre áreas. El payload binario y UTF-8 se maneja en bytes; la decodificación se realiza al completar el mensaje.

La prueba de red inició cinco procesos reales usando las tablas del enunciado. Para coexistir con actividad 5, los puertos 8881-8885 se tradujeron a 28881-28885. Los MTU, rangos y enlaces se mantuvieron. La evidencia detallada está en evidencia-red.txt y se reproduce con python prueba_red.py.

Cuatro mensajes pequeños de cinco bytes y TTL inicial 10 llegaron completos a R5 sin fragmentación: cada datagrama midió 25 bytes. El primero usó ID 347 y mensaje hola!, como en el enunciado. Las primeras cuatro decisiones de R2 alternaron R3, R4, R3 y R4. Las trazas muestran decremento del TTL y retornos hacia routers ya visitados debido a las rutas cíclicas. Un paquete adicional con TTL 1 salió de R1 como TTL 0 y fue descartado en R2. Lo mismo ocurrió con los dos fragmentos de otro datagrama de 150 bytes con TTL 1. También se verificó descarte con TTL 0 directamente en R5 y sin ruta en R1.

Se enviaron seis paquetes de 150 bytes totales (20 de header y 130 de datos): tres desde R1 y uno desde cada router R2, R3 y R4, todos hacia R5. Los seis payloads se recibieron completos. En el caso ID 1000, R1 produjo paquetes de 100 y 70 bytes con offsets 0 y 80. R2 refragmentó el primero en paquetes de 50, 50 y 40 bytes, con offsets 0, 30 y 60; el otro fragmento conservó offset 80. Todos los envíos registrados respetaron el MTU elegido.

Estos datagramas grandes usaron TTL inicial 30 para permitir observar fragmentación y entrega aun cuando las rutas produjeran recorridos con retornos. El TTL 10 del ejemplo pequeño y los casos de agotamiento se probaron por separado. La siguiente tabla resume la primera fragmentación de cada envío según la evidencia guardada; los tamaños incluyen header:

| ID | Origen | MTU elegido al salir | Tamaños de los primeros fragmentos | Resultado en R5 |
| --- | --- | ---: | --- | --- |
| 1000 | R1 | 100 | 100, 70 | Mensaje completo |
| 1001 | R1 | 100 | 100, 70 | Mensaje completo |
| 1002 | R2 | 80 | 80, 80, 30 | Mensaje completo |
| 1003 | R3 | 55 | 55, 55, 55, 45 | Mensaje completo |
| 1004 | R4 | 80 | 80, 80, 30 | Mensaje completo |
| 1005 | R1 | 100 | 100, 70 | Mensaje completo |

Cambiar el router de entrada modifica el primer MTU y el estado de round-robin que se encuentra. En ID 1002, desde R2, el primer enlace elegido tuvo MTU 80 y produjo paquetes de 80, 80 y 30 bytes (offsets 0, 60 y 120). Los fragmentos pueden seguir rutas diferentes, acumular TTL distintos y llegar desordenados; el reensamblaje depende de ID, offset y FLAG, no del orden de llegada.

Se verificó además recepción directa en R5 de un datagrama fragmentado en orden y de otros dos IDs con fragmentos en orden inverso e intercalados. Los tres mensajes se imprimieron completos. En test_reception.py se comprobó que el router no imprime mientras falta un fragmento, incluso si ya llegó el último con FLAG 0. Completar uno de dos IDs intercalados no provoca la impresión del otro. También se verificó un duplicado mientras el datagrama estaba pendiente y un mensaje UTF-8 con caracteres divididos entre fragmentos.

Por último se ejecutó enviar.py por consola con la interfaz de actividad 5 y las opciones --id 4000 --total 150. El emisor produjo un paquete de 150 bytes y R5 recibió los 130 bytes de datos completos. Así se verificaron tanto las funciones como el script de envío pedido en el enunciado.

Las pruebas del emisor verificaron que el destino del header se conserva aunque el paquete se envíe a un puerto de entrada diferente, que el tamaño se calcula en bytes UTF-8 y que puede generarse un ID automáticamente. También se rechazaron TTL fuera de 1-255, un ID fuera de 32 bits, una dirección IPv4 inválida y tamaños totales incompatibles con el mensaje o el máximo de UDP IPv4.

## Reproducción y límites

Desde la carpeta del repositorio, con Python 3 y sin dependencias externas:

```powershell
python -m unittest -v
python prueba_red.py
```

El primer comando ejecuta las 15 pruebas. El segundo levanta sus cinco routers, realiza los envíos, comprueba MTU y entrega, escribe evidencia-red.txt y cierra los procesos. Los puertos 28881-28885 deben estar disponibles. El orden global de las líneas de diagnóstico y algunos recorridos pueden variar entre ejecuciones porque los routers son procesos concurrentes; la tabla anterior corresponde a la evidencia incluida.

Para un envío manual, con los cinco routers del README.md escuchando en 8881-8885:

```powershell
python enviar.py 127.0.0.1 8885 'hola!' 127.0.0.1 8881 10 --id 347
python enviar.py 127.0.0.1 8885 'mensaje de prueba' 127.0.0.1 8881 30 --id 348 --total 150
```

El primer comando construye un datagrama de 25 bytes; el segundo completa con puntos un payload de 130 bytes para alcanzar 150 bytes totales. Ambos entran por R1 y tienen como destino final R5.

UDP no garantiza entrega. No se incorporaron retransmisiones ni expiración de listas incompletas; un fragmento perdido deja el datagrama pendiente. Los IDs deben distinguir datagramas simultáneos. Duplicados idénticos se toleran mientras el datagrama está pendiente; no se suprimen repeticiones posteriores a una entrega completa. Las observaciones corresponden a ejecución local, sin implicar publicación en GitHub ni entrega en U-Cursos.
