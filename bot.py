import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
from config import BOT_TOKEN, DEFAULT_TZ, INACTIVE_DAYS, NUDGE_COOLDOWN_DAYS
from states import Form


QUESTIONS = [
    "1) Что за сегодняшний день Вы сделали хорошо?",
    "2) Что люди вокруг Вас сделали такого, за что Вы им благодарны (неважно, сделали они это по отношению к Вам или нет)? Кому Вы за это благодарны?",
    "3) Что Вы в течение сегодняшнего дня видели, слышали, пробовали на вкус, осязали, обоняли, что наполняет Вас благодарностью к миру / что принесло Вам удовлетворение?",
    "4) Какие мелочи порадовали / повеселили Вас сегодня?",
]

ALLOWED_TIMES = ["20:00", "21:00", "22:00"]

# Грубые регионы -> timezone
TZ_GROUPS = {
    "Москва": "Europe/Moscow",
    "Европа": "Europe/Berlin",
    "Азия": "Asia/Almaty",
    "Америка": "America/New_York",
}

# ---------- keyboards ----------

region_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Москва"), KeyboardButton(text="Европа")],
        [KeyboardButton(text="Азия"), KeyboardButton(text="Америка")],
        [KeyboardButton(text="↩️ Назад")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

time_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t)] for t in ALLOWED_TIMES] + [[KeyboardButton(text="↩️ Назад")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Запустить")],
        [KeyboardButton(text="🌍 Регион"), KeyboardButton(text="⏰ Время")],
        [KeyboardButton(text="⏭️ Пропустить сегодня"), KeyboardButton(text="⛔ Остановить")],
    ],
    resize_keyboard=True,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# scheduler можно держать в UTC — мы задаём timezone на уровне job
scheduler = AsyncIOScheduler()


# ---------- helpers ----------

def tz_for_user(user_id: int) -> ZoneInfo:
    u = db.get_user(user_id) or {}
    group = u.get("timezone_group") or "Москва"
    tz_name = TZ_GROUPS.get(group, DEFAULT_TZ)
    return ZoneInfo(tz_name)

def today_str_for_user(user_id: int) -> str:
    tz = tz_for_user(user_id)
    return datetime.now(tz).date().isoformat()

def schedule_user(user_id: int, hhmm: str):
    hour, minute = map(int, hhmm.split(":"))
    tz = tz_for_user(user_id)

    scheduler.add_job(
        send_daily_questions,
        trigger="cron",
        hour=hour,
        minute=minute,
        timezone=tz,
        args=[user_id],
        id=str(user_id),
        replace_existing=True,
    )

def unschedule_user(user_id: int):
    job = scheduler.get_job(str(user_id))
    if job:
        scheduler.remove_job(str(user_id))

async def fsm_ctx_outside(user_id: int) -> FSMContext:
    key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    return FSMContext(dp.storage, key)

async def get_state_outside(user_id: int):
    ctx = await fsm_ctx_outside(user_id)
    return await ctx.get_state()

async def get_data_outside(user_id: int):
    ctx = await fsm_ctx_outside(user_id)
    return await ctx.get_data()

async def set_state_outside(user_id: int, state_name):
    ctx = await fsm_ctx_outside(user_id)
    await ctx.set_state(state_name)

async def set_data_outside(user_id: int, data: dict):
    ctx = await fsm_ctx_outside(user_id)
    await ctx.update_data(**data)

async def clear_state_outside(user_id: int):
    ctx = await fsm_ctx_outside(user_id)
    await ctx.clear()


# ---------- start / menu ----------

async def start_flow(message: Message, state: FSMContext):
    db.upsert_user(message.from_user.id, notify_time=None, timezone_group="Москва", is_active=1)
    db.touch_activity(message.from_user.id)

    await message.answer(
        "Это бот «Вопросы для хорошей жизни».\n\n"
        "Он поможет поддерживать ежедневную практику благодарностей и замечания вдохновляющих мелочей.\n\n"
        "Сначала выберите регион (примерно), чтобы «20:00» было по вашему местному времени.",
        reply_markup=region_keyboard,
    )
    await state.set_state(Form.wait_region)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await start_flow(message, state)

@dp.message(F.text == "▶️ Запустить")
async def btn_start(message: Message, state: FSMContext):
    await start_flow(message, state)


@dp.message(F.text == "🌍 Регион")
async def btn_region(message: Message, state: FSMContext):
    db.touch_activity(message.from_user.id)
    await message.answer(
        "Выберите регион (грубо):\n"
        "• Москва = Europe/Moscow\n"
        "• Европа = центральная Европа (Берлин)\n"
        "• Америка = восточное время (Нью-Йорк)\n"
        "• Азия = условно Алматы\n",
        reply_markup=region_keyboard,
    )
    await state.set_state(Form.wait_region)

@dp.message(F.text == "⏰ Время")
@dp.message(Command("change_time"))
async def btn_time(message: Message, state: FSMContext):
    db.touch_activity(message.from_user.id)
    await message.answer("Выберите время отправки ежедневных вопросов:", reply_markup=time_keyboard)
    await state.set_state(Form.wait_time)

@dp.message(F.text == "⛔ Остановить")
@dp.message(Command("stop"))
async def stop_flow(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)
    unschedule_user(user_id)
    db.set_active(user_id, 0)
    await state.clear()
    await message.answer("Остановлено ✅", reply_markup=main_keyboard)


# ---------- skip today ----------

@dp.message(F.text == "⏭️ Пропустить сегодня")
async def skip_today(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)

    today = today_str_for_user(user_id)
    db.set_skip_date(user_id, today)

    # если в FSM уже стояло ожидание "сегодняшних" вопросов — уберём
    data = await state.get_data()
    if data.get("pending_date") == today:
        await state.update_data(pending_date=None)

    await message.answer(
        "Ок, пропускаем сегодняшние вопросы ✅\n"
        "Завтра всё продолжится по расписанию.",
        reply_markup=main_keyboard,
    )


# ---------- choose region ----------

@dp.message(Form.wait_region)
async def choose_region(message: Message, state: FSMContext):
    db.touch_activity(message.from_user.id)

    if message.text == "↩️ Назад":
        await state.clear()
        await message.answer("Ок. Что делаем дальше?", reply_markup=main_keyboard)
        return

    if message.text not in TZ_GROUPS:
        await message.answer("Пожалуйста, выберите регион кнопкой 🌍", reply_markup=region_keyboard)
        return

    db.update_timezone_group(message.from_user.id, message.text)

    await message.answer(
        f"Принято. Регион: {message.text}.\n"
        "Теперь выберите время отправки ежедневных вопросов:",
        reply_markup=time_keyboard,
    )
    await state.set_state(Form.wait_time)


# ---------- choose time ----------

@dp.message(Form.wait_time)
async def choose_time(message: Message, state: FSMContext):
    db.touch_activity(message.from_user.id)

    if message.text == "↩️ Назад":
        await message.answer("Хорошо. Тогда сначала выберите регион:", reply_markup=region_keyboard)
        await state.set_state(Form.wait_region)
        return

    if message.text not in ALLOWED_TIMES:
        await message.answer("Пожалуйста, выберите время кнопкой ⏰", reply_markup=time_keyboard)
        return

    user_id = message.from_user.id
    hhmm = message.text

    db.update_notify_time(user_id, hhmm)
    schedule_user(user_id, hhmm)

    await state.clear()
    await message.answer(
        f"Готово 🌿 Буду писать каждый день в {hhmm} по вашему выбранному региону.",
        reply_markup=main_keyboard,
    )


# ---------- daily flow (с учётом “опоздал с ответами”, pending и skip) ----------

async def send_daily_questions(user_id: int):
    """
    В выбранное время каждый день:
    - если skip_date == today -> не начинаем новый набор
    - если пользователь НЕ в процессе ответов -> начинаем новый дневной набор
    - если пользователь ещё отвечает на прошлые вопросы -> не прерываем, ставим pending_date=today
      и начнём сегодняшние сразу после завершения q4 (если не нажали "пропустить сегодня")
    """
    today = today_str_for_user(user_id)
    u = db.get_user(user_id) or {}
    if u.get("skip_date") == today:
        # пропускаем сегодня, завтра продолжим
        return

    current_state = await get_state_outside(user_id)

    if current_state is None:
        await clear_state_outside(user_id)
        await set_data_outside(user_id, {"session_date": today, "pending_date": None})
        await bot.send_message(user_id, QUESTIONS[0], reply_markup=main_keyboard)
        await set_state_outside(user_id, Form.q1)
        return

    data = await get_data_outside(user_id)
    pending = data.get("pending_date")

    if pending != today:
        await set_data_outside(user_id, {"pending_date": today})
        await bot.send_message(
            user_id,
            "⏳ Пора на новые вопросы, но вы ещё отвечаете на предыдущие.\n"
            "Закончите текущий набор — и я начну сегодняшний.",
            reply_markup=main_keyboard,
        )


# ---------- answers (с запуском pending дня после q4, если не “пропущен”) ----------

@dp.message(Form.q1)
async def q1(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)

    d = await state.get_data()
    session_date = d.get("session_date", today_str_for_user(user_id))
    db.save_answer(user_id, session_date, 1, QUESTIONS[0], message.text)

    await message.answer(QUESTIONS[1], reply_markup=main_keyboard)
    await state.set_state(Form.q2)

@dp.message(Form.q2)
async def q2(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)

    d = await state.get_data()
    session_date = d.get("session_date", today_str_for_user(user_id))
    db.save_answer(user_id, session_date, 2, QUESTIONS[1], message.text)

    await message.answer(QUESTIONS[2], reply_markup=main_keyboard)
    await state.set_state(Form.q3)

@dp.message(Form.q3)
async def q3(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)

    d = await state.get_data()
    session_date = d.get("session_date", today_str_for_user(user_id))
    db.save_answer(user_id, session_date, 3, QUESTIONS[2], message.text)

    await message.answer(QUESTIONS[3], reply_markup=main_keyboard)
    await state.set_state(Form.q4)

@dp.message(Form.q4)
async def q4(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.touch_activity(user_id)

    d = await state.get_data()
    session_date = d.get("session_date", today_str_for_user(user_id))
    db.save_answer(user_id, session_date, 4, QUESTIONS[3], message.text)

    pending_date = d.get("pending_date")
    await state.clear()

    today = today_str_for_user(user_id)
    u = db.get_user(user_id) or {}
    skip_today = (u.get("skip_date") == today)

    # если есть pending на сегодня и сегодня не пропущен — стартуем сразу
    if pending_date == today and not skip_today:
        await message.answer("Спасибо! 🌿 Теперь начнём сегодняшний набор.", reply_markup=main_keyboard)
        await set_data_outside(user_id, {"session_date": today, "pending_date": None})
        await bot.send_message(user_id, QUESTIONS[0], reply_markup=main_keyboard)
        await set_state_outside(user_id, Form.q1)
        return

    await message.answer("Спасибо за ответы. До завтра!", reply_markup=main_keyboard)


# ---------- тихое правило (проверка раз в день) ----------

async def check_inactive_users():
    """
    Раз в день проверяем:
    - если last_activity_at старше INACTIVE_DAYS
    - и last_nudge_at либо пустой, либо старше NUDGE_COOLDOWN_DAYS
    -> отправляем мягкий пинг
    """
    now = datetime.utcnow()
    users = db.get_users_for_nudge()

    for u in users:
        user_id = u["user_id"]

        last_activity = u.get("last_activity_at")
        if not last_activity:
            continue

        try:
            last_activity_dt = datetime.fromisoformat(last_activity)
        except:
            continue

        if now - last_activity_dt < timedelta(days=INACTIVE_DAYS):
            continue

        last_nudge = u.get("last_nudge_at")
        if last_nudge:
            try:
                last_nudge_dt = datetime.fromisoformat(last_nudge)
                if now - last_nudge_dt < timedelta(days=NUDGE_COOLDOWN_DAYS):
                    continue
            except:
                pass

        try:
            await bot.send_message(
                user_id,
                "Я рядом 🌿\n"
                "Если хотите продолжить практику — нажмите «▶️ Запустить» или просто ответьте здесь.",
                reply_markup=main_keyboard,
            )
            db.save_nudge_sent(user_id)
        except:
            # если пользователь заблокировал бота/ошибка доставки — молча пропускаем
            pass


# ---------- restore ----------

async def restore_jobs_from_db():
    for row in db.get_active_users_for_schedule():
        user_id = row["user_id"]
        hhmm = row["notify_time"]
        tz_group = row.get("timezone_group")
        if not tz_group:
            db.update_timezone_group(user_id, "Москва")
        schedule_user(user_id, hhmm)


# ---------- main ----------

async def main():
    await bot.delete_webhook(drop_pending_updates=True)

    scheduler.start()

    # ежедневная проверка "тихого правила" (в 10:00 UTC)
    scheduler.add_job(check_inactive_users, trigger="cron", hour=10, minute=0)

    await restore_jobs_from_db()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
