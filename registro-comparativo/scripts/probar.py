"""Ejecuta las pruebas funcionales, CORS en Chromium y los escenarios JMeter."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import csv
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
from statistics import mean
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import psutil
from PIL import Image

from generar_datos_prueba import ROOT, verify

PORTS = {"fastapi": (8000, 8100), "express": (3000, 8101), "eagle": (8080, 8102)}
RAISE_SECONDS = 5
ITERATIONS = 10
SAMPLE_SECONDS = 0.25
PLAN = ROOT / "pruebas/jmeter/registro.jmx"
RESULTS = ROOT / "pruebas/resultados"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def url(port, path=""):
    return f"http://127.0.0.1:{port}{path}"


def http(port, path, *, data=None, headers=None, method=None):
    request = Request(url(port, path), data=data, headers=headers or {}, method=method)
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, dict(response.headers), response.read()


def json_get(port, path):
    code, _, data = http(port, path)
    assert code == 200, (path, code, data)
    return json.loads(data)


def multipart(port, dni, payload, names=" Usuario Prueba ", surnames=" Apellido Prueba ", kind="image/png"):
    boundary = uuid4().hex
    segments = []
    for name, value in (("dni", dni), ("nombres", names), ("apellidos", surnames)):
        segments.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                         f"\r\n\r\n{value}\r\n").encode())
    segments.append((f'--{boundary}\r\nContent-Disposition: form-data; name="imagen"; filename="prueba.img"'
                     f"\r\nContent-Type: {kind}\r\n\r\n").encode())
    segments.extend((payload, f"\r\n--{boundary}--\r\n".encode()))
    code, _, body = http(port, "/registros", data=b"".join(segments),
                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return code, json.loads(body)


@contextmanager
def process(command, cwd, log, environment=None):
    with log.open("wb") as stream:
        proc = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        try:
            yield proc
        finally:
            if proc.poll() is None:
                children = psutil.Process(proc.pid).children(recursive=True)
                for child in reversed(children):
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def listeners(port):
    return {
        connection.pid
        for connection in psutil.net_connections(kind="tcp4")
        if connection.status == psutil.CONN_LISTEN
        and connection.laddr.port == port
        and connection.laddr.ip in {"127.0.0.1", "0.0.0.0"}
    }


def port_in_use(port):
    return RuntimeError(
        f"El puerto {port} está ocupado. Detén el servidor que lo usa con Ctrl+C "
        "en su terminal y vuelve a ejecutar la prueba."
    )


def require_free_port(port):
    if listeners(port):
        raise port_in_use(port)


def ready(port, proc, log, path="/health"):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        bound = listeners(port)
        if proc.poll() is not None:
            if bound:
                raise port_in_use(port)
            break
        if bound:
            try:
                owned = {proc.pid, *(child.pid for child in psutil.Process(proc.pid).children(recursive=True))}
            except psutil.NoSuchProcess:
                break
            if not bound <= owned:
                raise port_in_use(port)
            try:
                if http(port, path)[0] == 200:
                    return
            except (URLError, TimeoutError):
                pass
        time.sleep(0.15)
    raise RuntimeError(f"No se pudo iniciar el servidor en {url(port, path)}. Revisa {log}")


@contextmanager
def server(framework, output, eagle_bin):
    port, _ = PORTS[framework]
    require_free_port(port)
    output.mkdir(parents=True)
    data = output / "data"
    log = output / "servidor.log"
    env = {**os.environ, "REGISTRO_DATA_DIR": str(data), "PORT": str(port)}
    command = {
        "fastapi": [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                    "--port", str(port), "--workers", "1", "--no-access-log"],
        "express": ["node", "app.js"],
        "eagle": [str(eagle_bin)],
    }[framework]
    with process(command, ROOT / framework / "backend", log, env) as proc:
        ready(port, proc, log)
        if not (data / "imagenes").is_dir() or not (data / "registros.sqlite3").is_file():
            raise RuntimeError(f"El servidor no inicializó el almacenamiento de esta prueba. Revisa {log}")
        assert json_get(port, "/registros/conteo")["total"] == 0
        yield port, proc, data


def check_storage(data, expected=None):
    with closing(sqlite3.connect(data / "registros.sqlite3")) as connection:
        records = connection.execute("SELECT dni,nombres,apellidos,imagen FROM registros").fetchall()
    paths = {p.name for p in (data / "imagenes").iterdir()}
    references = {row[3] for row in records}
    valid = 0
    mismatched = []
    for dni, names, surnames, filename in records:
        path = data / "imagenes" / filename
        try:
            with Image.open(path, formats=("PNG", "JPEG")) as picture:
                picture.load()
            if path.stat().st_size < 1_000_000:
                valid += 1
            if expected is not None:
                row = expected[dni]
                if (names, surnames) != (row["nombres"], row["apellidos"]) or path.read_bytes() != (ROOT / row["imagen_path"]).read_bytes():
                    mismatched.append(dni)
        except (OSError, KeyError):
            mismatched.append(dni)
    return {"filas": len(records), "archivos": len(paths), "imagenes_validas": valid,
            "sin_archivo": sorted(references - paths), "huerfanos": sorted(paths - references),
            "datos_distintos": mismatched}


def functional(framework, output, eagle_bin, sample, browser_channel):
    with server(framework, output, eagle_bin) as (port, proc, data):
        status, row = multipart(port, "90000000", sample)
        assert status == 201, (framework, status, row)
        assert (row["dni"], row["nombres"], row["apellidos"]) == ("90000000", "Usuario Prueba", "Apellido Prueba")
        image_code, _, image_data = http(port, row["imagen"])
        assert image_code == 200 and image_data == sample
        assert json_get(port, "/registros/conteo")["total"] == 1
        outcomes = {"manual": {"status": status, "respuesta": row, "imagen_http": image_code, "filas": 1}}
        cases = {
            "duplicado": ("90000000", sample, " Usuario ", 409),
            "limite_exacto": ("91000000", sample.ljust(1_000_000, b"\0"), " Usuario ", 413),
            "sobre_limite": ("91000000", sample.ljust(1_000_001, b"\0"), " Usuario ", 413),
            "formato_falso": ("91000000", b"GIF89a no es PNG", " Usuario ", 415),
            "png_truncado": ("91000000", sample[:32], " Usuario ", 415),
            "dni_invalido": ("1234567", sample, " Usuario ", 400),
            "nombres_vacios": ("91000000", sample, "  ", 400),
        }
        for name, (dni, payload, names, wanted) in cases.items():
            code, body = multipart(port, dni, payload, names)
            assert code == wanted and type(body.get("error")) is str, (framework, name, code, body)
            outcomes[name] = {"status": code, "respuesta": body}

        jpeg = BytesIO()
        with Image.open(BytesIO(sample)) as picture:
            picture.save(jpeg, format="JPEG")
        code, jpeg_row = multipart(port, "91000000", jpeg.getvalue(), kind="application/octet-stream")
        assert code == 201 and jpeg_row["imagen"].endswith(".jpg"), (framework, code, jpeg_row)
        outcomes["jpeg"] = code
        code, limit_row = multipart(port, "91000001", sample.ljust(999_999, b"\0"))
        assert code == 201 and http(port, limit_row["imagen"])[2] == sample.ljust(999_999, b"\0"), (framework, code, limit_row)
        outcomes["justo_bajo_limite"] = code

        # Impide las escrituras en una carpeta exclusiva de esta ejecución.
        images = data / "imagenes"
        saved = data / "imagenes-respaldo"
        images.rename(saved)
        try:
            images.write_text("archivo temporal de prueba", encoding="utf-8")
            code, body = multipart(port, "91000002", sample)
            assert code == 500 and "error" in body, (framework, code, body)
            assert json_get(port, "/registros/conteo")["total"] == 3
            outcomes["fallo_escritura_revertido"] = code
        finally:
            if images.is_file():
                images.unlink()
            saved.rename(images)
        assert multipart(port, "91000002", sample)[0] == 201

        with ThreadPoolExecutor(10) as pool:
            distinct = Counter(pool.map(lambda index: multipart(port, str(92000000 + index), sample)[0], range(20)))
            repeated = Counter(pool.map(lambda _: multipart(port, "93000000", sample)[0], range(10)))
        assert distinct == {201: 20} and repeated == {201: 1, 409: 9}, (framework, distinct, repeated)

        outcomes.update({"concurrentes_distintos": distinct, "concurrentes_mismo_dni": repeated})
        browser_created = False
        if browser_channel != "omitido":
            from probar_cors import browser_check
            outcomes["cors"] = browser_check(framework, port, output, browser_channel)
            browser_created = True

        expected = 25 + browser_created
        assert json_get(port, "/registros/conteo")["total"] == expected
        outcomes["almacenamiento"] = check_storage(data)
        assert all(outcomes["almacenamiento"][key] == expected for key in ("filas", "archivos", "imagenes_validas"))
        outcomes["metricas"] = json_get(port, "/metrics")
        write_json(output / "funcional.json", outcomes)
        return outcomes


def jmeter_command(location):
    if location.suffix == ".jar":
        return ["java", "-jar", str(location)]
    if os.name == "nt" and location.suffix.lower() in {".cmd", ".bat"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(location)]
    return [str(location)]


def load(framework, threads, output, eagle_bin, jmeter, rows):
    with server(framework, output, eagle_bin) as (port, proc, data):
        jtl = output / "muestras.jtl"
        html = output / "html"
        command = jmeter_command(jmeter) + [
            "-n", "-t", str(PLAN), "-l", str(jtl), "-e", "-o", str(html),
            "-j", str(output / "jmeter.log"), "-Jroot=" + ROOT.as_posix(),
            "-Jhost=127.0.0.1", f"-Jport={port}", f"-Jthreads={threads}",
            f"-Jramp={RAISE_SECONDS}", f"-Jloops={ITERATIONS}",
            "-Jjmeter.save.saveservice.assertion_results_failure_message=true",
            "-Jaggregate_rpt_pct1=90", "-Jaggregate_rpt_pct2=95", "-Jaggregate_rpt_pct3=99",
        ]
        write_json(output / "comando.json", command)
        monitored = psutil.Process(proc.pid)
        # On Windows the Python venv launcher delegates to the interpreter.
        if framework == "fastapi" and os.name == "nt":
            children = monitored.children()
            if len(children) == 1:
                monitored = children[0]
        monitored.cpu_percent()
        resources = []
        start = time.monotonic()
        with process(command, ROOT, output / "jmeter-cli.log") as client:
            while True:
                resources.append({"segundo": time.monotonic() - start,
                                  "cpu_pct": monitored.cpu_percent(),
                                  "rss_mib": monitored.memory_info().rss / 1024**2})
                try:
                    exit_code = client.wait(timeout=SAMPLE_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
        cli_seconds = time.monotonic() - start
        with (output / "recursos.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=("segundo", "cpu_pct", "rss_mib"))
            writer.writeheader()
            writer.writerows(resources)
        assert exit_code == 0 and jtl.is_file() and (html / "index.html").is_file(), (
            f"JMeter falló (código {exit_code}). Consulta {output}"
        )

        with jtl.open(newline="", encoding="utf-8") as stream:
            samples = list(csv.DictReader(stream))
        if not samples:
            raise RuntimeError(f"JMeter no produjo muestras. Consulta {output}")
        stats = json.loads((html / "statistics.json").read_text(encoding="utf-8"))["Total"]
        duration_ms = max(int(sample["timeStamp"]) + int(sample["elapsed"]) for sample in samples) - min(
            int(sample["timeStamp"]) for sample in samples)
        codes = Counter(sample["responseCode"] for sample in samples)
        status_201 = codes["201"]
        good = sum(sample["responseCode"] == "201" and sample["success"] == "true" for sample in samples)
        metrics = json_get(port, "/metrics")
        server_post = [entry for entry in metrics["solicitudes"]
                       if entry["metodo"] == "POST" and entry["ruta"] == "/registros"]
        server_codes = {str(entry["estado"]): entry["total"] for entry in server_post}
        server_avg = sum(e["duracion_ms_suma"] for e in server_post) / max(1, sum(server_codes.values()))
        artifacts = check_storage(data, rows)
        total_api = json_get(port, "/registros/conteo")["total"]
        consistent = (total_api == artifacts["filas"] == artifacts["archivos"] ==
                      artifacts["imagenes_validas"] == status_201 == good and
                      not any(artifacts[k] for k in ("sin_archivo", "huerfanos", "datos_distintos")) and
                      codes == server_codes)
        write_json(output / "metricas.json", metrics)
        summary = {
            "framework": framework, "hilos": threads, "subida_s": RAISE_SECONDS, "iteraciones": ITERATIONS,
            "duracion_s": duration_ms / 1000, "cli_s": cli_seconds,
            "previstas": threads * ITERATIONS, "solicitudes": len(samples), "estados": codes,
            "http_201": status_201, "exitos_assertion": good, "errores": len(samples) - good,
            "error_pct": stats["errorPct"], "req_s": stats["throughput"],
            "promedio_ms": stats["meanResTime"], "mediana_ms": stats["medianResTime"], "p95_ms": stats["pct2ResTime"],
            "servidor": server_codes, "servidor_promedio_ms": server_avg, "conteo_api": total_api,
            **artifacts, "consistente": consistent,
            "cpu_media_pct": mean(point["cpu_pct"] for point in resources[1:] or resources),
            "cpu_max_pct": max(point["cpu_pct"] for point in resources),
            "rss_max_mib": max(point["rss_mib"] for point in resources),
            "muestras_sistema": len(resources),
        }
        write_json(output / "resumen.json", summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jmeter", type=Path, help="Ruta a jmeter, jmeter.bat o ApacheJMeter.jar")
    parser.add_argument("--eagle-bin", type=Path, default=ROOT / "eagle/backend/bin" / ("eagle.exe" if os.name == "nt" else "eagle"))
    parser.add_argument("--framework", nargs="+", choices=PORTS, default=list(PORTS))
    parser.add_argument("--hilos", nargs="+", type=int, choices=(10, 50, 100), default=[10, 50, 100])
    parser.add_argument("--navegador", choices=("chrome", "msedge", "chromium", "omitido"), default="chrome")
    parser.add_argument("--solo-funcional", action="store_true")
    parser.add_argument("--cantidad", type=int, default=1000)
    args = parser.parse_args()
    if not args.solo_funcional:
        if args.jmeter is None:
            executable = shutil.which("jmeter")
            if not executable:
                parser.error("Indica --jmeter o agrega JMeter a PATH.")
            args.jmeter = Path(executable)
        args.jmeter = args.jmeter.resolve(strict=True)
        if max(args.hilos) * ITERATIONS > args.cantidad:
            parser.error("El mayor escenario excede los DNI disponibles.")
    if "eagle" in args.framework:
        args.eagle_bin = args.eagle_bin.resolve(strict=True)
    verify(args.cantidad)
    with (ROOT / "pruebas/datos/usuarios.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["dni"]: row for row in csv.DictReader(stream)}
    sample = (ROOT / next(iter(rows.values()))["imagen_path"]).read_bytes()
    run = RESULTS / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    run.mkdir(parents=True)
    print(f"Evidencia en {run}", flush=True)
    metadata = {"equipo": platform.platform(), "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
                "cpu_logicas": psutil.cpu_count(), "ram_gib": psutil.virtual_memory().total / 1024**3,
                "python": platform.python_version(), "sqlite_python": sqlite3.sqlite_version,
                "cliente_servidor_misma_maquina": True, "procesos_por_servidor": 1,
                "intervalo_muestreo_s": SAMPLE_SECONDS, "jmeter": str(args.jmeter) if args.jmeter else None}
    write_json(run / "entorno.json", metadata)
    summaries = []
    for framework in args.framework:
        result = functional(framework, run / (framework + "_funcional"), args.eagle_bin, sample, args.navegador)
        print(f"{framework}: pruebas funcionales correctas, {result['almacenamiento']['filas']} filas.", flush=True)
    if not args.solo_funcional:
        for threads in args.hilos:
            for framework in args.framework:
                summary = load(framework, threads, run / f"{framework}_{threads}", args.eagle_bin, args.jmeter, rows)
                summaries.append(summary)
                write_json(run / "resumen.json", summaries)
                print(f"{framework} {threads} hilos: {summary['http_201']}/{summary['previstas']} respuestas 201, "
                      f"{summary['filas']} filas, {summary['archivos']} archivos.", flush=True)
        if any(not item["consistente"] or item["errores"] or item["solicitudes"] != item["previstas"] for item in summaries):
            sys.exit("La ejecución contiene diferencias. Consulta los resúmenes y las muestras JTL.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
