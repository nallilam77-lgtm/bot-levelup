import os
import re
import asyncio
import hmac
from typing import List, Union
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# Sin clave de respaldo en el código: debe configurarse WEBHOOK_SECRET en Railway
# (y la misma clave en RAILWAY_SECRET de Vercel).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
if not WEBHOOK_SECRET:
    print("ERROR: FALTA LA VARIABLE WEBHOOK_SECRET: todas las peticiones protegidas se rechazarán con 503.")

# Un solo canje a la vez: cada canje abre páginas de Chromium y varios a la vez agotaban los
# procesos del contenedor ("BlockingIOError: [Errno 11] Resource temporarily unavailable").
# Si otro canje está en curso se espera hasta ESPERA_TURNO_S; pasado eso se responde 503
# (Vercel lo trata como "no procesado": reintenta o devuelve los pines al inventario).
ESPERA_TURNO_S = 15
turno = asyncio.Semaphore(1)

# Un solo Chromium para todos los canjes (antes se abría uno nuevo, con su Playwright, en cada
# petición). Cada canje usa su propio contexto (cookies limpias) y lo cierra al terminar.
# Se reinicia cada CANJES_POR_NAVEGADOR canjes o si se cae, para no acumular memoria.
CANJES_POR_NAVEGADOR = 30
_playwright = None
_navegador = None
_canjes_con_este_navegador = 0

ARGS_CHROMIUM = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",  # Evita que Railway se quede sin memoria compartida
    "--disable-gpu",            # Ahorra recursos al apagar la aceleración gráfica
    "--disable-blink-features=AutomationControlled",
    "--start-maximized",
]

PIN_VALIDO = re.compile(r"^\S{4,64}$")
ID_VALIDO = re.compile(r"^\d{5,15}$")
MAX_PINES = 10


class NavegadorNoDisponible(Exception):
    """Chromium no pudo abrirse: no se intentó canjear ningún pin."""


def verificar_secreto(x_secret_token: Union[str, None]):
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Bot sin configurar (falta WEBHOOK_SECRET)")
    # compare_digest evita filtrar la clave midiendo tiempos de respuesta
    if not x_secret_token or not hmac.compare_digest(x_secret_token.encode(), WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=401, detail="No autorizado")


class CanjeRequest(BaseModel):
    pin: Union[str, None] = None
    pins: Union[List[str], None] = None
    player_id: str


async def cerrar_navegador():
    global _playwright, _navegador
    try:
        if _navegador:
            await _navegador.close()
    except Exception:
        pass
    try:
        if _playwright:
            await _playwright.stop()
    except Exception:
        pass
    _playwright = None
    _navegador = None


async def obtener_navegador():
    global _playwright, _navegador, _canjes_con_este_navegador
    if _navegador and (not _navegador.is_connected() or _canjes_con_este_navegador >= CANJES_POR_NAVEGADOR):
        await cerrar_navegador()
    if not _navegador:
        try:
            _playwright = await async_playwright().start()
            _navegador = await _playwright.chromium.launch(headless=True, args=ARGS_CHROMIUM)
            _canjes_con_este_navegador = 0
        except Exception as e:
            await cerrar_navegador()
            raise NavegadorNoDisponible(str(e)) from e
    _canjes_con_este_navegador += 1
    return _navegador


@app.on_event("shutdown")
async def al_apagar():
    await cerrar_navegador()


async def automatizar_hype_secuencial(pines: List[str], player_id: str):
    navegador = await obtener_navegador()
    try:
        context = await navegador.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES"
        )
        page = await context.new_page()
    except Exception as e:
        # El navegador quedó inservible: se cierra para que el próximo canje abra uno nuevo
        await cerrar_navegador()
        raise NavegadorNoDisponible(str(e)) from e

    pines_exitosos = []
    pines_pendientes = list(pines)
    try:
        for index, pin in enumerate(pines):
            intentos_maximos = 2  # Reintentará hasta 2 veces este pin si falla por timeout

            for intento in range(1, intentos_maximos + 1):
                try:
                    print(f"[{index + 1}/{len(pines)}] (Intento {intento}/{intentos_maximos}) Iniciando canje para PIN: {pin} e ID: {player_id}")

                    await page.goto("https://redeem.hype.games", timeout=60000)

                    await page.wait_for_selector("input", timeout=45000)
                    await page.locator("input").first.fill(pin)
                    await page.click("button:has-text('CANJEAR')")

                    # Limpiar cookies si molestan
                    try:
                        await page.click("button:has-text('Accept'), button:has-text('Aceptar')", timeout=4000)
                    except Exception:
                        pass
                    await page.evaluate("() => { document.querySelectorAll('[id*=\"adopt\"], [class*=\"cookie\"]').forEach(el => el.remove()); }")

                    await asyncio.sleep(3)

                    # Escribir ID con el método blindado
                    try:
                        caja_id = page.locator("input:not([type='checkbox']):not([type='hidden']):visible").first
                        await caja_id.click(timeout=5000)
                        await page.keyboard.insert_text(player_id)
                    except Exception:
                        # El ID se pasa como argumento, nunca pegado dentro del código JavaScript
                        await page.evaluate("""
                            (id) => {
                                const cajas = Array.from(document.querySelectorAll('input'));
                                const cajaVisible = cajas.find(i => i.type !== 'checkbox' && i.type !== 'hidden' && i.offsetParent !== null);
                                if (cajaVisible) {
                                    cajaVisible.focus();
                                    cajaVisible.value = id;
                                    cajaVisible.dispatchEvent(new Event('input', {bubbles: true}));
                                    cajaVisible.dispatchEvent(new Event('change', {bubbles: true}));
                                }
                            }
                        """, player_id)

                    # Aceptar términos y condiciones
                    await page.locator("input[type='checkbox']").first.check()

                    # Clic en verificar ID
                    await page.click("button:has-text('VERIFICAR ID')")

                    # Esperar a que el ID esté verificado (Tiempo ampliado a 45s)
                    await page.wait_for_selector("text='ID verificado'", timeout=45000)

                    # Clic en el botón final de canje
                    await page.click("button:has-text('¡CANJEAR AHORA!')")

                    # Pausa para procesar el salto final del PIN actual
                    await asyncio.sleep(4)

                    # ¡Éxito en este pin! Lo movemos a exitosos y salimos del bucle de reintentos
                    pines_exitosos.append(pin)
                    pines_pendientes.remove(pin)
                    print(f"✅ PIN {pin} canjeado con éxito.")
                    break

                except Exception as pin_error:
                    print(f"⚠️ Fallo en intento {intento} para el PIN {pin}: {str(pin_error)}")
                    if intento < intentos_maximos:
                        print(f"🔄 Reintentando canje del PIN {pin} en 3 segundos...")
                        await asyncio.sleep(3)
                    else:
                        # Si se agotaron los reintentos para este pin, lanzamos el error hacia arriba
                        raise pin_error

        return {
            "success": True,
            "message": "Todos los PINes fueron canjeados con éxito.",
            "pines_exitosos": pines_exitosos,
            "pines_pendientes": pines_pendientes
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error crítico definitivo en el proceso: {error_msg}")
        if pines_pendientes:
            print(f"🚨 ADVERTENCIA: Los siguientes PINes NO pudieron ser canjeados y quedaron pendientes: {pines_pendientes}")

        try:
            await page.screenshot(path="error_cloud.png", full_page=True)
        except Exception:
            pass

        return {
            "success": False,
            "error": error_msg,
            "pines_exitosos": pines_exitosos,
            "pines_pendientes": pines_pendientes
        }
    finally:
        # SIEMPRE se cierra el contexto (y sus páginas), pase lo que pase
        try:
            await context.close()
        except Exception:
            pass


@app.post("/canjear")
async def procesar_canje(req: CanjeRequest, x_secret_token: str = Header(None)):
    verificar_secreto(x_secret_token)

    lista_pines = []
    if req.pins and isinstance(req.pins, list):
        lista_pines = [str(p).strip() for p in req.pins]
    elif req.pin:
        lista_pines = [str(req.pin).strip()]

    if not lista_pines:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún PIN para canjear.")
    if len(lista_pines) > MAX_PINES or not all(PIN_VALIDO.match(p) for p in lista_pines):
        raise HTTPException(status_code=400, detail="PINes con formato inválido.")
    player_id = str(req.player_id).strip()
    if not ID_VALIDO.match(player_id):
        raise HTTPException(status_code=400, detail="ID de jugador inválido.")

    # Turno: si otro canje tarda demasiado, 503 (ningún pin se tocó)
    try:
        await asyncio.wait_for(turno.acquire(), timeout=ESPERA_TURNO_S)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Bot ocupado con otro canje. No se canjeó ningún PIN.")

    try:
        resultado = await automatizar_hype_secuencial(lista_pines, player_id)
    except NavegadorNoDisponible as e:
        # 503 = "no procesado" para Vercel: devuelve los pines al inventario
        print(f"❌ No se pudo abrir el navegador: {e}")
        raise HTTPException(status_code=503, detail="El navegador del bot no está disponible. No se canjeó ningún PIN.")
    finally:
        turno.release()

    if not resultado["success"]:
        return {
            "status": "error",
            "detail": f"Error: {resultado['error']} | PINes NO canjeados: {resultado['pines_pendientes']}",
            "pines_exitosos": resultado["pines_exitosos"],
            "pines_pendientes": resultado["pines_pendientes"]
        }

    return {
        "status": "success",
        "pines_exitosos": resultado["pines_exitosos"],
        "pines_pendientes": resultado["pines_pendientes"]
    }


@app.get("/ver-error")
async def ver_error(x_secret_token: str = Header(None)):
    # La captura puede mostrar IDs de jugadores o PINs: solo con la misma clave del webhook
    verificar_secreto(x_secret_token)
    if os.path.exists("error_cloud.png"):
        return FileResponse("error_cloud.png")
    return {"error": "Aún no hay ninguna captura de error guardada."}
