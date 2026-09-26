import os
import asyncio
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "TuClaveSecretaSuperSegura123")

class CanjeRequest(BaseModel):
    pin: str
    player_id: str

async def automatizar_hype(pin: str, player_id: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = await browser.new_page()

        try:
            print(f"Iniciando canje para PIN: {pin} e ID: {player_id}")
            # Ampliamos el timeout de navegación a 60 segundos
            await page.goto("https://redeem.hype.games", timeout=60000)

            await page.wait_for_selector("input", timeout=20000)
            await page.locator("input").first.fill(pin)
            await page.click("button:has-text('CANJEAR')")

            try:
                await page.click("text='Aceptar'", timeout=5000)
            except:
                pass

            # Pausa de seguridad para la animación
            await asyncio.sleep(4)

            # Sistema blindado para escribir el ID dinámico
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

            await page.locator("input[type='checkbox']").first.check()
            await page.click("button:has-text('VERIFICAR ID')")
            
            # Timeout ampliado a 30 segundos para la validación del ID
            await page.wait_for_selector("text='ID verificado'", timeout=30000)
            await page.click("button:has-text('¡CANJEAR AHORA!')")

            # Timeout ampliado a 45 segundos para que la nube espere con calma la pantalla de éxito
            await page.wait_for_selector("text='ENTREGA DE CRÉDITOS EN PROCESO.'", timeout=45000)

            await browser.close()
            return {"success": True, "message": f"PIN canjeado con éxito para el ID {player_id}."}

        except Exception as e:
            print(f"❌ Error en el proceso: {str(e)}")
            await browser.close()
            return {"success": False, "error": str(e)}

@app.post("/canjear")
async def procesar_canje(req: CanjeRequest, x_secret_token: str = Header(None)):
    if x_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="No autorizado")

    resultado = await automatizar_hype(req.pin, req.player_id)
    
    if not resultado["success"]:
        raise HTTPException(status_code=500, detail=resultado["error"])

    return {"status": "success", "result": resultado}
