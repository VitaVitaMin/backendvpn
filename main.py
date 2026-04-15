import os
import uuid
import base64
import asyncio
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8651000393:AAEF3Gkl7AAguYfz5rP7xLI359eBo5jexqE"
NODE_SECRET = "secret_key_123"
DB_NAME = "users.db"
PORT = int(os.environ.get("PORT", 8080))
# Render сам подставит URL, если нет — впиши свой https://backendvpn.onrender.com
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://backendvpn.onrender.com")

dp = Dispatcher()
bot = Bot(token=BOT_TOKEN)
node_data = {"ip": "0.0.0.0", "keys": {}}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (tg_id INTEGER, uuid TEXT, token TEXT)")
        await db.commit()

async def sync_node(request):
    try:
        data = await request.json()
        if data.get("secret") != NODE_SECRET: return web.Response(status=403)
        node_data["ip"] = data.get("ip")
        node_data["keys"] = data.get("keys")
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT uuid FROM users") as c:
                rows = await c.fetchall()
        return web.json_response({"uuids": [r[0] for r in rows]})
    except: return web.Response(status=400)

async def sub_handler(request):
    token = request.match_info.get('token')
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT uuid FROM users WHERE token = ?", (token,)) as c:
            user = await c.fetchone()
    if not user or not node_data["keys"]: return web.Response(status=404, text="Node not synced")
    
    # Формируем прямую ссылку VLESS
    vless = (f"vless://{user[0]}@{node_data['ip']}:443?encryption=none&security=reality"
             f"&sni=google.com&fp=chrome&pbk={node_data['keys']['public']}"
             f"&sid={node_data['keys']['shortId']}&flow=xtls-rprx-vision#MyHomeVPN")
    
    # Кодируем в Base64 (стандарт для подписок)
    return web.Response(text=base64.b64encode((vless + "\n").encode()).decode())

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🚀 Подключиться", callback_data="get_vpn"))
    await message.answer("Управление VPN подпиской", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "get_vpn")
async def handle_sub(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT token FROM users WHERE tg_id = ?", (callback.from_user.id,)) as c:
            user = await c.fetchone()
        if not user:
            u_id, token = str(uuid.uuid4()), uuid.uuid4().hex[:16]
            await db.execute("INSERT INTO users (tg_id, uuid, token) VALUES (?, ?, ?)", (callback.from_user.id, u_id, token))
            await db.commit()
            user = (token,)
    
    sub_link = f"{RENDER_URL}/sub/{user[0]}"
    await callback.message.edit_text(f"Твоя ссылка для Nekobox/v2ray:\n\n`{sub_link}`", parse_mode="Markdown")

async def startup_process(app):
    await init_db()
    asyncio.create_task(dp.start_polling(bot))

app = web.Application()
app.router.add_post('/sync', sync_node)
app.router.add_get('/sub/{token}', sub_handler)
app.on_startup.append(startup_process)

if __name__ == "__main__":
    web.run_app(app, host='0.0.0.0', port=PORT)
