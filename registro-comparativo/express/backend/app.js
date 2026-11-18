import express from 'express';
import multer from 'multer';
import sharp from 'sharp';
import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';
import { closeSync, mkdirSync, openSync, unlinkSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { performance } from 'node:perf_hooks';

const LIMIT = 1_000_000;
const ORIGIN = 'http://127.0.0.1:8101';
const data = resolve(process.env.REGISTRO_DATA_DIR || join(import.meta.dirname, 'data'));
const images = join(data, 'imagenes');
mkdirSync(images, { recursive: true });

const db = new DatabaseSync(join(data, 'registros.sqlite3'));
db.exec(`
  PRAGMA journal_mode=WAL;
  PRAGMA busy_timeout=5000;
  CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY, dni TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL, apellidos TEXT NOT NULL, imagen TEXT NOT NULL UNIQUE
  );
`);
const insert = db.prepare('INSERT INTO registros(dni,nombres,apellidos,imagen) VALUES(?,?,?,?)');
const count = db.prepare('SELECT COUNT(*) AS total FROM registros');

const app = express();
app.disable('x-powered-by');
app.enable('strict routing');
app.enable('case sensitive routing');
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: LIMIT, files: 1, fields: 3, fieldSize: LIMIT },
}).single('imagen');

const requests = new Map();
const cors = { options: 0, permitidos: 0, rechazados: 0 };
let errors = 0;
const routes = new Set(['/health', '/registros', '/registros/conteo', '/metrics']);
const error = (res, status, message) => res.status(status).json({ error: message });

app.use((req, res, next) => {
  const start = performance.now();
  const { method, path } = req;
  const origin = req.get('Origin');
  const route = routes.has(path) ? path : path.startsWith('/imagenes/') ? '/imagenes/:nombre' : 'otra';
  const hasOrigin = origin !== undefined;
  const preflight = method === 'OPTIONS' && hasOrigin;
  const requestedHeaders = (req.get('Access-Control-Request-Headers') || '').toLowerCase().split(',');
  const allowed = origin === ORIGIN && (!preflight ||
    (['GET', 'POST'].includes(req.get('Access-Control-Request-Method')) &&
      requestedHeaders.every(value => ['', 'content-type', 'x-registro-cliente'].includes(value.trim()))));

  res.once('finish', () => {
    const status = res.statusCode;
    const key = `${method} ${route} ${status}`;
    const entry = requests.get(key) || { metodo: method, ruta: route, estado: status, total: 0, duracion_ms_suma: 0 };
    entry.total += 1;
    entry.duracion_ms_suma += performance.now() - start;
    requests.set(key, entry);
    if (status >= 400) errors += 1;
    if (method === 'OPTIONS') cors.options += 1;
    if (hasOrigin) {
      const resultado = allowed ? 'permitido' : 'rechazado';
      cors[allowed ? 'permitidos' : 'rechazados'] += 1;
      console.log('CORS', JSON.stringify({ origen: origin, metodo: method, resultado, estado: status }));
    }
  });

  res.vary('Origin');
  if (hasOrigin && !allowed) return error(res, 403, 'Origen CORS rechazado.');
  if (allowed) res.set('Access-Control-Allow-Origin', ORIGIN);
  if (preflight) {
    return res.set({
      'Access-Control-Allow-Methods': 'GET, POST',
      'Access-Control-Allow-Headers': 'Content-Type, X-Registro-Cliente',
    }).status(204).end();
  }
  next();
});

app.get('/health', (_req, res) => res.json({ status: 'ok' }));
app.get('/metrics', (_req, res) => res.json({ solicitudes: [...requests.values()], errores_total: errors, cors }));
app.get('/registros/conteo', (_req, res) => res.json(count.get()));
app.get('/imagenes/:nombre', (req, res, next) => {
  if (!/^[a-f0-9]{32}\.(png|jpg)$/.test(req.params.nombre)) return error(res, 404, 'Imagen no encontrada.');
  res.set('X-Content-Type-Options', 'nosniff');
  res.sendFile(req.params.nombre, { root: images }, err => {
    if (err?.status === 404) error(res, 404, 'Imagen no encontrada.');
    else if (err) next(err);
  });
});

app.post('/registros', (req, res, next) => {
  if (!req.is('multipart/form-data')) return error(res, 400, 'Se requiere multipart/form-data.');
  upload(req, res, err => {
    if (err?.code === 'LIMIT_FILE_SIZE') return error(res, 413, 'La imagen debe pesar menos de 1 000 000 bytes.');
    if (err) return error(res, 400, 'Formulario multipart inválido.');
    next();
  });
}, async (req, res) => {
  const { dni, nombres, apellidos } = req.body;
  if (typeof dni !== 'string' || !/^[0-9]{8}$/.test(dni)) return error(res, 400, 'El DNI debe tener exactamente ocho dígitos.');
  if (typeof nombres !== 'string' || !nombres.trim()) return error(res, 400, 'Los nombres son obligatorios.');
  if (typeof apellidos !== 'string' || !apellidos.trim()) return error(res, 400, 'Los apellidos son obligatorios.');
  if (!req.file) return error(res, 400, 'La imagen es obligatoria.');
  const { buffer, size } = req.file;
  if (size >= LIMIT) return error(res, 413, 'La imagen debe pesar menos de 1 000 000 bytes.');

  let extension;
  try {
    const picture = sharp(buffer, { failOn: 'warning' });
    const { format } = await picture.metadata();
    if (!['jpeg', 'png'].includes(format)) return error(res, 415, 'La imagen debe ser un PNG o JPEG válido.');
    await picture.raw().toBuffer();
    extension = format === 'png' ? 'png' : 'jpg';
  } catch {
    return error(res, 415, 'La imagen debe ser un PNG o JPEG válido.');
  }

  const filename = `${randomUUID().replaceAll('-', '')}.${extension}`;
  const path = join(images, filename);
  const names = nombres.trim();
  const surnames = apellidos.trim();
  let written = false;
  let id;
  db.exec('BEGIN');
  try {
    id = Number(insert.run(dni, names, surnames, filename).lastInsertRowid);
    const fd = openSync(path, 'wx');
    written = true;
    try {
      writeFileSync(fd, buffer);
    } finally {
      closeSync(fd);
    }
    db.exec('COMMIT');
  } catch (err) {
    try {
      db.exec('ROLLBACK');
    } finally {
      if (written) unlinkSync(path);
    }
    if (err.errcode === 2067 && err.message.includes('registros.dni')) {
      return error(res, 409, 'El DNI ya está registrado.');
    }
    throw err;
  }
  return res.status(201).json({ id, dni, nombres: names, apellidos: surnames, imagen: `/imagenes/${filename}` });
});

app.use((_req, res) => error(res, 404, 'Ruta no encontrada.'));
app.use((err, _req, res, next) => {
  console.error(err);
  if (res.headersSent) return next(err);
  return error(res, 500, 'No se pudo procesar la solicitud.');
});
const port = Number(process.env.PORT || 3000);
app.listen(port, '127.0.0.1', () => console.log(`Express en http://127.0.0.1:${port}`));
