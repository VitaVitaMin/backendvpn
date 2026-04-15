import os, uuid, base64, asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8651000393:AAEF3Gkl7AAguYfz5rP7xLI359eBo5jexqE"
NODE_SECRET = "secret_key_123"
PORT = int(os.environ.get("PORT", 8080))
RENDER_URL = "https://backendvpn.onrender.com"

dp = Dispatcher()
bot = Bot(token=BOT_TOKEN)
state = {"ip": "0.0.0.0", "keys": {}, "users": {}, "pending": []}

async def sync_handler(request):
    try:
        data = await request.json()
        if data.get("secret") != NODE_SECRET: return web.Response(status=403)
        state["ip"] = data.get("ip")
        state["keys"] = data.get("keys")
        state["users"] = {u['tg_id']: u for u in data.get("users", [])}
        new_regs = list(state["pending"])
        state["pending"] = []
        return web.json_response({"new_registrations": new_regs})
    except: return web.Response(status=400)

async def sub_handler(request):
    token = request.match_info.get('token')
    user = next((u for u in state["users"].values() if u['token'] == token), None)
    if not user or not state["keys"]: return web.Response(status=404, text="Offline")
    vless = (f"vless://{user['uuid']}@{state['ip']}:443?encryption=none&security=reality"
             f"&sni=google.com&fp=chrome&pbk={state['keys']['public']}"
             f"&sid={state['keys']['shortId']}&flow=xtls-rprx-vision#MyHomeVPN")
    return web.Response(text=base64.b64encode((vless + "\n").encode()).decode())

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🚀 Получить VPN", callback_data="get_vpn"))
    await message.answer("Master-Mirror VPN System", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "get_vpn")
async def handle_get_vpn(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    if tg_id in state["users"]:
        user = state["users"][tg_id]
        link = f"{RENDER_URL}/sub/{user['token']}"
        await callback.message.edit_text(f"Твоя ссылка:\n`{link}`", parse_mode="Markdown")
    elif any(u['tg_id'] == tg_id for u in state["pending"]):
        await callback.answer("Регистрация в очереди... Подожди 15 секунд.", show_alert=True)
    else:
        new_u = {"tg_id": tg_id, "uuid": str(uuid.uuid4()), "token": uuid.uuid4().hex[:16]}
        state["pending"].append(new_u)
        await callback.answer("Создаю ключ... Подожди 15-20 секунд и нажми еще раз.", show_alert=True)

async def startup(app):
    asyncio.create_task(dp.start_polling(bot))

app = web.Application()
app.router.add_post('/sync', sync_handler)
app.router.add_get('/sub/{token}', sub_handler)
app.on_startup.append(startup)

if __name__ == "__main__":
    web.run_app(app, host='0.0.0.0', port=PORT)
