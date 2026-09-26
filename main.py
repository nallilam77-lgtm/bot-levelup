import os
import asyncio
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "TuClaveSecretaSuperSegura123")

class CanjeRequest(BaseModel):
    pin: str
    player_id: str

async def automatizar_hype(pin: str, player_id: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox",
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

        try:
            print(f"Iniciando canje para PIN: {pin} e ID: {player_id}")
            await page.goto("https://redeem.hype.games", timeout=60000)

            await page.wait_for_selector("input", timeout=20000)
            await page.locator("input").first.fill(pin)
            await page.click("button:has-text('CANJEAR')")

            # --- MATAR EL BANNER DE COOKIES POR COMPLETO ---
            try:
                await page.click("button:has-text('Accept'), button:has-text('Aceptar')", timeout=4000)
            except:
                pass
            # Borra cualquier resto de cookies del DOM con JavaScript
            await page.evaluate("() => { document.querySelectorAll('[id*=\"adopt\"], [class*=\"cookie\"]').forEach(el => el.remove()); }")

            await asyncio.sleep(4)

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
            
            # Esperar a que el ID esté verificado
            print("Esperando validación del ID...")
            await page.wait_for_selector("text='ID verificado'", timeout=30000)

            # Clic directo y sin dudas en el botón final de canje
            print("Dando clic en ¡CANJEAR AHORA!...")
            await page.click("button:has-text('¡CANJEAR AHORA!')")

            # Esperar la confirmación final de éxito
            await page.wait_for_selector("text='ENTREGA DE CRÉDITOS EN PROCESO.'", timeout=45000)

            print("¡Canje exitoso en la nube!")
            await browser.close()
            return {"success": True, "message": f"PIN canjeado con éxito para el ID {player_id}."}

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error en el proceso: {error_msg}")
            try:
                await page.screenshot(path="error_cloud.png", full_page=True)
                print("📸 Captura de pantalla del error guardada como error_cloud.png")
            except:
                pass
            
            await browser.close()
            return {"success": False, "error": error_msg}

@app.post("/canjear")
async def procesar_canje(req: CanjeRequest, x_secret_token: str = Header(None)):
    if x_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="No autorizado")

    resultado = await automatizar_hype(req.pin, req.player_id)
    
    if not resultado["success"]:
        raise HTTPException(status_code=500, detail=resultado["error"])

    return {"status": "success", "result": resultado}

@app.get("/ver-error")
async def ver_error():
    if os.path.exists("error_cloud.png"):
        return FileResponse("error_cloud.png")
    return {"error": "Aún no hay ninguna captura de error guardada."}
