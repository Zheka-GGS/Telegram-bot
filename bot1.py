import asyncio
import logging
import random
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Логи
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота (вставь свой от @BotFather)
TOKEN = "7827778941:AAErsqM4phOqhQY4xH3UKJMHuA_V-Wrtakk"

# Переводы
translations = {
    'ru': {
        'welcome': 'Добро пожаловать!',
        'choose_language': 'Выбери язык:',
        'language_set': 'Язык установлен!',
        'found_partner': '✅ Нашёл!',
        'waiting': '⏳ Жди, ищу...',
        'already_in_chat': '❌ Ты уже в чате!',
        'already_in_queue': '⏳ Ты уже в очереди, жди!',
        'banned': '❌ Ты забанен, братан!',
        'partner_left': '😶 Свалил, ищи нового. /next',
        'quit': '🚶 Свалил, пока!',
        'admin_prompt': '🔑 Введи код админа:',
        'admin_success': '✅ Ты админ! Выбираю рандомный чат...',
        'no_active_chats': '😶 Нет активных чатов.',
        'wrong_code': '❌ Код неверный!',
        'ban_success': '✅ Юзер {user_id} забанен.',
        'unban_success': '✅ Юзер {user_id} разбанен.',
        'ban_usage': '❌ Введи /ban <user_id>',
        'unban_usage': '❌ Введи /unban <user_id>',
    },
    'en': {
        'welcome': 'Welcome to the hood!',
        'choose_language': 'Choose language:',
        'language_set': 'Language set!',
        'found_partner': '✅ Found you a dude, chat away!',
        'waiting': '⏳ Waiting, looking for a dude...',
        'already_in_chat': '❌ You’re already in a chat!',
        'already_in_queue': '⏳ You’re already in the queue, wait!',
        'banned': '❌ You’re banned, dude!',
        'partner_left': '😶 Dude left, find a new one. /next',
        'quit': '🚶 Bailed from the hood, peace!',
        'admin_prompt': '🔑 Enter admin code:',
        'admin_success': '✅ You’re admin! Picking a random chat...',
        'no_active_chats': '😶 No active chats.',
        'wrong_code': '❌ Wrong code!',
        'ban_success': '✅ User {user_id} banned.',
        'unban_success': '✅ User {user_id} unbanned.',
        'ban_usage': '❌ Use /ban <user_id>',
        'unban_usage': '❌ Use /unban <user_id>',
    }
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        language TEXT DEFAULT 'en'
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_chats (
        user_id INTEGER,
        partner_id INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY
    )''')
    conn.commit()
    return conn

# Сохранение данных
def save_to_db(conn, table, data):
    cursor = conn.cursor()
    if table == 'users':
        cursor.execute('INSERT OR REPLACE INTO users (user_id, language) VALUES (?, ?)', data)
    elif table == 'active_chats':
        cursor.execute('INSERT OR REPLACE INTO active_chats (user_id, partner_id) VALUES (?, ?)', data)
        cursor.execute('INSERT OR REPLACE INTO active_chats (user_id, partner_id) VALUES (?, ?)', (data[1], data[0]))
    elif table == 'banned_users':
        cursor.execute('INSERT OR REPLACE INTO banned_users (user_id) VALUES (?)', (data,))
    conn.commit()
    logger.info(f"Saved to {table}: {data}")

# Удаление данных
def delete_from_db(conn, table, user_id, partner_id=None):
    cursor = conn.cursor()
    if table == 'active_chats':
        cursor.execute('DELETE FROM active_chats WHERE user_id = ? OR partner_id = ?', (user_id, user_id))
        if partner_id:
            cursor.execute('DELETE FROM active_chats WHERE user_id = ? OR partner_id = ?', (partner_id, partner_id))
    elif table == 'banned_users':
        cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    conn.commit()
    logger.info(f"Deleted from {table}: user_id={user_id}, partner_id={partner_id}")

# Загрузка данных при старте
def load_from_db(conn):
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, language FROM users')
    user_languages = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute('SELECT user_id FROM banned_users')
    banned_users = set(row[0] for row in cursor.fetchall())
    cursor.execute('SELECT user_id, partner_id FROM active_chats')
    active_chats = {row[0]: row[1] for row in cursor.fetchall()}
    logger.info(f"Loaded: user_languages={user_languages}, banned_users={banned_users}, active_chats={active_chats}")
    return user_languages, banned_users, active_chats

# Инициализация
conn = init_db()
user_languages, banned_users, active_chats = load_from_db(conn)
waiting_queue = []  # Очередь в памяти

# FSM для админа
class AdminStates(StatesGroup):
    waiting_code = State()
    monitoring = State()

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot)

# Функция для соединения юзеров
async def connect_users(user_id, lang):
    if len(waiting_queue) >= 2:
        # Ищем партнёра, который не текущий юзер
        partner_id = next((uid for uid in waiting_queue if uid != user_id), None)
        if partner_id:
            waiting_queue.remove(user_id)
            waiting_queue.remove(partner_id)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            save_to_db(conn, 'active_chats', (user_id, partner_id))
            logger.info(f"Connected {user_id} with {partner_id}, active_chats={active_chats}")
            await bot.send_message(partner_id, translations[user_languages.get(partner_id, 'en')]['found_partner'])
            await bot.send_message(user_id, translations[lang]['found_partner'])

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"User {user_id} triggered /start, waiting_queue={waiting_queue}, active_chats={active_chats}")
    if user_id in banned_users:
        await message.answer(translations.get(user_languages.get(user_id, 'en'))['banned'])
        return
    if user_id in active_chats:
        await message.answer(translations[user_languages.get(user_id, 'en')]['already_in_chat'])
        return
    if user_id not in user_languages:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="lang_ru")],
            [InlineKeyboardButton(text="English", callback_data="lang_en")]
        ])
        await message.answer(translations['en']['choose_language'], reply_markup=keyboard)
        return
    lang = user_languages[user_id]
    # Удаляем дубликаты из очереди
    waiting_queue[:] = [uid for uid in waiting_queue if uid != user_id]
    # Добавляем юзера в очередь
    if user_id not in waiting_queue:
        waiting_queue.append(user_id)
        logger.info(f"User {user_id} added to waiting_queue, waiting_queue={waiting_queue}")
        await message.answer(translations[lang]['waiting'])
    # Проверяем, можно ли соединить
    await connect_users(user_id, lang)

# Выбор языка
@dp.callback_query()
async def process_language_choice(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    lang = callback_query.data.split('_')[1]
    user_languages[user_id] = lang
    save_to_db(conn, 'users', (user_id, lang))
    logger.info(f"User {user_id} chose language: {lang}")
    await bot.send_message(user_id, translations[lang]['welcome'])
    await callback_query.message.delete()
    # Автоматически запускаем поиск
    if user_id not in active_chats and user_id not in waiting_queue:
        waiting_queue.append(user_id)
        logger.info(f"User {user_id} added to waiting_queue after language choice, waiting_queue={waiting_queue}")
        await bot.send_message(user_id, translations[lang]['waiting'])
        await connect_users(user_id, lang)

# Команда /next
@dp.message(Command("next"))
async def next_chat(message: types.Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} triggered /next, active_chats={active_chats}, waiting_queue={waiting_queue}")
    # Если юзер в чате, разрываем его и уведомляем партнёра
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        del active_chats[user_id]
        del active_chats[partner_id]
        delete_from_db(conn, 'active_chats', user_id, partner_id)
        logger.info(f"Disconnected {user_id} from {partner_id}, active_chats={active_chats}")
        await bot.send_message(partner_id, translations[user_languages.get(partner_id, 'en')]['partner_left'])
    # Удаляем дубликаты из очереди
    waiting_queue[:] = [uid for uid in waiting_queue if uid != user_id]
    # Добавляем юзера в очередь
    if user_id not in waiting_queue:
        waiting_queue.append(user_id)
        logger.info(f"User {user_id} added to waiting_queue, waiting_queue={waiting_queue}")
        await message.answer(translations[lang]['waiting'])
    # Проверяем, можно ли соединить
    await connect_users(user_id, lang)

# Команда /quit
@dp.message(Command("quit"))
async def quit_chat(message: types.Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} triggered /quit, active_chats={active_chats}, waiting_queue={waiting_queue}")
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        del active_chats[user_id]
        del active_chats[partner_id]
        delete_from_db(conn, 'active_chats', user_id, partner_id)
        await bot.send_message(partner_id, translations[user_languages.get(partner_id, 'en')]['partner_left'])
        logger.info(f"Disconnected {user_id} from {partner_id}, active_chats={active_chats}")
    if user_id in waiting_queue:
        waiting_queue.remove(user_id)
        logger.info(f"Removed {user_id} from waiting_queue, waiting_queue={waiting_queue}")
    await message.answer(translations[lang]['quit'])

# Команда /language
@dp.message(Command("language"))
async def change_language(message: types.Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} triggered /language with text: {message.text}")
    # Парсим аргументы вручную
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    if args in ['ru', 'en']:
        user_languages[user_id] = args
        save_to_db(conn, 'users', (user_id, args))
        await message.answer(translations[args]['language_set'])
    else:
        await message.answer("Только ru или en, братан!" if lang == 'ru' else "Only ru or en, dude!")

# Пересылка сообщений
@dp.message()
async def forward_message(message: types.Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} sent message, active_chats={active_chats}")
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        if message.text:
            await bot.send_message(partner_id, message.text)
        elif message.photo:
            await bot.send_photo(partner_id, message.photo[-1].file_id)
        elif message.video:
            await bot.send_video(partner_id, message.video.file_id)
        elif message.audio:
            await bot.send_audio(partner_id, message.audio.file_id)
        elif message.document:
            await bot.send_document(partner_id, message.document.file_id)
        elif message.sticker:
            await bot.send_sticker(partner_id, message.sticker.file_id)
    else:
        await message.answer(translations[lang]['not_in_chat'])

# Админ-панель: вход
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} triggered /admin")
    await message.answer(translations[lang]['admin_prompt'])
    await state.set_state(AdminStates.waiting_code)

# Проверка кода админа
@dp.message(AdminStates.waiting_code)
async def check_admin_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"User {user_id} entered admin code: {message.text}")
    if message.text == "20071807":
        await message.answer(translations[lang]['admin_success'])
        await state.set_state(AdminStates.monitoring)
        if active_chats:
            user_id = random.choice(list(active_chats.keys()))
            partner_id = active_chats[user_id]
            await message.answer(f"Ты в чате / You're in chat: {user_id} <-> {partner_id}\n"
                                f"Команды / Commands: /ban <id>, /unban <id>")
        else:
            await message.answer(translations[lang]['no_active_chats'])
    else:
        await message.answer(translations[lang]['wrong_code'])
        await state.clear()

# Бан юзера
@dp.message(AdminStates.monitoring, Command("ban"))
async def ban_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"Admin {user_id} triggered /ban")
    try:
        user_id_to_ban = int(message.text.split()[1])
        banned_users.add(user_id_to_ban)
        save_to_db(conn, 'banned_users', user_id_to_ban)
        await message.answer(translations[lang]['ban_success'].format(user_id=user_id_to_ban))
        if user_id_to_ban in active_chats:
            partner_id = active_chats[user_id_to_ban]
            del active_chats[user_id_to_ban]
            del active_chats[partner_id]
            delete_from_db(conn, 'active_chats', user_id_to_ban, partner_id)
            await bot.send_message(partner_id, translations[user_languages.get(partner_id, 'en')]['partner_left'])
    except (IndexError, ValueError):
        await message.answer(translations[lang]['ban_usage'])

# Разбан юзера
@dp.message(AdminStates.monitoring, Command("unban"))
async def unban_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'en')
    logger.info(f"Admin {user_id} triggered /unban")
    try:
        user_id_to_unban = int(message.text.split()[1])
        banned_users.discard(user_id_to_unban)
        delete_from_db(conn, 'banned_users', user_id_to_unban)
        await message.answer(translations[lang]['unban_success'].format(user_id=user_id_to_unban))
    except (IndexError, ValueError):
        await message.answer(translations[lang]['unban_usage'])

# Запуск бота
async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())