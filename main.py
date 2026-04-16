import os, uuid, base64, asyncio, time
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8651000393:AAEF3Gkl7AAguYfz5rP7xLI359eBo5jexqE"
NODE_SECRET = "secret_key_123"
ADMIN_ID = 12345678 # ЗАМЕНИ НА СВОЙ ID
PORT = int(os.environ.get("PORT", 8080))
RENDER_URL = "https://backendvpn.onrender.com"

dp = Dispatcher()
bot = Bot(token=BOT_TOKEN)

# Глобальное состояние
nodes = {} # {node_id: {"ip": str, "keys": dict, "last_seen": float, "load": int}}
users = {} # {tg_id: {"uuid": str, "token": str, "expiry": float, "is_premium": bool}}
pending_regs = []

PRICES = {
    "trial": {"name": "Пробный (1 день)", "days": 1, "price": 0},
    "week": {"name": "Неделя", "days": 7, "price": 50},
    "2weeks": {"name": "2 Недели", "days": 14, "price": 85},
    "month": {"name": "Месяц", "days": 30, "price": 150},
    "6months": {"name": "6 Месяцев", "days": 180, "price": 750},
    "year": {"name": "Год", "days": 365, "price": 1300},
    "forever": {"name": "Премиум Навсегда", "days": 36500, "price": 3000}
}

async def sync_handler(request):
    data = await request.json()
    if data.get("secret") != NODE_SECRET: return web.Response(status=403)
    
    node_id = data.get("node_id", "default")
    nodes[node_id] = {
        "ip": data.get("ip"),
        "keys": data.get("keys"),
        "last_seen": time.time(),
        "load": data.get("load", 0)
    }
    
    # Синхронизация базы пользователей с нодой
    if data.get("is_master"):
        for u in data.get("users_backup", []):
            if u['tg_id'] not in users: users[u['tg_id']] = u

    new_regs = list(pending_regs)
    pending_regs.clear()
    
    # Отправляем только активных пользователей (у которых не кончилась подписка)
    active_users = [u for u in users.values() if u['expiry'] > time.time()]
    return web.json_response({"new_registrations": new_regs, "active_users": active_users})

async def sub_handler(request):
    token = request.match_info.get('token')
    user = next((u for u in users.values() if u['token'] == token), None)
    if not user or user['expiry'] < time.time(): return web.Response(status=403, text="Expired")
    
    # Балансировка: выбираем живую ноду с минимальной нагрузкой
    live_nodes = [n for n in nodes.values() if time.time() - n['last_seen'] < 60]
    if not live_nodes: return web.Response(status=503, text="No active nodes")
    best_node = min(live_nodes, key=lambda x: x['load'])
    
    vless = (f"vless://{user['uuid']}@{best_node['ip']}:34523?encryption=none&security=reality"
             f"&sni=dl.google.com&fp=chrome&pbk={best_node['keys']['public']}"
             f"&sid={best_node['keys']['shortId']}&flow=xtls-rprx-vision#ClusterVPN")
    return web.Response(text=base64.b64encode((vless + "\n").encode()).decode())

# --- ТЕЛЕГРАМ БОТ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_menu"))
    kb.row(types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile"))
    if message.from_user.id == ADMIN_ID:
        kb.row(types.InlineKeyboardButton(text="⚙️ Админка", callback_data="admin_panel"))
    await message.answer("🤖 VPN Cluster Bot\nВыберите действие:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "profile")
async def view_profile(callback: types.CallbackQuery):
    u = users.get(callback.from_user.id)
    if not u:
        text = "У вас нет активной подписки."
    else:
        rem = u['expiry'] - time.time()
        status = "Infinity" if rem > 10**9 else f"{int(rem//86400)}д. {int((rem%86400)//3600)}ч."
        text = f"ID: `{callback.from_user.id}`\nОсталось: {status}\nСсылка: `{RENDER_URL}/sub/{u['token']}`"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="Назад", callback_data="start")).as_markup())

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    for k, v in PRICES.items():
        kb.row(types.InlineKeyboardButton(text=f"{v['name']} - {v['price']}₽", callback_data=f"pay_{k}"))
    await callback.message.edit_text("Выберите тариф:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("pay_"))
async def handle_payment(callback: types.CallbackQuery):
    plan = callback.data.split("_")[1]
    p = PRICES[plan]
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"confirm_{plan}"))
    await callback.message.edit_text(f"Оплата тарифа: {p['name']}\nЦена: {p['price']}₽\nПереведите на карту/номер...", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    plan = callback.data.split("_")[1]
    tg_id = callback.from_user.id
    days = PRICES[plan]['days']
    
    if tg_id not in users:
        users[tg_id] = {"tg_id": tg_id, "uuid": str(uuid.uuid4()), "token": uuid.uuid4().hex[:16], "expiry": time.time() + (days*86400), "is_premium": (plan=="forever")}
        pending_regs.append(users[tg_id])
    else:
        users[tg_id]['expiry'] = max(users[tg_id]['expiry'], time.time()) + (days*86400)
    
    await callback.message.edit_text("✅ Подписка активирована! Обновите конфиг в приложении.")

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    text = f"Статистика:\nСерверов: {len(nodes)}\nЮзеров: {len(users)}"
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Удалить юзера", callback_data="adm_del"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

async def checker_loop():
    while True:
        now = time.time()
        for uid, u in list(users.items()):
            rem = u['expiry'] - now
            if 3540 < rem < 3660: # 1 час
                await bot.send_message(uid, "⚠️ Подписка кончится через 1 час!")
            elif 86340 < rem < 86460: # 1 день
                await bot.send_message(uid, "⚠️ Подписка кончится через 1 день!")
        await asyncio.sleep(300) # раз в 5 минут

async def startup_process(app):
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(checker_loop())

app = web.Application()
app.router.add_post('/sync', sync_handler)
app.router.add_get('/sub/{token}', sub_handler)
app.on_startup.append(startup_process)
web.run_app(app, host='0.0.0.0', port=PORT)
