# Informe de resultados

Ejecución del 17 de noviembre de 2026, hora de Lima. Se realizaron **4800 solicitudes** en nueve escenarios. **4800** pasaron las aserciones de JMeter, con **0 errores**, **4800 filas** y **4800 imágenes válidas** en total.

## Entorno y método

- Windows-10-10.0.19044-SP0, AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD, 12 procesadores lógicos y 7,36 GiB de RAM. JMeter y el servidor se ejecutaron en la misma máquina por loopback. El proyecto, SQLite y las imágenes estaban en la unidad Q.
- FastAPI 0.135.1, Uvicorn 0.41.0, Starlette 1.10.0, python-multipart 0.0.22, Pillow 12.1.1, Python 3.12.10 y SQLite 3.49.1.
- Express 5.2.1, Multer 2.2.0, Sharp 0.34.5 y Node.js 24.18.0 con SQLite 3.53.1.
- Eagle 1.11.0, Gin 1.10.1, Go 1.25.5 y modernc.org/sqlite 1.37.1. El arranque usa el transporte HTTP de Eagle con Gin como manejador. Basta el ejecutable, SQLite y el sistema de archivos.
- JMeter 5.6.3 en modo CLI con Java 27. El archivo local está en `.tooling/apache-jmeter-5.6.3/bin/ApacheJMeter.jar`. [Entorno registrado](20261117-232431-805467/entorno.json).
- Una ejecución por combinación, con un proceso servidor, arranque nuevo, almacenamiento vacío por corrida y escenarios secuenciales. Cada escenario usó 5 s de subida y 10 iteraciones por hilo. Las pruebas funcionales y CORS corrieron con sus propias bases de datos.
- El navegador se cerró antes de la carga. Las aserciones de JMeter verificaron código, campos del CSV, identificador y referencia PNG. Se compararon los estados con `/metrics` y se contrastaron nombres, apellidos y bytes de la imagen con la fila de origen.
- CPU y RSS del proceso servidor con psutil 7.2.2, una muestra aproximadamente cada 250 ms durante la ejecución del CLI, incluida la preparación y generación del panel. El 100 % de CPU equivale a un núcleo lógico ocupado. En FastAPI se midió el intérprete hijo del lanzador de Python de Windows.

El comando comprobado de carga completa, ejecutado desde la raíz, fue:

```powershell
.\.venv\Scripts\python.exe scripts/probar.py --jmeter .tooling/apache-jmeter-5.6.3/bin/ApacheJMeter.jar
```

## Resultados de JMeter

La duración real va desde el inicio de la primera solicitud hasta el fin de la última. Rendimiento, promedio, mediana, p95 y tasa de error proceden del panel de cada corrida.

| Hilos | Framework | Solicitudes | 201 válidos | Duración (s) | Solicitudes/s | Promedio (ms) | Mediana (ms) | p95 (ms) | Error % | Evidencia |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10 | FastAPI | 100 | 100 | 4,738 | 21,11 | 30,95 | 31,00 | 51,60 | 0,00 | [HTML](20261117-232431-805467/fastapi_10/html/index.html) · [JTL](20261117-232431-805467/fastapi_10/muestras.jtl) |
| 10 | Express | 100 | 100 | 4,740 | 21,10 | 29,28 | 22,50 | 55,55 | 0,00 | [HTML](20261117-232431-805467/express_10/html/index.html) · [JTL](20261117-232431-805467/express_10/muestras.jtl) |
| 10 | Eagle | 100 | 100 | 4,728 | 21,15 | 27,79 | 22,00 | 52,85 | 0,00 | [HTML](20261117-232431-805467/eagle_10/html/index.html) · [JTL](20261117-232431-805467/eagle_10/muestras.jtl) |
| 50 | FastAPI | 500 | 500 | 12,585 | 39,73 | 748,81 | 777,00 | 1182,60 | 0,00 | [HTML](20261117-232431-805467/fastapi_50/html/index.html) · [JTL](20261117-232431-805467/fastapi_50/muestras.jtl) |
| 50 | Express | 500 | 500 | 12,986 | 38,50 | 774,85 | 843,50 | 1132,95 | 0,00 | [HTML](20261117-232431-805467/express_50/html/index.html) · [JTL](20261117-232431-805467/express_50/muestras.jtl) |
| 50 | Eagle | 500 | 500 | 12,436 | 40,21 | 701,48 | 431,00 | 2376,45 | 0,00 | [HTML](20261117-232431-805467/eagle_50/html/index.html) · [JTL](20261117-232431-805467/eagle_50/muestras.jtl) |
| 100 | FastAPI | 1000 | 1000 | 25,389 | 39,39 | 1954,51 | 2154,00 | 2631,00 | 0,00 | [HTML](20261117-232431-805467/fastapi_100/html/index.html) · [JTL](20261117-232431-805467/fastapi_100/muestras.jtl) |
| 100 | Express | 1000 | 1000 | 25,508 | 39,20 | 1945,12 | 2149,00 | 2555,00 | 0,00 | [HTML](20261117-232431-805467/express_100/html/index.html) · [JTL](20261117-232431-805467/express_100/muestras.jtl) |
| 100 | Eagle | 1000 | 1000 | 24,859 | 40,23 | 1747,29 | 1111,00 | 5681,55 | 0,00 | [HTML](20261117-232431-805467/eagle_100/html/index.html) · [JTL](20261117-232431-805467/eagle_100/muestras.jtl) |

## Servidor y almacenamiento

| Hilos | Framework | Estados POST en servidor | Duración media servidor (ms) | Filas | Imágenes válidas | CPU media % | CPU pico % | RSS pico (MiB) | Detalles |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10 | FastAPI | 201 × 100 | 28,63 | 100 | 100 | 4,88 | 18,80 | 47,78 | [Detalles](20261117-232431-805467/fastapi_10/resumen.json) |
| 10 | Express | 201 × 100 | 27,43 | 100 | 100 | 4,07 | 35,40 | 67,88 | [Detalles](20261117-232431-805467/express_10/resumen.json) |
| 10 | Eagle | 201 × 100 | 26,03 | 100 | 100 | 3,35 | 23,50 | 22,11 | [Detalles](20261117-232431-805467/eagle_10/resumen.json) |
| 50 | FastAPI | 201 × 500 | 746,84 | 500 | 500 | 12,58 | 41,10 | 55,05 | [Detalles](20261117-232431-805467/fastapi_50/resumen.json) |
| 50 | Express | 201 × 500 | 449,71 | 500 | 500 | 12,86 | 47,00 | 82,90 | [Detalles](20261117-232431-805467/express_50/resumen.json) |
| 50 | Eagle | 201 × 500 | 700,10 | 500 | 500 | 7,85 | 41,30 | 26,57 | [Detalles](20261117-232431-805467/eagle_50/resumen.json) |
| 100 | FastAPI | 201 × 1000 | 1952,58 | 1000 | 1000 | 13,79 | 35,20 | 61,17 | [Detalles](20261117-232431-805467/fastapi_100/resumen.json) |
| 100 | Express | 201 × 1000 | 1158,83 | 1000 | 1000 | 14,09 | 76,70 | 103,92 | [Detalles](20261117-232431-805467/express_100/resumen.json) |
| 100 | Eagle | 201 × 1000 | 1746,09 | 1000 | 1000 | 9,40 | 100,20 | 32,66 | [Detalles](20261117-232431-805467/eagle_100/resumen.json) |

Los conteos de `/registros/conteo`, SQLite y disco coincidieron con las respuestas 201 en los nueve escenarios. Se verificó el contenido de cada archivo persistido y su fila correspondiente. Los archivos `metricas.json`, `recursos.csv` y `servidor.log` están junto a cada panel. [Resumen completo](20261117-232431-805467/resumen.json).

## Pruebas funcionales y CORS

En cada API se validó un primer 201 con su imagen accesible, DNI duplicado 409, archivo de 1 000 000 y 1 000 001 bytes con 413, archivo de 999 999 bytes con 201, PNG truncado y formato ajeno con 415, JPEG válido, DNI inválido y nombres vacíos con 400. El fallo simulado de escritura devolvió 500 y la fila se revirtió. Con 10 hilos se obtuvieron 20 respuestas 201 para 20 DNI distintos. Diez solicitudes con el mismo DNI produjeron un 201 y nueve 409.

Chrome 157.0.8103.79 confirmó los siguientes intercambios. El origen autorizado recibió su valor exacto en `Access-Control-Allow-Origin`. El origen en el puerto 8199 recibió 403 sin ese encabezado y la consola registró el bloqueo. Cada servidor contabilizó 2 OPTIONS, 2 solicitudes con origen permitido y 1 con origen rechazado. Las capturas y logs están junto a la evidencia.

| API | Origen autorizado | Autorizado | Rechazado | Evidencia |
| --- | --- | --- | --- | --- |
| FastAPI | http://127.0.0.1:8100 | 204, luego POST 201 | 403 y POST bloqueado | [Red del permitido](20261117-232431-805467/fastapi_funcional/cors/permitido-red.json) · [Red del rechazo](20261117-232431-805467/fastapi_funcional/cors/rechazado-red.json) · [Consola](20261117-232431-805467/fastapi_funcional/cors/rechazado-consola.json) |
| Express | http://127.0.0.1:8101 | 204, luego POST 201 | 403 y POST bloqueado | [Red del permitido](20261117-232431-805467/express_funcional/cors/permitido-red.json) · [Red del rechazo](20261117-232431-805467/express_funcional/cors/rechazado-red.json) · [Consola](20261117-232431-805467/express_funcional/cors/rechazado-consola.json) |
| Eagle | http://127.0.0.1:8102 | 204, luego POST 201 | 403 y POST bloqueado | [Red del permitido](20261117-232431-805467/eagle_funcional/cors/permitido-red.json) · [Red del rechazo](20261117-232431-805467/eagle_funcional/cors/rechazado-red.json) · [Consola](20261117-232431-805467/eagle_funcional/cors/rechazado-consola.json) |

[Pruebas funcionales de FastAPI](20261117-232431-805467/fastapi_funcional/funcional.json) · [Express](20261117-232431-805467/express_funcional/funcional.json) · [Eagle](20261117-232431-805467/eagle_funcional/funcional.json).

## Comparación y límites

- Con 10 hilos, Eagle obtuvo el mayor rendimiento (21,15 solicitudes/s) y FastAPI registró el p95 más bajo (51,60 ms).
- Con 50 hilos, Eagle obtuvo el mayor rendimiento (40,21 solicitudes/s) y Express registró el p95 más bajo (1132,95 ms).
- Con 100 hilos, Eagle obtuvo el mayor rendimiento (40,23 solicitudes/s) y Express registró el p95 más bajo (2555,00 ms).

Al pasar de 50 a 100 hilos, el rendimiento se mantuvo entre 38,50 y 40,23 solicitudes/s y el p95 aumentó en los tres servidores. Eagle registró el menor RSS pico en cada nivel. Con 100 hilos midió 32,66 MiB, frente a 61,17 MiB de FastAPI y 103,92 MiB de Express.

Los tiempos miden solicitudes con PNG sintéticos de 48 × 48, una transacción SQLite y una escritura de archivo por registro. Los resultados corresponden a una pasada por combinación, con el cliente y el servidor compartiendo CPU, memoria y almacenamiento. La subida de 5 s y los diez envíos por hilo influyen en el promedio y el rendimiento. Cada servidor cierra su medición interna en un punto distinto del envío de la respuesta. Una prueba con imágenes mayores, más repeticiones o un cliente en otra máquina puede producir otro orden.

Durante la puesta a punto, la aserción Groovy falló con Java 27 y se reemplazó por aserciones nativas. Una corrida previa detectó 26 respuestas 500 de FastAPI a 50 hilos por bloqueo de SQLite. Se conservó esa evidencia y se serializaron las escrituras de FastAPI con una conexión compartida antes de repetir los nueve escenarios. También se ajustó el muestreo del PID para medir el intérprete del servidor. [Muestras de la aserción anterior](20261117-231846-100716/fastapi_10/muestras.jtl) · [Log del bloqueo SQLite](20261117-232205-105676/fastapi_50/servidor.log).
