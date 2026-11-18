"""Registra los eventos Red y Consola del navegador en una corrida funcional."""
from contextlib import ExitStack
import sys

from playwright.sync_api import sync_playwright, expect

from probar import PORTS, ROOT, json_get, process, ready, require_free_port, url, write_json

REJECTED_PORT = 8199


def browser_check(framework, api_port, output, channel):
    _, frontend_port = PORTS[framework]
    expected_origin = url(frontend_port)
    frontend = ROOT / framework / "frontend"
    evidence = output / "cors"
    evidence.mkdir()
    outcomes = {}
    with ExitStack() as stack:
        for port in (frontend_port, REJECTED_PORT):
            require_free_port(port)
            command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
            log = evidence / f"frontend-{port}.log"
            proc = stack.enter_context(process(command, frontend, log))
            ready(port, proc, log, "/")
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch(channel=channel if channel != "chromium" else None)
        stack.callback(browser.close)
        outcomes["navegador"] = browser.version
        for origin_port, allowed in ((frontend_port, True), (REJECTED_PORT, False)):
            label = "permitido" if allowed else "rechazado"
            context = browser.new_context()
            try:
                page = context.new_page()
                cdp = context.new_cdp_session(page)
                network = []
                console = []
                requests = {}

                def started(event):
                    request = event["request"]
                    if request["url"] == url(api_port, "/registros"):
                        requests[event["requestId"]] = request["method"]
                        network.append({"evento": "solicitud", "metodo": request["method"],
                                        "url": request["url"], "encabezados": request["headers"]})

                def received(event):
                    if event["requestId"] in requests:
                        response = event["response"]
                        network.append({"evento": "respuesta", "metodo": requests[event["requestId"]],
                                        "estado": response["status"], "encabezados": response["headers"]})

                def extra(event):
                    if event["requestId"] in requests:
                        network.append({"evento": "encabezados de respuesta", "metodo": requests[event["requestId"]],
                                        "estado": event["statusCode"], "encabezados": event["headers"]})

                def failed(event):
                    if event["requestId"] in requests:
                        network.append({"evento": "bloqueo", "metodo": requests[event["requestId"]],
                                        "error": event["errorText"], "cors": event.get("corsErrorStatus")})

                cdp.on("Network.requestWillBeSent", started)
                cdp.on("Network.responseReceived", received)
                cdp.on("Network.responseReceivedExtraInfo", extra)
                cdp.on("Network.loadingFailed", failed)
                cdp.send("Network.enable")
                page.on("console", lambda message: console.append({"tipo": message.type, "texto": message.text}))
                page.goto(url(origin_port))
                page.get_by_role("button", name="Crear registro").click()
                expect(page.locator("#resultado")).to_have_text("El DNI debe tener exactamente ocho dígitos.")
                page.locator("#dni").fill("94000000")
                page.locator("#nombres").fill("Usuario Navegador")
                page.locator("#apellidos").fill("Apellido Prueba")
                page.locator("#imagen").set_input_files(str(ROOT / "pruebas/datos/imagenes/usuario_0001.png"))
                page.get_by_role("button", name="Crear registro").click()
                result = page.locator("#resultado")
                expect(result).to_have_attribute("data-estado", "ok" if allowed else "error")
                if allowed:
                    expect(page.get_by_role("link", name="Ver imagen")).to_be_visible()
                else:
                    assert any("CORS" in event["texto"] for event in console), console

                page.screenshot(path=evidence / f"{label}.png")
                write_json(evidence / f"{label}-red.json", network)
                write_json(evidence / f"{label}-consola.json", console)
                preflight = next(
                    (event for event in network if event.get("metodo") == "OPTIONS"
                     and event.get("estado") == (204 if allowed else 403)), None)
                assert preflight, (label, network)
                headers = {key.lower(): value for key, value in preflight["encabezados"].items()}
                if allowed:
                    assert headers.get("access-control-allow-origin") == expected_origin, headers
                    assert "x-registro-cliente" in headers["access-control-allow-headers"].lower(), headers
                    assert any(event.get("metodo") == "POST" and event.get("estado") == 201
                               for event in network), network
                else:
                    assert "access-control-allow-origin" not in headers, headers
                    assert any(event["evento"] == "bloqueo" and event.get("metodo") == "POST"
                               for event in network), network
                outcomes[label] = {"origen": url(origin_port), "preflight": preflight["estado"],
                                   "access_control_allow_origin": headers.get("access-control-allow-origin"),
                                   "mensaje": result.inner_text()}
            finally:
                context.close()
    cors = json_get(api_port, "/metrics")["cors"]
    assert cors == {"options": 2, "permitidos": 2, "rechazados": 1}, cors
    outcomes["contadores"] = cors
    write_json(evidence / "resumen.json", outcomes)
    return outcomes
