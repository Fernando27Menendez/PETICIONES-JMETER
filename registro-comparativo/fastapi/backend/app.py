import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import ClientDisconnect
from starlette.concurrency import run_in_threadpool

LIMIT = 1_000_000
ORIGIN = "http://127.0.0.1:8100"
DATA = Path(os.getenv("REGISTRO_DATA_DIR", Path(__file__).parent / "data"))
IMAGES = DATA / "imagenes"
IMAGES.mkdir(parents=True, exist_ok=True)
SCHEMA = """
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY, dni TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL, apellidos TEXT NOT NULL, imagen TEXT NOT NULL UNIQUE
)
"""
db = sqlite3.connect(DATA / "registros.sqlite3", check_same_thread=False)
db_lock = Lock()
with db:
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(SCHEMA)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
requests = {}
cors = {"options": 0, "permitidos": 0, "rechazados": 0}
errors = 0
logger = logging.getLogger("uvicorn.error")


def error(status, message):
    return JSONResponse({"error": message}, status_code=status)


def route_for(path):
    if path in ("/health", "/registros", "/registros/conteo", "/metrics"):
        return path
    return "/imagenes/:nombre" if path.startswith("/imagenes/") else "otra"


@app.middleware("http")
async def observability(request: Request, call_next):
    global errors
    start = perf_counter()
    method = request.method
    origin = request.headers.get("origin")
    path = route_for(request.url.path)
    requested_method = request.headers.get("access-control-request-method")
    requested_headers = set(request.headers.get("access-control-request-headers", "").lower().replace(" ", "").split(","))
    allowed = origin == ORIGIN
    if method == "OPTIONS" and origin is not None:
        allowed = allowed and requested_method in {"GET", "POST"} and requested_headers <= {"", "content-type", "x-registro-cliente"}
    try:
        if origin is not None and not allowed:
            response = error(403, "Origen CORS rechazado.")
        elif method == "OPTIONS" and origin is not None:
            response = Response(status_code=204, headers={
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "Content-Type, X-Registro-Cliente",
            })
        else:
            response = await call_next(request)
    except Exception:
        logger.exception("Error de solicitud")
        response = error(500, "No se pudo procesar la solicitud.")
    response.headers.append("Vary", "Origin")
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = ORIGIN
    status = response.status_code
    key = (method, path, status)
    entry = requests.setdefault(key, {"metodo": method, "ruta": path, "estado": status,
                                       "total": 0, "duracion_ms_suma": 0.0})
    entry["total"] += 1
    entry["duracion_ms_suma"] += (perf_counter() - start) * 1000
    errors += int(status >= 400)
    cors["options"] += int(method == "OPTIONS")
    if origin is not None:
        cors["permitidos" if allowed else "rechazados"] += 1
        logger.info("CORS %s", json.dumps({"origen": origin, "metodo": method,
                    "resultado": "permitido" if allowed else "rechazado", "estado": status}))
    return response


@app.exception_handler(HTTPException)
async def http_error(_request, exc):
    return error(exc.status_code, exc.detail)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return {"solicitudes": list(requests.values()), "errores_total": errors, "cors": cors}


@app.get("/registros/conteo")
def count():
    with db_lock:
        return {"total": db.execute("SELECT COUNT(*) FROM registros").fetchone()[0]}


@app.get("/imagenes/{nombre}")
def image(nombre: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg)", nombre) or not (IMAGES / nombre).is_file():
        return error(404, "Imagen no encontrada.")
    return FileResponse(IMAGES / nombre, headers={"X-Content-Type-Options": "nosniff"})


def save(dni, names, surnames, payload):
    try:
        with Image.open(io.BytesIO(payload), formats=("PNG", "JPEG")) as picture:
            picture.load()
            extension = "png" if picture.format == "PNG" else "jpg"
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return error(415, "La imagen debe ser un PNG o JPEG válido.")
    filename = f"{uuid4().hex}.{extension}"
    image_path = IMAGES / filename
    written = False
    try:
        with db_lock, db:
            cursor = db.execute(
                "INSERT INTO registros(dni,nombres,apellidos,imagen) VALUES(?,?,?,?)",
                (dni, names, surnames, filename),
            )
            with image_path.open("xb") as stream:
                written = True
                stream.write(payload)
        return JSONResponse({"id": cursor.lastrowid, "dni": dni, "nombres": names,
                             "apellidos": surnames, "imagen": f"/imagenes/{filename}"},
                            status_code=201)
    except BaseException as exc:
        if written:
            image_path.unlink(missing_ok=True)
        if isinstance(exc, sqlite3.IntegrityError) and exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE" and "registros.dni" in str(exc):
            return error(409, "El DNI ya está registrado.")
        raise


@app.post("/registros", status_code=201)
async def register(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        return error(400, "Se requiere multipart/form-data.")
    try:
        async with request.form(max_files=1, max_fields=3, max_part_size=LIMIT) as form:
            dni = form.get("dni")
            names = form.get("nombres")
            surnames = form.get("apellidos")
            uploaded = form.get("imagen")
            if not isinstance(dni, str) or not re.fullmatch(r"[0-9]{8}", dni):
                return error(400, "El DNI debe tener exactamente ocho dígitos.")
            if not isinstance(names, str) or not names.strip():
                return error(400, "Los nombres son obligatorios.")
            if not isinstance(surnames, str) or not surnames.strip():
                return error(400, "Los apellidos son obligatorios.")
            if not isinstance(uploaded, UploadFile) or not uploaded.filename:
                return error(400, "La imagen es obligatoria.")
            payload = await uploaded.read(LIMIT)
            if len(payload) >= LIMIT:
                return error(413, "La imagen debe pesar menos de 1 000 000 bytes.")
            return await run_in_threadpool(save, dni, names.strip(), surnames.strip(), payload)
    except (HTTPException, MultiPartException, ClientDisconnect, ValueError):
        return error(400, "Formulario multipart inválido.")
