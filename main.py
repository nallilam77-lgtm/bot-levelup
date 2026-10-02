import os
import asyncio
from typing import List, Union
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "TuClaveSecretaSuperSegura123")

class CanjeRequest(BaseModel):
    pin: Union[str, None] = None
    pins: Union[List[str], None] = None
    player_id: str

async def automatizar_hype_secuencial(pines: List[str], player_id: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", # 🔥 AÑADIDO: Evita que Railway se quede sin memoria compartida
                "--disable-gpu",           # 🔥 AÑADIDO: Ahorra recursos al apagar aceleración gráfica
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-ES"
        )
        page = await context.new_page()

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
                        except:
                            pass
                        await page.evaluate("() => { document.querySelectorAll('[id*=\"adopt\"], [class*=\"cookie\"]').forEach(el => el.remove()); }")

                        await asyncio.sleep(3)

                        # Escribir ID con el método blindado
                        try:
                            caja_id = page.locator("input:not([type='checkbox']):not([type='hidden']):visible").first
                            await caja_id.click(timeout=5000)
                            await page.keyboard.insert_text(player_id)
                        except Exception:
                            await page.evaluate(f"""
                                () => {{
                                    const cajas = Array.from(document.querySelectorAll('input'));
                                    const cajaVisible = cajas.find(i => i.type !== 'checkbox' && i.type !== 'hidden' && i.offsetParent !== null);
                                    if (cajaVisible) {{
                                        cajaVisible.focus();
                                        cajaVisible.value = '{player_id}';
                                        cajaVisible.dispatchEvent(new Event('input', {{bubbles: true}}));
                                        cajaVisible.dispatchEvent(new Event('change', {{bubbles: true}}));
                                    }}
                                }}
                            """)

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

            await browser.close()
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
            except:
                pass
            
            await browser.close()
            return {
                "success": False, 
                "error": error_msg,
                "pines_exitosos": pines_exitosos,
                "pines_pendientes": pines_pendientes
            }

@app.post("/canjear")
async def procesar_canje(req: CanjeRequest, x_secret_token: str = Header(None)):
    if x_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="No autorizado")

    lista_pines = []
    if req.pins and isinstance(req.pins, list):
        lista_pines = req.pins
    elif req.pin:
        lista_pines = [req.pin]

    if not lista_pines:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún PIN para canjear.")

    resultado = await automatizar_hype_secuencial(lista_pines, req.player_id)
    
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
async def ver_error():
    if os.path.exists("error_cloud.png"):
        return FileResponse("error_cloud.png")
    return {"error": "Aún no hay ninguna captura de error guardada."}
