# FastAPI

Desde `fastapi/backend`, con las dependencias instaladas según el README principal.

```powershell
..\..\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Uvicorn sirve FastAPI con Starlette y python-multipart para los formularios. Pillow decodifica la imagen y `sqlite3` de Python guarda la fila. La decodificación y persistencia se ejecutan en el grupo de hilos de Starlette. Las transacciones comparten una conexión SQLite dentro de un bloqueo para serializar las escrituras. `REGISTRO_DATA_DIR` puede indicar un directorio de datos alternativo. El valor predeterminado es `fastapi/backend/data`.
