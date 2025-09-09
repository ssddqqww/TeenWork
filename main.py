import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import Command
from config import BOT_TOKEN

# Токен Знаходится в config.py

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()

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
    
async def main():
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)
    
if __name__ == "__main__":
    asyncio.run(main())