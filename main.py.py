import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, CallbackQueryHandler,
    Filters, CallbackContext
)

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8695461708:AAHqGplWvv9Ek_Ih8AYG67wPXAUv5k2jGCE"
GROUP_ID = -1003982153873  # Tasdiqlash guruhi ID si

ADMIN_IDS = [1118535187]  # Bot adminlari

CARD_NUMBER = "5614681871473652"
CARD_OWNER = "jasurbek t"

VIP_PRICES = {
    "1_kun": 6000,
    "3_kun": 9000,
    "1_hafta": 13000,
    "2_hafta": 18000,
    "1_oy": 27000,
    "3_oy": 60000,
    "1_yil": 65000,
}
VIP_LABELS = {
    "1_kun": "1 kun - 6,000",
    "3_kun": "3 kun - 9,000",
    "1_hafta": "1 hafta - 13,000",
    "2_hafta": "2 hafta - 18,000",
    "1_oy": "1 oy - 27,000",
    "3_oy": "3 oy - 60,000",
    "1_yil": "1 yil - 65,000",
}
VIP_DAYS = {
    "1_kun": 1,
    "3_kun": 3,
    "1_hafta": 7,
    "2_hafta": 14,
    "1_oy": 30,
    "3_oy": 90,
    "1_yil": 365,
}

VILOYATLAR = [
    "Toshkent", "Andijon", "Buxoro", "Farg'ona",
    "Jizzax", "Xorazm", "Namangan", "Navoiy",
    "Qashqadaryo", "Qoraqalpog'iston", "Samarqand",
    "Sirdaryo", "Surxondaryo"
]

SURXONDARYO_TUMANLAR = [
    "Termiz shahri", "Angor", "Bandixon", "Denov",
    "Jarqo'rg'on", "Qiziriq", "Qumqo'rg'on", "Muzrabot",
    "Oltinsoy", "Sariosiyo", "Sherobod", "Sho'rchi",
    "Termiz tumani", "Uzun", "Boysun"
]

# Holatlar
STATE_REG_PHOTO    = "reg_photo_wait"
STATE_REG_NAME     = "reg_name_wait"
STATE_REG_GENDER   = "reg_gender_wait"
STATE_REG_AGE      = "reg_age_wait"
STATE_REG_VILOYAT  = "reg_viloyat_wait"
STATE_REG_TUMAN    = "reg_tuman_wait"
STATE_MSG_TARGET   = "msg_target"
STATE_EDITING      = "editing"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================

def init_db():
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()

    # Users jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        photo_id TEXT,
        gender TEXT,
        age INTEGER,
        viloyat TEXT,
        tuman TEXT,
        vip_until TEXT,
        rating REAL DEFAULT 0,
        rating_count INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        registered_at TEXT,
        is_active INTEGER DEFAULT 1
    )""")

    # Payments jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        period TEXT,
        days INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        confirmed_at TEXT,
        confirmed_by INTEGER
    )""")

    # MIGRATION: eski DB ga yetishmayotgan ustunlarni qo'shish
    pay_cols = [row[1] for row in c.execute("PRAGMA table_info(payments)").fetchall()]
    if "confirmed_at" not in pay_cols:
        c.execute("ALTER TABLE payments ADD COLUMN confirmed_at TEXT")
        logger.info("Migration: payments.confirmed_at qoshildi")
    if "confirmed_by" not in pay_cols:
        c.execute("ALTER TABLE payments ADD COLUMN confirmed_by INTEGER")
        logger.info("Migration: payments.confirmed_by qoshildi")

    usr_cols = [row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()]
    if "is_active" not in usr_cols:
        c.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
        logger.info("Migration: users.is_active qoshildi")

    conn.commit()
    conn.close()
    logger.info("DB init/migration muvaffaqiyatli bajarildi")

def get_user(user_id):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "photo_id": row[3], "gender": row[4], "age": row[5],
            "viloyat": row[6], "tuman": row[7], "vip_until": row[8],
            "rating": row[9], "rating_count": row[10], "likes": row[11],
            "registered_at": row[12], "is_active": row[13]
        }
    return None

def save_user(data):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO users
        (user_id, username, full_name, photo_id, gender, age, viloyat, tuman, registered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["user_id"], data.get("username"), data.get("full_name"),
         data.get("photo_id"), data.get("gender"), data.get("age"),
         data.get("viloyat"), data.get("tuman", ""),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def is_vip(user_id):
    user = get_user(user_id)
    if not user or not user["vip_until"]:
        return False
    try:
        vip_date = datetime.strptime(user["vip_until"], "%Y-%m-%d %H:%M:%S")
        return vip_date > datetime.now()
    except Exception:
        return False

def get_random_user(exclude_id, gender=None):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    if gender:
        c.execute("""SELECT * FROM users WHERE user_id != ? AND gender = ?
                     AND is_active = 1 ORDER BY RANDOM() LIMIT 1""",
                  (exclude_id, gender))
    else:
        c.execute("""SELECT * FROM users WHERE user_id != ?
                     AND is_active = 1 ORDER BY RANDOM() LIMIT 1""",
                  (exclude_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "photo_id": row[3], "gender": row[4], "age": row[5],
            "viloyat": row[6], "tuman": row[7], "likes": row[11]
        }
    return None

def save_payment(user_id, amount, period, days):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    # Oldingi pending to'lovlarni bekor qilish
    c.execute("UPDATE payments SET status='cancelled' WHERE user_id=? AND status='pending'", (user_id,))
    c.execute("""INSERT INTO payments (user_id, amount, period, days, created_at)
                 VALUES (?, ?, ?, ?, ?)""",
              (user_id, amount, period, days,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid

def get_payment_by_id(payment_id):
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "amount": row[2],
                "period": row[3], "days": row[4], "status": row[5]}
    return None

def activate_vip(user_id, days, confirmed_by, payment_id):
    user = get_user(user_id)
    now = datetime.now()
    if user and user["vip_until"]:
        try:
            cur = datetime.strptime(user["vip_until"], "%Y-%m-%d %H:%M:%S")
            new_date = (cur if cur > now else now) + timedelta(days=days)
        except Exception:
            new_date = now + timedelta(days=days)
    else:
        new_date = now + timedelta(days=days)
    update_user(user_id, vip_until=new_date.strftime("%Y-%m-%d %H:%M:%S"))
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute("""UPDATE payments SET status='confirmed', confirmed_at=?, confirmed_by=?
                 WHERE id=?""",
              (now.strftime("%Y-%m-%d %H:%M:%S"), confirmed_by, payment_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE vip_until > ?",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    vip_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM payments WHERE status='confirmed'")
    pays = c.fetchone()[0]
    conn.close()
    return total, vip_count, pays

# ==================== KEYBOARDS ====================

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🔍 Tanishuv boshlash"],
        ["👦 O'g'il bola izlash 👑", "👸 Qiz bola izlash 👑"],
        ["Profil 👤", "Baholarim ⭐"],
        ["💎 VIP olish"],
    ], resize_keyboard=True)

def gender_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👦 O'g'il bola", callback_data="gender_ogil"),
        InlineKeyboardButton("👸 Qiz bola", callback_data="gender_qiz"),
    ]])

def age_kb():
    buttons = []
    row = []
    for age in range(14, 46):
        row.append(InlineKeyboardButton(str(age), callback_data=f"age_{age}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def viloyat_kb():
    buttons = []
    row = []
    for v in VILOYATLAR:
        row.append(InlineKeyboardButton(v, callback_data=f"vil_{v}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def tuman_kb():
    buttons = []
    row = []
    for t in SURXONDARYO_TUMANLAR:
        row.append(InlineKeyboardButton(t, callback_data=f"tum_{t}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def vip_period_kb():
    buttons = []
    row = []
    for key, label in VIP_LABELS.items():
        row.append(InlineKeyboardButton(
            f"💎 {label} so'm",
            callback_data=f"vip_{key}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_vip")])
    return InlineKeyboardMarkup(buttons)

def confirm_payment_kb(user_id, payment_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ To'lov qildim", callback_data=f"paid_{user_id}_{payment_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_pay")],
    ])

def search_kb(found_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❤️ Like", callback_data=f"like_{found_id}"),
            InlineKeyboardButton("⏭ O'tkazish", callback_data=f"skip_{found_id}"),
            InlineKeyboardButton("⚠️ Shikoyat", callback_data=f"rep_{found_id}"),
        ],
        [InlineKeyboardButton("✉️ Xabar yuborish", callback_data=f"msg_{found_id}")],
    ])

def profile_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_menu")],
    ])

def edit_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Rasm", callback_data="ed_photo"),
         InlineKeyboardButton("⚤ Jins", callback_data="ed_gender")],
        [InlineKeyboardButton("🎂 Yosh", callback_data="ed_age"),
         InlineKeyboardButton("📍 Viloyat", callback_data="ed_viloyat")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="ed_back")],
    ])

def admin_confirm_kb(payment_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ VIP tasdiqlash",
                callback_data=f"confirmvip_{payment_id}_{user_id}"
            ),
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"rejectvip_{payment_id}_{user_id}"
            )
        ]
    ])

# ==================== HELPERS ====================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def vip_label(user_id):
    if is_vip(user_id):
        user = get_user(user_id)
        try:
            d = datetime.strptime(user["vip_until"], "%Y-%m-%d %H:%M:%S")
            days = (d - datetime.now()).days
            return f"✅ Faol ({days} kun qoldi)"
        except Exception:
            return "✅ Faol"
    return "❌ Faol emas"

def gender_text(g):
    return "O'g'il bola" if g == "ogil" else "Qiz bola"

def format_my_profile(user):
    nomalum = "Noma'lum"
    loc = f"{user['viloyat']}, {user['tuman']}" if user.get("tuman") else (user["viloyat"] or nomalum)
    return (
        "Sizning anketangiz:\n\n"
        f"👤 Ism: {user['full_name'] or nomalum}\n"
        f"👤 Username: @{user['username'] or nomalum}\n"
        f"❤️ Jins: {gender_text(user['gender'])}\n"
        f"🎂 Yosh: {user['age']}\n"
        f"📍 Joylashuv: {loc}\n"
        f"❤️ Likelar: {user['likes'] or 0}\n"
        f"💎 VIP: {vip_label(user['user_id'])}"
    )

def format_stranger(user, viewer_vip):
    nomalum = "Noma'lum"
    loc = f"{user['viloyat']}, {user['tuman']}" if user.get("tuman") else str(user['viloyat'] or nomalum)
    hidden = "🔒 VIP kerak"
    if viewer_vip:
        return (
            f"👤 Ism: {user['full_name'] or nomalum}\n"
            f"👤 Username: @{user['username'] or nomalum}\n"
            f"❤️ Jins: {gender_text(user['gender'])}\n"
            f"🎂 Yosh: {user['age']}\n"
            f"📍 Joylashuv: {loc}\n"
            f"❤️ Likelar: {user['likes'] or 0}"
        )
    else:
        return (
            f"👤 Ism: {hidden}\n"
            f"👤 Username: {hidden}\n"
            f"❤️ Jins: {hidden}\n"
            f"🎂 Yosh: {hidden}\n"
            f"📍 Joylashuv: {hidden}\n"
            f"❤️ Likelar: {user['likes'] or 0}\n\n"
            f"💎 VIP olish uchun: /vip"
        )

# ==================== HANDLERS ====================

def cmd_start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    db_user = get_user(uid)
    if db_user:
        update.message.reply_text(
            "👋 Xush kelibsiz!\n\nQuyidagi tugmalardan birini tanlang:",
            reply_markup=main_keyboard()
        )
        return

    context.user_data.clear()
    context.user_data["state"] = STATE_REG_PHOTO
    update.message.reply_text(
        "👋 Xush kelibsiz! Botdan foydalanish uchun anketa to'ldiring.\n\n"
        "📸 Birinchi bo'lib rasmingizni yuboring:"
    )

def cmd_vip(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if not get_user(uid):
        update.message.reply_text("Avval ro'yxatdan o'ting: /start")
        return
    _show_vip_menu(update.message, uid)

def _show_vip_menu(message, uid):
    status = vip_label(uid)
    text = (
        f"👑 VIP STATUS BO'LIMI\n\n"
        f"💎 Holat: {status}\n\n"
        f"VIP bo'lsangiz:\n"
        f"✅ Jins bo'yicha qidiruv\n"
        f"✅ Ism va Username ko'rish\n"
        f"✅ Yosh va viloyat ko'rish\n\n"
        f"💎 Tarif narxlari:\n"
        f"1 kun   — 6,000 so'm\n"
        f"3 kun   — 9,000 so'm\n"
        f"1 hafta — 13,000 so'm\n"
        f"2 hafta — 18,000 so'm\n"
        f"1 oy    — 27,000 so'm\n"
        f"3 oy    — 60,000 so'm\n"
        f"1 yil   — 65,000 so'm\n\n"
        f"👇 Muddatni tanlang:"
    )
    message.reply_text(text, reply_markup=vip_period_kb())

def cmd_admin(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        update.message.reply_text("❌ Ruxsat yo'q!")
        return
    total, vip_count, pays = get_stats()
    update.message.reply_text(
        f"🔧 ADMIN PANELI\n\n"
        f"👥 Foydalanuvchilar: {total}\n"
        f"💎 VIP foydalanuvchilar: {vip_count}\n"
        f"💰 Tasdiqlangan to'lovlar: {pays}"
    )

def handle_message(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    text = update.message.text or ""

    # Ro'yxatdan o'tish - rasm kutish holati
    if state == STATE_REG_PHOTO:
        update.message.reply_text("❌ Iltimos, rasm (foto) yuboring!")
        return

    # Ro'yxatdan o'tish - ism holati
    if state == STATE_REG_NAME:
        full_name = text.strip()
        if len(full_name) < 2:
            update.message.reply_text("❌ Ismingizni to'g'ri kiriting (kamida 2 harf):")
            return
        context.user_data["reg_name"] = full_name
        context.user_data["state"] = STATE_REG_GENDER
        update.message.reply_text(
            f"✅ Ism: {full_name}\n\nJinsingizni tanlang:",
            reply_markup=gender_kb()
        )
        return

    # Xabar yuborish holati
    if context.user_data.get(STATE_MSG_TARGET):
        target_id = context.user_data.pop(STATE_MSG_TARGET)
        try:
            context.bot.send_message(
                chat_id=target_id,
                text=f"✉️ Sizga anonim xabar:\n\n{text}"
            )
            update.message.reply_text("✅ Xabar yuborildi!")
        except Exception:
            update.message.reply_text("❌ Xabar yuborishda xato.")
        return

    # Tahrirlash holati - matnli maydonlar
    if state == STATE_EDITING:
        edit_field = context.user_data.get("edit_field")
        if edit_field == "name":
            full_name = text.strip()
            if len(full_name) < 2:
                update.message.reply_text("❌ Ismingizni to'g'ri kiriting:")
                return
            update_user(uid, full_name=full_name)
            context.user_data.pop("state", None)
            context.user_data.pop("edit_field", None)
            update.message.reply_text("✅ Ism yangilandi!", reply_markup=main_keyboard())
        return

    # Ro'yxatdan o'tmagan bo'lsa
    db_user = get_user(uid)
    if not db_user:
        cmd_start(update, context)
        return

    # Asosiy menyu
    if text == "🔍 Tanishuv boshlash":
        _do_search(update, context, uid, gender=None)
    elif text == "👦 O'g'il bola izlash 👑":
        if not is_vip(uid):
            update.message.reply_text(
                "⚠️ Bu funksiya faqat VIP a'zolar uchun!\n\n"
                "VIP olish uchun: /vip yoki '💎 VIP olish' tugmasini bosing."
            )
        else:
            _do_search(update, context, uid, gender="ogil")
    elif text == "👸 Qiz bola izlash 👑":
        if not is_vip(uid):
            update.message.reply_text(
                "⚠️ Bu funksiya faqat VIP a'zolar uchun!\n\n"
                "VIP olish uchun: /vip yoki '💎 VIP olish' tugmasini bosing."
            )
        else:
            _do_search(update, context, uid, gender="qiz")
    elif text == "Profil 👤":
        _show_profile(update, context, uid)
    elif text == "Baholarim ⭐":
        user = get_user(uid)
        update.message.reply_text(
            f"⭐ Baholaringiz:\n\n"
            f"📊 O'rtacha: {user['rating']:.1f}/5\n"
            f"🗳 Ovozlar: {user['rating_count']}\n"
            f"❤️ Likelar: {user['likes'] or 0}"
        )
    elif text == "💎 VIP olish":
        _show_vip_menu(update.message, uid)
    else:
        update.message.reply_text("Tugmalardan birini tanlang 👇", reply_markup=main_keyboard())

def handle_photo(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    tg_user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    state = context.user_data.get("state")

    # Ro'yxatdan o'tish - rasm bosqichi
    if state == STATE_REG_PHOTO:
        context.user_data["reg_photo"] = photo_id
        context.user_data["state"] = STATE_REG_NAME
        update.message.reply_text(
            "✅ Rasm qabul qilindi!\n\n"
            "📝 Endi ismingizni yozing:"
        )
        return

    # Tahrirlash - rasm yangilash
    if state == STATE_EDITING and context.user_data.get("edit_field") == "photo":
        update_user(uid, photo_id=photo_id)
        context.user_data.pop("state", None)
        context.user_data.pop("edit_field", None)
        update.message.reply_text("✅ Rasm yangilandi!", reply_markup=main_keyboard())
        return

    # Ro'yxatdan o'tmagan bo'lib rasm yuborsa
    if not get_user(uid) and state != STATE_REG_NAME:
        context.user_data["reg_photo"] = photo_id
        context.user_data["state"] = STATE_REG_NAME
        update.message.reply_text(
            "✅ Rasm qabul qilindi!\n\n"
            "📝 Endi ismingizni yozing:"
        )

def _do_search(update, context, uid, gender=None):
    viewer_vip = is_vip(uid)
    found = get_random_user(uid, gender=gender)
    if not found:
        update.message.reply_text("😔 Hozircha mos foydalanuvchi topilmadi.")
        return
    caption = format_stranger(found, viewer_vip)
    kb = search_kb(found["user_id"])
    if found.get("photo_id"):
        update.message.reply_photo(photo=found["photo_id"], caption=caption, reply_markup=kb)
    else:
        update.message.reply_text(caption, reply_markup=kb)

def _show_profile(update, context, uid):
    user = get_user(uid)
    if not user:
        update.message.reply_text("❌ Profil topilmadi.")
        return
    text = format_my_profile(user)
    if user.get("photo_id"):
        update.message.reply_photo(photo=user["photo_id"], caption=text, reply_markup=profile_kb())
    else:
        update.message.reply_text(text, reply_markup=profile_kb())

def _finish_reg(query, context, tg_user):
    data = context.user_data
    save_user({
        "user_id": tg_user.id,
        "username": tg_user.username,
        "full_name": data.get("reg_name"),
        "photo_id": data.get("reg_photo"),
        "gender": data.get("reg_gender"),
        "viloyat": data.get("reg_viloyat"),
        "tuman": data.get("reg_tuman", ""),
        "age": data.get("reg_age"),
    })
    context.user_data.clear()
    try:
        query.edit_message_text("🎉 Ro'yxatdan o'tish yakunlandi!")
    except Exception:
        pass
    query.message.reply_text(
        "✅ Tabriklaymiz! Anketa to'ldirildi.\n\nAsosiy menyu 👇",
        reply_markup=main_keyboard()
    )

def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    tg_user = query.from_user
    state = context.user_data.get("state")

    # ── Ro'yxatdan o'tish: Jins ──
    if data.startswith("gender_") and state == STATE_REG_GENDER:
        gender = data.replace("gender_", "")
        context.user_data["reg_gender"] = gender
        context.user_data["state"] = STATE_REG_AGE
        try:
            query.edit_message_text(
                f"Jins: {gender_text(gender)} ✅\n\nYoshingizni tanlang:",
                reply_markup=age_kb()
            )
        except Exception:
            query.message.reply_text("Yoshingizni tanlang:", reply_markup=age_kb())
        return

    # ── Ro'yxatdan o'tish: Yosh ──
    if data.startswith("age_") and state == STATE_REG_AGE:
        age = int(data.replace("age_", ""))
        context.user_data["reg_age"] = age
        context.user_data["state"] = STATE_REG_VILOYAT
        try:
            query.edit_message_text(
                f"Yosh: {age} ✅\n\nViloyatingizni tanlang:",
                reply_markup=viloyat_kb()
            )
        except Exception:
            query.message.reply_text("Viloyatingizni tanlang:", reply_markup=viloyat_kb())
        return

    # ── Ro'yxatdan o'tish: Viloyat ──
    if data.startswith("vil_") and state == STATE_REG_VILOYAT:
        viloyat = data.replace("vil_", "")
        context.user_data["reg_viloyat"] = viloyat
        if viloyat == "Surxondaryo":
            context.user_data["state"] = STATE_REG_TUMAN
            try:
                query.edit_message_text(
                    f"Viloyat: {viloyat} ✅\n\nTumaningizni tanlang:",
                    reply_markup=tuman_kb()
                )
            except Exception:
                query.message.reply_text("Tumaningizni tanlang:", reply_markup=tuman_kb())
        else:
            _finish_reg(query, context, tg_user)
        return

    # ── Ro'yxatdan o'tish: Tuman ──
    if data.startswith("tum_") and state == STATE_REG_TUMAN:
        tuman = data.replace("tum_", "")
        context.user_data["reg_tuman"] = tuman
        _finish_reg(query, context, tg_user)
        return

    # ── Tahrirlash: Jins ──
    if data.startswith("gender_") and state == STATE_EDITING:
        gender = data.replace("gender_", "")
        update_user(uid, gender=gender)
        context.user_data.pop("state", None)
        context.user_data.pop("edit_field", None)
        try:
            query.edit_message_text(f"✅ Jins yangilandi: {gender_text(gender)}")
        except Exception:
            query.message.reply_text(f"✅ Jins yangilandi: {gender_text(gender)}")
        return

    # ── Tahrirlash: Yosh ──
    if data.startswith("age_") and state == STATE_EDITING:
        age = int(data.replace("age_", ""))
        update_user(uid, age=age)
        context.user_data.pop("state", None)
        context.user_data.pop("edit_field", None)
        try:
            query.edit_message_text(f"✅ Yosh yangilandi: {age}")
        except Exception:
            query.message.reply_text(f"✅ Yosh yangilandi: {age}")
        return

    # ── Tahrirlash: Viloyat ──
    if data.startswith("vil_") and state == STATE_EDITING:
        viloyat = data.replace("vil_", "")
        update_user(uid, viloyat=viloyat)
        if viloyat == "Surxondaryo":
            context.user_data["edit_field"] = "tuman"
            try:
                query.edit_message_text("Tumaningizni tanlang:", reply_markup=tuman_kb())
            except Exception:
                query.message.reply_text("Tumaningizni tanlang:", reply_markup=tuman_kb())
        else:
            context.user_data.pop("state", None)
            context.user_data.pop("edit_field", None)
            try:
                query.edit_message_text(f"✅ Viloyat yangilandi: {viloyat}")
            except Exception:
                query.message.reply_text(f"✅ Viloyat yangilandi: {viloyat}")
        return

    # ── Tahrirlash: Tuman ──
    if data.startswith("tum_") and state == STATE_EDITING:
        tuman = data.replace("tum_", "")
        update_user(uid, tuman=tuman)
        context.user_data.pop("state", None)
        context.user_data.pop("edit_field", None)
        try:
            query.edit_message_text(f"✅ Tuman yangilandi: {tuman}")
        except Exception:
            query.message.reply_text(f"✅ Tuman yangilandi: {tuman}")
        return

    # ── VIP davr tanlash ──
    if data.startswith("vip_"):
        period = data.replace("vip_", "")
        if period not in VIP_PRICES:
            return
        amount = VIP_PRICES[period]
        days = VIP_DAYS[period]
        label = VIP_LABELS[period]

        payment_id = save_payment(uid, amount, period, days)

        text = (
            f"💳 TO'LOV MA'LUMOTLARI\n\n"
            f"💰 Summa: {amount:,} so'm\n"
            f"📅 Muddat: {label}\n\n"
            f"⚠️ Aynan shu summani yuboring!\n\n"
            f"💳 Karta raqami:\n"
            f"<code>{CARD_NUMBER}</code>\n"
            f"👤 Karta egasi: {CARD_OWNER}\n\n"
            f"To'lovdan so'ng '✅ To'lov qildim' tugmasini bosing."
        )
        try:
            query.edit_message_text(
                text,
                reply_markup=confirm_payment_kb(uid, payment_id),
                parse_mode="HTML"
            )
        except Exception:
            query.message.reply_text(
                text,
                reply_markup=confirm_payment_kb(uid, payment_id),
                parse_mode="HTML"
            )
        return

    if data == "cancel_vip":
        try:
            query.edit_message_text("❌ Bekor qilindi.")
        except Exception:
            pass
        return

    # ── Foydalanuvchi "To'lov qildim" bosganda ──
    if data.startswith("paid_"):
        # Format: paid_{user_id}_{payment_id}
        parts = data[len("paid_"):].split("_")
        if len(parts) < 2:
            return
        try:
            target_uid = int(parts[0])
            payment_id = int(parts[1])
        except ValueError:
            return

        payment = get_payment_by_id(payment_id)
        if not payment or payment["status"] != "pending":
            query.answer("❌ To'lov topilmadi yoki allaqachon tasdiqlangan!", show_alert=True)
            return

        user = get_user(target_uid)
        if not user:
            query.answer("❌ Foydalanuvchi topilmadi!", show_alert=True)
            return

        period = payment["period"]
        label = VIP_LABELS.get(period, period)
        amount = payment["amount"]

        nomalum = "Noma'lum"
        user_name_display = user['full_name'] or nomalum
        user_username_display = user['username'] or nomalum
        group_msg = (
            f"💳 YANGI VIP TO'LOV SO'ROVI!\n\n"
            f"👤 Ism: {user_name_display}\n"
            f"🆔 ID: <code>{target_uid}</code>\n"
            f"👤 Username: @{user_username_display}\n"
            f"❤️ Jins: {gender_text(user['gender'])}\n"
            f"🎂 Yosh: {user['age']}\n"
            f"📍 Viloyat: {user['viloyat']}\n"
            f"💰 Summa: {amount:,} so'm\n"
            f"📅 Muddat: {label}\n"
            f"⏰ Vaqt: {now_str()}\n\n"
            f"⬇️ VIP berish yoki rad etish uchun tugmani bosing:"
        )

        try:
            context.bot.send_message(
                chat_id=GROUP_ID,
                text=group_msg,
                reply_markup=admin_confirm_kb(payment_id, target_uid),
                parse_mode="HTML"
            )
            try:
                query.edit_message_text(
                    f"✅ So'rovingiz yuborildi!\n\n"
                    f"⏳ Admin tasdiqlashini kuting...\n"
                    f"📅 Muddat: {label}\n\n"
                    f"Tasdiqlanganidan so'ng VIP avtomatik faollashadi."
                )
            except Exception:
                query.message.reply_text(
                    f"✅ So'rovingiz yuborildi!\n\n"
                    f"⏳ Admin tasdiqlashini kuting...\n"
                    f"📅 Muddat: {label}"
                )
        except Exception as e:
            logger.error(f"Guruhga xabar yuborish xatosi: {e}")
            try:
                query.edit_message_text(
                    "❌ Xatolik yuz berdi. Keyinroq qaytadan urinib ko'ring."
                )
            except Exception:
                pass
        return

    if data == "cancel_pay":
        conn = sqlite3.connect("yangitanishbot.db")
        c = conn.cursor()
        c.execute(
            "UPDATE payments SET status='cancelled' WHERE user_id=? AND status='pending'",
            (uid,)
        )
        conn.commit()
        conn.close()
        try:
            query.edit_message_text("❌ To'lov bekor qilindi.")
        except Exception:
            pass
        return

    # ── Admin: VIP tasdiqlash ──
    # callback_data format: confirmvip_{payment_id}_{user_id}
    if data.startswith("confirmvip_"):
        caller_id = query.from_user.id
        chat_id = update.effective_chat.id

        # Admin yoki guruh egasimi tekshirish
        is_admin_flag = caller_id in ADMIN_IDS
        if not is_admin_flag:
            try:
                member = context.bot.get_chat_member(chat_id, caller_id)
                is_admin_flag = member.status in ("administrator", "creator")
            except Exception:
                pass

        if not is_admin_flag:
            query.answer(
                "❌ Faqat admin yoki guruh egasi tasdiqlashi mumkin!",
                show_alert=True
            )
            return

        parts = data[len("confirmvip_"):].split("_")
        if len(parts) < 2:
            return
        try:
            payment_id = int(parts[0])
            target_uid = int(parts[1])
        except ValueError:
            return

        payment = get_payment_by_id(payment_id)
        if not payment or payment["status"] != "pending":
            query.answer(
                "❌ Bu to'lov allaqachon tasdiqlangan yoki topilmadi!",
                show_alert=True
            )
            try:
                query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        days = payment["days"]
        period = payment["period"]
        label = VIP_LABELS.get(period, period)

        # VIP faollashtirish
        activate_vip(target_uid, days, caller_id, payment_id)

        # Foydalanuvchiga xabar
        try:
            context.bot.send_message(
                chat_id=target_uid,
                text=(
                    f"🎉 TABRIKLAYMIZ!\n\n"
                    f"✅ VIP statusingiz tasdiqlandi!\n"
                    f"📅 Muddat: {label}\n"
                    f"👑 Endi barcha VIP imkoniyatlar ochiq!\n\n"
                    f"• Jins bo'yicha qidiruv\n"
                    f"• Ism va username ko'rish\n"
                    f"• Yosh va viloyat ko'rish"
                ),
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.error(f"Foydalanuvchiga xabar yuborish xatosi: {e}")

        # Guruhda natija
        try:
            query.edit_message_text(
                f"✅ VIP TASDIQLANDI!\n\n"
                f"👤 Foydalanuvchi ID: {target_uid}\n"
                f"📅 Muddat: {label}\n"
                f"👑 Tasdiqladi: {query.from_user.first_name}\n"
                f"⏰ Vaqt: {now_str()}"
            )
        except Exception:
            pass
        query.answer("✅ VIP muvaffaqiyatli tasdiqlandi!", show_alert=True)
        return

    # ── Admin: VIP rad etish ──
    # callback_data format: rejectvip_{payment_id}_{user_id}
    if data.startswith("rejectvip_"):
        caller_id = query.from_user.id
        chat_id = update.effective_chat.id

        is_admin_flag = caller_id in ADMIN_IDS
        if not is_admin_flag:
            try:
                member = context.bot.get_chat_member(chat_id, caller_id)
                is_admin_flag = member.status in ("administrator", "creator")
            except Exception:
                pass

        if not is_admin_flag:
            query.answer(
                "❌ Faqat admin rad etishi mumkin!",
                show_alert=True
            )
            return

        parts = data[len("rejectvip_"):].split("_")
        if len(parts) < 2:
            return
        try:
            payment_id = int(parts[0])
            target_uid = int(parts[1])
        except ValueError:
            return

        payment = get_payment_by_id(payment_id)
        if not payment:
            query.answer("❌ To'lov topilmadi!", show_alert=True)
            return

        if payment["status"] != "pending":
            query.answer("❌ Bu to'lov allaqachon ko'rib chiqilgan!", show_alert=True)
            try:
                query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        # To'lovni rad etish
        conn = sqlite3.connect("yangitanishbot.db")
        c = conn.cursor()
        c.execute(
            "UPDATE payments SET status='rejected', confirmed_at=?, confirmed_by=? WHERE id=?",
            (now_str(), caller_id, payment_id)
        )
        conn.commit()
        conn.close()

        # Foydalanuvchiga xabar
        try:
            context.bot.send_message(
                chat_id=target_uid,
                text=(
                    "❌ Sizning VIP to'lov so'rovingiz rad etildi.\n\n"
                    "Iltimos, to'g'ri miqdorni yuborib, qaytadan urinib ko'ring.\n"
                    "Savollar bo'lsa admin bilan bog'laning."
                )
            )
        except Exception:
            pass

        try:
            query.edit_message_text(
                f"❌ VIP RAD ETILDI!\n\n"
                f"🆔 Payment ID: {payment_id}\n"
                f"👤 Foydalanuvchi: {target_uid}\n"
                f"👤 Rad etdi: {query.from_user.first_name}\n"
                f"⏰ Vaqt: {now_str()}"
            )
        except Exception:
            pass
        query.answer("❌ To'lov rad etildi!", show_alert=True)
        return

    # ── Qidiruv: Like ──
    if data.startswith("like_"):
        try:
            target = int(data.replace("like_", ""))
        except ValueError:
            return
        u = get_user(target)
        if u:
            update_user(target, likes=(u["likes"] or 0) + 1)
        query.answer("❤️ Like qo'shildi!", show_alert=True)
        try:
            query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # ── Qidiruv: O'tkazish ──
    if data.startswith("skip_"):
        try:
            query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        query.message.reply_text("⏭ O'tkazib yuborildi.", reply_markup=main_keyboard())
        return

    # ── Qidiruv: Shikoyat ──
    if data.startswith("rep_"):
        query.answer("⚠️ Shikoyat yuborildi! Ko'rib chiqamiz.", show_alert=True)
        return

    # ── Qidiruv: Xabar yuborish ──
    if data.startswith("msg_"):
        try:
            target = int(data.replace("msg_", ""))
        except ValueError:
            return
        context.user_data[STATE_MSG_TARGET] = target
        query.message.reply_text("✉️ Xabaringizni yozing (anonim yuboriladi):")
        return

    # ── Profil tahrirlash menyusi ──
    if data == "edit_menu":
        try:
            query.edit_message_reply_markup(reply_markup=edit_kb())
        except Exception:
            query.message.reply_text("Tahrirlash:", reply_markup=edit_kb())
        return

    if data == "ed_photo":
        context.user_data["state"] = STATE_EDITING
        context.user_data["edit_field"] = "photo"
        query.message.reply_text("📷 Yangi rasmingizni yuboring:")
        return

    if data == "ed_gender":
        context.user_data["state"] = STATE_EDITING
        context.user_data["edit_field"] = "gender"
        try:
            query.edit_message_text("Yangi jinsingizni tanlang:", reply_markup=gender_kb())
        except Exception:
            query.message.reply_text("Yangi jinsingizni tanlang:", reply_markup=gender_kb())
        return

    if data == "ed_age":
        context.user_data["state"] = STATE_EDITING
        context.user_data["edit_field"] = "age"
        try:
            query.edit_message_text("Yangi yoshingizni tanlang:", reply_markup=age_kb())
        except Exception:
            query.message.reply_text("Yangi yoshingizni tanlang:", reply_markup=age_kb())
        return

    if data == "ed_viloyat":
        context.user_data["state"] = STATE_EDITING
        context.user_data["edit_field"] = "viloyat"
        try:
            query.edit_message_text("Yangi viloyatingizni tanlang:", reply_markup=viloyat_kb())
        except Exception:
            query.message.reply_text("Yangi viloyatingizni tanlang:", reply_markup=viloyat_kb())
        return

    if data == "ed_back":
        try:
            query.edit_message_reply_markup(reply_markup=profile_kb())
        except Exception:
            pass
        return

# ==================== VIP EXPIRY JOB ====================

def check_vip_expiry(context: CallbackContext):
    """Har 30 daqiqada ishga tushadi. Muddati tugagan VIPlarni o'chiradi."""
    now = datetime.now()
    conn = sqlite3.connect("yangitanishbot.db")
    c = conn.cursor()
    c.execute(
        """SELECT user_id, vip_until FROM users
           WHERE vip_until IS NOT NULL AND vip_until != ''
           AND vip_until <= ?""",
        (now.strftime("%Y-%m-%d %H:%M:%S"),)
    )
    expired = c.fetchall()
    for user_id, vip_until in expired:
        c.execute("UPDATE users SET vip_until = NULL WHERE user_id = ?", (user_id,))
        logger.info(f"VIP tugadi: user_id={user_id}")
        try:
            context.bot.send_message(
                chat_id=user_id,
                text=(
                    "⏰ VIP MUDDATINGIZ TUGADI!\n\n"
                    "❌ VIP statusingiz o'chirildi.\n\n"
                    "💎 Davom ettirish uchun yangi VIP oling:\n"
                    "/vip yoki '💎 VIP olish' tugmasini bosing."
                ),
                reply_markup=main_keyboard()
            )
        except Exception as e:
            logger.warning(f"VIP expiry xabari yuborilmadi user_id={user_id}: {e}")
    if expired:
        conn.commit()
        logger.info(f"VIP expiry: {len(expired)} ta VIP o'chirildi")
    conn.close()


# ==================== ERROR HANDLER ====================

def error_handler(update, context: CallbackContext):
    logger.error(f"Xato: {context.error}", exc_info=context.error)
    try:
        if update and update.effective_message:
            update.effective_message.reply_text(
                "⚠️ Texnik xato yuz berdi. Iltimos, qaytadan urinib ko'ring."
            )
    except Exception:
        pass


# ==================== MAIN ====================

def main():
    print("🤖 Yangitanishbot ishga tushmoqda...")
    print(f"📊 Guruh ID: {GROUP_ID}")

    init_db()

    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    jq = updater.job_queue

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("vip", cmd_vip))
    dp.add_handler(CommandHandler("admin", cmd_admin))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Xato handleri - barcha xatolarni ushlaydi
    dp.add_error_handler(error_handler)

    # VIP muddati tekshiruvi: har 30 daqiqada, botdan 60 soniya keyin boshlaydi
    jq.run_repeating(check_vip_expiry, interval=1800, first=60)

    print("✅ Bot muvaffaqiyatli ishga tushdi!")
    print("🔄 Ishlayapti... (To'xtatish: Ctrl+C)")

    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
