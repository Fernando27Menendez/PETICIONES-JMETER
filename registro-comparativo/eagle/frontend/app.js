const api = document.querySelector('meta[name=registro-api]').content;
const form = document.querySelector('form');
const result = document.querySelector('#resultado');
const button = form.querySelector('button');

function show(message, state) {
  result.textContent = message;
  result.dataset.estado = state;
}

function fieldError(name, message) {
  const field = form.elements[name];
  field.setAttribute('aria-invalid', 'true');
  field.focus();
  show(message, 'error');
}

form.addEventListener('input', event => event.target.removeAttribute('aria-invalid'));
form.addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData(form);
  if (!/^[0-9]{8}$/.test(data.get('dni'))) {
    return fieldError('dni', 'El DNI debe tener exactamente ocho dígitos.');
  }
  for (const name of ['nombres', 'apellidos']) {
    const value = data.get(name).trim();
    if (!value) return fieldError(name, `Los ${name} son obligatorios.`);
    data.set(name, value);
  }
  const file = data.get('imagen');
  if (!file.name) return fieldError('imagen', 'La imagen es obligatoria.');
  if (file.size >= 1_000_000) return fieldError('imagen', 'La imagen debe pesar menos de 1 000 000 bytes.');
  if (!['image/png', 'image/jpeg'].includes(file.type)) {
    return fieldError('imagen', 'La imagen debe ser un PNG o JPEG válido.');
  }

  button.disabled = true;
  show('Guardando registro…', '');
  try {
    const response = await fetch(api + '/registros', {
      method: 'POST',
      headers: { 'X-Registro-Cliente': 'formulario' },
      body: data,
    });
    const json = await response.json();
    if (response.status !== 201) return show(json.error, 'error');
    form.reset();
    show(`Registro ${json.id} guardado. `, 'ok');
    const link = document.createElement('a');
    link.href = new URL(json.imagen, api);
    link.textContent = 'Ver imagen';
    result.append(link);
  } catch {
    show('No se pudo conectar con la API. Verifica el servidor y el origen del formulario.', 'error');
  } finally {
    button.disabled = false;
  }
});
