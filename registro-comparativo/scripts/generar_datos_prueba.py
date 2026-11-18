"""Crea y verifica un conjunto determinista de PNG RGB y su CSV."""
import argparse
import csv
import hashlib
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "pruebas" / "datos"
IMAGES = DATA / "imagenes"
CSV = DATA / "usuarios.csv"
FIELDS = ("dni", "nombres", "apellidos", "imagen_path")
SIGNATURE = b"\x89PNG\r\n\x1a\n"
SIZE = 48


def chunk(name, payload):
    return (struct.pack(">I", len(payload)) + name + payload
            + struct.pack(">I", zlib.crc32(name + payload)))


def png(index):
    rows = bytearray()
    for y in range(SIZE):
        rows.append(0)
        for x in range(SIZE):
            rows.extend(((index + x * 5) % 256, (index // 256 * 53 + y * 5) % 256,
                         ((x // 8 ^ y // 8) * 32 + index) % 256))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def verify_png(data):
    if not data.startswith(SIGNATURE) or not 0 < len(data) < 1_000_000:
        raise ValueError("Firma o tamaño PNG inválido")
    offset = len(SIGNATURE)
    parts = {}
    while offset < len(data):
        size, name = struct.unpack_from(">I4s", data, offset)
        end = offset + 8 + size
        payload = data[offset + 8:end]
        if name in parts or zlib.crc32(name + payload) != struct.unpack_from(">I", data, end)[0]:
            raise ValueError("Bloque PNG inválido")
        parts[name] = payload
        offset = end + 4
    if list(parts) != [b"IHDR", b"IDAT", b"IEND"] or parts[b"IEND"]:
        raise ValueError("Estructura PNG inválida")
    if struct.unpack(">IIBBBBB", parts[b"IHDR"]) != (SIZE, SIZE, 8, 2, 0, 0, 0):
        raise ValueError("Cabecera PNG inválida")
    pixels = zlib.decompress(parts[b"IDAT"])
    stride = SIZE * 3 + 1
    if len(pixels) != SIZE * stride or any(pixels[::stride]):
        raise ValueError("Píxeles PNG inválidos")


def generate(count):
    IMAGES.mkdir(parents=True, exist_ok=True)
    expected = set()
    with CSV.with_suffix(".tmp").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for index in range(1, count + 1):
            tag = f"{index:04d}"
            path = IMAGES / f"usuario_{tag}.png"
            expected.add(path)
            path.write_bytes(png(index))
            writer.writerow((str(89_999_999 + index), f"Usuario Prueba {tag}",
                             f"Apellido Prueba {tag}", path.relative_to(ROOT).as_posix()))
    for path in IMAGES.glob("usuario_*.png"):
        if path not in expected and re.fullmatch(r"usuario_[0-9]+\.png", path.name):
            path.unlink()
    CSV.with_suffix(".tmp").replace(CSV)


def verify(count):
    with CSV.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Encabezado CSV inválido")
        rows = list(reader)
    if len(rows) != count:
        raise ValueError(f"Se esperaban {count} filas, llegaron {len(rows)}")
    hashes = set()
    for index, row in enumerate(rows, 1):
        tag = f"{index:04d}"
        expected = (str(89_999_999 + index), f"Usuario Prueba {tag}", f"Apellido Prueba {tag}",
                    f"pruebas/datos/imagenes/usuario_{tag}.png")
        if tuple(row[field] for field in FIELDS) != expected:
            raise ValueError(f"Fila {index} inválida")
        data = (ROOT / row["imagen_path"]).read_bytes()
        verify_png(data)
        hashes.add(hashlib.sha256(data).digest())
    if len(hashes) != count:
        raise ValueError("Hay imágenes repetidas")
    print(f"{count} DNI únicos y {count} PNG distintos verificados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cantidad", type=int, default=1000)
    parser.add_argument("--verificar", action="store_true")
    options = parser.parse_args()
    if not 1 <= options.cantidad <= 65_536:
        parser.error("--cantidad debe estar entre 1 y 65536")
    if not options.verificar:
        generate(options.cantidad)
    verify(options.cantidad)
