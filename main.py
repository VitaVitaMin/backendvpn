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
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://srv-d7fucdhj2pic73e11gdg.onrender.com")

dp = Dispatcher()
bot = Bot(token=BOT_TOKEN)
node_data = {"ip": "0.0.0.0", "keys": {}}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (tg_id INTEGER, uuid TEXT, token TEXT)")
        await db.commit()

async def sync_node(request):
    data = await request.json()
    if data.get("secret") != NODE_SECRET:
        return web.Response(status=403)
    
    node_data["ip"] = data.get("ip", node_data["ip"])
    if "keys" in data:
        node_data["keys"] = data["keys"]
        
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT uuid FROM users") as c:
            rows = await c.fetchall()
            
    uuids = [row[0] for row in rows]
    if not uuids:
        uuids = [str(uuid.uuid4())]
        
    return web.json_response({"uuids": uuids})

async def sub_handler(request):
    token = request.match_info.get('token')
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT uuid FROM users WHERE token = ?", (token,)) as c:
            user = await c.fetchone()
            
    if not user or not node_data["keys"]:
        return web.Response(status=404)
        
    config = f"vless://{user[0]}@{node_data['ip']}:443?encryption=none&security=reality&sni=google.com&fp=chrome&pbk={node_data['keys'].get('public', '')}&sid={node_data['keys'].get('shortId', '')}&flow=xtls-rprx-vision#VPN"
    return web.Response(text=base64.b64encode(config.encode()).decode())

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Подключиться", callback_data="get_vpn"))
    await message.answer("VPN Подписка", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "get_vpn")
async def handle_sub(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT token FROM users WHERE tg_id = ?", (callback.from_user.id,)) as c:
            user = await c.fetchone()
        if not user:
            u_id, token = str(uuid.uuid4()), uuid.uuid4().hex[:16]
            await db.execute("INSERT INTO users (tg_id, uuid, token) VALUES (?, ?, ?)", (callback.from_user.id, u_id, token))
            await db.commit()
        else:
            token = user[0]
            
    await callback.message.edit_text(f"`{RENDER_URL}/sub/{token}`", parse_mode="Markdown")

async def on_startup(app):
    await init_db()
    asyncio.create_task(dp.start_polling(bot))

app = web.Application()
app.router.add_post('/sync', sync_node)
app.router.add_get('/sub/{token}', sub_handler)
app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, host='0.0.0.0', port=PORT)
