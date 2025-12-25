import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
from config import BOT_TOKEN, TIMEZONE
from states import Form


tz = ZoneInfo(TIMEZONE)

QUESTIONS = [
    "1) Что за сегодняшний день Вы сделали хорошо?",
    "2) Что люди вокруг Вас сделали такого, за что Вы им благодарны (неважно, сделали они это по отношению к Вам или нет)? Кому Вы за это благодарны?",
    "3) Что Вы в течение сегодняшнего дня видели, слышали, пробовали на вкус, осязали, обоняли, что наполняет Вас благодарностью к миру / что принесло Вам удовлетворение?",
    "4) Какие мелочи порадовали / повеселили Вас сегодня?",
]

ALLOWED_TIMES = ["20:00", "21:00", "22:00"]

# ---------- клавиатуры ----------

# Выбор времени
time_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t)] for t in ALLOWED_TIMES] + [[KeyboardButton(text="↩️ Назад")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# Главное меню
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Запустить")],
        [KeyboardButton(text="⏰ Сменить время"), KeyboardButton(text="⛔ Остановить")],
    ],
    resize_keyboard=True,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()


# ---------- helpers ----------

def schedule_user(user_id: int, hhmm: str):
    hour, minute = map(int, hhmm.split(":"))
    scheduler.add_job(
        send_daily_questions,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[user_id],
        id=str(user_id),
        replace_existing=True,
    )

def unschedule_user(user_id: int):
    job = scheduler.get_job(str(user_id))
    if job:
        scheduler.remove_job(str(user_id))

async def set_state_outside(user_id: int, state_name):
    key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    ctx = FSMContext(dp.storage, key)
    await ctx.set_state(state_name)

async def set_data_outside(user_id: int, data: dict):
    key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    ctx = FSMContext(dp.storage, key)
    await ctx.update_data(**data)

async def clear_state_outside(user_id: int):
    key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    ctx = FSMContext(dp.storage, key)
    await ctx.clear()

def today_str() -> str:
    return datetime.now(tz).date().isoformat()


# ---------- start / launch ----------

async def start_flow(message: Message, state: FSMContext):
    db.upsert_user(message.from_user.id, notify_time=None, is_active=1)
    await message.answer(
        "Это бот «Вопросы для хорошей жизни».\n\n"
        "Он поможет поддерживать ежедневную практику благодарностей "
        "и замечания вдохновляющих мелочей.\n\n"
        "Выберите время отправки ежедневного сообщения с вопросами "
        "(ответы на эти вопросы вы сможете отправлять прямо в этот чат):",
        reply_markup=time_keyboard,
    )
    await state.set_state(Form.wait_time)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await start_flow(message, state)


@dp.message(F.text == "▶️ Запустить")
async def btn_start(message: Message, state: FSMContext):
    await start_flow(message, state)


# ---------- change / stop ----------

@dp.message(Command("change_time"))
@dp.message(F.text == "⏰ Сменить время")
async def change_time(message: Message, state: FSMContext):
    await message.answer("Выберите новое время:", reply_markup=time_keyboard)
    await state.set_state(Form.wait_time)


@dp.message(Command("stop"))
@dp.message(F.text == "⛔ Остановить")
async def stop_flow(message: Message, state: FSMContext):
    user_id = message.from_user.id
    unschedule_user(user_id)
    db.upsert_user(user_id, notify_time=None, is_active=0)
    await state.clear()
    await message.answer(
        "Остановлено ✅\n"
        "Вы можете снова запустить бота в любой момент.",
        reply_markup=main_keyboard,
    )


# ---------- choose time ----------

@dp.message(Form.wait_time)
async def choose_time(message: Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.clear()
        await message.answer("Хорошо. Что делаем дальше?", reply_markup=main_keyboard)
        return

    if message.text not in ALLOWED_TIMES:
        await message.answer("Пожалуйста, выберите время кнопкой ⏰", reply_markup=time_keyboard)
        return

    user_id = message.from_user.id
    hhmm = message.text

    db.upsert_user(user_id, notify_time=hhmm, is_active=1)
    schedule_user(user_id, hhmm)

    await state.clear()
    await message.answer(
        f"Готово 🌿 Я буду писать каждый день в {hhmm}.",
        reply_markup=main_keyboard,
    )


# ---------- daily flow ----------

async def send_daily_questions(user_id: int):
    session_date = today_str()

    await clear_state_outside(user_id)
    await set_data_outside(user_id, {"session_date": session_date})

    await bot.send_message(user_id, QUESTIONS[0], reply_markup=main_keyboard)
    await set_state_outside(user_id, Form.q1)


# ---------- answers ----------

@dp.message(Form.q1)
async def q1(message: Message, state: FSMContext):
    d = await state.get_data()
    db.save_answer(message.from_user.id, d.get("session_date", today_str()), 1, QUESTIONS[0], message.text)
    await message.answer(QUESTIONS[1], reply_markup=main_keyboard)
    await state.set_state(Form.q2)

@dp.message(Form.q2)
async def q2(message: Message, state: FSMContext):
    d = await state.get_data()
    db.save_answer(message.from_user.id, d.get("session_date", today_str()), 2, QUESTIONS[1], message.text)
    await message.answer(QUESTIONS[2], reply_markup=main_keyboard)
    await state.set_state(Form.q3)

@dp.message(Form.q3)
async def q3(message: Message, state: FSMContext):
    d = await state.get_data()
    db.save_answer(message.from_user.id, d.get("session_date", today_str()), 3, QUESTIONS[2], message.text)
    await message.answer(QUESTIONS[3], reply_markup=main_keyboard)
    await state.set_state(Form.q4)

@dp.message(Form.q4)
async def q4(message: Message, state: FSMContext):
    d = await state.get_data()
    db.save_answer(message.from_user.id, d.get("session_date", today_str()), 4, QUESTIONS[3], message.text)
    await message.answer("Спасибо за ответы. До завтра!", reply_markup=main_keyboard)
    await state.clear()


# ---------- restore ----------

async def restore_jobs_from_db():
    for user_id, hhmm in db.get_active_users():
        schedule_user(user_id, hhmm)


# ---------- main ----------

async def main():
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler.start()
    await restore_jobs_from_db()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
