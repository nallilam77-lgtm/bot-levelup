import os
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
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Conectando a Hype Games...")
            await page.goto("https://redeem.hype.games", timeout=60000)

            print("Buscando campo de PIN...")
            # Esperamos a que aparezca el input de texto del PIN
            await page.wait_for_selector("input", timeout=15000)
            
            print("Insertando PIN...")
            await page.locator("input").first.fill(pin)
            
            print("Dando clic en CANJEAR...")
            await page.click("button:has-text('CANJEAR')")

            print("Esperando la pantalla del ID de jugador...")
            await page.wait_for_selector("text='Solo necesitamos algunos datos'", timeout=15000)
            
            print("Escribiendo ID de jugador...")
            await page.locator("input[type='text']").last.fill(player_id)
            
            print("Aceptando términos y condiciones...")
            await page.locator("input[type='checkbox']").check()
            
            print("Verificando ID...")
            await page.click("button:has-text('VERIFICAR ID')")

            print("Esperando confirmación de ID verificado...")
            await page.wait_for_selector("text='ID verificado'", timeout=15000)
            
            print("Dando clic en canjear ahora...")
            await page.click("button:has-text('¡CANJEAR AHORA!')")

            print("Esperando confirmación final...")
            await page.wait_for_selector("text='ENTREGA DE CRÉDITOS EN PROCESO.'", timeout=20000)

            await browser.close()
            return {"success": True, "message": f"PIN canjeado con éxito para el ID {player_id}."}

        except Exception as e:
            print(f"❌ Error detallado en Playwright: {str(e)}")
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
