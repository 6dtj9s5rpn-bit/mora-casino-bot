import asyncio
import os
import random
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB = "casino.db"
START_BAL = 1000
BONUS = 500
MIN_BET = 10

def init():
    with closing(sqlite3.connect(DB)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS u (id INTEGER PRIMARY KEY, name TEXT, bal INTEGER DEFAULT 0, last TEXT)")
        c.commit()

def get(uid):
    with closing(sqlite3.connect(DB)) as c:
        return c.execute("SELECT bal, last FROM u WHERE id=?", (uid,)).fetchone()

def add(uid, delta):
    with closing(sqlite3.connect(DB)) as c:
        c.execute("UPDATE u SET bal = bal + ? WHERE id=?", (delta, uid))
        c.commit()

def new_user(uid, name):
    with closing(sqlite3.connect(DB)) as c:
        c.execute("INSERT OR IGNORE INTO u (id, name, bal) VALUES (?,?,?)", (uid, name or "", START_BAL))
        c.commit()

def set_last(uid):
    with closing(sqlite3.connect(DB)) as c:
        c.execute("UPDATE u SET last=? WHERE id=?", (datetime.utcnow().isoformat(), uid))
        c.commit()

def top(limit=5):
    with closing(sqlite3.connect(DB)) as c:
        return c.execute("SELECT name, bal FROM u ORDER BY bal DESC LIMIT ?", (limit,)).fetchall()

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Ставка", callback_data="bet")],
        [InlineKeyboardButton(text="🎁 Бонус", callback_data="bonus"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
    ])

@dp.message(CommandStart())
async def start(msg: Message):
    new_user(msg.from_user.id, msg.from_user.username)
    bal = get(msg.from_user.id)[0]
    await msg.answer(
        f"🎰 <b>МораКазино</b>\n\n"
        f"Привет, {msg.from_user.first_name}!\n"
        f"Баланс: <b>{bal} МК</b>\n\n"
        f"Как играть: нажми 🎲 и напиши сумму ставки.\n"
        f"Кубик против бота. У кого больше — забирает ×2.",
        reply_markup=menu()
    )

@dp.callback_query(F.data == "bet")
async def cb_bet(cb):
    await cb.message.answer("Напиши сумму ставки (минимум 10 МК):")
    await cb.answer()

@dp.callback_query(F.data == "bonus")
async def cb_bonus(cb):
    row = get(cb.from_user.id)
    if row[1]:
        last = datetime.fromisoformat(row[1])
        if datetime.utcnow() - last < timedelta(hours=24):
            await cb.answer("Уже брал. Через сутки.", show_alert=True)
            return
    add(cb.from_user.id, BONUS)
    set_last(cb.from_user.id)
    await cb.answer(f"+{BONUS} МК 🎁", show_alert=True)

@dp.callback_query(F.data == "top")
async def cb_top(cb):
    rows = top()
    text = "🏆 <b>Топ-5</b>\n\n"
    for i, (name, bal) in enumerate(rows, 1):
        text += f"{i}. {name or 'anon'} — {bal} МК\n"
    await cb.message.answer(text)
    await cb.answer()

@dp.message(F.text.regexp(r"^\d+$"))
async def bet(msg: Message):
    row = get(msg.from_user.id)
    if not row:
        await msg.answer("Сначала /start")
        return
    bal = row[0]
    amount = int(msg.text)

    if amount < MIN_BET:
        await msg.answer(f"Минимум {MIN_BET} МК.")
        return
    if amount > bal:
        await msg.answer(f"Не хватает. У тебя {bal} МК.")
        return

    add(msg.from_user.id, -amount)
    you = random.randint(1, 6)
    opp = random.randint(1, 6)

    if you > opp:
        add(msg.from_user.id, amount * 2)
        result = f"🎲 Ты: {you} | Бот: {opp}\n\n🏆 Победа! +{amount} МК"
    elif you < opp:
        result = f"🎲 Ты: {you} | Бот: {opp}\n\n💀 Проигрыш. -{amount} МК"
    else:
        add(msg.from_user.id, amount)
        result = f"🎲 Ты: {you} | Бот: {opp}\n\n🤝 Ничья. Ставка возвращена."

    new_bal = get(msg.from_user.id)[0]
    await msg.answer(f"{result}\n\n💰 Баланс: <b>{new_bal} МК</b>", reply_markup=menu())

@dp.message(Command("bal"))
async def bal(msg: Message):
    row = get(msg.from_user.id)
    if not row:
        await msg.answer("Сначала /start")
        return
    await msg.answer(f"💰 {row[0]} МК")

@dp.message(Command("give"))
async def give(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) != 3:
        await msg.answer("/give ID сумма")
        return
    try:
        uid, amount = int(parts[1]), int(parts[2])
    except ValueError:
        await msg.answer("ID и сумма — числа.")
        return
    add(uid, amount)
    await msg.answer(f"✅ +{amount} МК для {uid}")

async def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN не задан.")
        return
    init()
    print("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
