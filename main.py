import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from db import init_pool, close_pool, save_user


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


def build_skills_kb(selected: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for s in SKILLS:
        if s not in selected:
            rows.append([InlineKeyboardButton(text=s, callback_data=f"skill:{s}")])
    rows.append([InlineKeyboardButton(text="✅ Все", callback_data="done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# Кнопка "Готовий(-а)"
def ready_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Готовий(-а)")]],
        resize_keyboard=True
    )
    return keyboard
# Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    start_text = (
        "Привіт, дорогий(-а) учаснику(-це). 👋\n\n"
        "Я - бот молодіжної організації, який\n"
        "📎допоможе Тобі покращити будь-які Твої навички;\n"
        "📎знайде завдання відповідно до Твого досвіду, за виконання яких Ти отримуватимеш "
        "бонусні бали.\n\n"
        "⏰Після отримання завдання починається відлік часу, за який Тобі потрібно виконати "
        "завдання та здати роботу. Після цього адміністратор перевірить Твою роботу і або "
        "дасть Тобі бонусні бали, або надішле на доопрацювання. *Якщо Ти не встигнеш "
        "виконати завдання до дедлайну, завдання анулюється.\n\n"
        "-> Наприклад, Ти - креативна молода особистість, умієш працювати із Canva/ "
        "створювати контент у Соцмережах, бот підбере Тобі відповідне завдання, яке Ти "
        "зможеш виконати протягом наступних 24 годин. Після цього, якщо завдання виконано "
        "якісно, Ти отримаєш бонусні бали. 🪙\n\n"
        "😉\nОтож, якщо готовий(а) покращувати свої навички та отримувати за це бонуси, давай "
        "познайомимося!"
    )
    
    await message.answer(start_text, reply_markup=ready_keyboard())


@dp.message(F.text == "✅ Готовий(-а)")
async def ready_pressed(message: types.Message, state: FSMContext):
    await state.set_state(Reg.name)
    await message.answer("Як Тебе звати?")


@dp.message(Reg.name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Reg.age)
    await message.answer("Скільки Тобі років?")


@dp.message(Reg.age)
async def reg_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text.strip())
    except Exception:
        await message.answer("Введи число")
        return
    await state.update_data(age=age, selected=[])
    kb = build_skills_kb([])
    await state.set_state(Reg.skills)
    await message.answer("Який досвід та навички маєш", reply_markup=kb)


@dp.callback_query(Reg.skills, F.data.startswith("skill:"))
async def pick_skill(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[str] = list(data.get("selected", []))
    skill = callback.data.split(":", 1)[1]
    if skill not in selected:
        selected.append(skill)
    await state.update_data(selected=selected)
    text = "Обрано: " + ", ".join(selected) if selected else "Обрано: -"
    await callback.message.edit_text(text, reply_markup=build_skills_kb(selected))
    await callback.answer()


@dp.callback_query(Reg.skills, F.data == "done")
async def skills_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name = data.get("name", "")
    age = int(data.get("age", 0))
    selected: list[str] = list(data.get("selected", []))
    await save_user(callback.from_user.id, name, age, selected)
    await state.clear()
    await callback.message.edit_text("Готово")
    await callback.answer()
    
async def main():
    await init_pool()
    bot = Bot(BOT_TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await close_pool()
    
if __name__ == "__main__":
    asyncio.run(main())