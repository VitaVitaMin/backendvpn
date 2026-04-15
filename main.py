import os
import asyncio
import base64
from aiohttp import web

state = {"home_ip": "0.0.0.0"}

async def update_ip(request):
    try:
        data = await request.json()
        new_ip = data.get("ip")
        if new_ip and len(new_ip) <= 15:
            state["home_ip"] = new_ip
            return web.Response(text="OK")
    except: pass
    return web.Response(status=400)

async def sub_handler(request):
    if state["home_ip"] == "0.0.0.0":
        return web.Response(status=503, text="Server not ready")
    
    # Эти данные должны СОВПАДАТЬ с теми, что генерирует ваш ПК в reality.keys
    # В идеале их стоит передавать при обновлении IP или прописать вручную
    UUID = "ВАШ_UUID" 
    PBK = "ВАШ_PUBLIC_KEY"
    SID = "ВАШ_SHORT_ID"
    
    config = f"vless://{UUID}@{state['home_ip']}:443?encryption=none&security=reality&sni=google.com&fp=chrome&pbk={PBK}&sid={SID}&flow=xtls-rprx-vision#Ultimate_Home_VPN"
    return web.Response(text=base64.b64encode(config.encode()).decode())

async def index(request):
    return web.Response(text="Cloud Sync Active")

app = web.Application()
app.router.add_get('/', index)
app.router.add_post('/update', update_ip)
app.router.add_get('/sub/{token}', sub_handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host='0.0.0.0', port=port)
