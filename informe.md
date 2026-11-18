# Actividad 6: Fragmentación de datagramas

Pruebas locales realizadas el 18 de noviembre de 2026 con Python y sockets UDP.

## Flujo de funcionamiento

El sistema extiende el forwarding con TTL de actividad 5. Cada router es un proceso con un socket UDP propio; en la simulación comparten la IP 127.0.0.1 y se distinguen por el puerto. El emisor indica por separado el destino final del header y el router de entrada: enviar inicialmente a R1 no cambia que el paquete pueda estar dirigido a R5.

1. El emisor codifica el mensaje en UTF-8, construye el header y envía el datagrama al router de entrada.
2. El router espera paquetes en un ciclo bloqueante. Al recibir uno, interpreta su header y comprueba la coherencia del tamaño y del FLAG. Los paquetes inválidos se descartan con un diagnóstico.
3. Si el TTL recibido es 0, descarta el paquete, incluso si está dirigido al propio router.
4. Si la IP y el puerto destino coinciden con los del router, guarda el fragmento en la lista de su ID e intenta reensamblar. Si aún faltan datos, vuelve a esperar; si está completo, imprime únicamente el mensaje y elimina esa lista.
5. Si el destino es otro router, consulta el siguiente salto y su MTU. Si no hay ruta, descarta el paquete. Si existe, resta uno al TTL, fragmenta cuando sea necesario y envía todos los fragmentos producidos por el siguiente salto elegido. Después vuelve a esperar otro paquete.

Las líneas FORWARD y DESCARTE permiten observar las decisiones de los routers; no son entregas del mensaje a la aplicación. Los routers intermedios no reensamblan los datos.

## Decisiones de diseño

### Representación de los paquetes

Elegimos un header binario de campos de ancho fijo para poder separar los datos por posición, sin delimitadores que pudieran confundirse con el contenido del mensaje. Los enteros se codifican en big-endian para que emisor y routers interpreten el mismo orden de bytes. La estructura ocupa 20 bytes:

| Campo | Bytes | Motivo de la elección |
| --- | ---: | --- |
| IP | 4 | Representar IPv4 y mantener el formato de actividad 5. |
| Puerto | 2 | Representar los puertos de la simulación y conservar actividad 5. |
| TTL | 1 | Cubrir el rango 0-255 con el mismo comportamiento de actividad 5. |
| ID | 4 | Disponer de identificadores entre 0 y 2^32 - 1 sin limitarse a pocos envíos. |
| Offset | 4 | Representar posiciones en bytes con el mismo ancho que el tamaño. |
| Tamaño | 4 | Cumplir el ancho exigido por el enunciado; cuenta solo los datos. |
| FLAG | 1 | Representar 0 o 1 directamente, sin operaciones adicionales de bits. |

Los cuatro bytes de ID y offset amplían su rango a costa de un header mayor. Esto reduce la cantidad de datos que cabe en cada fragmento, por lo que el cálculo de capacidad siempre descuenta los 20 bytes completos. El ID lo elige el usuario y debe distinguir datagramas simultáneos; un rango amplio no evita por sí solo que se reutilice un ID.

Usamos un diccionario con campos nombrados para trabajar con la información interpretada: permite acceder a TTL, offset o mensaje sin recordar sus posiciones en el header. Las funciones parse_packet y create_packet concentran la conversión entre esa representación y los bytes enviados, para que el resto de las funciones no repita la codificación. Se usan cortes de bytes, int.from_bytes() y to_bytes() para expresar explícitamente el formato, siguiendo el estilo de actividad 5, sin necesitar struct.

El mensaje permanece en bytes durante la fragmentación y el reensamblaje. Esta elección evita confundir cantidad de caracteres con tamaño real: una letra con tilde o un emoji puede ocupar varios bytes y quedar dividido entre fragmentos. La conversión a texto se realiza después de recuperar el mensaje completo.

### Rutas, MTU y TTL

Conservamos round-robin por área de red, identificada por la red y el rango de puertos. Así, destinos de una misma área comparten turno, mientras que el tráfico hacia otra área no altera su alternancia. Se respeta la primera área coincidente de la tabla y se alternan sus alternativas. check_routes retorna el siguiente salto junto con su MTU para mantener asociados el enlace elegido y el límite que debe respetar el envío.

Cada paquete o fragmento recibido elige una ruta una sola vez; sus subfragmentos comparten siguiente salto y MTU. Esto permite fragmentar usando el límite de ese enlace. Al llegar al próximo router, cada fragmento puede encontrar otro MTU y necesitar refragmentación.

El TTL se resta una vez por reenvío, antes de fragmentar, para que dividir un paquete no cuente como varios saltos. Se conserva la regla de actividad 5: un TTL 1 puede entregarse localmente o reenviarse como TTL 0, que el siguiente router descarta. Así se limitan los recorridos cíclicos sin modificar el destino final del header.

Para comprobar pertenencia a redes CIDR reutilizamos la función ip_a_entero de actividad 5. Valida los cuatro componentes de la dirección, los convierte a bytes y obtiene un entero. Después desplazamos a la derecha 32 - prefijo bits tanto la dirección de red como el destino, y comparamos los resultados. Así se comparan solo los bits de red, en lugar de exigir que las cadenas de IP sean idénticas. Elegimos esta operación para mantener el mismo criterio de actividad 5 con operaciones básicas de Python, sin ipaddress. El prefijo se valida entre 0 y 32; /0 admite cualquier IPv4 y /32 exige coincidencia exacta. Las tablas provistas se conservan: en R5, cuando falta el prefijo se asume /32, que coincide con 127.0.0.1 en esta simulación.

### Fragmentación y reensamblaje

La capacidad de datos se calcula como MTU - 20, porque cada fragmento necesita su propio header. Usamos toda esa capacidad salvo en el último trozo para evitar producir más fragmentos de los necesarios para el enlace elegido. Si el paquete ya cabe, se devuelve sin cambios dentro de una lista, de modo que el reenvío pueda recorrer el resultado de la misma forma en ambos casos.

En la refragmentación, el offset suma el desplazamiento dentro del padre al offset del padre, porque debe seguir indicando la posición en el datagrama original. Todos los subfragmentos salvo el último llevan FLAG 1; el último conserva el FLAG del padre. Poner siempre FLAG 0 al terminar de dividir un padre sería incorrecto: podrían existir otros fragmentos posteriores del datagrama original.

En destino usamos un diccionario de listas por ID, como pide el enunciado, para separar datagramas que llegan intercalados. Ordenar cada lista por offset permite reconstruir mensajes que llegan desordenados. No basta con recibir FLAG 0: también exigimos cobertura continua desde offset 0, porque podría haber llegado el último fragmento antes que los anteriores. Por eso una lista de un elemento solo está completa cuando su offset es 0 y su FLAG es 0.

Los duplicados idénticos se toleran mientras el datagrama está pendiente; los solapamientos incompatibles no se aceptan como un mensaje completo. Al terminar se elimina la lista para liberar sus fragmentos. El TTL del paquete rearmado se define como el mínimo recibido, una decisión conservadora porque los fragmentos pueden recorrer caminos con distinta cantidad de saltos. La comparación binaria con el original se realiza sin tránsito; durante el tránsito el TTL cambia legítimamente.

### Interfaz y verificación

Conservamos los primeros seis argumentos del emisor de actividad 5 y agregamos ID obligatorio y tamaño total opcional. Se leen con sys.argv para mantener una interfaz sencilla, repetible desde la terminal y consistente con la actividad anterior, sin argparse. Pedir el ID explícitamente evita generación aleatoria y permite identificar cada envío en las trazas. El tamaño total opcional rellena los datos con puntos para reproducir exactamente el experimento de 150 bytes.

Usamos el emisor binario para realizar los envíos. Aunque un apartado menciona netcat, otro pide el script de forwarding y el protocolo requiere campos binarios: escribir IP, puerto y mensaje como texto no construye ese header. Tanto el router como el emisor usan únicamente socket y sys. No se utiliza secrets.

Separamos las pruebas de funciones de las pruebas con procesos UDP: las primeras permiten comprobar límites de tamaño y fragmentos faltantes de forma controlada; las segundas verifican que el ciclo de recepción, las rutas y el envío realmente se integran. Para los datagramas grandes usamos TTL 30 y comprobamos el agotamiento en casos separados, de modo que un descarte por TTL no oculte el funcionamiento de la fragmentación.

## Pruebas y observaciones

Se ejecutaron 18 pruebas con resultado OK: 15 pruebas de funciones, una de recepción UDP con un proceso router real y dos de la interfaz del emisor. Cubren ida y vuelta de bytes construidos manualmente, validación de paquetes, límites de MTU, refragmentación, reensamblaje de un datagrama refragmentado, fragmentos faltantes o duplicados e IDs intercalados, solapamientos, payload vacío, TTL diferentes y selección de rutas con MTU. Se verificó round-robin con tres alternativas, turnos compartidos por área e independencia entre áreas. Se agregaron casos CIDR /0, /8, /16, /24, /31 y /32, direcciones sin prefijo, entradas inválidas y redes equivalentes escritas con distintos bits de host: estas últimas deben compartir el turno de round-robin. El payload binario y UTF-8 se maneja en bytes; la decodificación se realiza al completar el mensaje.

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

Cambiar el router de entrada modifica el primer MTU y el estado de round-robin que se encuentra. En ID 1002, desde R2, el primer enlace elegido tuvo MTU 80 y produjo paquetes de 80, 80, 30 bytes (offsets 0, 60, 120). Los fragmentos pueden seguir rutas diferentes, acumular TTL distintos y llegar desordenados; el reensamblaje depende de ID, offset y FLAG, no del orden de llegada.

Se verificó además recepción directa en R5 de un datagrama fragmentado en orden y de otros dos IDs con fragmentos en orden inverso e intercalados. Los tres mensajes se imprimieron completos. En test_reception.py se comprobó que el router no imprime mientras falta un fragmento, incluso si ya llegó el último con FLAG 0. Completar uno de dos IDs intercalados no provoca la impresión del otro. También se verificó un duplicado mientras el datagrama estaba pendiente y un mensaje UTF-8 con caracteres divididos entre fragmentos.

Por último se ejecutó enviar.py por consola con los argumentos de actividad 5 seguidos de ID 4000 y tamaño total 150. El emisor produjo un paquete de 150 bytes y R5 recibió los 130 bytes de datos completos. Así se verificaron tanto las funciones como el script de envío pedido en el enunciado.

Las pruebas del emisor verificaron que el destino del header se conserva aunque el paquete se envíe a un puerto de entrada diferente, que el tamaño se calcula en bytes UTF-8 y que el ID indicado por el usuario se conserva. También se rechazaron la ausencia del ID, TTL fuera de 1-255, IDs negativos o fuera de 32 bits, argumentos numéricos inválidos, una dirección IPv4 inválida y tamaños totales incompatibles con el mensaje o el máximo de UDP IPv4. La prueba del header verifica sus campos contra bytes construidos manualmente, incluidos los valores máximos representables de IP, puerto, TTL, ID y offset.

## Reproducción y límites

Desde la carpeta del repositorio, con Python 3 y sin dependencias externas:

```powershell
python -m unittest -v
python prueba_red.py
```

El primer comando ejecuta las 18 pruebas. El segundo levanta sus cinco routers, realiza los envíos, comprueba MTU y entrega, escribe evidencia-red.txt y cierra los procesos. Los puertos 28881-28885 deben estar disponibles. El orden global de las líneas de diagnóstico y algunos recorridos pueden variar entre ejecuciones porque los routers son procesos concurrentes; la tabla anterior corresponde a la evidencia incluida.

Para ejecutar manualmente la red, abrir cinco terminales en la carpeta del repositorio y ejecutar una línea en cada una. Cada línea inicia un proceso independiente:

```powershell
python router.py 127.0.0.1 8881 rutas_R1_v3_mtu.txt
python router.py 127.0.0.1 8882 rutas_R2_v3_mtu.txt
python router.py 127.0.0.1 8883 rutas_R3_v3_mtu.txt
python router.py 127.0.0.1 8884 rutas_R4_v3_mtu.txt
python router.py 127.0.0.1 8885 rutas_R5_v3_mtu.txt
```

Los argumentos son IP donde escucha el router, puerto y archivo de rutas. Cada línea de ese archivo contiene `red puerto_inicial puerto_final IP_siguiente puerto_siguiente MTU`. Los archivos deben mantenerse junto al código al usar estos comandos. Los puertos 8881-8885 deben estar disponibles y los procesos se pueden detener con Ctrl+C.

Con los cinco routers esperando paquetes, desde una sexta terminal ejecutar el emisor con esta interfaz:

```text
python enviar.py IP_final puerto_final "mensaje" IP_envio puerto_envio TTL ID [tamano_total]
```

Por ejemplo:

```powershell
python enviar.py 127.0.0.1 8885 'hola!' 127.0.0.1 8881 10 347
python enviar.py 127.0.0.1 8885 'mensaje de prueba' 127.0.0.1 8881 30 348 150
```

El primer comando construye un datagrama de 25 bytes; el segundo completa con puntos un payload de 130 bytes para alcanzar 150 bytes totales. Ambos entran por R1 y tienen como destino final R5.

UDP no garantiza entrega. No se incorporaron retransmisiones ni expiración de listas incompletas; un fragmento perdido deja el datagrama pendiente. Los IDs deben distinguir datagramas simultáneos. Duplicados idénticos se toleran mientras el datagrama está pendiente; no se suprimen repeticiones posteriores a una entrega completa. Las observaciones corresponden a ejecución local, sin implicar publicación en GitHub ni entrega en U-Cursos.
