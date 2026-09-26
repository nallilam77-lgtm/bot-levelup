import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI()

# Clave de seguridad para tu webhook
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "TuClaveSecretaSuperSegura123")

class CanjeRequest(BaseModel):
    pin: str
    player_id: str

async def automatizar_hype(pin: str, player_id: str):
    async with async_playwright() as p:
        # Abrimos el navegador oculto
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. Entrar a la página de canje
            print("Entrando a Hype Games...")
            await page.goto("https://redeem.hype.games", timeout=60000)

            # 2. Insertar el PIN y dar clic en CANJEAR
            print("Insertando PIN...")
            await page.fill("input[type='text']", pin) 
            await page.click("button:has-text('CANJEAR')")

            # 3. Esperar la segunda pantalla, llenar el ID y aceptar términos
            print("Esperando validación de PIN y llenando ID...")
            await page.wait_for_selector("text='Solo necesitamos algunos datos'", timeout=15000)
            
            # Hay un input para el ID del jugador, lo llenamos
            await page.locator("input[type='text']").last.fill(player_id)
            
            # Clic en el checkbox de los términos y condiciones
            await page.locator("input[type='checkbox']").check()
            
            # Clic en VERIFICAR ID
            await page.click("button:has-text('VERIFICAR ID')")

            # 4. Esperar a que el ID sea validado y canjear
            print("Verificando ID...")
            await page.wait_for_selector("text='ID verificado'", timeout=15000)
            await page.click("button:has-text('¡CANJEAR AHORA!')")

            # 5. Esperar confirmación final de éxito
            print("Esperando confirmación final...")
            await page.wait_for_selector("text='ENTREGA DE CRÉDITOS EN PROCESO.'", timeout=20000)

            await browser.close()
            return {"success": True, "message": f"PIN canjeado con éxito para el ID {player_id}."}

        except Exception as e:
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