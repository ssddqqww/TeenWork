import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, ADMIN_IDS
from db import init_pool, close_pool, save_user, get_user_by_telegram, get_tasks_by_skills, get_task_by_id, list_all_users, create_user_task, get_user_task_by_id, update_user_task_status, save_user_task_file, list_user_task_files, increment_user_points
from db import list_submitted_user_tasks, get_user_by_id, has_in_progress_task_for_telegram
import asyncio
import re


logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())

SKILLS = [
    "SMM",
    "Дизайн",
    "Аналітик",
    "Копірайтер",
    "Ретушер",
    "Розробник опитувань",
    "Перекладач",
    "Відеомонтажер",
]


class Reg(StatesGroup):
    name = State()
    age = State()
    skills = State()


class Submit(StatesGroup):
    files = State()


def build_skills_kb(selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for s in SKILLS:
        if s not in selected:
            rows.append([InlineKeyboardButton(text=s, callback_data=f"skill:{s}")])
    rows.append([InlineKeyboardButton(text="✅ Все", callback_data="done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard(user_id: int | None = None) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Завдання"), KeyboardButton(text="Профіль"), KeyboardButton(text="Правила/Інфо")]],
        resize_keyboard=True
    )
    if user_id is not None and user_id in ADMIN_IDS:
        keyboard.keyboard.append([KeyboardButton(text="Адмін панель")])
    return keyboard


class TaskLockMiddleware:
    async def __call__(self, handler, event, data):
        try:
            user_id = None
            is_admin = False
            state: FSMContext | None = data.get("state")
            if isinstance(event, types.Message):
                user_id = event.from_user.id
            elif isinstance(event, types.CallbackQuery):
                user_id = event.from_user.id
            if user_id is None:
                return await handler(event, data)
            if user_id in ADMIN_IDS:
                is_admin = True
            if is_admin:
                return await handler(event, data)
            if not await has_in_progress_task_for_telegram(user_id):
                return await handler(event, data)
            allowed = False
            if isinstance(event, types.Message):
                if state is not None:
                    cur = await state.get_state()
                    if cur == Submit.files.state:
                        allowed = True
                text = (event.text or "").strip()
                if text == "Здати роботу":
                    allowed = True
                if text == "Завершити здачу":
                    allowed = True
                if text == "Повернення до головного меню":
                    allowed = True
                if text.startswith("/done"):
                    allowed = True
                if event.content_type in {"photo", "document", "video", "audio", "voice"}:
                    allowed = True
                if not allowed or delete_messages:
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    return None
                return await handler(event, data)
            elif isinstance(event, types.CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
                return None
            return await handler(event, data)
        except Exception:
            return await handler(event, data)


class CleanupMiddleware:
    async def __call__(self, handler, event, data):
        try:
            state: FSMContext | None = data.get("state")
            if isinstance(event, types.Message):
                if delete_messages:
                    try:
                        await event.delete()
                    except Exception:
                        pass
                to_delete: list[int] = []
                if state is not None:
                    try:
                        stored = await state.get_data()
                        to_delete = list(stored.get("to_delete", []))
                    except Exception:
                        to_delete = []
                if to_delete:
                    chat_id = event.chat.id
                    bot = event.bot
                    if delete_messages:
                        for mid in set(to_delete):
                            try:
                                await bot.delete_message(chat_id, mid)
                            except Exception:
                                pass
                        if state is not None:
                            try:
                                await state.update_data(to_delete=[])
                            except Exception:
                                pass
            return await handler(event, data)
        except Exception:
            return await handler(event, data)


dp.message.middleware(CleanupMiddleware())
dp.callback_query.middleware(CleanupMiddleware())
dp.message.middleware(TaskLockMiddleware())
dp.callback_query.middleware(TaskLockMiddleware())

def back_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Повернення до головного меню")]],
        resize_keyboard=True
    )
    return keyboard

# Кнопка "Готовий(-а)"
def ready_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Готовий(-а)")]],
        resize_keyboard=True
    )
    return keyboard


delete_messages = False
async def cleanup_user_messages(message: types.Message, state: FSMContext):
    if delete_messages:
        try:
            await message.delete()
        except Exception:
            pass


async def track_message(state: FSMContext, message_id: int):
    try:
        data = await state.get_data()
        to_delete = list(data.get("to_delete", []))
        to_delete.append(message_id)
        await state.update_data(to_delete=to_delete)
    except Exception:
        pass
# Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    start_text = (
        "<b>Привіт, дорогий(-а) учаснику(-це). 👋</b>\n\n"
        "<b>Я - бот молодіжної організації</b>, який:\n"
        "<i>📎допоможе Тобі покращити будь-які Твої навички;</i>\n"
        "<i>📎знайде завдання відповідно до Твого досвіду, за виконання яких Ти отримуватимеш </i>"
        "<b>бонусні бали.</b>\n\n"
        "<i>⏰Після отримання завдання починається відлік часу, за який Тобі потрібно виконати </i>"
        "<i>завдання та здати роботу. Після цього адміністратор перевірить Твою роботу і або </i>"
        "дасть Тобі бонусні бали, або надішле на доопрацювання. <b>Якщо Ти не встигнеш </b>"
        "<b>виконати завдання до дедлайну, завдання анулюється.</b>\n\n"
        "-&gt; Наприклад, Ти - креативна молода особистість, умієш працювати із Canva/ "
        "створювати контент у Соцмережах, бот підбере Тобі відповідне завдання, яке Ти "
        "зможеш виконати протягом наступних 24 годин. Після цього, якщо завдання виконано "
        "якісно, Ти отримаєш бонусні бали. 🪙\n\n"
        "😉\n<b>Отож, якщо готовий(а) покращувати свої навички та отримувати за це бонуси, давай </b>"
        "<b>познайомимося!</b>"
    )
    existing = await get_user_by_telegram(message.from_user.id)
    if existing:
        await state.clear()
        user_name = existing.get("name", "")
        await message.answer(
            f"Чудово, {user_name}! Тепер обери, що хочеш зробити далі\n👇",
            reply_markup=main_menu_keyboard(message.from_user.id)
        )
        return
    await state.clear()
    sent = await message.answer(start_text, reply_markup=ready_keyboard())
    await state.update_data(to_delete=[sent.message_id, message.message_id])


@dp.message(F.text == "✅ Готовий(-а)")
async def ready_pressed(message: types.Message, state: FSMContext):
    existing = await get_user_by_telegram(message.from_user.id)
    if existing:
        await message.answer("<code>Ты уже зареган</code>", reply_markup=ReplyKeyboardRemove())
        return
    data = await state.get_data()
    to_delete = list(data.get("to_delete", []))
    to_delete.append(message.message_id)
    await state.update_data(to_delete=to_delete)
    await state.set_state(Reg.name)
    bot_msg = await message.answer("Як Тебе звати?", reply_markup=ReplyKeyboardRemove())
    await track_message(state, bot_msg.message_id)


@dp.message(Reg.name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    to_delete = list(data.get("to_delete", []))
    to_delete.append(message.message_id)
    await state.update_data(to_delete=to_delete)
    await state.set_state(Reg.age)
    bot_msg = await message.answer("Скільки Тобі років?")
    await track_message(state, bot_msg.message_id)


@dp.message(Reg.age)
async def reg_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text.strip())
    except Exception:
        await message.answer("<code>Введи число</code>")
        return
    if age < 0 or age > 100:
        await message.answer("<code>Введи число від 0 до 100</code>")
        return
    data = await state.get_data()
    to_delete = list(data.get("to_delete", []))
    to_delete.append(message.message_id)
    await state.update_data(age=age, selected=[], to_delete=to_delete)
    kb = build_skills_kb([])
    await state.set_state(Reg.skills)
    bot_msg = await message.answer("Який досвід та навички маєш", reply_markup=kb)
    await track_message(state, bot_msg.message_id)


@dp.callback_query(Reg.skills, F.data.startswith("skill:"))
async def pick_skill(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[str] = list(data.get("selected", []))
    skill = callback.data.split(":", 1)[1]
    if skill not in selected:
        selected.append(skill)
    await state.update_data(selected=selected)
    text = "Обрано: " + ",".join(selected) if selected else "Обрано: -"
    if delete_messages:
        await callback.message.edit_text(text, reply_markup=build_skills_kb(selected))
    else:
        await callback.message.answer(text, reply_markup=build_skills_kb(selected))
    await callback.answer()


@dp.callback_query(Reg.skills, F.data == "done")
async def skills_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name = data.get("name", "")
    age = int(data.get("age", 0))
    selected: list[str] = list(data.get("selected", []))
    await save_user(callback.from_user.id, name, age, selected)
    chat_id = callback.message.chat.id
    to_delete = list(data.get("to_delete", []))
    if delete_messages:
        for mid in set(to_delete):
            try:
                await callback.message.bot.delete_message(chat_id, mid)
            except Exception:
                pass
        try:
            await callback.message.bot.delete_message(chat_id, callback.message.message_id)
        except Exception:
            pass
    await state.clear()
    await callback.message.bot.send_message(
        chat_id,
        f"Чудово, {name}! Тепер обери, що хочеш зробити далі\n👇",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("review_files:"))
async def review_files(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    try:
        user_task_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    files = await list_user_task_files(user_task_id)
    if not files:
        await callback.message.answer("<code>Файлів не знайдено для цього завдання.</code>")
        await callback.answer()
        return
    await callback.message.answer(f"Файли для роботи #{user_task_id}:")
    for f in files[:20]:
        if f["file_type"] == "photo":
            await callback.message.bot.send_photo(callback.message.chat.id, f["file_id"], caption=f.get("caption"))
        elif f["file_type"] == "document":
            await callback.message.bot.send_document(callback.message.chat.id, f["file_id"], caption=f.get("caption"))
        elif f["file_type"] == "video":
            await callback.message.bot.send_video(callback.message.chat.id, f["file_id"], caption=f.get("caption"))
        elif f["file_type"] == "audio":
            await callback.message.bot.send_audio(callback.message.chat.id, f["file_id"], caption=f.get("caption"))
        elif f["file_type"] == "voice":
            await callback.message.bot.send_voice(callback.message.chat.id, f["file_id"], caption=f.get("caption"))
    await callback.answer()


@dp.callback_query(F.data.startswith("approve:"))
async def approve_task(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    try:
        user_task_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    ut = await get_user_task_by_id(user_task_id)
    if not ut:
        await callback.answer()
        return
    task = await get_task_by_id(ut["task_id"])
    points_str = task.get("title") or "0"
    digits = re.findall(r"\d+", points_str)
    points = int(digits[0]) if digits else 0
    await update_user_task_status(user_task_id, "approved")
    await increment_user_points(ut["user_id"], points)
    user = await get_user_by_id(ut["user_id"])
    if user:
        await callback.message.bot.send_message(
            user["telegram_id"],
            f"Гарна робота! <b>Твоє завдання оцінено!</b> Ти отримуєш {points} бонусних балів.\nХочеш нове завдання? Тоді натискай на кнопку <code>«Отримати завдання»</code>",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отримати завдання")],[KeyboardButton(text="Перевірити баланс")]], resize_keyboard=True)
        )
    if delete_messages:
        await callback.message.edit_text("<code>Зараховано</code>")
    else:
        await callback.message.answer("<code>Зараховано</code>")
    await callback.answer()


@dp.callback_query(F.data.startswith("reject:"))
async def reject_task(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    try:
        user_task_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    ut = await get_user_task_by_id(user_task_id)
    if not ut:
        await callback.answer()
        return
    await update_user_task_status(user_task_id, "rejected")
    user = await get_user_by_id(ut["user_id"])
    if user:
        await callback.message.bot.send_message(
            user["telegram_id"],
            "❌На жаль, <b>Ти не виконав/ виконала усі необхідні пункти</b>, які включало завдання.\nАдміністратор повернув Тобі завдання на <b>доопрацювання</b>. Надішли, будь ласка, свою\nроботу повторно після виконання завдання.",
        )
    if delete_messages:
        await callback.message.edit_text("<code>Повернуто на доопрацювання</code>")
    else:
        await callback.message.answer("<code>Повернуто на доопрацювання</code>")
    await callback.answer()


@dp.message(F.text == "Перевірити баланс")
async def check_balance(message: types.Message):
    user = await get_user_by_telegram(message.from_user.id)
    points = (user or {}).get("points", 0)
    await message.answer(
        f"⚡️\nНа вашому рахунку {points} балів. Щоб отримати більше балів – виконуйте більше\nзавдань!",
        reply_markup=back_menu_keyboard()
    )


@dp.message(F.text == "Правила/Інфо")
async def rules_info(message: types.Message):
    text = (
        "ℹ️ Тут короткі правила:\n"
        "👇🏼\n"
        "1. Виконуй завдання у <b>визначений час</b>.\n"
        "2. Якщо <b>робота якісна</b> — отримуєш <b>бали</b>.\n"
        "3. Якщо <b>запізнився/здав неякісно</b> — завдання <b>анулюється</b> або повертається на\n"
        "<b>доопрацювання</b>\n"
        "Якщо усе зрозуміло, спробуй виконати своє завдання!\n"
        "⚡️"
    )
    await message.answer(text, reply_markup=back_menu_keyboard())


def build_tasks_kb(tasks: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in tasks:
        skill = t.get("skill_required") or ""
        tid = t.get("id")
        rows.append([InlineKeyboardButton(text=skill, callback_data=f"task:{tid}")])
    if not rows:
        rows = [[InlineKeyboardButton(text="Немає завдань", callback_data="noop")]]
    rows.append([InlineKeyboardButton(text="⬅️ До меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(F.text == "Завдання")
async def list_tasks(message: types.Message):
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("<b>Спочатку зареєструйся:</b> <code>/start</code>", reply_markup=ready_keyboard())
        return
    skills_raw = user.get("skills", "")
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
    tasks = await get_tasks_by_skills(skills)
    kb = build_tasks_kb(tasks)
    sent = await message.answer("Оберіть завдання за вашими навичками:", reply_markup=kb)
    try:
        state = dp.fsm.get_context(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id)  # type: ignore
        await track_message(state, sent.message_id)  # type: ignore
    except Exception:
        pass


@dp.message(F.text == "Отримати завдання")
async def get_task_again(message: types.Message):
    await list_tasks(message)


@dp.callback_query(F.data.startswith("task:"))
async def show_task(callback: types.CallbackQuery):
    try:
        task_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    task = await get_task_by_id(task_id)
    if not task:
        await callback.answer("<code>Завдання не знайдено</code>", show_alert=False)
        return
    skill = task.get("skill_required") or ""
    description = task.get("description") or ""
    points = task.get("title") or ""
    text = f"[{skill}]\n\n{description}\n\nБали: {points}"
    buttons = [
        [InlineKeyboardButton(text="Прийняти завдання", callback_data=f"accept:{task_id}")],
        [InlineKeyboardButton(text="⬅️ До меню", callback_data="back_to_menu")]
    ]
    if delete_messages:
        await callback.message.edit_text("<code>Повернуто на доопрацювання</code>")
    else:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("accept:"))
async def accept_task(callback: types.CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    # map telegram_id to Users.id
    user = await get_user_by_telegram(callback.from_user.id)
    if not user:
        await callback.answer("<code>Спочатку зареєструйся</code>", show_alert=True)
        return
    user_task_id = await create_user_task(user_id=user["id"], task_id=task_id)
    task = await get_task_by_id(task_id)
    deadline_hours = int(task.get("deadline_hours") or 0)
    if delete_messages:
        await callback.message.edit_text("Завдання <b>прийнято</b>. Можеш надсилати роботу, коли будеш готовий.")
    else:
        await callback.message.answer("Завдання <b>прийнято</b>. Можеш надсилати роботу, коли будеш готовий.")
    await callback.message.answer(
        "Коли будеш готовий здати роботу — натисни кнопку нижче:",
        reply_markup=submit_keyboard(user_task_id)
    )
    await state.update_data(current_user_task_id=user_task_id)
    bot: Bot = callback.message.bot
    asyncio.create_task(schedule_halfway_reminder(bot, user_task_id, callback.message.chat.id, deadline_hours))
    await callback.answer()


def submit_keyboard(user_task_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Здати роботу")], [KeyboardButton(text="Повернення до головного меню")]],
        resize_keyboard=True
    )
    return kb


@dp.message(F.text == "Здати роботу")
async def submit_work_start(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_task_id = data.get("current_user_task_id")
    if not user_task_id:
        await message.answer("<code>Немає активного завдання.</code>")
        return
    await state.set_state(Submit.files)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Завершити здачу")], [KeyboardButton(text="Повернення до головного меню")]],
        resize_keyboard=True
    )
    await message.answer("<b>Надішли файл(и)</b> з доказами виконання. Коли завершиш — натисни <code>«Завершити здачу»</code>", reply_markup=kb)


@dp.message(Submit.files, F.content_type.in_({"photo", "document", "video", "audio", "voice"}))
async def collect_files(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_task_id = int(data.get("current_user_task_id"))
    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"
    if file_id and file_type:
        await save_user_task_file(user_task_id, file_id, file_type, message.caption)
        await message.answer("<code>Файл збережено.</code> Надішли ще або натисни <code>«Завершити здачу»</code>")


@dp.message(Submit.files, F.text == "Завершити здачу")
async def submit_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_task_id = int(data.get("current_user_task_id"))
    await update_user_task_status(user_task_id, "submitted")
    await state.clear()
    await message.answer(
        "🎉 Твоє завдання <b>успішно здано</b>* Зачекай, поки його <b>перевірить адміністратор!</b>",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )


@dp.message(F.text == "Профіль")
async def show_profile(message: types.Message, state: FSMContext):
    await cleanup_user_messages(message, state)
    user = await get_user_by_telegram(message.from_user.id)
    if not user:
        sent = await message.answer("Спочатку зареєструйся: <code>/start</code>", reply_markup=ready_keyboard())
        await state.update_data(to_delete=[sent.message_id])
        return
    name = user.get("name", "")
    age = user.get("age", 0)
    skills_raw = user.get("skills", "")
    skills_display = ", ".join([s for s in skills_raw.split(",") if s]) if skills_raw else "-"
    points = user.get("points", 0)
    text = (
        f"👇🏼📊 Ось твій профіль {name}:\n"
        f"👤 Імʼя: {name}\n"
        f"🎂 Вік: {age}\n"
        f"💡 Навички: {skills_display}\n"
        f"🪙 Бали: {points}\n"
        f"Бажаєш перейти до виконання завдань чи читання правил?"
    )
    sent = await message.answer(text, reply_markup=back_menu_keyboard())
    await state.update_data(to_delete=[sent.message_id])


@dp.message(F.text == "Повернення до головного меню")
async def back_to_main_menu(message: types.Message):
    user = await get_user_by_telegram(message.from_user.id)
    name = (user or {}).get("name", "")
    await message.answer(
        f"Чудово, {name}! Тепер обери, що хочеш зробити далі\n👇",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data == "back_to_menu")
async def back_inline_to_menu(callback: types.CallbackQuery):
    await callback.answer()
    user = await get_user_by_telegram(callback.from_user.id)
    name = (user or {}).get("name", "")
    await callback.message.answer(
        f"Чудово, {name}! Тепер обери, що хочеш зробити далі\n👇",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Усі користувачі"), KeyboardButton(text="Перевірка робіт")], [KeyboardButton(text="Повернення до головного меню")]],
        resize_keyboard=True
    )
    return keyboard


async def schedule_halfway_reminder(bot: Bot, user_task_id: int, user_chat_id: int, deadline_hours: int):
    try:
        if not deadline_hours or deadline_hours <= 0:
            return
        half_seconds = int(deadline_hours * 3600 / 2)
        await asyncio.sleep(half_seconds)
        ut = await get_user_task_by_id(user_task_id)
        if not ut or ut.get("status") != "in_progress":
            return
        await bot.send_message(
            user_chat_id,
            "<b>⏳Увага!</b> У Тебе залишилася <b>половина часу</b> на <i>виконання завдання</i>. Будь ласка,\n<i>виконай його</i> до зазначеного дедлайну."
        )
    except Exception:
        pass


@dp.message(F.text == "Адмін панель")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("<code>Недостатньо прав.</code>")
        return
    await message.answer("<code>Адмін панель</code>", reply_markup=admin_menu_keyboard())


@dp.message(F.text == "Усі користувачі")
async def admin_list_users(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("<code>Недостатньо прав.</code>")
        return
    users = await list_all_users()
    if not users:
        await message.answer("<code>Недостатньо прав.</code>")
        return
    chunk: list[str] = []
    sent_any = False
    for u in users:
        line = f"#{u['id']} | {u.get('name','')} | {u.get('age','-')} | {u.get('skills','-')} | {u.get('points',0)}"
        chunk.append(line)
        if len("\n".join(chunk)) > 3500:
            await message.answer("\n".join(chunk))
            sent_any = True
            chunk = []
    if chunk:
        await message.answer("\n".join(chunk))
        sent_any = True
    if not sent_any:
        await message.answer("<code>Користувачів не знайдено.</code>")


@dp.message(F.text == "Перевірка робіт")
async def admin_review_stub(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("<code>Недостатньо прав.</code>")
        return
    await message.answer("<code>Список зданих робіт завантажується...</code>")
    submitted = await list_submitted_user_tasks()
    if not submitted:
        await message.answer("<code>Немає зданих робіт.</code>")
        return
    for item in submitted[:20]:
        text = (
            f"Задача #{item['task_id']} [{item.get('skill_required','')}]\n"
            f"Опис: {item.get('description','')}\n\n"
            f"Користувач: #{item['user_id']} {item.get('user_name','')}\n"
            f"Бали: {item.get('title','')}\n"
        )
        buttons = [
            [InlineKeyboardButton(text="Переглянути файли", callback_data=f"review_files:{item['user_task_id']}")],
            [InlineKeyboardButton(text="✅ Зарахувати", callback_data=f"approve:{item['user_task_id']}")],
            [InlineKeyboardButton(text="❌ Повернути на доопрацювання", callback_data=f"reject:{item['user_task_id']}")],
        ]
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
async def main():
    await init_pool()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await dp.start_polling(bot)
    finally:
        await close_pool()
    
if __name__ == "__main__":
    asyncio.run(main())
