"""SQLite schema and database helpers for Rep Up.

Keep the existing database file; init_db only creates/migrates tables.
"""
import sqlite3
from datetime import datetime

def init_db(db_name, channel_id, admin_ids):
    conn = sqlite3.connect(db_name)
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
    for configured_admin in admin_ids:
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
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_id', ?)", (channel_id,))
    cur.execute("UPDATE settings SET value = ? WHERE key = 'channel_id' AND value = '@Client_Voice_NEWS'", (channel_id,))
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


def db_execute(db_name, query, params=()):
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    result = cur.fetchall()
    conn.close()
    return result

