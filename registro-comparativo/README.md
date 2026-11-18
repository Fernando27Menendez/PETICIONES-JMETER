# Registro comparativo

El mismo formulario guarda un DNI ficticio, nombres, apellidos y una imagen en tres aplicaciones locales independientes. La comparación envía el mismo CSV y las mismas imágenes con Apache JMeter. Consulta el [informe de resultados](pruebas/resultados/INFORME.md) para ver las mediciones.

## Instalación

Desde esta carpeta, con Python 3.12, Node.js 24, Go 1.23 o posterior y Apache JMeter 5.6.3 con Java. Los comandos son para PowerShell. En Linux o macOS usa `.venv/bin/python`, `npm` y un binario Go sin la extensión `.exe`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r fastapi/backend/requirements.txt -r pruebas/requirements.txt
npm.cmd --prefix express/backend ci
Push-Location eagle/backend
go build -o bin/eagle.exe ./cmd/server
Pop-Location
.\.venv\Scripts\python.exe scripts/generar_datos_prueba.py
```

Si `python` apunta a una instalación sin pip, usa la ruta de Python 3.12 para crear el entorno virtual. El generador usa únicamente la biblioteca estándar. Genera DNI del 90000000 al 90000999, un PNG RGB de 48 × 48 por DNI y un CSV UTF-8 con rutas relativas. Valida el encabezado, los registros, CRC y píxeles de cada PNG, tamaño y unicidad de las imágenes. Volver a ejecutarlo reconstruye el conjunto. Usa `--verificar` para solo validarlo o `--cantidad N` para cambiar la cantidad de entradas.

## Aplicaciones

| Implementación | API | Formulario autorizado | Instrucciones |
| --- | --- | --- | --- |
| FastAPI | http://127.0.0.1:8000 | http://127.0.0.1:8100 | [FastAPI](fastapi/backend/README.md) |
| Express | http://127.0.0.1:3000 | http://127.0.0.1:8101 | [Express](express/backend/README.md) |
| Eagle | http://127.0.0.1:8080 | http://127.0.0.1:8102 | [Eagle](eagle/backend/README.md) |

Ejecuta el servidor API indicado en su enlace. En otra terminal, desde esta carpeta, sirve su frontend. Sustituye `8100` y `fastapi` por los del framework que quieras probar.

```powershell
.\.venv\Scripts\python.exe -m http.server 8100 --bind 127.0.0.1 --directory fastapi/frontend
```

Abre el formulario con la dirección exacta de la tabla. Para provocar un rechazo, sirve esa misma carpeta en el puerto 8199 y repite el envío desde `http://127.0.0.1:8199`. En las herramientas del navegador abre Red y Consola. Filtra por `registros` y busca el `OPTIONS` generado por la cabecera `X-Registro-Cliente`. El origen permitido recibe 204 con `Access-Control-Allow-Origin`, métodos y encabezados permitidos, seguido del POST. El otro recibe 403 sin ese encabezado y el navegador bloquea el POST. El ensayo automatizado conserva las cabeceras, estados, eventos de consola y capturas.

## Contrato HTTP

- `GET /health` devuelve `{"status":"ok"}`.
- `POST /registros` recibe `multipart/form-data` con `dni` de ocho dígitos ASCII, `nombres` y `apellidos` obligatorios tras quitar espacios extremos, e `imagen` PNG o JPEG de menos de 1 000 000 bytes. La API decodifica el archivo para verificar su contenido.
- El 201 incluye `id`, `dni`, `nombres`, `apellidos` e `imagen`. El último campo contiene una ruta accesible en esa API, como `/imagenes/…png`.
- Error uniforme `{"error":"mensaje"}`. Estados 400 para formulario inválido, 409 para DNI repetido, 413 para archivo de al menos 1 000 000 bytes, 415 para imagen inválida y 403 para origen rechazado.
- `GET /registros/conteo` devuelve `{"total":N}`. Cada API usa su propia base SQLite en modo WAL con una restricción UNIQUE sobre el DNI. La fila se confirma después de completar el archivo con un nombre UUID. Si la operación reporta un fallo, se revierte la fila y se intenta eliminar el archivo parcial. Una terminación abrupta del proceso o del equipo entre la escritura del archivo y el commit puede dejar un archivo huérfano.
- `GET /metrics` devuelve `solicitudes` agrupadas por `metodo`, `ruta` y `estado`. Cada grupo contiene `total` y `duracion_ms_suma`. `errores_total` cuenta estados a partir de 400. `cors.options` cuenta todos los OPTIONS y `cors.permitidos` y `cors.rechazados` cuentan las solicitudes con Origin según su resultado. La ruta de imagen se agrupa como `/imagenes/:nombre`. Las métricas se reinician junto con el proceso y la respuesta incluye las observaciones ya registradas. El momento de cierre de la medición depende de cada servidor HTTP. Las solicitudes que llevan Origin también producen una línea `CORS` con origen, método, resultado y estado.

## Prueba manual y carga

Con una API iniciada y datos de prueba generados, ejecuta desde la raíz. Cambia el puerto para las otras API. Usa un almacenamiento vacío para la primera prueba.

```powershell
curl.exe -i -F "dni=90000000" -F "nombres=Usuario Prueba 0001" -F "apellidos=Apellido Prueba 0001" -F "imagen=@pruebas/datos/imagenes/usuario_0001.png;type=image/png" http://127.0.0.1:8000/registros
curl.exe http://127.0.0.1:8000/registros/conteo
```

Comprueba 201, el conteo de 1 y descarga la ruta devuelta en `imagen`. El ejecutor repite este control y prueba 400, 409, 413, 415, recuperación ante un fallo de escritura y concurrencia con DNI distintos y repetidos. Ejecuta las pruebas funcionales y de carga con los servidores de la tabla detenidos. Requiere Chrome local para el modo predeterminado. También admite `--navegador msedge` o `--navegador chromium` tras instalar Chromium con `python -m playwright install chromium`.

```powershell
.\.venv\Scripts\python.exe scripts/probar.py --jmeter 'C:\ruta\apache-jmeter-5.6.3\bin\ApacheJMeter.jar'
```

También admite `--solo-funcional`, `--framework fastapi express eagle` y `--hilos 10 50 100`. Ejecuta primero la prueba funcional con otra base y después cada escenario de forma secuencial con un proceso y un directorio de datos nuevo. Cada hilo realiza 10 iteraciones y la subida dura 5 s. Produce 100, 500 y 1000 solicitudes por framework. El ejecutor guarda JTL, panel HTML, comando, métricas, uso de CPU y RSS del proceso servidor cada 250 ms, logs y cotejo de campos e imágenes por fila bajo `pruebas/resultados/<ejecución>/`. El fichero `resumen.json` reúne los escenarios.

Si el ejecutor indica que un puerto está ocupado, pulsa **Ctrl+C** en la terminal del servidor que usa ese puerto y vuelve a ejecutar el comando. Usa `--navegador omitido` si solo quieres ejecutar las pruebas de API y JMeter.

Para ejecutar un escenario directamente, arranca su API con `REGISTRO_DATA_DIR` apuntando a una carpeta nueva y vacía. Corre JMeter desde la raíz con un destino de salida nuevo. El plan usa `root` para resolver el CSV y el archivo de cada fila, y toma del encabezado los nombres de las columnas. Los hilos comparten un solo cursor, sin reciclar filas. Las aserciones nativas de JMeter comprueban el 201, el identificador, la ruta de imagen y los campos enviados.

```powershell
jmeter -n -t pruebas/jmeter/registro.jmx -l pruebas/resultados/fastapi_100.jtl -e -o pruebas/resultados/fastapi_100_html "-Jroot=$($PWD.Path.Replace('\','/'))" -Jhost=127.0.0.1 -Jport=8000 -Jthreads=100 -Jramp=5 -Jloops=10
```

Usa un puerto de la tabla y mantén `threads × loops` dentro del número de entradas. Los tres escenarios representan usuarios virtuales concurrentes con subida gradual.

## Referencias técnicas

- [Eagle v1.11.0 y su estructura](https://github.com/go-eagle/eagle/tree/v1.11.0)
- [FastAPI y multipart](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/)
- [Express y Multer](https://expressjs.com/en/resources/middleware/multer/)
- [JMeter y configuración de componentes](https://jmeter.apache.org/usermanual/component_reference.html)
- [JMeter en modo CLI](https://jmeter.apache.org/usermanual/get-started.html)
- [CORS y preflight](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
