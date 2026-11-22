import asyncio
import sqlite3
import random
import string
import logging
import re
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as _InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton as _KeyboardButton, LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# ========== КОНФИГ ==========
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "Rep_Up_bot").lstrip("@")
ADMIN_IDS = list({8959461245, 7684821454, *[int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]})
CHANNEL_ID = os.getenv("CHANNEL_ID", "@Rep_Up").strip()
PAYOUT_CHANNEL_ID = os.getenv("PAYOUT_CHANNEL_ID", "@Rep_Up_scren").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "mamutov_r")

COST_PER_TASK = 5  # стоимость одного внутреннего задания в Stars

# ========== СЛОВА ДЛЯ ПРОВЕРКИ ==========
BAD_WORDS = [
    "хуй", "хуя", "хую", "хуем", "хуе", "хуё", "пизд", "пизда", "пиздец",
    "бля", "блять", "блядь", "еб", "еба", "ебу", "ебал", "ебать", "ебан",
    "гандон", "гнида", "говно", "дерьмо", "мудак", "мудила", "уебок",
    "пидор", "пидр", "сука", "сучка", "шлюха", "курва", "мент", "лох",
    "дебил", "даун", "тупой", "олень", "козел", "осел", "свин", "свинья",
    "залуп", "очко", "жопа", "жоп", "срать", "срал", "насрать", "засра",
    "подонок", "тварь", "петух", "петушара", "петуш"
]

STAR_GIFT_OPTIONS = {
    15: {"name": "🐻 Мишка", "stars": 15},
    25: {"name": "🎁 Подарок 25⭐", "stars": 25},
    50: {"name": "🎁 Подарок 50⭐", "stars": 50},
    100: {"name": "🎁 Подарок 100⭐", "stars": 100},
    250: {"name": "🎁 Подарок 250⭐", "stars": 250},
    500: {"name": "🎁 Подарок 500⭐", "stars": 500},
    1000: {"name": "🎁 Подарок 1000⭐", "stars": 1000},
}

DB_NAME = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"
os.makedirs(os.path.dirname(os.path.abspath(DB_NAME)), exist_ok=True)
logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            language TEXT DEFAULT 'ru',
            balance INTEGER DEFAULT 1,
            ref_code TEXT UNIQUE,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0,
            device_id TEXT,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            username TEXT,
            theme TEXT,
            count INTEGER,
            review_type TEXT,
            example_text TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            user_id INTEGER,
            review_text TEXT,
            created_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            request_id TEXT UNIQUE,
            stars_amount INTEGER,
            get_amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            get_amount INTEGER,
            stars_amount INTEGER,
            gift_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_get INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            bonus_get INTEGER,
            uses_limit INTEGER,
            used_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER,
            user_id INTEGER,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            bonus_get INTEGER,
            start_date TEXT,
            end_date TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contest_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contest_id INTEGER,
            user_id INTEGER,
            completed_tasks INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stars_amount INTEGER,
            get_amount INTEGER,
            payment_id TEXT UNIQUE,
            status TEXT DEFAULT 'completed',
            created_at TEXT,
            referral_bonus INTEGER DEFAULT 0,
            referrer_id INTEGER
        )
    """)
    
    cur.execute("""CREATE TABLE IF NOT EXISTS bot_admins (
        user_id INTEGER PRIMARY KEY, permissions TEXT NOT NULL DEFAULT '{}' , created_at TEXT NOT NULL
    )""")
    cur.execute("INSERT OR IGNORE INTO bot_admins (user_id, permissions, created_at) VALUES (?, '{}', ?)", (8959461245, datetime.now().isoformat()))
    import json
    default_admin_permissions = json.dumps({k: True for k in ['users','balance','payments','broadcast','bans','promos','contests','channel','task_price','reset_db']})
    cur.execute("INSERT OR IGNORE INTO bot_admins (user_id, permissions, created_at) VALUES (?, ?, ?)", (7684821454, default_admin_permissions, datetime.now().isoformat()))
    for configured_admin in ADMIN_IDS:
        if configured_admin not in (8959461245,):
            cur.execute("INSERT OR IGNORE INTO bot_admins (user_id, permissions, created_at) VALUES (?, ?, ?)", (configured_admin, default_admin_permissions, datetime.now().isoformat()))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    payment_columns = {row[1] for row in cur.execute("PRAGMA table_info(payments)").fetchall()}
    if "referral_bonus" not in payment_columns:
        cur.execute("ALTER TABLE payments ADD COLUMN referral_bonus INTEGER DEFAULT 0")
    if "referrer_id" not in payment_columns:
        cur.execute("ALTER TABLE payments ADD COLUMN referrer_id INTEGER")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id)")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_id', ?)", (CHANNEL_ID,))
    cur.execute("UPDATE settings SET value = ? WHERE key = 'channel_id' AND value = '@Client_Voice_NEWS'", (CHANNEL_ID,))
    # One-time conversion from legacy GET subunits (1000 = 1 Star) to whole Stars.
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('currency_stars_migrated', '0')")
    cur.execute("SELECT value FROM settings WHERE key = 'currency_stars_migrated'")
    if cur.fetchone()[0] != '1':
        for table, column in [("users", "balance"), ("deposit_requests", "get_amount"),
                              ("withdraw_requests", "get_amount"), ("referrals", "bonus_get"),
                              ("promo_codes", "bonus_get"), ("contests", "bonus_get"),
                              ("payments", "get_amount")]:
            cur.execute(f"UPDATE {table} SET {column} = CAST({column} / 1000 AS INTEGER) WHERE {column} IS NOT NULL")
        cur.execute("UPDATE settings SET value = '1' WHERE key = 'currency_stars_migrated'")
    cur.execute("""CREATE TABLE IF NOT EXISTS user_channels (
        user_id INTEGER PRIMARY KEY, channel_id TEXT NOT NULL, channel_title TEXT,
        connected_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS creator_limits (
        user_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, creator_id)
    )""")
    # Переносим старые выполнения в ограничитель: один исполнитель на одного заказчика.
    cur.execute("""INSERT OR IGNORE INTO creator_limits (user_id, creator_id, created_at)
        SELECT tc.user_id, t.creator_id, MIN(tc.created_at)
        FROM task_completions tc JOIN tasks t ON t.id = tc.task_id
        GROUP BY tc.user_id, t.creator_id""")
    conn.commit()
    conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    result = cur.fetchall()
    conn.close()
    return result

MASTER_ADMIN_ID = 8959461245
ADMIN_PERMISSIONS = {
    'users': 'Пользователи', 'balance': 'Изменение баланса', 'payments': 'Заявки и выплаты',
    'broadcast': 'Рассылка', 'bans': 'Блокировки', 'promos': 'Промокоды',
    'contests': 'Конкурсы', 'channel': 'Управление каналом', 'task_price': 'Цена задания',
    'reset_db': 'Сброс базы данных'
}

def admin_permissions(user_id):
    if int(user_id) == MASTER_ADMIN_ID:
        return set(ADMIN_PERMISSIONS)
    row = db_execute("SELECT permissions FROM bot_admins WHERE user_id = ?", (int(user_id),))
    if not row:
        return set()
    try:
        import json
        data = json.loads(row[0][0] or '{}')
        return {k for k, v in data.items() if v}
    except Exception:
        return set()

def is_admin(user_id, permission=None):
    if int(user_id) == MASTER_ADMIN_ID:
        return True
    row = db_execute("SELECT user_id FROM bot_admins WHERE user_id = ?", (int(user_id),))
    if not row:
        return False
    perms = admin_permissions(user_id)
    return bool(perms) if permission is None else permission in perms

def get_task_cost():
    row = db_execute("SELECT value FROM settings WHERE key = 'cost_per_task'")
    try:
        return max(1, int(row[0][0])) if row else COST_PER_TASK
    except Exception:
        return COST_PER_TASK


def get_user(user_id):
    result = db_execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result[0] if result else None

def get_user_by_device(device_id):
    result = db_execute("SELECT * FROM users WHERE device_id = ?", (device_id,))
    return result[0] if result else None

def create_user(user_id, username, device_id, ref_code=None, language='ru'):
    existing = get_user(user_id)
    if existing:
        return existing
    
    if device_id:
        existing_device = get_user_by_device(device_id)
        if existing_device and existing_device[0] != user_id:
            return None
    
    ref_code_new = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    referred_by = None
    
    if ref_code:
        try:
            referrer_id = int(ref_code)
            referrer = get_user(referrer_id)
            if referrer:
                referred_by = referrer_id
        except:
            referrer = db_execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
            if referrer:
                referred_by = referrer[0][0]
    
    db_execute("""
        INSERT INTO users (user_id, username, language, balance, ref_code, referred_by, device_id, is_banned, is_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, language, 1, ref_code_new, referred_by, device_id, 0, 0, datetime.now().isoformat()))
    
    if referred_by:
        # Бонус за регистрацию убран: 50% начисляется только с подтверждённых пополнений.
        db_execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id, bonus_get, created_at) VALUES (?, ?, 0, ?)",
                   (referred_by, user_id, datetime.now().isoformat()))
        try:
            asyncio.create_task(bot.send_message(referred_by,
                f"🎉 По вашей ссылке зарегистрировался @{username or user_id}! Теперь вы получаете 50% от его подтверждённых пополнений."))
        except RuntimeError:
            pass
    
    return get_user(user_id)

def add_balance(user_id, amount):
    db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

def subtract_balance(user_id, amount):
    user = get_user(user_id)
    if user and user[3] >= amount:
        db_execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        return True
    return False

def generate_request_id():
    return f"REQ-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=6))}"

def get_channel():
    result = db_execute("SELECT value FROM settings WHERE key = 'channel_id'")
    return result[0][0] if result else None

def get_user_channel(user_id):
    result = db_execute("SELECT channel_id, channel_title FROM user_channels WHERE user_id = ?", (user_id,))
    return result[0] if result else None

def claim_creator_once(user_id, creator_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO creator_limits (user_id, creator_id, created_at) VALUES (?, ?, ?)",
                (user_id, creator_id, datetime.now().isoformat()))
    claimed = cur.rowcount == 1
    conn.commit()
    conn.close()
    return claimed

def set_channel(channel):
    db_execute("UPDATE settings SET value = ? WHERE key = 'channel_id'", (channel,))

def check_bad_words(text):
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            return True
    return False

def check_theme_match(text, theme):
    text_lower = text.lower()
    theme_words = theme.lower().split()
    
    if len(theme_words) == 1:
        return theme_words[0] in text_lower
    
    for word in theme_words:
        if len(word) > 2 and word in text_lower:
            return True
    return False

# ========== ЯЗЫКИ ==========
LANGUAGES = {
    'ru': {
        'start': "👋 Добро пожаловать в Rep Up, {username}!\n\n📝 Выберите раздел:\n💰 Баланс: {balance} Stars",
        'banned': "🚫 Вы забанены!",
        'subscribe': "📢 Подпишись на канал: {channel}",
        'check_sub': "✅ Подписка подтверждена!",
        'not_sub': "❌ Вы не подписались!",
        'balance': "💰 Баланс: {balance} Stars\nБаланс и награды указаны в Stars",
        'referrals': "👥 Рефералы: {count}\n💸 Вы получаете 50% от подтверждённых пополнений друзей.\n🔗 Ссылка: https://t.me/{bot}?start={code}",
        'stats': "📊 Статистика\n👥 {users}\n📋 {tasks}\n✅ {completed}\n💰 {balance} Stars",
        'no_tasks': "📭 Нет активных заданий",
        'task_created': "✅ Задание #{task_id} создано!",
        'task_completed': "✅ Отзыв для #{task_id} принят!\n💰 +5 Stars\nБаланс: {balance} Stars",
        'not_enough': "❌ Недостаточно средств! Нужно {cost} Stars, у вас {balance} Stars",
        'review_forward': "📩 Новый отзыв от: @{username}",
        'short_review': "❌ Минимум 15 символов",
        'bad_words': "❌ Обнаружены нецензурные слова! Перепишите отзыв:",
        'theme_mismatch': "❌ Отзыв не соответствует теме задания!\nНапишите про **{theme}**:",
        'no_username': "❌ Вы не указали @username в отзыве!\nДобавьте @{username} в текст:",
        'deposit_confirm': "✅ Оплата {stars} ⭐ получена!\n💰 +{get} Stars на баланс!",
        'deposit_manual': "💎 Пополнение от 15 ⭐:\nПереведите {stars} ⭐ админу @{support} с комментарием `{request_id}`\nОтправьте скриншот",
        'exchange': "🎁 Вывод Stars:\n{text}\n💰 Баланс: {balance} Stars",
        'exchange_done': "✅ Заявка {request_id} отправлена",
        'leaderboard': "🏆 Топ рефералов за неделю:\n{text}",
        'contests': "🎯 Активные конкурсы:\n{text}",
        'deposit_title': "Пополнение Stars",
        'deposit_desc': "Покупка Stars-коинов",
        'deposit_choose': "💎 Выберите сумму для пополнения:\n\nБаланс и награды указаны в Stars",
        'deposit_manual_btn': "15+ ⭐ (админ)",
        'back': "🔙 Назад",
        'my_tasks': "📋 МОИ ЗАДАНИЯ\n\nВыберите раздел:",
        'my_tasks_active': "📋 Активные задания:\n\n{text}",
        'my_tasks_completed': "📋 Выполненные задания:\n\n{text}",
        'my_tasks_empty': "📭 У вас нет {status} заданий",
        'task_deleted': "✅ Задание #{task_id} удалено!\n💰 {amount} Stars возвращены на баланс",
        'task_delete_confirm': "⚠️ Вы уверены, что хотите удалить задание #{task_id}?\n\nStars будут возвращены на баланс.",
        'task_delete_cancel': "❌ Удаление отменено",
        'task_create_step1': "📝 ШАГ 1: Укажите @username заказчика\n\nЭто тот человек, которому вы хотите собрать отзывы.\n\nПример: @mamutov_r",
        'task_create_step2': "📝 ШАГ 2: Укажите тематику отзыва\n\nОпишите, о чём должен быть отзыв.\n\n📌 Важно: отзыв будет проверяться на соответствие теме!\n\nПример: криптокошелек, игра, магазин, услуги",
        'task_create_step3': "📝 ШАГ 3: Укажите количество отзывов\n\nСколько человек должно написать отзыв.\n\n💰 Стоимость: 5 ⭐ за 1 отзыв\n\n⚠️ С вашего баланса спишется {cost} Stars за каждое задание",
        'task_create_step4': "📝 ШАГ 4: Выберите тип отзыва\n\n👍 Положительный — хвалят\n👎 Негативный — критикуют",
        'task_create_step5': "📝 ШАГ 5: Напишите пример отзыва\n\nЭто шаблон для исполнителей.\n\n💡 Совет: напишите красивый развёрнутый отзыв\n\nИсполнители будут использовать ваш пример как образец.",
        'task_create_confirm': "📋 ПРОВЕРЬТЕ ДАННЫЕ:\n\n👤 Заказчик: {username}\n📂 Тема: {theme}\n🔢 Количество: {count} шт.\n📊 Тип: {type}\n📝 Пример: {example}\n\n💰 Стоимость: {cost} Stars\n💰 Ваш баланс: {balance} Stars",
        'task_not_enough_balance': "❌ НЕДОСТАТОЧНО СРЕДСТВ!\n\nСоздание {count} заданий стоит {total_cost} Stars\nВаш баланс: {balance} Stars\n\nПополните баланс в разделе 💎 Пополнить Stars",
        'review_step1': "✍️ НАПИШИТЕ ОТЗЫВ\n\n📌 ТРЕБОВАНИЯ:\n1. Отзыв должен быть по теме: **{theme}**\n2. Обязательно укажите @{username} в тексте\n3. Минимум 15 символов\n4. Без мата\n\n📝 Пример:\n{example}\n\nНапишите свой отзыв:",
        'review_bad_username': "❌ В отзыве не найден @{username}!\n\nДобавьте @{username} в текст отзыва.",
    },
    'en': {
        'start': "👋 Welcome to Rep Up, {username}!\n\n📝 Select a section:\n💰 Balance: {balance} Stars",
        'banned': "🚫 You are banned!",
        'subscribe': "📢 Subscribe to channel: {channel}",
        'check_sub': "✅ Subscription confirmed!",
        'not_sub': "❌ You are not subscribed!",
        'balance': "💰 Balance: {balance} Stars\nBalance and rewards are shown in Stars",
        'referrals': "👥 Referrals: {count}\n💸 Earn 50% of friends’ confirmed top-ups.\n🔗 Link: https://t.me/{bot}?start={code}",
        'stats': "📊 Statistics\n👥 {users}\n📋 {tasks}\n✅ {completed}\n💰 {balance} Stars",
        'no_tasks': "📭 No active tasks",
        'task_created': "✅ Task #{task_id} created!",
        'task_completed': "✅ Review for #{task_id} accepted!\n💰 +5 Stars\nBalance: {balance} Stars",
        'not_enough': "❌ Insufficient funds! Need {cost} Stars, you have {balance} Stars",
        'review_forward': "📩 New review from: @{username}",
        'short_review': "❌ Minimum 15 characters",
        'bad_words': "❌ Bad words detected! Rewrite the review:",
        'theme_mismatch': "❌ Review does not match the theme!\nWrite about **{theme}**:",
        'no_username': "❌ You didn't specify @username in the review!\nAdd @{username} to the text:",
        'deposit_confirm': "✅ Payment of {stars} ⭐ received!\n💰 +{get} Stars to balance!",
        'deposit_manual': "💎 Deposit from 15 ⭐:\nSend {stars} ⭐ to admin @{support} with comment `{request_id}`\nSend screenshot",
        'exchange': "🎁 Withdraw Stars:\n{text}\n💰 Balance: {balance} Stars",
        'exchange_done': "✅ Request {request_id} sent",
        'leaderboard': "🏆 Top referrers for the week:\n{text}",
        'contests': "🎯 Active contests:\n{text}",
        'deposit_title': "Top up Stars",
        'deposit_desc': "Buy Stars coins",
        'deposit_choose': "💎 Select the number of Stars to add:\n\nYour balance and rewards are shown in Stars",
        'deposit_manual_btn': "15+ ⭐ (admin)",
        'back': "🔙 Back",
        'my_tasks': "📋 MY TASKS\n\nSelect a section:",
        'my_tasks_active': "📋 Active tasks:\n\n{text}",
        'my_tasks_completed': "📋 Completed tasks:\n\n{text}",
        'my_tasks_empty': "📭 You have no {status} tasks",
        'task_deleted': "✅ Task #{task_id} deleted!\n💰 {amount} Stars returned to balance",
        'task_delete_confirm': "⚠️ Are you sure you want to delete task #{task_id}?\n\nStars will be returned to balance.",
        'task_delete_cancel': "❌ Deletion cancelled",
        'task_create_step1': "📝 STEP 1: Enter @username of the customer\n\nThis is the person you want to collect reviews for.\n\nExample: @mamutov_r",
        'task_create_step2': "📝 STEP 2: Enter the theme of the review\n\nDescribe what the review should be about.\n\n📌 Important: the review will be checked for theme match!\n\nExample: crypto wallet, game, store, services",
        'task_create_step3': "📝 STEP 3: Enter the number of reviews\n\nHow many people should write a review.\n\n💰 Cost: 5 ⭐ per 1 review\n\n⚠️ {cost} Stars will be deducted from your balance for each task",
        'task_create_step4': "📝 STEP 4: Select review type\n\n👍 Positive — praise\n👎 Negative — criticize",
        'task_create_step5': "📝 STEP 5: Write an example review\n\nThis is a template for performers.\n\n💡 Tip: write a beautiful detailed review",
        'task_create_confirm': "📋 CHECK THE DATA:\n\n👤 Customer: {username}\n📂 Theme: {theme}\n🔢 Quantity: {count} pcs.\n📊 Type: {type}\n📝 Example: {example}\n\n💰 Cost: {cost} Stars\n💰 Your balance: {balance} Stars",
        'task_not_enough_balance': "❌ INSUFFICIENT FUNDS!\n\nCreating {count} tasks costs {total_cost} Stars\nYour balance: {balance} Stars\n\nTop up your balance in 💎 Top up Stars",
        'review_step1': "✍️ WRITE A REVIEW\n\n📌 REQUIREMENTS:\n1. Review must be on topic: **{theme}**\n2. Be sure to include @{username} in the text\n3. Minimum 15 characters\n4. No swearing\n\n📝 Example:\n{example}\n\nWrite your review:",
        'review_bad_username': "❌ @{username} not found in the review!\n\nAdd @{username} to the review text.",
    }
}

def get_text(lang, key, **kwargs):
    text = LANGUAGES.get(lang, LANGUAGES['ru']).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ========== ЦВЕТНОЕ ОФОРМЛЕНИЕ КНОПОК TELEGRAM ==========
def _button_style(text, inline=False, kwargs=None):
    """Telegram supports only three predefined button colors: blue, green, red."""
    value = str(text or "").lower()
    data = str((kwargs or {}).get("callback_data", "")).lower()
    if any(x in value for x in ("отмена", "cancel", "удалить", "delete", "снять", "убрать", "reject", "отклон", "бан", "сброс", "reset", "❌", "🚫", "➖")) or any(x in data for x in ("cancel", "delete", "reject", "remove", "ban", "reset")):
        return "danger"
    if any(x in value for x in ("подтверд", "confirm", "пополн", "deposit", "проверить", "check", "выполн", "complete", "создать", "create", "сохран", "save", "принять", "approve", "✅", "💚", "🟢", "➕")) or any(x in data for x in ("confirm", "approve", "check", "complete", "accept")):
        return "success"
    return "primary"

def KeyboardButton(*args, **kwargs):
    kwargs.setdefault("style", _button_style(kwargs.get("text", args[0] if args else ""), kwargs=kwargs))
    return _KeyboardButton(*args, **kwargs)

def InlineKeyboardButton(*args, **kwargs):
    kwargs.setdefault("style", _button_style(kwargs.get("text", args[0] if args else ""), inline=True, kwargs=kwargs))
    return _InlineKeyboardButton(*args, **kwargs)

# ========== КЛАВИАТУРЫ ==========
def main_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📝 Создать задание")],
            [KeyboardButton(text="📋 Задания для выполнения")],
            [KeyboardButton(text="💰 Мой баланс"), KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="💎 Пополнить Stars"), KeyboardButton(text="🎁 Вывести Stars")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🏆 Топ рефералов")],
            [KeyboardButton(text="🎯 Конкурсы"), KeyboardButton(text="📋 Мои задания")],
            [KeyboardButton(text="📣 Мой канал")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📝 Create task")],
            [KeyboardButton(text="📋 Tasks to do")],
            [KeyboardButton(text="💰 My balance"), KeyboardButton(text="👥 Referrals")],
            [KeyboardButton(text="💎 Top up Stars"), KeyboardButton(text="🎁 Withdraw Stars")],
            [KeyboardButton(text="📊 Statistics"), KeyboardButton(text="🏆 Top referrers")],
            [KeyboardButton(text="🎯 Contests"), KeyboardButton(text="📋 My tasks")],
            [KeyboardButton(text="📣 My channel")]
        ], resize_keyboard=True)

def admin_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="💳 Заявки на пополнение")],
            [KeyboardButton(text="💸 Заявки на вывод")],
            [KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="🔨 Управление балансом")],
            [KeyboardButton(text="🚫 Баны")],
            [KeyboardButton(text="🎟 Создать промокод")],
            [KeyboardButton(text="🏆 Топ рефералов")],
            [KeyboardButton(text="🎯 Конкурсы")],
            [KeyboardButton(text="👑 Администраторы и цена задания")],
            [KeyboardButton(text="📢 Управление каналом")],
            [KeyboardButton(text="🗑 Сбросить БД")],
            [KeyboardButton(text="⬅️ Выйти из админки")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="👥 Users")],
            [KeyboardButton(text="💳 Deposit requests")],
            [KeyboardButton(text="💸 Withdraw requests")],
            [KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="🔨 Balance management")],
            [KeyboardButton(text="🚫 Bans")],
            [KeyboardButton(text="🎟 Create promo")],
            [KeyboardButton(text="🏆 Top referrers")],
            [KeyboardButton(text="🎯 Contests")],
            [KeyboardButton(text="👑 Admins and task price")],
            [KeyboardButton(text="📢 Channel management")],
            [KeyboardButton(text="🗑 Reset DB")],
            [KeyboardButton(text="⬅️ Exit admin")]
        ], resize_keyboard=True)

def back_keyboard(lang='ru'):
    text = get_text(lang, 'back')
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=text)]], resize_keyboard=True)

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")]
    ])

def task_actions_keyboard(task_id, lang='ru'):
    write_text = "✍️ Написать отзыв" if lang == 'ru' else "✍️ Write review"
    back_text = get_text(lang, 'back')
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=write_text, callback_data=f"do_task_{task_id}")],
        [InlineKeyboardButton(text=back_text, callback_data="back_to_tasks")]
    ])

def tasks_list_keyboard(tasks, lang='ru'):
    buttons = []
    for task in tasks[:10]:
        task_id = task[0]
        buttons.append([InlineKeyboardButton(
            text=f"✅ Задание #{task_id}" if lang == 'ru' else f"✅ Task #{task_id}",
            callback_data=f"view_task_{task_id}"
        )])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def my_tasks_keyboard(tasks, lang='ru', status='active'):
    buttons = []
    for task in tasks[:10]:
        task_id = task[0]
        if status == 'active':
            buttons.append([InlineKeyboardButton(
                text=f"🗑 Задание #{task_id}" if lang == 'ru' else f"🗑 Task #{task_id}",
                callback_data=f"delete_task_{task_id}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=f"📝 Задание #{task_id}" if lang == 'ru' else f"📝 Task #{task_id}",
                callback_data=f"view_completed_{task_id}"
            )])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_my_tasks")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def gift_selection_keyboard(lang='ru'):
    buttons = []
    for get_amount, info in STAR_GIFT_OPTIONS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['name']} ({get_amount} ⭐)",
            callback_data=f"gift_{get_amount}"
        )])
    buttons.append([InlineKeyboardButton(
        text="⭐ Вывести Stars вручную (от 50)" if lang == 'ru' else "⭐ Manual Stars payout (min 50)",
        callback_data="withdraw_manual_stars"
    )])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def deposit_keyboard(lang='ru'):
    buttons = []
    for stars in [2, 4, 10, 20]:
        get_amount = stars
        buttons.append([InlineKeyboardButton(
            text=(f"➕ Пополнить на {stars} ⭐" if lang == 'ru' else f"➕ Add {stars} ⭐"),
            callback_data=f"deposit_{stars}"
        )])
    buttons.append([InlineKeyboardButton(
        text=("🎁 Отправить подарок админу" if lang == 'ru' else "🎁 Send a gift to admin"),
        url="tg://send_gift?to=8959461245"
    )])
    back_text = get_text(lang, 'back')
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== СОСТОЯНИЯ ==========
class CreateTaskStates(StatesGroup):
    username = State()
    theme = State()
    count = State()
    review_type = State()
    example = State()
    confirm = State()

class DepositStates(StatesGroup):
    amount = State()
    confirm = State()

class AdminStates(StatesGroup):
    broadcast = State()
    ban_user = State()
    unban_user = State()
    add_balance = State()
    remove_balance = State()
    promo_code = State()
    promo_bonus = State()
    promo_limit = State()
    channel_add = State()
    channel_delete = State()
    contest_name = State()
    contest_desc = State()
    contest_bonus = State()
    contest_start = State()
    contest_end = State()
    leaderboard_bonus = State()
    reset_db_confirm = State()
    withdraw_proof = State()
    admin_add_id = State()
    admin_remove_id = State()
    task_cost = State()

class ReviewStates(StatesGroup):
    writing = State()

class UserChannelStates(StatesGroup):
    waiting_for_channel = State()

class WithdrawStates(StatesGroup):
    stars_amount = State()
    gift_text = State()

class LanguageStates(StatesGroup):
    selecting = State()

# ========== ПРОВЕРКИ ==========
async def check_subscription(user_id):
    if is_admin(user_id):
        return True
    
    channel = get_channel()
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ========== ХЕНДЛЕРЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    user = get_user(user_id)
    if not user:
        parts = (message.text or "").split(maxsplit=1)
        ref_code = parts[1].strip() if len(parts) > 1 else None
        await state.update_data(ref_code=ref_code)
        await message.answer(
            "🌍 Выберите язык / Select language:",
            reply_markup=language_keyboard()
        )
        await state.set_state(LanguageStates.selecting)
        return
    
    if user[6] == 1:
        await message.answer(get_text(user[2], 'banned'))
        return
    
    if not await check_subscription(user_id):
        channel = get_channel()
        if channel:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{channel[1:]}")],
                [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
            ])
            await message.answer(
                get_text(user[2], 'subscribe', channel=channel),
                reply_markup=keyboard
            )
            return
    
    await message.answer(
        get_text(user[2], 'start', username=message.from_user.username or str(user_id), balance=user[3]),
        reply_markup=main_keyboard(user[2])
    )

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    username = callback.from_user.username or str(user_id)
    
    state_data = await state.get_data()
    ref_code = state_data.get("ref_code")
    
    device_id = str(callback.from_user.id)
    user = create_user(user_id, username, device_id, ref_code, lang)
    if not user:
        await callback.answer("❌ Твинк обнаружен! / Twin detected!", show_alert=True)
        return
    
    await state.clear()
    
    if not await check_subscription(user_id):
        channel = get_channel()
        if channel:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{channel[1:]}")],
                [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
            ])
            await callback.message.edit_text(
                get_text(lang, 'subscribe', channel=channel),
                reply_markup=keyboard
            )
            return
    
    await callback.message.edit_text(
        get_text(lang, 'start', username=username, balance=user[3]),
        reply_markup=main_keyboard(lang)
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if await check_subscription(user_id):
        await callback.message.edit_text(get_text(user[2], 'check_sub'))
        await callback.message.answer(
            get_text(user[2], 'start', username=callback.from_user.username or str(user_id), balance=user[3]),
            reply_markup=main_keyboard(user[2])
        )
    else:
        await callback.answer(get_text(user[2], 'not_sub'), show_alert=True)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

@dp.message(F.text.in_(["🔙 Назад", "🔙 Back"]))
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Ошибка")
        return
    
    if is_admin(message.from_user.id):
        await message.answer(
            "🔙 Админ-панель" if user[2] == 'ru' else "🔙 Admin panel",
            reply_markup=admin_keyboard(user[2])
        )
    else:
        await message.answer(
            "🔙 Главное меню" if user[2] == 'ru' else "🔙 Main menu",
            reply_markup=main_keyboard(user[2])
        )

# ========== МОИ ЗАДАНИЯ ==========
@dp.message(F.text.in_(["📋 Мои задания", "📋 My tasks"]))
async def my_tasks_menu(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Активные" if lang == 'ru' else "📋 Active")],
        [KeyboardButton(text="✅ Выполненные" if lang == 'ru' else "✅ Completed")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        get_text(lang, 'my_tasks'),
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["📋 Активные", "📋 Active"]))
async def my_active_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    user_id = message.from_user.id
    
    tasks = db_execute("SELECT id, username, theme, count FROM tasks WHERE creator_id = ? AND status = 'active'", (user_id,))
    
    if not tasks:
        await message.answer(
            get_text(lang, 'my_tasks_empty', status="активных" if lang == 'ru' else "active"),
            reply_markup=back_keyboard(lang)
        )
        return
    
    text = ""
    for task in tasks:
        text += f"🆔 Задание #{task[0]}\n👤 {task[1]}\n📂 {task[2]}\n📌 Доступно: {task[3]} шт.\n💰 Стоимость: 5 ⭐\n{'='*20}\n\n"
    
    await message.answer(
        get_text(lang, 'my_tasks_active', text=text[:4000]),
        reply_markup=my_tasks_keyboard(tasks, lang, 'active')
    )

@dp.message(F.text.in_(["✅ Выполненные", "✅ Completed"]))
async def my_completed_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    user_id = message.from_user.id
    
    tasks = db_execute("""
        SELECT t.id, t.username, t.theme, tc.created_at 
        FROM tasks t
        JOIN task_completions tc ON t.id = tc.task_id
        WHERE tc.user_id = ?
        ORDER BY tc.created_at DESC
        LIMIT 20
    """, (user_id,))
    
    if not tasks:
        await message.answer(
            get_text(lang, 'my_tasks_empty', status="выполненных" if lang == 'ru' else "completed"),
            reply_markup=back_keyboard(lang)
        )
        return
    
    text = ""
    for task in tasks:
        text += f"🆔 Задание #{task[0]}\n👤 {task[1]}\n📂 {task[2]}\n📅 {task[3][:16]}\n{'='*20}\n\n"
    
    await message.answer(
        get_text(lang, 'my_tasks_completed', text=text[:4000]),
        reply_markup=my_tasks_keyboard(tasks, lang, 'completed')
    )

@dp.callback_query(F.data.startswith("delete_task_"))
async def delete_task_confirm(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[2])
    
    task = db_execute("SELECT * FROM tasks WHERE id = ? AND creator_id = ?", (task_id, callback.from_user.id))
    if not task:
        await callback.answer("❌ Задание не найдено" if lang == 'ru' else "❌ Task not found")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить" if lang == 'ru' else "✅ Yes, delete", callback_data=f"confirm_delete_{task_id}")],
        [InlineKeyboardButton(text="❌ Отмена" if lang == 'ru' else "❌ Cancel", callback_data="back_to_my_tasks")]
    ])
    
    await callback.message.edit_text(
        get_text(lang, 'task_delete_confirm', task_id=task_id),
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def delete_task_execute(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[2])
    
    task = db_execute("SELECT * FROM tasks WHERE id = ? AND creator_id = ?", (task_id, callback.from_user.id))
    if not task:
        await callback.answer("❌ Задание не найдено" if lang == 'ru' else "❌ Task not found")
        return
    
    task = task[0]
    
    # Возвращаем Stars на баланс (только если задание активное и никто не выполнил)
    completions = db_execute("SELECT COUNT(*) FROM task_completions WHERE task_id = ?", (task_id,))
    if completions and completions[0][0] == 0:
        add_balance(callback.from_user.id, get_task_cost())
        amount_returned = get_task_cost()
    else:
        amount_returned = 0
    
    # Удаляем задание
    db_execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    
    await callback.message.edit_text(
        get_text(lang, 'task_deleted', task_id=task_id, amount=amount_returned),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад" if lang == 'ru' else "🔙 Back", callback_data="back_to_my_tasks")]
        ])
    )

@dp.callback_query(F.data == "back_to_my_tasks")
async def back_to_my_tasks(callback: CallbackQuery):
    await callback.message.delete()
    await my_tasks_menu(callback.message)

# ========== ПОПОЛНЕНИЕ ЧЕРЕЗ STARS ==========
@dp.message(F.text.in_(["💎 Пополнить Stars", "💎 Top up Stars"]))
async def deposit_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    await message.answer(
        get_text(lang, 'deposit_choose'),
        reply_markup=deposit_keyboard(lang)
    )

@dp.callback_query(F.data.startswith("deposit_"))
async def process_deposit(callback: CallbackQuery):
    # Сразу закрываем индикатор загрузки Telegram, чтобы он не зависал,
    # если Bot API вернёт ошибку при создании счёта.
    await callback.answer()
    user = get_user(callback.from_user.id)
    if not user or user[6] == 1:
        await bot.send_message(callback.from_user.id, "❌ Не удалось определить аккаунт. Нажмите /start и попробуйте снова.")
        return

    lang = user[2]
    data = callback.data.split("_")
    if len(data) < 2:
        await bot.send_message(callback.from_user.id, "❌ Некорректная кнопка. Откройте меню пополнения заново.")
        return

    if data[1] == "manual":
        if callback.message:
            try:
                await callback.message.delete()
            except Exception:
                logging.exception("Не удалось удалить сообщение пополнения")
        request_id = generate_request_id()
        db_execute(
            """INSERT INTO deposit_requests
               (user_id, request_id, stars_amount, get_amount, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (callback.from_user.id, request_id, 15, 15, 'pending', datetime.now().isoformat())
        )
        await bot.send_message(
            callback.from_user.id,
            get_text(lang, 'deposit_manual', stars="15+", support=SUPPORT_USERNAME, request_id=request_id),
            reply_markup=back_keyboard(lang)
        )
        return

    try:
        stars = int(data[1])
        if stars not in (2, 4, 10, 20):
            raise ValueError("Недопустимая сумма")
    except (ValueError, IndexError):
        await bot.send_message(callback.from_user.id, "❌ Некорректная сумма. Откройте меню пополнения заново.")
        return

    try:
        # Telegram Stars: currency=XTR, provider_token должен быть пустым.
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="Пополнение Rep Up",
            description=f"Пополнение внутреннего баланса на {stars} Stars",
            payload=f"deposit_{stars}_{callback.from_user.id}_{int(datetime.now().timestamp())}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"Rep Up — {stars} Stars", amount=stars)],
            start_parameter="deposit",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить Stars", pay=True)],
                [InlineKeyboardButton(text=get_text(lang, 'back'), callback_data="back_to_main")]
            ])
        )
        logging.info("Invoice sent: user_id=%s stars=%s", callback.from_user.id, stars)
    except Exception:
        logging.exception(
            "Не удалось создать Telegram Stars invoice: user_id=%s amount=%s",
            callback.from_user.id, stars
        )
        await bot.send_message(
            callback.from_user.id,
            "⚠️ Telegram не смог создать счёт на оплату. Попробуйте ещё раз позже. "
            "Если ошибка повторится, администратор сможет найти точную причину в логах."
        )

@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout: PreCheckoutQuery):
    try:
        parts = pre_checkout.invoice_payload.split("_")
        valid = (len(parts) >= 4 and parts[0] == "deposit"
                 and int(parts[1]) == int(pre_checkout.total_amount)
                 and int(parts[2]) == int(pre_checkout.from_user.id)
                 and pre_checkout.currency == "XTR")
    except (ValueError, TypeError):
        valid = False
    await pre_checkout.answer(ok=valid, error_message=None if valid else "Некорректный счёт пополнения.")

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    payment_id = payment.telegram_payment_charge_id
    stars_amount = int(payment.total_amount)
    try:
        payload_parts = payment.invoice_payload.split("_")
        payload_valid = (len(payload_parts) >= 4 and payload_parts[0] == "deposit"
                         and int(payload_parts[1]) == stars_amount
                         and int(payload_parts[2]) == user_id
                         and payment.currency == "XTR")
    except (ValueError, TypeError):
        payload_valid = False
    if not payload_valid:
        logging.error("Отклонён платёж с некорректным payload: user_id=%s", user_id)
        await message.answer("⚠️ Не удалось проверить платёж. Напишите в поддержку, повторно не оплачивайте.")
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_NAME, timeout=30)
    referral_bonus = 0
    referrer_id = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM payments WHERE payment_id = ?", (payment_id,)).fetchone():
            conn.rollback()
            await message.answer("ℹ️ Этот платёж уже был обработан.")
            return
        row = conn.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,)).fetchone()
        referrer_id = row[0] if row else None
        referral_bonus = stars_amount // 2 if referrer_id and referrer_id != user_id else 0
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (stars_amount, user_id))
        if referral_bonus:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (referral_bonus, referrer_id))
        conn.execute('''INSERT INTO payments
            (user_id, stars_amount, get_amount, payment_id, status, created_at, referral_bonus, referrer_id)
            VALUES (?, ?, ?, ?, 'completed', ?, ?, ?)''',
            (user_id, stars_amount, stars_amount, payment_id, now, referral_bonus, referrer_id))
        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Ошибка обработки успешного платежа")
        await message.answer("⚠️ Платёж получен, но возникла ошибка зачисления. Обратитесь в поддержку; повторно платить не нужно.")
        return
    finally:
        conn.close()
    user = get_user(user_id)
    lang = user[2] if user else 'ru'
    if referral_bonus:
        try:
            await bot.send_message(referrer_id, f"🎉 Ваш реферал пополнил баланс на {stars_amount} ⭐. Вам начислено {referral_bonus} ⭐ (50%).")
        except Exception:
            logging.exception("Не удалось уведомить реферера")
    await message.answer(get_text(lang, 'deposit_confirm', stars=stars_amount, get=stars_amount),
                         reply_markup=main_keyboard(lang))

# ========== ОБМЕН Stars ==========
@dp.message(F.text.in_(["🎁 Вывести Stars", "🎁 Withdraw Stars"]))
async def exchange_start(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    text = ""
    for get_amount, info in STAR_GIFT_OPTIONS.items():
        text += f"{info['name']}: {get_amount} ⭐ = {info['stars']} ⭐\n"
    
    await message.answer(
        get_text(lang, 'exchange', text=text, balance=user[3]),
        reply_markup=gift_selection_keyboard(lang)
    )

@dp.callback_query(F.data == "withdraw_manual_stars")
async def manual_stars_withdraw_start(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return
    await callback.message.answer(
        f"Введите количество Stars для ручной выплаты (минимум 50).\n"
        f"Ваш баланс: {user[3]} ⭐."
    )
    await state.set_state(WithdrawStates.stars_amount)
    await callback.answer()

@dp.message(WithdrawStates.stars_amount)
async def manual_stars_withdraw_submit(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        await state.clear()
        return
    try:
        stars = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Введите целое число Stars.")
        return
    if stars < 50:
        await message.answer("Минимальная сумма ручного вывода — 50 Stars.")
        return
    get_amount = stars
    if user[3] < get_amount:
        await message.answer(f"Недостаточно Stars. Нужно {get_amount} ⭐, у вас {user[3]} ⭐.")
        return
    request_id = generate_request_id()
    db_execute("""INSERT INTO withdraw_requests
        (user_id, username, get_amount, stars_amount, gift_name, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
        (message.from_user.id, message.from_user.username or str(message.from_user.id),
         get_amount, stars, "Ручная выплата Stars", datetime.now().isoformat()))
    if not subtract_balance(message.from_user.id, get_amount):
        await message.answer("Не удалось списать баланс. Попробуйте ещё раз.")
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id,
                f"⭐ Заявка на ручную выплату Stars {request_id}\n"
                f"Пользователь: @{message.from_user.username or message.from_user.id}\n"
                f"Сумма: {stars}⭐ / {get_amount} ⭐")
        except Exception:
            logging.exception("Failed to notify admin about Stars withdrawal")
    await state.clear()
    await message.answer(f"✅ Заявка {request_id} создана. Выплата будет обработана администратором после проверки.",
                         reply_markup=main_keyboard(user[2]))

@dp.callback_query(F.data.startswith("gift_"))
async def exchange_gift(callback: CallbackQuery, state: FSMContext):
    """Выбор суммы внутреннего вывода, затем реального подарка из каталога Telegram."""
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    try:
        get_amount = int(callback.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная сумма", show_alert=True)
        return
    if get_amount not in STAR_GIFT_OPTIONS:
        await callback.answer("Недоступная сумма", show_alert=True)
        return
    if user[3] < get_amount:
        await callback.answer(f"❌ Нужно {get_amount} ⭐", show_alert=True)
        return

    # Получаем актуальный каталог подарков и показываем только варианты ровно на выбранную сумму.
    try:
        gifts_result = await bot.get_available_gifts()
        gifts = getattr(gifts_result, "gifts", []) or []
    except Exception as exc:
        logging.exception("Не удалось получить каталог Telegram Gifts: %s", exc)
        await callback.answer("Не удалось загрузить подарки. Попробуйте позже.", show_alert=True)
        return

    matching = []
    for gift in gifts:
        price = getattr(gift, "star_count", None)
        gift_id = getattr(gift, "id", None)
        if price == get_amount and gift_id:
            sticker = getattr(gift, "sticker", None)
            emoji = getattr(sticker, "emoji", None) if sticker else None
            title = f"{emoji or '🎁'} Подарок — {price} ⭐"
            matching.append((gift_id, title))

    if not matching:
        await callback.answer(
            f"Сейчас в каталоге Telegram нет подарков ровно за {get_amount} ⭐. Баланс не списан.",
            show_alert=True
        )
        return

    await state.clear()
    await state.update_data(withdraw_amount=get_amount, gift_choices=matching)
    rows = [[InlineKeyboardButton(text=title, callback_data=f"giftpick_{i}")]
            for i, (_, title) in enumerate(matching[:8])]
    await callback.message.answer(
        f"🎁 Выберите подарок стоимостью {get_amount} Telegram Stars.\n"
        "После этого выберите текст для подарка. Баланс Rep Up будет списан только при успешной отправке.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("giftpick_"))
async def gift_pick(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    choices = data.get("gift_choices", [])
    try:
        index = int(callback.data.split("_", 1)[1])
        gift_id, gift_title = choices[index]
    except (ValueError, IndexError, TypeError):
        await callback.answer("Выбор устарел. Начните вывод заново.", show_alert=True)
        return
    await state.update_data(selected_gift_id=gift_id, selected_gift_title=gift_title)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Текст от Rep Up", callback_data="gifttext_bot")],
        [InlineKeyboardButton(text="📝 Написать свой текст", callback_data="gifttext_custom")],
    ])
    await callback.message.answer("Какой текст добавить к подарку?", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "gifttext_bot")
async def gift_text_bot(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gift_text="Спасибо за участие в Rep Up! Ваш вывод вознаграждения отправлен.")
    await send_selected_gift(callback, state)

@dp.callback_query(F.data == "gifttext_custom")
async def gift_text_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawStates.gift_text)
    await callback.message.answer("Напишите текст для подарка (до 128 символов). Не указывайте ложные отзывы или результаты, которых не было.")
    await callback.answer()

@dp.message(WithdrawStates.gift_text)
async def gift_text_received(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 128:
        await message.answer("Текст должен содержать от 1 до 128 символов. Попробуйте ещё раз.")
        return
    await state.update_data(gift_text=text)
    # Отправляем выбранный подарок тем же пользователем, который оформляет вывод.
    await send_selected_gift(message, state)

async def send_selected_gift(event, state: FSMContext):
    data = await state.get_data()
    user_id = event.from_user.id
    amount = int(data.get("withdraw_amount", 0) or 0)
    gift_id = data.get("selected_gift_id")
    gift_title = data.get("selected_gift_title", "Telegram Gift")
    gift_text = (data.get("gift_text") or "").strip()[:128]
    user = get_user(user_id)
    if not user or amount <= 0 or not gift_id or user[3] < amount:
        await event.answer("Недостаточно Stars или выбор устарел. Начните заново.")
        await state.clear()
        return

    created_at = datetime.now().isoformat()
    db_execute("""INSERT INTO withdraw_requests
        (user_id, username, get_amount, stars_amount, gift_name, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'processing', ?)""",
        (user_id, event.from_user.username or str(user_id), amount, amount,
         gift_title, created_at))
    rows = db_execute("SELECT id FROM withdraw_requests WHERE user_id = ? AND created_at = ? ORDER BY id DESC LIMIT 1",
                      (user_id, created_at))
    request_db_id = rows[0][0] if rows else None

    if not subtract_balance(user_id, amount):
        if request_db_id:
            db_execute("UPDATE withdraw_requests SET status='failed' WHERE id=?", (request_db_id,))
        await event.answer("Не удалось списать внутренний баланс. Попробуйте позже.")
        await state.clear()
        return

    try:
        # Подарок отправляется непосредственно ботом из его собственного баланса Telegram Stars.
        await bot.send_gift(user_id=user_id, gift_id=gift_id, text=gift_text)
    except Exception as exc:
        logging.exception("Telegram sendGift failed: %s", exc)
        add_balance(user_id, amount)
        if request_db_id:
            db_execute("UPDATE withdraw_requests SET status='failed' WHERE id=?", (request_db_id,))
        await event.answer("❌ Telegram не смог отправить подарок. Внутренние Stars возвращены на баланс.")
        await state.clear()
        return

    if request_db_id:
        db_execute("UPDATE withdraw_requests SET status='completed' WHERE id=? AND status='processing'", (request_db_id,))

    # Bot API не возвращает скриншот личного диалога. Публикуем автоматический текстовый чек.
    try:
        username = (event.from_user.username or str(user_id)).lstrip('@')
        await bot.send_message(
            PAYOUT_CHANNEL_ID,
            f"🎁 <b>Автоматическая выплата Rep Up</b>\n"
            f"👤 Пользователь: @{username} (<code>{user_id}</code>)\n"
            f"🎁 Подарок: {gift_title}\n"
            f"⭐ Сумма: {amount} Telegram Stars\n"
            f"📝 Текст подарка: {gift_text or 'без текста'}\n"
            f"🧾 Заявка: #{request_db_id or request_id}\n"
            f"<i>Подарок отправлен ботом через Telegram Bot API.</i>",
            parse_mode="HTML"
        )
    except Exception as exc:
        logging.exception("Gift sent but payout channel report failed: %s", exc)

    await event.answer("✅ Подарок отправлен ботом! Внутренние Stars списаны.")
    await state.clear()

# ========== ОСТАЛЬНЫЕ ХЕНДЛЕРЫ (СОЗДАНИЕ, ВЫПОЛНЕНИЕ, АДМИН) ==========
# ... (продолжение следует)# ========== ЛИЧНЫЙ КАНАЛ ПОЛЬЗОВАТЕЛЯ ==========
@dp.message(Command("channel"))
@dp.message(F.text.in_(["📣 Мой канал", "📣 My channel"]))
async def user_channel_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    current = get_user_channel(message.from_user.id)
    current_text = f"\nСейчас подключён: {current[1] or current[0]}" if current else "\nКанал ещё не подключён."
    await message.answer(
        "📣 <b>Подключение своего канала</b>\n\n"
        "1. Добавьте бота в свой канал администратором.\n"
        "2. Включите право «Публикация сообщений».\n"
        "3. Пришлите @username канала или его числовой ID.\n\n"
        "После проверки бот будет пересылать туда исходные сообщения с отзывами "
        "с пометкой Telegram «Переслано от…»." + current_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True)
    )
    await state.set_state(UserChannelStates.waiting_for_channel)

@dp.message(UserChannelStates.waiting_for_channel)
async def user_channel_save(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пришлите @username или ID канала текстом.")
        return
    channel_id = message.text.strip()
    if channel_id in ["🔙 Назад", "🔙 Back"]:
        await state.clear()
        user = get_user(message.from_user.id)
        await message.answer("Главное меню", reply_markup=main_keyboard(user[2] if user else 'ru'))
        return
    if not (channel_id.startswith("@") or re.fullmatch(r"-100\d+", channel_id)):
        await message.answer("❌ Укажите публичный @username или ID вида -1001234567890.")
        return
    try:
        chat = await bot.get_chat(channel_id)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in ("administrator", "creator"):
            raise ValueError("Бот не является администратором канала.")
        if getattr(member, "can_post_messages", True) is False:
            raise ValueError("У бота нет права публикации сообщений.")
    except Exception as exc:
        logging.warning("User channel validation failed: %s", exc)
        await message.answer(
            "❌ Не удалось подтвердить права бота. Добавьте бота администратором с правом публикации "
            "и проверьте правильность @username/ID, затем отправьте канал ещё раз."
        )
        return
    db_execute("""INSERT INTO user_channels (user_id, channel_id, channel_title, connected_at)
        VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET
        channel_id=excluded.channel_id, channel_title=excluded.channel_title, connected_at=excluded.connected_at""",
        (message.from_user.id, str(chat.id), chat.title or chat.username or str(chat.id), datetime.now().isoformat()))
    await state.clear()
    await message.answer(
        f"✅ Канал «{chat.title or chat.username}» подключён. Теперь отзывы будут пересылаться туда от имени исходного автора.",
        reply_markup=main_keyboard(get_user(message.from_user.id)[2])
    )

# ========== СОЗДАНИЕ ЗАДАНИЯ ==========
@dp.message(F.text.in_(["📝 Создать задание", "📝 Create task"]))
async def create_task_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    
    await message.answer(
        get_text(lang, 'task_create_step1'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.username)

@dp.message(CreateTaskStates.username)
async def create_task_username(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("❌ Начинайте с @!" if lang == 'ru' else "❌ Start with @!")
        return
    
    await state.update_data(username=username)
    await message.answer(
        get_text(lang, 'task_create_step2'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.theme)

@dp.message(CreateTaskStates.theme)
async def create_task_theme(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    theme = message.text.strip()
    forbidden = ["18+", "скам", "scam", "мошенник", "обман", "порно", "секс", "наркотики"]
    if any(w in theme.lower() for w in forbidden):
        await message.answer("❌ Запрещённая тема!" if lang == 'ru' else "❌ Forbidden theme!")
        return
    
    if len(theme) < 5:
        await message.answer("❌ Тема слишком короткая! Минимум 5 символов." if lang == 'ru' else "❌ Theme is too short! Minimum 5 characters.")
        return
    
    await state.update_data(theme=theme)
    await message.answer(
        get_text(lang, 'task_create_step3', cost=get_task_cost()),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.count)

@dp.message(CreateTaskStates.count)
async def create_task_count(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число!" if lang == 'ru' else "❌ Enter a positive number!")
        return
    
    total_cost = count * get_task_cost()
    if user[3] < total_cost:
        await message.answer(
            get_text(lang, 'task_not_enough_balance', 
                     count=count, 
                     total_cost=total_cost, 
                     balance=user[3])
        )
        return
    
    await state.update_data(count=count)
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👍 Положительный" if lang == 'ru' else "👍 Positive")],
        [KeyboardButton(text="👎 Негативный" if lang == 'ru' else "👎 Negative")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        get_text(lang, 'task_create_step4'),
        reply_markup=keyboard
    )
    await state.set_state(CreateTaskStates.review_type)

@dp.message(CreateTaskStates.review_type)
async def create_task_type(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    if message.text not in ["👍 Положительный", "👎 Негативный", "👍 Positive", "👎 Negative"]:
        await message.answer("❌ Выберите из кнопок!" if lang == 'ru' else "❌ Choose from buttons!")
        return
    
    review_type = "positive" if "Положительный" in message.text or "Positive" in message.text else "negative"
    await state.update_data(review_type=review_type)
    
    await message.answer(
        get_text(lang, 'task_create_step5'),
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(CreateTaskStates.example)

@dp.message(CreateTaskStates.example)
async def create_task_example(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    example = message.text.strip()
    if len(example) < 20:
        await message.answer("❌ Пример слишком короткий! Минимум 20 символов." if lang == 'ru' else "❌ Example is too short! Minimum 20 characters.")
        return
    
    await state.update_data(example=example)
    data = await state.get_data()
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm")],
        [KeyboardButton(text="❌ Отменить" if lang == 'ru' else "❌ Cancel")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    type_text = "Положительный" if data['review_type'] == 'positive' else "Негативный"
    if lang == 'en':
        type_text = "Positive" if data['review_type'] == 'positive' else "Negative"
    
    total_cost = data['count'] * get_task_cost()
    
    await message.answer(
        get_text(lang, 'task_create_confirm',
                 username=data['username'],
                 theme=data['theme'],
                 count=data['count'],
                 type=type_text,
                 example=data['example'][:100] + "...",
                 cost=total_cost,
                 balance=user[3]),
        reply_markup=keyboard
    )
    await state.set_state(CreateTaskStates.confirm)

@dp.message(CreateTaskStates.confirm)
async def create_task_confirm(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await back_to_main(message, state)
        return
    
    if message.text in ["❌ Отменить", "❌ Cancel"]:
        await state.clear()
        await message.answer("❌ Отменено" if lang == 'ru' else "❌ Cancelled", reply_markup=main_keyboard(lang))
        return
    
    if message.text not in ["✅ Подтвердить", "✅ Confirm"]:
        return
    
    data = await state.get_data()
    user_id = message.from_user.id
    
    total_cost = data['count'] * get_task_cost()
    
    if not subtract_balance(user_id, total_cost):
        await message.answer("❌ Ошибка! Недостаточно средств." if lang == 'ru' else "❌ Error! Insufficient funds.")
        await state.clear()
        return
    
    created = 0
    for i in range(data['count']):
        db_execute("""
            INSERT INTO tasks (creator_id, username, theme, count, review_type, example_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['username'], data['theme'], 1, 
              data['review_type'], data['example'], datetime.now().isoformat()))
        created += 1
    
    await state.clear()
    user = get_user(user_id)
    await message.answer(
        f"✅ Создано {created} заданий!\n\n"
        f"💰 Списанo: {total_cost} Stars\n"
        f"💰 Текущий баланс: {user[3]} Stars",
        reply_markup=main_keyboard(lang)
    )

# ========== ВЫПОЛНЕНИЕ ЗАДАНИЙ ==========
@dp.message(F.text.in_(["📋 Задания для выполнения", "📋 Tasks to do"]))
async def show_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    tasks = db_execute("SELECT id, username, theme, count, review_type, example_text FROM tasks WHERE status = 'active'")
    
    if not tasks:
        await message.answer(
            get_text(lang, 'no_tasks'),
            reply_markup=main_keyboard(lang)
        )
        return
    
    text = "📋 Доступные задания:\n\n" if lang == 'ru' else "📋 Available tasks:\n\n"
    
    for task in tasks:
        task_id, username, theme, count, review_type, example = task
        type_text = "Положительный" if review_type == 'positive' else "Негативный"
        if lang == 'en':
            type_text = "Positive" if review_type == 'positive' else "Negative"
        
        example_short = example[:30] + "..." if len(example) > 30 else example
        
        text += (
            f"🆔 Задание #{task_id}\n"
            f"👤 Заказчик: {username}\n"
            f"📂 Тема: {theme}\n"
            f"📊 Тип: {type_text}\n"
            f"📌 Доступно: {count} шт.\n"
            f"📝 Пример: {example_short}\n"
            f"💰 Награда: 5 ⭐\n"
            f"{'='*20}\n\n"
        )
    
    await message.answer(
        text[:4000],
        reply_markup=tasks_list_keyboard(tasks, lang)
    )

@dp.callback_query(F.data.startswith("view_task_"))
async def view_task(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[2])
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    
    if not task:
        await callback.answer("❌ Задание не найдено" if lang == 'ru' else "❌ Task not found")
        return
    
    task = task[0]
    type_text = "Положительный" if task[5] == 'positive' else "Негативный"
    if lang == 'en':
        type_text = "Positive" if task[5] == 'positive' else "Negative"
    
    text = (
        f"📋 Задание #{task[0]}\n\n"
        f"👤 Заказчик: {task[2]}\n"
        f"📂 Тема: {task[3]}\n"
        f"📊 Тип: {type_text}\n"
        f"📌 Доступно: {task[4]} шт.\n"
        f"💰 Награда: 5 ⭐\n\n"
        f"📝 Пример отзыва:\n{task[6]}\n\n"
        f"Нажмите кнопку ниже, чтобы выполнить задание."
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=task_actions_keyboard(task_id, lang)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("do_task_"))
async def do_task(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user or user[6] == 1:
        await callback.answer("🚫 Доступ запрещён" if user and user[2] == 'ru' else "🚫 Access denied")
        return
    
    lang = user[2]
    task_id = int(callback.data.split("_")[2])
    
    existing = db_execute("SELECT * FROM task_completions WHERE task_id = ? AND user_id = ?", (task_id, callback.from_user.id))
    if existing:
        await callback.answer("❌ Вы уже выполнили это задание!" if lang == 'ru' else "❌ Already completed!", show_alert=True)
        return
    
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        await callback.answer("❌ Нет задания" if lang == 'ru' else "❌ No task")
        return
    
    task = task[0]
    if task[1] == callback.from_user.id:
        await callback.answer("❌ Своё нельзя!" if lang == 'ru' else "❌ Can't do your own!", show_alert=True)
        return
    if db_execute("SELECT 1 FROM creator_limits WHERE user_id = ? AND creator_id = ?",
                  (callback.from_user.id, task[1])):
        await callback.answer("❌ Вы уже выполняли задание этого пользователя. Повторно нельзя.", show_alert=True)
        return
    
    await state.update_data(task_id=task_id, task_data=task)
    
    await callback.message.edit_text(
        get_text(lang, 'review_step1',
                 theme=task[3],
                 username=task[2].replace("@", ""),
                 example=task[6]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена" if lang == 'ru' else "🔙 Cancel", callback_data="back_to_tasks")]
        ])
    )
    await state.set_state(ReviewStates.writing)

@dp.message(ReviewStates.writing)
async def submit_review(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return
    if not message.text:
        await message.answer("Отправьте отзыв текстовым сообщением, чтобы Telegram мог переслать его с авторством.")
        return
    lang = user[2]
    data = await state.get_data()
    task_id = data['task_id']
    task = data['task_data']
    review_text = message.text.strip()
    if len(review_text) < 15:
        await message.answer(get_text(lang, 'short_review'))
        return
    if check_bad_words(review_text):
        await message.answer(get_text(lang, 'bad_words'))
        return
    if not check_theme_match(review_text, task[3]):
        await message.answer(get_text(lang, 'theme_mismatch', theme=task[3]))
        return

    creator_id = task[1]
    target_channel = get_user_channel(creator_id)
    # Сначала пересылаем оригинал, чтобы не начислять награду при невозможности форварда.
    try:
        await bot.forward_message(chat_id=creator_id, from_chat_id=message.chat.id, message_id=message.message_id)
    except Exception as exc:
        logging.exception("Could not forward original review to task creator: %s", exc)
        await message.answer(
            "❌ Не получилось переслать исходное сообщение создателю задания. "
            "Проверьте, что он не заблокировал бота. Задание пока не засчитано."
        )
        return
    if target_channel:
        try:
            await bot.forward_message(chat_id=target_channel[0], from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception as exc:
            logging.exception("Could not forward review to user's channel: %s", exc)
            await message.answer(
                "❌ Не удалось переслать отзыв в подключённый канал. Проверьте, что бот всё ещё администратор "
                "и имеет право публикации. Задание пока не засчитано."
            )
            return

    # Защита от параллельной отправки и повторного выполнения заданий одного заказчика.
    if not claim_creator_once(message.from_user.id, creator_id):
        await message.answer("❌ Вы уже выполняли задание этого пользователя. Повторная награда не начислена.")
        await state.clear()
        return
    db_execute("INSERT INTO task_completions (task_id, user_id, review_text, created_at) VALUES (?, ?, ?, ?)",
               (task_id, message.from_user.id, review_text, datetime.now().isoformat()))
    db_execute("UPDATE tasks SET count = count - 1 WHERE id = ? AND count > 0", (task_id,))
    task_check = db_execute("SELECT count FROM tasks WHERE id = ?", (task_id,))
    if task_check and task_check[0][0] == 0:
        db_execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
    add_balance(message.from_user.id, 5)
    contests = db_execute("SELECT id FROM contests WHERE is_active = 1 AND datetime(start_date) <= datetime('now') AND datetime(end_date) >= datetime('now')")
    for contest in contests:
        participant = db_execute("SELECT * FROM contest_participants WHERE contest_id = ? AND user_id = ?", (contest[0], message.from_user.id))
        if not participant:
            db_execute("INSERT INTO contest_participants (contest_id, user_id, completed_tasks, created_at) VALUES (?, ?, 1, ?)",
                       (contest[0], message.from_user.id, datetime.now().isoformat()))
        else:
            db_execute("UPDATE contest_participants SET completed_tasks = completed_tasks + 1 WHERE contest_id = ? AND user_id = ?",
                       (contest[0], message.from_user.id))
    await state.clear()
    await message.answer(
        get_text(lang, 'task_completed', task_id=task_id, balance=get_user(message.from_user.id)[3]),
        reply_markup=main_keyboard(lang)
    )

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks_callback(callback: CallbackQuery):
    await callback.message.delete()
    await show_tasks(callback.message)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.delete()
    user = get_user(callback.from_user.id)
    if user:
        await callback.message.answer(
            "Главное меню" if user[2] == 'ru' else "Main menu",
            reply_markup=main_keyboard(user[2])
        )

# ========== БАЛАНС ==========
@dp.message(F.text.in_(["💰 Мой баланс", "💰 My balance"]))
async def show_balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    await message.answer(get_text(user[2], 'balance', balance=user[3]))

# ========== РЕФЕРАЛЫ ==========
@dp.message(F.text.in_(["👥 Рефералы", "👥 Referrals"]))
async def show_referrals(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    refs = db_execute("SELECT referred_id FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    await message.answer(
        get_text(lang, 'referrals', count=len(refs), code=message.from_user.id, bot=BOT_USERNAME)
    )

# ========== ТОП РЕФЕРАЛОВ ==========
@dp.message(F.text.in_(["🏆 Топ рефералов", "🏆 Top referrers"]))
async def show_leaderboard(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    leaderboard = db_execute("""
        SELECT u.user_id, u.username, COUNT(r.id) as ref_count
        FROM users u
        JOIN referrals r ON u.user_id = r.referrer_id
        WHERE r.created_at >= ?
        GROUP BY u.user_id
        ORDER BY ref_count DESC
        LIMIT 10
    """, (week_ago,))
    
    if not leaderboard:
        text = "📭 Нет данных за неделю" if lang == 'ru' else "📭 No data for this week"
    else:
        text = "🏆 Топ рефералов за неделю:\n\n" if lang == 'ru' else "🏆 Top referrers this week:\n\n"
        for i, entry in enumerate(leaderboard, 1):
            username = entry[1] or f"User {entry[0]}"
            text += f"{i}. @{username} — {entry[2]} чел.\n"
    
    await message.answer(text)

# ========== КОНКУРСЫ ==========
@dp.message(F.text.in_(["🎯 Конкурсы", "🎯 Contests"]))
async def show_contests(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    contests = db_execute("""
        SELECT id, name, description, bonus_get, start_date, end_date 
        FROM contests 
        WHERE is_active = 1 AND datetime(start_date) <= datetime('now') AND datetime(end_date) >= datetime('now')
    """)
    
    if not contests:
        text = "🎯 Активных конкурсов нет" if lang == 'ru' else "🎯 No active contests"
    else:
        text = "🎯 Активные конкурсы:\n\n" if lang == 'ru' else "🎯 Active contests:\n\n"
        for contest in contests:
            text += f"📌 {contest[1]}\n📝 {contest[2]}\n💰 Бонус: {contest[3]} Stars\n📅 До {contest[5]}\n{'='*20}\n\n"
    
    await message.answer(text)

# ========== СТАТИСТИКА ==========
@dp.message(F.text.in_(["📊 Статистика", "📊 Statistics"]))
async def show_stats(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        return
    
    lang = user[2]
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    tasks = db_execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")[0][0]
    completed = db_execute("SELECT COUNT(*) FROM task_completions")[0][0]
    
    await message.answer(
        get_text(lang, 'stats', users=users, tasks=tasks, completed=completed, balance=user[3])
    )

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
@dp.message(Command("stat"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "🛠 Админ-панель" if lang == 'ru' else "🛠 Admin panel",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["⬅️ Выйти из админки", "⬅️ Exit admin"]))
async def exit_admin(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Главное меню" if lang == 'ru' else "Main menu",
        reply_markup=main_keyboard(lang)
    )

# ========== ГЛАВНЫЙ АДМИН: РОЛИ, ДОСТУПЫ И ЦЕНА ЗАДАНИЯ ==========
@dp.message(F.text.in_(["👑 Администраторы и цена задания", "👑 Admins and task price"]))
async def admin_control_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    cost = get_task_cost()
    if message.from_user.id == MASTER_ADMIN_ID:
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="➕ Добавить админа"), KeyboardButton(text="➖ Убрать админа")],
            [KeyboardButton(text="🔐 Доступы админов")],
            [KeyboardButton(text="💰 Изменить цену задания")],
            [KeyboardButton(text="⬅️ Выйти из админки")]
        ], resize_keyboard=True)
        await message.answer(f"👑 Главный администратор защищён: {MASTER_ADMIN_ID}\nТекущая цена задания: {cost} Stars\n\nТолько главный админ может назначать/снимать админов и менять их права.", reply_markup=kb)
    else:
        await message.answer(f"Текущая цена задания: {cost} Stars. Управление администраторами доступно только главному администратору.", reply_markup=admin_keyboard())

@dp.message(F.text == "➕ Добавить админа")
async def admin_add_start(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    await message.answer("Отправьте Telegram ID нового администратора:", reply_markup=back_keyboard())
    await state.set_state(AdminStates.admin_add_id)

@dp.message(AdminStates.admin_add_id)
async def admin_add_save(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    try: uid = int(message.text.strip())
    except Exception:
        await message.answer("Нужен числовой Telegram ID."); return
    if uid == MASTER_ADMIN_ID:
        await message.answer("Главный администратор уже защищён."); return
    import json
    defaults = {k: True for k in ADMIN_PERMISSIONS}
    db_execute("INSERT OR IGNORE INTO bot_admins (user_id, permissions, created_at) VALUES (?, ?, ?)", (uid, json.dumps(defaults), datetime.now().isoformat()))
    await state.clear(); await message.answer(f"✅ Администратор {uid} добавлен. Все доступы включены; их можно ограничить в разделе «Доступы админов».", reply_markup=admin_keyboard())

@dp.message(F.text == "➖ Убрать админа")
async def admin_remove_start(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    await message.answer("Отправьте ID администратора, которого нужно снять:", reply_markup=back_keyboard())
    await state.set_state(AdminStates.admin_remove_id)

@dp.message(AdminStates.admin_remove_id)
async def admin_remove_save(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    try: uid = int(message.text.strip())
    except Exception:
        await message.answer("Нужен числовой Telegram ID."); return
    if uid == MASTER_ADMIN_ID:
        await message.answer("⛔ Нельзя снять главного администратора."); return
    db_execute("DELETE FROM bot_admins WHERE user_id = ?", (uid,))
    await state.clear(); await message.answer(f"✅ Доступ администратора {uid} отозван.", reply_markup=admin_keyboard())

@dp.message(F.text == "🔐 Доступы админов")
async def admin_permissions_list(message: Message):
    if message.from_user.id != MASTER_ADMIN_ID: return
    rows = db_execute("SELECT user_id, permissions FROM bot_admins ORDER BY user_id")
    if not rows:
        await message.answer("Администраторов нет."); return
    for uid, raw in rows:
        if uid == MASTER_ADMIN_ID: continue
        import json
        try: perms = json.loads(raw or '{}')
        except Exception: perms = {}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=("✅ " if perms.get(k, False) else "❌ ")+label, callback_data=f"admperm_{uid}_{k}")]
            for k, label in ADMIN_PERMISSIONS.items()
        ])
        await message.answer(f"Админ {uid}: нажмите, чтобы включить/выключить права", reply_markup=kb)

@dp.callback_query(F.data.startswith("admperm_"))
async def admin_permission_toggle(callback: CallbackQuery):
    if callback.from_user.id != MASTER_ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True); return
    try:
        _, uid_s, key = callback.data.split("_", 2); uid = int(uid_s)
        if uid == MASTER_ADMIN_ID or key not in ADMIN_PERMISSIONS: raise ValueError
        import json
        row = db_execute("SELECT permissions FROM bot_admins WHERE user_id = ?", (uid,))
        if not row: raise ValueError
        perms = json.loads(row[0][0] or '{}'); perms[key] = not bool(perms.get(key, False))
        db_execute("UPDATE bot_admins SET permissions = ? WHERE user_id = ?", (json.dumps(perms), uid))
        await callback.answer("Доступ обновлён")
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=("✅ " if perms.get(k, False) else "❌ ")+label, callback_data=f"admperm_{uid}_{k}")] for k, label in ADMIN_PERMISSIONS.items()
        ]))
    except Exception:
        await callback.answer("Не удалось изменить доступ", show_alert=True)

@dp.message(F.text == "💰 Изменить цену задания")
async def task_cost_start(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    await message.answer(f"Сейчас одно задание стоит {get_task_cost()} Stars. Введите новую цену (целое число от 1):", reply_markup=back_keyboard())
    await state.set_state(AdminStates.task_cost)

@dp.message(AdminStates.task_cost)
async def task_cost_save(message: Message, state: FSMContext):
    if message.from_user.id != MASTER_ADMIN_ID: return
    try: cost = int(message.text.strip()); assert 1 <= cost <= 1000000
    except Exception:
        await message.answer("Введите целое число от 1 до 1000000."); return
    db_execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cost_per_task', ?)", (str(cost),))
    await state.clear(); await message.answer(f"✅ Цена одного задания теперь {cost} Stars. Новая цена применяется к новым заказам.", reply_markup=admin_keyboard())

# ========== УПРАВЛЕНИЕ КАНАЛОМ ==========
@dp.message(F.text.in_(["📢 Управление каналом", "📢 Channel management"]))
async def channel_management(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'channel'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    current_channel = get_channel() or "Не установлен" if lang == 'ru' else "Not set"
    channel_text = f"📢 Текущий канал: {current_channel}" if lang == 'ru' else f"📢 Current channel: {current_channel}"
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить канал" if lang == 'ru' else "➕ Add channel")],
        [KeyboardButton(text="❌ Удалить канал" if lang == 'ru' else "❌ Delete channel")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(channel_text, reply_markup=keyboard)

@dp.message(F.text.in_(["➕ Добавить канал", "➕ Add channel"]))
async def add_channel_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'channel'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите @канал для обязательной подписки:" if lang == 'ru' else "Enter @channel for mandatory subscription:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.channel_add)

@dp.message(AdminStates.channel_add)
async def add_channel_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'channel'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await channel_management(message, state)
        await state.clear()
        return
    
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Канал должен начинаться с @" if lang == 'ru' else "❌ Channel must start with @")
        return
    
    set_channel(channel)
    await state.clear()
    await message.answer(
        f"✅ Канал {channel} добавлен в обязательную подписку!" if lang == 'ru' else f"✅ Channel {channel} added to mandatory subscription!",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["❌ Удалить канал", "❌ Delete channel"]))
async def delete_channel_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'channel'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    current = get_channel()
    if not current:
        await message.answer(
            "❌ Канал не установлен" if lang == 'ru' else "❌ Channel not set",
            reply_markup=admin_keyboard(lang)
        )
        return
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Да, удалить" if lang == 'ru' else "✅ Yes, delete")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        f"⚠️ Вы уверены, что хотите удалить канал {current}?" if lang == 'ru' else f"⚠️ Are you sure you want to delete channel {current}?",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.channel_delete)

@dp.message(AdminStates.channel_delete)
async def delete_channel_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'channel'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await channel_management(message, state)
        await state.clear()
        return
    
    if message.text in ["✅ Да, удалить", "✅ Yes, delete"]:
        set_channel("")
        await state.clear()
        await message.answer(
            "✅ Канал удалён из обязательной подписки!" if lang == 'ru' else "✅ Channel removed from mandatory subscription!",
            reply_markup=admin_keyboard(lang)
        )
    else:
        await message.answer(
            "❌ Отмена" if lang == 'ru' else "❌ Cancelled",
            reply_markup=admin_keyboard(lang)
        )
        await state.clear()

# ========== РАССЫЛКА ==========
@dp.message(F.text.in_(["📢 Рассылка", "📢 Broadcast"]))
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'broadcast'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "📢 Введите текст рассылки:" if lang == 'ru' else "📢 Enter broadcast text:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'broadcast'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    users = db_execute("SELECT user_id, language FROM users WHERE is_banned = 0")
    success = 0
    
    await message.answer(
        f"📢 Начинаю рассылку {len(users)} пользователям..." if lang == 'ru' else f"📢 Starting broadcast to {len(users)} users..."
    )
    
    for user_data in users:
        try:
            await bot.send_message(user_data[0], message.text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await state.clear()
    await message.answer(
        f"✅ Отправлено: {success}/{len(users)}" if lang == 'ru' else f"✅ Sent: {success}/{len(users)}"
    )

# ========== БАНЫ ==========
@dp.message(F.text.in_(["🚫 Баны", "🚫 Bans"]))
async def ban_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'bans'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔨 Забанить" if lang == 'ru' else "🔨 Ban")],
        [KeyboardButton(text="🔓 Разбанить" if lang == 'ru' else "🔓 Unban")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🚫 Управление банами" if lang == 'ru' else "🚫 Ban management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["🔨 Забанить", "🔨 Ban"]))
async def ban_user_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'bans'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID или @username" if lang == 'ru' else "Enter ID or @username",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.ban_user)

@dp.message(AdminStates.ban_user)
async def ban_user_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'bans'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user_data = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user_data:
            await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
            return
        user_id = user_data[0][0]
    
    db_execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(
        f"✅ Забанен {user_id}" if lang == 'ru' else f"✅ Banned {user_id}",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["🔓 Разбанить", "🔓 Unban"]))
async def unban_user_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'bans'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID или @username" if lang == 'ru' else "Enter ID or @username",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.unban_user)

@dp.message(AdminStates.unban_user)
async def unban_user_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'bans'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except:
        username = message.text.strip().replace("@", "")
        user_data = db_execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if not user_data:
            await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
            return
        user_id = user_data[0][0]
    
    db_execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    await state.clear()
    await message.answer(
        f"✅ Разбанен {user_id}" if lang == 'ru' else f"✅ Unbanned {user_id}",
        reply_markup=admin_keyboard(lang)
    )

# ========== УПРАВЛЕНИЕ БАЛАНСОМ ==========
@dp.message(F.text.in_(["🔨 Управление балансом", "🔨 Balance management"]))
async def balance_admin_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'balance'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Выдать Stars" if lang == 'ru' else "➕ Add Stars")],
        [KeyboardButton(text="➖ Забрать Stars" if lang == 'ru' else "➖ Remove Stars")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🔨 Управление балансом" if lang == 'ru' else "🔨 Balance management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["➕ Выдать Stars", "➕ Add Stars"]))
async def add_balance_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'balance'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID и сумму через пробел" if lang == 'ru' else "Enter ID and amount separated by space",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.add_balance)

@dp.message(AdminStates.add_balance)
async def add_balance_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'balance'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Нужно ID и сумма" if lang == 'ru' else "❌ Need ID and amount")
        return
    
    try:
        user_id, amount = int(parts[0]), int(parts[1])
    except:
        await message.answer("❌ Неверный формат" if lang == 'ru' else "❌ Invalid format")
        return
    
    add_balance(user_id, amount)
    await state.clear()
    await message.answer(
        f"✅ +{amount} Stars пользователю {user_id}" if lang == 'ru' else f"✅ +{amount} Stars to user {user_id}",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["➖ Забрать Stars", "➖ Remove Stars"]))
async def remove_balance_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'balance'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID и сумму" if lang == 'ru' else "Enter ID and amount",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.remove_balance)

@dp.message(AdminStates.remove_balance)
async def remove_balance_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'balance'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Нужно ID и сумма" if lang == 'ru' else "❌ Need ID and amount")
        return
    
    try:
        user_id, amount = int(parts[0]), int(parts[1])
    except:
        await message.answer("❌ Неверный формат" if lang == 'ru' else "❌ Invalid format")
        return
    
    if subtract_balance(user_id, amount):
        await message.answer(
            f"✅ -{amount} Stars у {user_id}" if lang == 'ru' else f"✅ -{amount} Stars from {user_id}",
            reply_markup=admin_keyboard(lang)
        )
    else:
        await message.answer(
            "❌ Недостаточно средств" if lang == 'ru' else "❌ Insufficient funds",
            reply_markup=admin_keyboard(lang)
        )
    await state.clear()

# ========== ЗАЯВКИ НА ПОПОЛНЕНИЕ ==========
@dp.message(F.text.in_(["💳 Заявки на пополнение", "💳 Deposit requests"]))
async def deposit_requests_admin(message: Message):
    if not is_admin(message.from_user.id, 'payments'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    requests = db_execute("""
        SELECT id, user_id, request_id, stars_amount, get_amount, status, created_at 
        FROM deposit_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет заявок" if lang == 'ru' else "📭 No requests")
        return
    
    for req in requests:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm", callback_data=f"confirm_dep_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить" if lang == 'ru' else "❌ Reject", callback_data=f"reject_dep_{req[0]}")]
        ])
        await message.answer(
            f"📩 #{req[2]}\n👤 {req[1]}\n⭐ {req[3]} = {req[4]} Stars",
            reply_markup=keyboard
        )

@dp.callback_query(F.data.startswith("confirm_dep_"))
async def confirm_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id, 'payments'):
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM deposit_requests WHERE id = ?", (req_id,))
    if not req:
        await callback.answer("❌ Нет")
        return
    
    req = req[0]
    add_balance(req[1], req[4])
    db_execute("UPDATE deposit_requests SET status = 'completed' WHERE id = ?", (req_id,))
    
    user = get_user(req[1])
    lang = user[2] if user else 'ru'
    await bot.send_message(req[1], f"✅ Пополнено на {req[4]} Stars!" if lang == 'ru' else f"✅ Deposited {req[4]} Stars!")
    await callback.message.edit_text(f"✅ Заявка {req[2]} подтверждена")
    await callback.answer("✅")

@dp.callback_query(F.data.startswith("reject_dep_"))
async def reject_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id, 'payments'):
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    db_execute("UPDATE deposit_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    await callback.message.edit_text("❌ Отклонено")
    await callback.answer("❌")

# ========== ЗАЯВКИ НА ВЫВОД ==========
@dp.message(F.text.in_(["💸 Заявки на вывод", "💸 Withdraw requests"]))
async def withdraw_requests_admin(message: Message):
    if not is_admin(message.from_user.id, 'payments'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    requests = db_execute("""
        SELECT id, user_id, username, get_amount, stars_amount, gift_name, status, created_at 
        FROM withdraw_requests WHERE status = 'pending'
    """)
    
    if not requests:
        await message.answer("📭 Нет заявок" if lang == 'ru' else "📭 No requests")
        return
    
    for req in requests:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить" if lang == 'ru' else "✅ Confirm", callback_data=f"confirm_wd_{req[0]}")],
            [InlineKeyboardButton(text="❌ Отклонить" if lang == 'ru' else "❌ Reject", callback_data=f"reject_wd_{req[0]}")]
        ])
        await message.answer(
            f"🎁 {req[5]}\n👤 @{req[2]}\n⭐ {req[4]} = {req[3]} Stars",
            reply_markup=keyboard
        )

@dp.callback_query(F.data.startswith("confirm_wd_"))
async def confirm_withdraw(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id, 'payments'):
        await callback.answer("❌ Не админ")
        return
    req_id = int(callback.data.split("_")[2])
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ?", (req_id,))
    if not req or req[0][6] != 'pending':
        await callback.answer("❌ Заявка уже обработана или не найдена", show_alert=True)
        return
    await state.update_data(withdraw_request_id=req_id)
    await state.set_state(AdminStates.withdraw_proof)
    db_execute("UPDATE withdraw_requests SET status = 'processing' WHERE id = ? AND status = 'pending'", (req_id,))
    await callback.message.answer(
        f"📸 Пришлите скриншот фактической выплаты по заявке #{req_id}. "
        f"После публикации подтверждение будет отправлено в {PAYOUT_CHANNEL_ID}."
    )
    await callback.answer("Ожидаю скриншот")

@dp.message(AdminStates.withdraw_proof, F.photo)
async def publish_withdraw_proof(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'payments'):
        return
    data = await state.get_data()
    req_id = data.get("withdraw_request_id")
    req_rows = db_execute("SELECT * FROM withdraw_requests WHERE id = ? AND status = 'processing'", (req_id,))
    if not req_rows:
        await state.clear()
        await message.answer("❌ Заявка не найдена или уже обработана.")
        return
    req = req_rows[0]
    username = (req[2] or str(req[1])).lstrip("@")
    caption = f"Выплата для @{username}\nСумма звезд: {req[4]} ⭐"
    try:
        await bot.copy_message(
            chat_id=PAYOUT_CHANNEL_ID, from_chat_id=message.chat.id,
            message_id=message.message_id, caption=caption
        )
    except Exception as exc:
        logging.exception("Failed to publish payout proof: %s", exc)
        await message.answer(
            f"❌ Не удалось опубликовать скриншот в {PAYOUT_CHANNEL_ID}. "
            "Проверьте, что бот является администратором канала и может публиковать сообщения. "
            "Заявка осталась в обработке."
        )
        return
    db_execute("UPDATE withdraw_requests SET status = 'completed' WHERE id = ? AND status = 'processing'", (req_id,))
    user = get_user(req[1])
    lang = user[2] if user else 'ru'
    await bot.send_message(req[1],
        f"✅ Выплата подтверждена. Скриншот опубликован в {PAYOUT_CHANNEL_ID}."
        if lang == 'ru' else f"✅ Payout confirmed. Proof posted in {PAYOUT_CHANNEL_ID}.")
    await message.answer(f"✅ Выплата #{req_id} опубликована и отмечена выполненной.")
    await state.clear()

@dp.message(AdminStates.withdraw_proof)
async def withdraw_proof_need_photo(message: Message):
    if is_admin(message.from_user.id):
        await message.answer("Пришлите именно фотографию/скриншот выплаты.")

@dp.callback_query(F.data.startswith("reject_wd_"))
async def reject_withdraw(callback: CallbackQuery):
    if not is_admin(callback.from_user.id, 'payments'):
        await callback.answer("❌ Не админ")
        return
    
    req_id = int(callback.data.split("_")[2])
    db_execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    
    req = db_execute("SELECT * FROM withdraw_requests WHERE id = ?", (req_id,))
    if req:
        add_balance(req[0][1], req[0][3])
        user = get_user(req[0][1])
        lang = user[2] if user else 'ru'
        await bot.send_message(req[0][1], 
            "❌ Заявка отклонена, Stars возвращены." if lang == 'ru' else "❌ Request rejected, Stars returned.")
    
    await callback.message.edit_text("❌ Отклонено")
    await callback.answer("❌")

# ========== ПРОМОКОДЫ ==========
@dp.message(F.text.in_(["🎟 Создать промокод", "🎟 Create promo"]))
async def create_promo_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'promos'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "🎟 Введите код:" if lang == 'ru' else "🎟 Enter code:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.promo_code)

@dp.message(AdminStates.promo_code)
async def create_promo_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'promos'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    code = message.text.strip().upper()
    if not code:
        await message.answer("❌ Пусто" if lang == 'ru' else "❌ Empty")
        return
    
    await state.update_data(promo_code=code)
    await message.answer(
        "Введите бонус в Stars:" if lang == 'ru' else "Enter bonus in Stars:"
    )
    await state.set_state(AdminStates.promo_bonus)

@dp.message(AdminStates.promo_bonus)
async def create_promo_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'promos'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        bonus = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    await state.update_data(promo_bonus=bonus)
    await message.answer(
        "Лимит (0 - безлимит):" if lang == 'ru' else "Limit (0 - unlimited):"
    )
    await state.set_state(AdminStates.promo_limit)

@dp.message(AdminStates.promo_limit)
async def create_promo_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'promos'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    try:
        limit = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    data = await state.get_data()
    db_execute("""
        INSERT INTO promo_codes (code, bonus_get, uses_limit, created_at)
        VALUES (?, ?, ?, ?)
    """, (data['promo_code'], data['promo_bonus'], limit, datetime.now().isoformat()))
    
    await state.clear()
    await message.answer(
        f"✅ Промокод {data['promo_code']} +{data['promo_bonus']} Stars" if lang == 'ru' else f"✅ Promo {data['promo_code']} +{data['promo_bonus']} Stars",
        reply_markup=admin_keyboard(lang)
    )

# ========== КОНКУРСЫ (АДМИН) ==========
@dp.message(F.text.in_(["🎯 Конкурсы", "🎯 Contests"]))
async def contests_admin_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать конкурс" if lang == 'ru' else "➕ Create contest")],
        [KeyboardButton(text="📋 Активные конкурсы" if lang == 'ru' else "📋 Active contests")],
        [KeyboardButton(text="🏆 Выдать бонусы" if lang == 'ru' else "🏆 Give bonuses")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "🎯 Управление конкурсами" if lang == 'ru' else "🎯 Contest management",
        reply_markup=keyboard
    )

@dp.message(F.text.in_(["➕ Создать конкурс", "➕ Create contest"]))
async def create_contest_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "📌 Название конкурса:" if lang == 'ru' else "📌 Contest name:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.contest_name)

@dp.message(AdminStates.contest_name)
async def create_contest_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    await state.update_data(contest_name=message.text.strip())
    await message.answer(
        "📝 Описание конкурса:" if lang == 'ru' else "📝 Contest description:"
    )
    await state.set_state(AdminStates.contest_desc)

@dp.message(AdminStates.contest_desc)
async def create_contest_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    await state.update_data(contest_desc=message.text.strip())
    await message.answer(
        "💰 Бонус за участие (Stars):" if lang == 'ru' else "💰 Bonus for participation (Stars):"
    )
    await state.set_state(AdminStates.contest_bonus)

@dp.message(AdminStates.contest_bonus)
async def create_contest_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        bonus = int(message.text.strip())
    except:
        await message.answer("❌ Число" if lang == 'ru' else "❌ Number")
        return
    
    await state.update_data(contest_bonus=bonus)
    await message.answer(
        "📅 Дата начала (ГГГГ-ММ-ДД):" if lang == 'ru' else "📅 Start date (YYYY-MM-DD):"
    )
    await state.set_state(AdminStates.contest_start)

@dp.message(AdminStates.contest_start)
async def create_contest_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        start = datetime.strptime(message.text.strip(), "%Y-%m-%d").isoformat()
    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД" if lang == 'ru' else "❌ Format: YYYY-MM-DD")
        return
    
    await state.update_data(contest_start=start)
    await message.answer(
        "📅 Дата окончания (ГГГГ-ММ-ДД):" if lang == 'ru' else "📅 End date (YYYY-MM-DD):"
    )
    await state.set_state(AdminStates.contest_end)

@dp.message(AdminStates.contest_end)
async def create_contest_end(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        end = datetime.strptime(message.text.strip(), "%Y-%m-%d").isoformat()
    except:
        await message.answer("❌ Формат: ГГГГ-ММ-ДД" if lang == 'ru' else "❌ Format: YYYY-MM-DD")
        return
    
    data = await state.get_data()
    
    db_execute("""
        INSERT INTO contests (name, description, bonus_get, start_date, end_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data['contest_name'], data['contest_desc'], data['contest_bonus'], 
          data['contest_start'], end, datetime.now().isoformat()))
    
    await state.clear()
    await message.answer(
        f"✅ Конкурс '{data['contest_name']}' создан!" if lang == 'ru' else f"✅ Contest '{data['contest_name']}' created!",
        reply_markup=admin_keyboard(lang)
    )

@dp.message(F.text.in_(["📋 Активные конкурсы", "📋 Active contests"]))
async def list_contests_admin(message: Message):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    contests = db_execute("SELECT id, name, description, bonus_get, start_date, end_date, is_active FROM contests")
    
    if not contests:
        await message.answer("📭 Нет конкурсов" if lang == 'ru' else "📭 No contests")
        return
    
    text = "📋 Конкурсы:\n\n" if lang == 'ru' else "📋 Contests:\n\n"
    for c in contests:
        status = "✅ Активен" if c[6] == 1 else "❌ Не активен"
        if lang == 'en':
            status = "✅ Active" if c[6] == 1 else "❌ Inactive"
        text += f"#{c[0]}: {c[1]}\n📝 {c[2]}\n💰 {c[3]} Stars\n📅 {c[4][:10]} → {c[5][:10]}\n{status}\n{'='*20}\n\n"
    
    await message.answer(text[:4000])

@dp.message(F.text.in_(["🏆 Выдать бонусы", "🏆 Give bonuses"]))
async def give_contest_bonuses(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    await message.answer(
        "Введите ID конкурса для выдачи бонусов:" if lang == 'ru' else "Enter contest ID to give bonuses:",
        reply_markup=back_keyboard(lang)
    )
    await state.set_state(AdminStates.leaderboard_bonus)

@dp.message(AdminStates.leaderboard_bonus)
async def give_contest_bonuses_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'contests'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await contests_admin_menu(message, state)
        await state.clear()
        return
    
    try:
        contest_id = int(message.text.strip())
    except:
        await message.answer("❌ Введите число" if lang == 'ru' else "❌ Enter a number")
        return
    
    contest = db_execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
    if not contest:
        await message.answer("❌ Конкурс не найден" if lang == 'ru' else "❌ Contest not found")
        return
    
    participants = db_execute("""
        SELECT user_id, completed_tasks
        FROM contest_participants
        WHERE contest_id = ?
        ORDER BY completed_tasks DESC
        LIMIT 3
    """, (contest_id,))
    
    if not participants:
        await message.answer("📭 Нет участников" if lang == 'ru' else "📭 No participants")
        await state.clear()
        return
    
    contest = contest[0]
    text = f"🏆 Призеры конкурса '{contest[1]}':\n\n" if lang == 'ru' else f"🏆 Contest '{contest[1]}' winners:\n\n"
    
    bonuses = [contest[3], contest[3] // 2, contest[3] // 3]
    
    for i, participant in enumerate(participants[:3]):
        user_id, tasks_done = participant
        bonus = bonuses[i] if i < len(bonuses) else 0
        add_balance(user_id, bonus)
        text += f"{i+1}. Пользователь {user_id} — {tasks_done} заданий, +{bonus} Stars\n" if lang == 'ru' else f"{i+1}. User {user_id} — {tasks_done} tasks, +{bonus} Stars\n"
        
        try:
            await bot.send_message(user_id, 
                f"🏆 Вы заняли {i+1} место в конкурсе '{contest[1]}'!\n💰 +{bonus} Stars на баланс!" if lang == 'ru' else
                f"🏆 You took {i+1} place in contest '{contest[1]}'!\n💰 +{bonus} Stars to balance!")
        except:
            pass
    
    await state.clear()
    await message.answer(text, reply_markup=admin_keyboard(lang))

# ========== ПОЛЬЗОВАТЕЛИ ==========
@dp.message(F.text.in_(["👥 Пользователи", "👥 Users"]))
async def users_list(message: Message):
    if not is_admin(message.from_user.id, 'users'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    users = db_execute("SELECT COUNT(*) FROM users")[0][0]
    banned = db_execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")[0][0]
    total = db_execute("SELECT SUM(balance) FROM users")[0][0]
    verified = db_execute("SELECT COUNT(*) FROM users WHERE is_verified = 1")[0][0]
    
    await message.answer(
        f"👥 Всего: {users}\n✅ Верифицированы: {verified}\n🚫 Забанено: {banned}\n💰 Общий баланс: {total if total else 0}\n🌐 Языки: RU/EN" if lang == 'ru' else
        f"👥 Total: {users}\n✅ Verified: {verified}\n🚫 Banned: {banned}\n💰 Total balance: {total if total else 0}\n🌐 Languages: RU/EN"
    )

# ========== СБРОС БАЗЫ ДАННЫХ ==========
@dp.message(F.text.in_(["🗑 Сбросить БД", "🗑 Reset DB"]))
async def reset_db_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'reset_db'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚠️ ДА, СБРОСИТЬ ВСЁ" if lang == 'ru' else "⚠️ YES, RESET ALL")],
        [KeyboardButton(text=get_text(lang, 'back'))]
    ], resize_keyboard=True)
    
    await message.answer(
        "⚠️ ВНИМАНИЕ! Это действие НЕОБРАТИМО!\n\n"
        "Будут удалены ВСЕ данные:\n"
        "- 👥 Все пользователи\n"
        "- 📋 Все задания\n"
        "- 💰 Все транзакции\n"
        "- 👥 Все рефералы\n"
        "- 🎯 Все конкурсы\n\n"
        "Вы уверены?" if lang == 'ru' else
        "⚠️ WARNING! This action is IRREVERSIBLE!\n\n"
        "ALL data will be deleted:\n"
        "- 👥 All users\n"
        "- 📋 All tasks\n"
        "- 💰 All transactions\n"
        "- 👥 All referrals\n"
        "- 🎯 All contests\n\n"
        "Are you sure?",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.reset_db_confirm)

@dp.message(AdminStates.reset_db_confirm)
async def reset_db_execute(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id, 'reset_db'):
        return
    
    user = get_user(message.from_user.id)
    lang = user[2] if user else 'ru'
    
    if message.text in ["🔙 Назад", "🔙 Back"]:
        await admin_panel(message)
        await state.clear()
        return
    
    if message.text not in ["⚠️ ДА, СБРОСИТЬ ВСЁ", "⚠️ YES, RESET ALL"]:
        await message.answer(
            "❌ Отмена" if lang == 'ru' else "❌ Cancelled",
            reply_markup=admin_keyboard(lang)
        )
        await state.clear()
        return
    
    try:
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            await message.answer(
                "✅ База данных полностью сброшена!\n\n"
                "Бот перезапускается с чистой БД..." if lang == 'ru' else
                "✅ Database completely reset!\n\n"
                "Bot restarting with clean DB...",
                reply_markup=admin_keyboard(lang)
            )
            init_db()
            await message.answer(
                "✅ База данных создана заново!" if lang == 'ru' else "✅ Database recreated!",
                reply_markup=admin_keyboard(lang)
            )
        else:
            await message.answer(
                "❌ Файл базы данных не найден. Создаю новый..." if lang == 'ru' else "❌ Database file not found. Creating new...",
                reply_markup=admin_keyboard(lang)
            )
            init_db()
            await message.answer(
                "✅ База данных создана!" if lang == 'ru' else "✅ Database created!",
                reply_markup=admin_keyboard(lang)
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при сбросе БД: {e}" if lang == 'ru' else f"❌ Error resetting DB: {e}",
            reply_markup=admin_keyboard(lang)
        )
    
    await state.clear()

# ========== ПРОМОКОДЫ (ДЛЯ ПОЛЬЗОВАТЕЛЕЙ) ==========
@dp.message(Command("promo"))
async def use_promo(message: Message):
    user = get_user(message.from_user.id)
    if not user or user[6] == 1:
        return
    
    lang = user[2]
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ /promo КОД" if lang == 'ru' else "❌ /promo CODE")
        return
    
    code = args[1].upper()
    promo = db_execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
    if not promo:
        await message.answer("❌ Не найден" if lang == 'ru' else "❌ Not found")
        return
    
    promo = promo[0]
    used = db_execute("SELECT * FROM promo_uses WHERE promo_id = ? AND user_id = ?", (promo[0], message.from_user.id))
    if used:
        await message.answer("❌ Уже использован" if lang == 'ru' else "❌ Already used")
        return
    
    if promo[3] > 0 and promo[4] >= promo[3]:
        await message.answer("❌ Лимит исчерпан" if lang == 'ru' else "❌ Limit reached")
        return
    
    add_balance(message.from_user.id, promo[2])
    db_execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?", (promo[0],))
    db_execute("INSERT INTO promo_uses (promo_id, user_id, created_at) VALUES (?, ?, ?)",
               (promo[0], message.from_user.id, datetime.now().isoformat()))
    
    await message.answer(f"✅ +{promo[2]} Stars" if lang == 'ru' else f"✅ +{promo[2]} Stars")

# ========== ЗАПУСК ==========
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Создайте .env по образцу .env.example")
    global bot
    if bot is None:
        raise RuntimeError("BOT_TOKEN не задан. Создайте .env по образцу .env.example")
    init_db()
    # Устанавливаем отображаемое имя Telegram-профиля бота.
    try:
        await bot.set_my_name(name="Rep Up")
    except Exception:
        logging.exception("Не удалось автоматически установить имя бота; задайте Rep Up через BotFather")
    logging.info("🚀 Rep Up запущен!")
    logging.info(f"📱 Бот: @{BOT_USERNAME}")
    logging.info(f"👑 Админ: {ADMIN_IDS[0]}")
    logging.info(f"📢 Канал: {get_channel()}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
