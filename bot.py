import os
import pytesseract

if os.name == "nt":  # Windows
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:  # Linux (Heroku)
    pytesseract.pytesseract.tesseract_cmd = "/app/.apt/usr/bin/tesseract"

# تعيين TESSDATA_PREFIX للمجلد الذي يحتوي على ملفات التدريب
os.environ["TESSDATA_PREFIX"] = "/app/.apt/usr/share/tesseract-ocr/5/tessdata/"

import re
import time
import json
import threading
import tempfile
import random
import telebot   # تأكد من تثبيت مكتبة pyTelegramBotAPI
from telebot import types
from gtts import gTTS
from PIL import Image

# للمعالجة المسبقة بالـ OpenCV
import cv2
import numpy as np

from google_trans_new import google_translator
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# -------------------------------------------------------------------------------------
#                           مكتبة Google GenAI
# -------------------------------------------------------------------------------------
from google import genai
from google.genai import types as genaitypes

# -------------------------------------------------------------------------------------
#                               إعدادات عامة
# -------------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "6669452404:AAHlWVC275ljXZaU03Yi7td9fBwruEm_PF8"  # <-- توكن البوت
BOT_ID = 6669452404

# مُعرّف القروب الذي سيستقبل إشعارات الانضمام والرسائل:
FORWARD_PRIVATE_TO_GROUP = "@iougtiugfkjlk"

# إذا لديك آيدي إدمن محدد أو أكثر (اختياري):
ADMIN_CHAT_ID = 5545208360
ADMIN_IDS = [5545208360]
ADMIN_USERNAMES = ["muneeralhu"]  # يمكنك تعديلها

# مفاتيح Google GenAI
GOOGLE_API_KEY = "AIzaSyDEFWvLbaMG7qv0hZePO4uEaA0SS_MymY"  # من مشروع جديد
GEMINI_MODEL_NAME = "gemini-2.0-flash"

GEMINI_API_KEYS = [
    "AIzaSyDEFWvLbaMG7qv0hZePO4uEaA0SS_MymY",  # المفتاح الأساسي (تأكد من صلاحياته)
    "AIzaSyCrJuUAJGnX8T_g-sEbNnq6z77_BgaYhgw",
    "AIzaSyB8nyQ0rpP952l0pEZooA4Wxm3mp266Lbs",
    "AIzaSyBtcYOmfIy3xwLIlaDA_kiez7xlOJXCE-M",
    "AIzaSyAWVtsXKuyHmUTrVAVUxOexxd_U-htisuo"
]

# ملفات JSON
SUBSCRIBERS_FILE = "subscribers.json"
BANNED_USERS_FILE = "banned_users.json"
FORCED_CHANNELS_FILE = "forced_channels.json"
STATS_FILE = "stats.json"
PAID_USERS_FILE = "paid_users.json"   # ملف المشتركين المدفوعين

# البوت
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
bot.remove_webhook()

translator = google_translator()

# -------------------------------------------------------------------------------------
#   تحميل / حفظ بيانات JSON
# -------------------------------------------------------------------------------------
def load_json_file(path, default_val):
    if not os.path.exists(path):
        return default_val
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default_val

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

subscribers = set(load_json_file(SUBSCRIBERS_FILE, []))
banned_users = set(load_json_file(BANNED_USERS_FILE, []))
forced_channels = set(load_json_file(FORCED_CHANNELS_FILE, []))
stats = load_json_file(STATS_FILE, {"total_words_used": 0})
paid_users = set(load_json_file(PAID_USERS_FILE, []))  # تحميل المشتركين المدفوعين

def save_subscribers(s):
    save_json_file(SUBSCRIBERS_FILE, list(s))

def save_banned_users(s):
    save_json_file(BANNED_USERS_FILE, list(s))

def save_forced_channels(ch):
    save_json_file(FORCED_CHANNELS_FILE, list(ch))

def save_stats(s):
    save_json_file(STATS_FILE, s)

def save_paid_users(s):
    save_json_file(PAID_USERS_FILE, list(s))

total_words_used = stats.get("total_words_used", 0)
print(f"Loaded {len(subscribers)} subscribers.")
print(f"Banned users: {len(banned_users)}")
print(f"Forced channels: {forced_channels}")
print(f"Total words used: {total_words_used}")
print(f"Paid users: {len(paid_users)}")

# -------------------------------------------------------------------------------------
#   إنشاء عميل Google GenAI
# -------------------------------------------------------------------------------------
client = genai.Client(api_key=GOOGLE_API_KEY)

def genai_generate_content(prompt):
    """
    تحاول إرسال الطلب لكل مفتاح API إلى أن ينجح أحدها.
    """
    for key in GEMINI_API_KEYS:
        try:
            client_temp = genai.Client(api_key=key)
            resp = client_temp.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=genaitypes.GenerateContentConfig(
                    temperature=0.0,
                    top_p=1.0
                )
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            print(f"Error with key {key}: {e}")
            continue
    return "لم يتم توليد رد."

# -------------------------------------------------------------------------------------
#   دوال الحظر
# -------------------------------------------------------------------------------------
def is_banned(user_id):
    return user_id in banned_users

def ban_user(user_id):
    banned_users.add(user_id)
    save_banned_users(banned_users)

# -------------------------------------------------------------------------------------
#   دوال التحقق من الاشتراك في القنوات
# -------------------------------------------------------------------------------------
def channels_not_subscribed(user_id):
    not_subscribed = []
    for ch in forced_channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                not_subscribed.append(ch)
        except:
            # في حال وجود خطأ أو عدم القدرة على التحقق، نعتبر المستخدم غير مشترك
            not_subscribed.append(ch)
    return not_subscribed

def is_subscribed_to_forced_channels(user_id):
    if not forced_channels:
        return True
    not_subbed = channels_not_subscribed(user_id)
    return (len(not_subbed) == 0)

# -------------------------------------------------------------------------------------
#   رسالة الاشتراك الإجباري مع زر التحقق
# -------------------------------------------------------------------------------------
def send_forced_subscription_message(chat_id):
    msg = "عزيزي المستخدم لا يمكنك استخدام البوت إلا بعد الاشتراك في القنوات التالية:\n\n"
    for fc in forced_channels:
        msg += f"- {fc}\n"
    msg += "\nاضغط على الزر بالأسفل للتحقق من اشتراكك."
    
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("اضغط هنا للتحقق من الاشتراك", callback_data="check_subscription"))
    bot.send_message(chat_id, msg, reply_markup=mk)

# -------------------------------------------------------------------------------------
#   زر "اضغط هنا للتحقق من الاشتراك"
# -------------------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data == "check_subscription")
def cb_check_subscription(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    not_subbed = channels_not_subscribed(user_id)
    if not not_subbed:
        # المستخدم مشترك في كل القنوات
        bot.answer_callback_query(call.id, "تم التحقق! شكرًا لانضمامك.", show_alert=True)
        bot.send_message(chat_id, "تهانينا! يمكنك الآن استخدام البوت.\n\nأرسل /start مجددًا للمتابعة.")
    else:
        msg = "عزيزي المستخدم، أنت لم تشترك بعد في القنوات التالية:\n\n"
        for ch in not_subbed:
            msg += f"- {ch}\n"
        msg += "\nيرجى الاشتراك فيها ثم اضغط على الزر مرة أخرى."
        bot.answer_callback_query(call.id, "لم تكتمل عملية الاشتراك!", show_alert=True)
        bot.send_message(chat_id, msg)

# -------------------------------------------------------------------------------------
#   إشعار القروب بأي انضمام جديد
# -------------------------------------------------------------------------------------
def notify_group_new_subscriber(user):
    if not FORWARD_PRIVATE_TO_GROUP:
        return
    full_name = user.first_name or ""
    if user.last_name:
        full_name += f" {user.last_name}"
    mention = f"@{user.username}" if user.username else "—"
    text = (
        "📩 <b>مشترك جديد في البوت</b>\n"
        f"👤 <b>الاسم:</b> {full_name.strip()} <code>{user.id}</code>\n"
        f"💬 <b>المعرف:</b> {mention}"
    )
    bot.send_message(FORWARD_PRIVATE_TO_GROUP, text, parse_mode="HTML")

# -------------------------------------------------------------------------------------
#   دالة لتحديد اللغة السائدة
# -------------------------------------------------------------------------------------
def detect_dominant_language(text: str) -> str:
    en_count = len(re.findall(r'[A-Za-z]', text))
    ar_count = len(re.findall(r'[\u0600-\u06FF]', text))
    if en_count == 0 and ar_count == 0:
        return "en"
    if en_count > 2 and ar_count <= 2:
        return "en"
    if ar_count > 2 and en_count <= 2:
        return "ar"
    if en_count >= ar_count:
        return "en"
    else:
        return "ar"

# -------------------------------------------------------------------------------------
#   دوال الترجمة / التعريب في استدعاء واحد
# -------------------------------------------------------------------------------------
def genai_en2ar(text):
    """ ترجمة كاملة من الإنجليزية إلى العربية """
    if not text.strip():
        return ""
    prompt = (
        "ترجم النص التالي من الإنجليزية إلى العربية بدقة، "
        "بدون أي شرح أو نص إضافي، واستخدم الحروف العربية فقط:\n\n"
        f"{text}\n\n"
        "الترجمة العربية:"
    )
    return genai_generate_content(prompt)

def genai_ar2en(text):
    """ ترجمة كاملة من العربية إلى الإنجليزية """
    if not text.strip():
        return ""
    prompt = (
        "ترجم النص التالي من العربية إلى الإنجليزية بدقة، "
        "بدون أي شرح أو نص إضافي، واستخدم الحروف الإنجليزية فقط:\n\n"
        f"{text}\n\n"
        "English translation:"
    )
    return genai_generate_content(prompt)

def genai_translit(text):
    """
    عربنة (تحويل النص الإنجليزي إلى حروف عربية)
    مع التأكيد على نطق حرف (g) بـ(ق) وليس (ج) أو (غ)
    """
    if not text.strip():
        return ""
    prompt = (
        "قم بتحويل النص الإنجليزي التالي إلى حروف عربية تمثل نطقه بدقة، "
        "بدون أي شرح أو كلام زائد، واستخدم الحروف العربية فقط، "
        "وتنبه دائماً أن حرف (g) يُنطق قافاً وليس جيمًا أو غيناً:\n\n"
        f"{text}\n\n"
        "العربنة:"
    )
    return genai_generate_content(prompt)

# -------------------------------------------------------------------------------------
#   دوال الصوت (TTS)
# -------------------------------------------------------------------------------------
def get_english_voice(text):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        fn = tmp.name
    tts = gTTS(text=text, lang='en')
    tts.save(fn)
    return fn

def get_arabic_voice(text):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        fn = tmp.name
    tts = gTTS(text=text, lang='ar')
    tts.save(fn)
    return fn

# -------------------------------------------------------------------------------------
#   إحصائية عدد الكلمات
# -------------------------------------------------------------------------------------
def update_total_words_used(count):
    global total_words_used
    total_words_used += count
    stats["total_words_used"] = total_words_used
    save_stats(stats)

# -------------------------------------------------------------------------------------
#   استخراج النص من الصور (OCR)
# -------------------------------------------------------------------------------------
def ocr_extract_text(file_id):
    try:
        file_info = bot.get_file(file_id)
        dld = bot.download_file(file_info.file_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(dld)
            local_pth = tmp.name
        
        try:
            image = cv2.imread(local_pth)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_img = Image.fromarray(thresh)
            txt = pytesseract.image_to_string(processed_img, lang="eng+ara").strip()
        except Exception as e:
            txt = f"⚠️ فشل استخراج النص: {str(e)}"
        
        os.remove(local_pth)
        return txt
    except Exception as e:
        return f"❌ خطأ أثناء معالجة الصورة: {str(e)}"

# -------------------------------------------------------------------------------------
#   لوحة تحكم الإدمن
# -------------------------------------------------------------------------------------
admin_broadcast_mode = False
admin_add_channel_members = False
admin_adding_forced_channel = False
admin_ban_mode = False
admin_unban_user_mode = False
admin_ban_by_id_mode = False
admin_add_paid_user_mode = False
admin_remove_paid_user_mode = False

channel_new_members = set()
channel_forward_count = 0
MAX_CHANNEL_FORWARDS = 15

def is_admin(user):
    if user.id in ADMIN_IDS:
        return True
    if user.username and user.username.lower() in [u.lower() for u in ADMIN_USERNAMES]:
        return True
    return False

@bot.message_handler(commands=['admin'])
def cmd_admin_panel(message):
    user = message.from_user
    if not is_admin(user):
        return bot.reply_to(message, "ليس لديك صلاحية الوصول.")

    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("عدد المشتركين", callback_data="subscriber_count"),
           types.InlineKeyboardButton("الكلمات المستخدمة", callback_data="words_used_count"))
    mk.add(types.InlineKeyboardButton("بث رسالة", callback_data="broadcast"))
    mk.add(types.InlineKeyboardButton("إضافة من القناة", callback_data="add_from_channel"))
    mk.add(types.InlineKeyboardButton("إضافة قناة إجباري", callback_data="add_forced_channel"),
           types.InlineKeyboardButton("حذف قناة إجباري", callback_data="remove_forced_channel"))
    mk.add(types.InlineKeyboardButton("استعراض القنوات", callback_data="list_forced_channels"))
    mk.add(types.InlineKeyboardButton("حظر مستخدم", callback_data="ban_user"),
           types.InlineKeyboardButton("إزالة الحظر", callback_data="unban_user"))
    mk.add(types.InlineKeyboardButton("حظر بالايدي", callback_data="ban_user_by_id"))
    mk.add(types.InlineKeyboardButton("إضافة مشترك مدفوع", callback_data="add_paid_user"),
           types.InlineKeyboardButton("حذف مشترك مدفوع", callback_data="remove_paid_user"))

    bot.send_message(message.chat.id, "لوحة الإدارة:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data in [
    "subscriber_count","words_used_count","broadcast",
    "add_from_channel","add_forced_channel","ban_user","unban_user","ban_user_by_id",
    "add_paid_user","remove_forced_channel","list_forced_channels","remove_paid_user"
])
def cb_admin_panel(call):
    global admin_broadcast_mode, admin_add_channel_members
    global admin_adding_forced_channel, admin_ban_mode, admin_unban_user_mode
    global admin_ban_by_id_mode, admin_add_paid_user_mode, admin_remove_paid_user_mode

    chat_id = call.message.chat.id
    user = call.from_user
    if not is_admin(user):
        bot.answer_callback_query(call.id, "لا تملك الصلاحية.", show_alert=True)
        return

    data = call.data
    if data == "subscriber_count":
        bot.send_message(chat_id, f"عدد المشتركين: {len(subscribers)}")
    elif data == "words_used_count":
        bot.send_message(chat_id, f"الكلمات المستخدمة: {stats.get('total_words_used', 0)}")
    elif data == "broadcast":
        admin_broadcast_mode = True
        bot.send_message(chat_id, "أرسل النص ليتم بثه لجميع المشتركين.")
    elif data == "add_from_channel":
        admin_add_channel_members = True
        channel_new_members.clear()
        bot.send_message(chat_id, f"قم بإعادة توجيه {MAX_CHANNEL_FORWARDS} رسالة من القناة لأضيف مرسليها.")
    elif data == "add_forced_channel":
        admin_adding_forced_channel = True
        bot.send_message(chat_id, "أرسل معرف القناة (مثلاً: @MyChannel).")
    elif data == "ban_user":
        admin_ban_mode = True
        bot.send_message(chat_id, "أعد توجيه رسالة من المستخدم المطلوب حظره.")
    elif data == "unban_user":
        admin_unban_user_mode = True
        bot.send_message(chat_id, "أعد توجيه رسالة من المستخدم لإزالة حظره.")
    elif data == "ban_user_by_id":
        admin_ban_by_id_mode = True
        bot.send_message(chat_id, "أرسل الآن رقم الـ ID للمستخدم المطلوب حظره.")
    elif data == "add_paid_user":
        admin_add_paid_user_mode = True
        bot.send_message(chat_id, "أعد توجيه رسالة من المستخدم أو أرسل آيديه. سيتم تحويله لمشترك مدفوع بلا حدود.")
    elif data == "remove_forced_channel":
        if not forced_channels:
            bot.send_message(chat_id, "لا توجد قنوات اشتراك إجباري حالياً.")
        else:
            kb = types.InlineKeyboardMarkup()
            for fc in forced_channels:
                kb.add(types.InlineKeyboardButton(fc, callback_data="rmfc_" + fc))
            bot.send_message(chat_id, "اختر القناة لحذفها:", reply_markup=kb)
    elif data == "list_forced_channels":
        if not forced_channels:
            bot.send_message(chat_id, "لا توجد قنوات اشتراك إجباري حالياً.")
        else:
            msg = "القنوات الإجبارية:\n"
            for fc in forced_channels:
                msg += f"• {fc}\n"
            bot.send_message(chat_id, msg)
    elif data == "remove_paid_user":
        admin_remove_paid_user_mode = True
        bot.send_message(chat_id, "أعد توجيه رسالة من المستخدم أو أرسل آيديه لحذفه من قائمة المدفوعين.")

    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmfc_"))
def cb_remove_forced_channel(call):
    user = call.from_user
    chat_id = call.message.chat.id
    if not is_admin(user):
        bot.answer_callback_query(call.id, "لا تملك الصلاحية.", show_alert=True)
        return

    channel_to_remove = call.data.replace("rmfc_", "")
    if channel_to_remove in forced_channels:
        forced_channels.remove(channel_to_remove)
        save_forced_channels(forced_channels)
        bot.send_message(chat_id, f"تم حذف القناة {channel_to_remove} من الاشتراك الإجباري.")
    else:
        bot.send_message(chat_id, "القناة غير موجودة في القائمة.")
    bot.answer_callback_query(call.id)


def broadcast_in_thread(message_text, admin_id):
    count = 0
    for user_id in subscribers:
        try:
            bot.send_message(user_id, message_text)
            count += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(admin_id, f"تم بث الرسالة إلى {count} مشترك.")

def handle_admin_broadcast(chat_id, text):
    global admin_broadcast_mode
    admin_broadcast_mode = False
    bot.send_message(chat_id, "جاري إرسال الرسالة للجميع...")
    th = threading.Thread(target=broadcast_in_thread, args=(text, chat_id))
    th.start()

# -------------------------------------------------------------------------------------
#   تتبع آخر المستخدمين وعدد رسائلهم المجانية (اختياري)
# -------------------------------------------------------------------------------------
recent_users = {}
free_message_count = {}

def record_recent_user(user_id):
    recent_users[user_id] = time.time()

@bot.message_handler(commands=['recoverrecent'])
def cmd_recover_recent(message):
    user = message.from_user
    if not is_admin(user):
        return bot.reply_to(message, "ليس لديك صلاحية الوصول.")

    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        hours = int(parts[1])
    else:
        hours = 24

    cutoff = time.time() - (hours * 3600)
    new_count = 0
    for uid, tstamp in recent_users.items():
        if tstamp >= cutoff:
            if uid not in subscribers:
                subscribers.add(uid)
                new_count += 1

    if new_count > 0:
        save_subscribers(subscribers)
    bot.send_message(message.chat.id, f"تمت استعادة {new_count} مستخدم في آخر {hours} ساعة.")

# -------------------------------------------------------------------------------------
#   إرسال صورة ترحيبية
# -------------------------------------------------------------------------------------
def show_welcome_image(chat_id):
    try:
        with open("magicbot.jpg", "rb") as photo:
            cap = "مرحبًا بك في بوت الناطق! 💙"
            bot.send_photo(chat_id, photo, caption=cap)
    except Exception as e:
        print(f"Error showing welcome image: {e}")

# -------------------------------------------------------------------------------------
#   ضبط الحد الأقصى لكلمات الرسالة (50 كلمة)
# -------------------------------------------------------------------------------------
DAILY_LIMIT = 999999999  # غير مستخدم عملياً
daily_usage = {}

def reset_daily_usage():
    global daily_usage
    daily_usage = {}
    print("✅ تم إعادة تعيين الاستهلاك اليومي لجميع المستخدمين.")

scheduler = BackgroundScheduler()
scheduler.add_job(reset_daily_usage, 'cron', hour=0, minute=0)
scheduler.start()

def get_user_daily_usage(user_id):
    return daily_usage.get(user_id, 0)

def add_user_daily_usage(user_id, count):
    daily_usage[user_id] = daily_usage.get(user_id, 0) + count

def can_user_process(words_count):
    return (words_count <= 50)

def notify_limit_exceeded(chat_id):
    bot.send_message(
        chat_id,
        "عذراً، لا يسمح بأكثر من 50 كلمة في كل رسالة/صورة."
    )

# -------------------------------------------------------------------------------------
#   استقبال الأوامر الأساسية
# -------------------------------------------------------------------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    user = message.from_user

    if is_banned(user.id):
        return bot.send_message(chat_id, "🚫 أنت محظور من استخدام هذا البوت.")

    # التحقق من الاشتراك في القنوات دائماً
    if not is_subscribed_to_forced_channels(chat_id):
        send_forced_subscription_message(chat_id)
        return

    # إذا كان المستخدم جديداً ولم يكن في قائمة subscribers:
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        notify_group_new_subscriber(user)
        show_welcome_image(chat_id)

    bot.send_message(chat_id,
        "مرحبًا بك في بوت الناطق!\n\n"
        "• يمكنك إرسال أي عدد من الرسائل أو الصور.\n"
        "• الحد الوحيد: ألا تتجاوز الرسالة أو النص المستخرج من الصورة 50 كلمة.\n\n"
        "استمتع باستخدام البوت! للمزيد أو للاشتراك المدفوع، تواصل مع الإدمن."
    )

@bot.message_handler(commands=['help'])
def cmd_help(message):
    chat_id = message.chat.id
    user = message.from_user

    if is_banned(user.id):
        return bot.send_message(chat_id, "🚫 أنت محظور.")

    # في كل مرة نتحقق من الاشتراك في القنوات الإجباري
    if not is_subscribed_to_forced_channels(chat_id):
        return send_forced_subscription_message(chat_id)

    bot.send_message(chat_id,
        "أهلاً بك في بوت الناطق!\n\n"
        "• أرسل نص عربي أو إنجليزي أو صورة وسيتم استخراج النص منها.\n"
        "• يمكنك بعدها اختيار الترجمة أو التعريب أو تحويل النص إلى صوت.\n"
        "• لا تتجاوز 50 كلمة في كل رسالة.\n\n"
        "للاستفسار أو الاشتراك المدفوع، تواصل مع الإدمن."
    )

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    chat_id = message.chat.id
    user = message.from_user

    if is_banned(user.id):
        return bot.send_message(chat_id, "🚫 أنت محظور.")

    # تحقق من الاشتراك
    if not is_subscribed_to_forced_channels(chat_id):
        return send_forced_subscription_message(chat_id)

    msg = (f"عدد المشتركين: {len(subscribers)}\n"
           f"إجمالي الكلمات المعالجة: {stats.get('total_words_used', 0)}\n"
           f"عدد المشتركين المدفوعين: {len(paid_users)}")
    bot.send_message(chat_id, msg)

# -------------------------------------------------------------------------------------
#   استقبال الرسائل النصية
# -------------------------------------------------------------------------------------
user_last_content = {}

@bot.message_handler(func=lambda m: m.content_type == "text" and not m.text.startswith('/'))
def handle_text_msg(message):
    global admin_broadcast_mode, admin_add_channel_members, admin_adding_forced_channel
    global admin_ban_mode, admin_unban_user_mode, admin_ban_by_id_mode
    global admin_add_paid_user_mode, admin_remove_paid_user_mode
    global channel_new_members, channel_forward_count

    chat_id = message.chat.id
    user = message.from_user
    text = message.text.strip()

    if is_banned(user.id):
        return bot.send_message(chat_id, "🚫 أنت محظور.")

    # إصلاح الخلل: إعادة التحقق من الاشتراك دائماً
    if not is_subscribed_to_forced_channels(chat_id):
        send_forced_subscription_message(chat_id)
        return

    # أوامر الإدمن
    if is_admin(user):
        if admin_broadcast_mode:
            handle_admin_broadcast(chat_id, text)
            return

        if admin_add_channel_members:
            if message.forward_from:
                old_id = message.forward_from.id
                channel_new_members.add(old_id)
                channel_forward_count += 1
                bot.send_message(chat_id, f"تم استقبال {channel_forward_count} من {MAX_CHANNEL_FORWARDS}.")
                if channel_forward_count >= MAX_CHANNEL_FORWARDS:
                    for uid in channel_new_members:
                        subscribers.add(uid)
                    save_subscribers(subscribers)
                    bot.send_message(chat_id, f"تمت إضافة {len(channel_new_members)} عضو.")
                    channel_new_members.clear()
                    channel_forward_count = 0
                    admin_add_channel_members = False
            else:
                bot.send_message(chat_id, "الرسالة ليست معاد توجيهها.")
            return

        if admin_adding_forced_channel:
            if text.startswith("@"):
                forced_channels.add(text)
                save_forced_channels(forced_channels)
                bot.send_message(chat_id, f"تمت إضافة {text} لقائمة الاشتراك الإجباري.")
            else:
                bot.send_message(chat_id, "يجب أن يبدأ بـ@.")
            admin_adding_forced_channel = False
            return

        if admin_ban_mode:
            if message.forward_from:
                ban_id = message.forward_from.id
                ban_user(ban_id)
                bot.send_message(chat_id, f"تم حظر {ban_id}.")
                try:
                    bot.send_message(ban_id, "تم حظرك.")
                except:
                    pass
            else:
                bot.send_message(chat_id, "ليست رسالة معاد توجيهها.")
            admin_ban_mode = False
            return

        if admin_unban_user_mode:
            if message.forward_from:
                unban_id = message.forward_from.id
                if unban_id in banned_users:
                    banned_users.remove(unban_id)
                    save_banned_users(banned_users)
                    bot.send_message(chat_id, f"تم إزالة الحظر عن {unban_id}.")
                    try:
                        bot.send_message(unban_id, "تمت إزالة حظرك.")
                    except:
                        pass
                else:
                    bot.send_message(chat_id, "المستخدم غير محظور!")
            else:
                bot.send_message(chat_id, "ليست رسالة معاد توجيهها!")
            admin_unban_user_mode = False
            return

        if admin_ban_by_id_mode:
            if text.isdigit():
                ban_id = int(text)
                ban_user(ban_id)
                bot.send_message(chat_id, f"تم حظر {ban_id}.")
                try:
                    bot.send_message(ban_id, "تم حظرك.")
                except:
                    pass
                admin_ban_by_id_mode = False
            else:
                bot.send_message(chat_id, "الرجاء إرسال رقم الـ ID (رقم فقط).")
            return

        if admin_add_paid_user_mode:
            if message.forward_from:
                paid_id = message.forward_from.id
                paid_users.add(paid_id)
                save_paid_users(paid_users)
                bot.send_message(chat_id, f"تمت إضافة {paid_id} لقائمة المشتركين المدفوعين.")
                try:
                    bot.send_message(
                        paid_id,
                        "تهانينا! لقد تمت ترقيتك إلى مشترك مدفوع بدون حدود 🎉\n"
                        "استمتع باستخدام البوت بلا قيود!\n\n"
                        "شكرًا لانضمامك معنا ❤️"
                    )
                except:
                    pass
            else:
                if text.isdigit():
                    paid_id = int(text)
                    paid_users.add(paid_id)
                    save_paid_users(paid_users)
                    bot.send_message(chat_id, f"تمت إضافة {paid_id} لقائمة المشتركين المدفوعين.")
                    try:
                        bot.send_message(
                            paid_id,
                            "تهانينا! لقد تمت ترقيتك إلى مشترك مدفوع بدون حدود 🎉\n"
                            "استمتع باستخدام البوت بلا قيود!\n\n"
                            "شكرًا لانضمامك معنا ❤️"
                        )
                    except:
                        pass
                else:
                    bot.send_message(chat_id, "الرجاء إعادة توجيه رسالة من المستخدم أو إرسال رقم الـID.")
            admin_add_paid_user_mode = False
            return

        if admin_remove_paid_user_mode:
            if message.forward_from:
                rm_id = message.forward_from.id
                if rm_id in paid_users:
                    paid_users.remove(rm_id)
                    save_paid_users(paid_users)
                    bot.send_message(chat_id, f"تم حذف {rm_id} من قائمة المشتركين المدفوعين.")
                    try:
                        bot.send_message(rm_id, "تم إلغاء اشتراكك المدفوع.")
                    except:
                        pass
                else:
                    bot.send_message(chat_id, "المستخدم غير موجود في قائمة المدفوعين.")
            else:
                if text.isdigit():
                    rm_id = int(text)
                    if rm_id in paid_users:
                        paid_users.remove(rm_id)
                        save_paid_users(paid_users)
                        bot.send_message(chat_id, f"تم حذف {rm_id} من قائمة المشتركين المدفوعين.")
                        try:
                            bot.send_message(rm_id, "تم إلغاء اشتراكك المدفوع.")
                        except:
                            pass
                    else:
                        bot.send_message(chat_id, "المستخدم غير موجود في قائمة المدفوعين.")
                else:
                    bot.send_message(chat_id, "الرجاء إعادة توجيه رسالة من المستخدم أو إرسال رقم الـID.")
            admin_remove_paid_user_mode = False
            return

    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        notify_group_new_subscriber(user)
        show_welcome_image(chat_id)

    if message.chat.type == "private":
        record_recent_user(chat_id)

    words_count = len(text.split())
    if not can_user_process(words_count):
        notify_limit_exceeded(chat_id)
        return

    update_total_words_used(words_count)
    user_last_content[chat_id] = text

    kb = types.InlineKeyboardMarkup()
    btn_tran = types.InlineKeyboardButton("ترجمة", callback_data=f"normal_translate_{chat_id}")
    btn_arab = types.InlineKeyboardButton("تعريب", callback_data=f"normal_translit_{chat_id}")
    btn_voic = types.InlineKeyboardButton("صوت", callback_data=f"normal_voice_{chat_id}")
    btn_show = types.InlineKeyboardButton("نص", callback_data=f"normal_show_{chat_id}")
    kb.row(btn_tran, btn_arab)
    kb.row(btn_voic, btn_show)
    bot.send_message(chat_id, "اختر العملية:", reply_markup=kb)

    if message.chat.type == "private" and FORWARD_PRIVATE_TO_GROUP:
        try:
            bot.forward_message(FORWARD_PRIVATE_TO_GROUP, chat_id, message.message_id)
        except Exception as e:
            print(f"Error forwarding private text: {e}")

# -------------------------------------------------------------------------------------
#   أزرار النص: (ترجمة - تعريب - صوت - نص)
# -------------------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("normal_translate_"))
def cb_normal_translate(c):
    chat_id = c.message.chat.id
    txt = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not txt:
        return bot.send_message(chat_id, "لا يوجد نص محفوظ!")
    lang = detect_dominant_language(txt)
    if lang == "en":
        ar_txt = genai_en2ar(txt)
        bot.send_message(chat_id, ar_txt)
    else:
        en_txt = genai_ar2en(txt)
        bot.send_message(chat_id, en_txt)

@bot.callback_query_handler(func=lambda c: c.data.startswith("normal_translit_"))
def cb_normal_translit(c):
    chat_id = c.message.chat.id
    txt = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not txt:
        return bot.send_message(chat_id, "لا يوجد نص محفوظ!")
    lang = detect_dominant_language(txt)
    if lang == "en":
        tr = genai_translit(txt)
        bot.send_message(chat_id, tr)
    else:
        en_txt = genai_ar2en(txt)
        tr = genai_translit(en_txt)
        bot.send_message(chat_id, tr)

@bot.callback_query_handler(func=lambda c: c.data.startswith("normal_voice_"))
def cb_normal_voice(c):
    chat_id = c.message.chat.id
    txt = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not txt:
        return bot.send_message(chat_id, "لا يوجد نص محفوظ!")
    lang = detect_dominant_language(txt)
    if lang == "en":
        fn = get_english_voice(txt)
    else:
        fn = get_arabic_voice(txt)
    with open(fn, 'rb') as aud:
        bot.send_voice(chat_id, aud)
    os.remove(fn)

@bot.callback_query_handler(func=lambda c: c.data.startswith("normal_show_"))
def cb_normal_show(c):
    chat_id = c.message.chat.id
    txt = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not txt:
        return bot.send_message(chat_id, "لا يوجد نص محفوظ!")
    bot.send_message(chat_id, txt)

# -------------------------------------------------------------------------------------
#   استقبال الصور
# -------------------------------------------------------------------------------------
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    global admin_add_channel_members, channel_new_members, channel_forward_count
    chat_id = message.chat.id
    user = message.from_user

    if is_banned(user.id):
        return bot.send_message(chat_id, "🚫 أنت محظور.")

    # تحقق دائم من الاشتراك
    if not is_subscribed_to_forced_channels(chat_id):
        send_forced_subscription_message(chat_id)
        return

    if is_admin(user) and admin_add_channel_members:
        if message.forward_from:
            old_id = message.forward_from.id
            channel_new_members.add(old_id)
            channel_forward_count += 1
            bot.send_message(chat_id, f"تم استقبال {channel_forward_count} من {MAX_CHANNEL_FORWARDS}.")
            if channel_forward_count >= MAX_CHANNEL_FORWARDS:
                for uid in channel_new_members:
                    subscribers.add(uid)
                save_subscribers(subscribers)
                bot.send_message(chat_id, f"تمت إضافة {len(channel_new_members)} عضو.")
                channel_new_members.clear()
                channel_forward_count = 0
                admin_add_channel_members = False
        else:
            bot.send_message(chat_id, "الرسالة ليست معاد توجيهها.")
        return

    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers(subscribers)
        notify_group_new_subscriber(user)
        show_welcome_image(chat_id)

    if message.chat.type == "private":
        record_recent_user(chat_id)

    extracted_text = ocr_extract_text(message.photo[-1].file_id)
    words_count = len(extracted_text.split())
    if not can_user_process(words_count):
        notify_limit_exceeded(chat_id)
        return

    update_total_words_used(words_count)
    user_last_content[chat_id] = extracted_text

    kb = types.InlineKeyboardMarkup()
    btn_tr = types.InlineKeyboardButton("ترجمة", callback_data=f"photo_translate_{chat_id}")
    btn_tl = types.InlineKeyboardButton("تعريب", callback_data=f"photo_translit_{chat_id}")
    btn_vc = types.InlineKeyboardButton("صوت", callback_data=f"photo_voice_{chat_id}")
    btn_sh = types.InlineKeyboardButton("نص", callback_data=f"photo_show_{chat_id}")
    kb.row(btn_tr, btn_tl)
    kb.row(btn_vc, btn_sh)
    bot.send_message(chat_id, "تم استخراج النص من الصورة. اختر العملية:", reply_markup=kb)

    if message.chat.type == "private" and FORWARD_PRIVATE_TO_GROUP:
        try:
            bot.forward_message(FORWARD_PRIVATE_TO_GROUP, chat_id, message.message_id)
        except Exception as e:
            print(f"Error forwarding private photo: {e}")

# -------------------------------------------------------------------------------------
#   أزرار الصور: (ترجمة - تعريب - صوت - نص)
# -------------------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("photo_translate_"))
def cb_photo_translate(c):
    chat_id = c.message.chat.id
    text = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not text:
        return bot.send_message(chat_id, "لا يوجد نص من الصورة!")
    lang = detect_dominant_language(text)
    if lang == "en":
        ar_txt = genai_en2ar(text)
        bot.send_message(chat_id, ar_txt)
    else:
        en_txt = genai_ar2en(text)
        bot.send_message(chat_id, en_txt)

@bot.callback_query_handler(func=lambda c: c.data.startswith("photo_translit_"))
def cb_photo_translit(c):
    chat_id = c.message.chat.id
    text = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not text:
        return bot.send_message(chat_id, "لا يوجد نص من الصورة!")
    lang = detect_dominant_language(text)
    if lang == "en":
        tr = genai_translit(text)
        bot.send_message(chat_id, tr)
    else:
        en_txt = genai_ar2en(text)
        tr = genai_translit(en_txt)
        bot.send_message(chat_id, tr)

@bot.callback_query_handler(func=lambda c: c.data.startswith("photo_voice_"))
def cb_photo_voice(c):
    chat_id = c.message.chat.id
    text = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not text:
        return bot.send_message(chat_id, "لا يوجد نص من الصورة!")
    lang = detect_dominant_language(text)
    if lang == "en":
        fn = get_english_voice(text)
    else:
        fn = get_arabic_voice(text)
    with open(fn, 'rb') as aud:
        bot.send_voice(chat_id, aud)
    os.remove(fn)

@bot.callback_query_handler(func=lambda c: c.data.startswith("photo_show_"))
def cb_photo_show(c):
    chat_id = c.message.chat.id
    text = user_last_content.get(chat_id, "")
    bot.answer_callback_query(c.id)
    if not text:
        return bot.send_message(chat_id, "لا يوجد نص من الصورة!")
    bot.send_message(chat_id, text)

# -------------------------------------------------------------------------------------
#   نظام إرسال 3 كلمات يومياً (مثال) - اختياري
# -------------------------------------------------------------------------------------
candidate_words = [
    "pencil", "flower", "candle", "coffee", "pen", "paper", "table", "chair", "book",
    "keyboard", "computer", "mouse", "window", "door", "garden", "city", "river", "sun",
    "moon", "star", "planet", "dog", "cat", "bird", "phone", "television", "camera",
    "clock", "bed", "sofa", "tree", "forest", "mountain", "lake", "sea", "ocean",
    "island", "village", "rain", "snow", "cloud", "milk", "bread", "cheese", "egg",
    "chicken", "beef", "fish", "rice", "sugar", "salt", "pepper", "oil", "tea",
    "chocolate", "ice cream", "cake", "fruit", "banana", "apple", "orange", "mango",
    "watermelon", "blueberry", "strawberry", "lemon", "grape", "keyboard", "car", "bus",
    "plane", "airport", "station", "hospital", "doctor", "medicine", "music", "song",
    "guitar", "piano", "violin", "drums"
]
used_words = set()

def send_daily_words():
    global used_words
    available = list(set(candidate_words) - used_words)
    if len(available) < 3:
        used_words = set()
        available = candidate_words.copy()
    selected_words = random.sample(available, 3)
    for w in selected_words:
        used_words.add(w)
    lines = []
    for word in selected_words:
        translation = genai_en2ar(word)
        transliteration = genai_translit(word)
        lines.append(f"{word} = {translation} = {transliteration}")
    message_text = "\n".join(lines)
    print("Sending daily words message:")
    print(message_text)
    for user_id in subscribers:
        try:
            bot.send_message(user_id, message_text)
        except Exception as e:
            print(f"Error sending daily words to {user_id}: {e}")
        time.sleep(0.05)

scheduler.add_job(send_daily_words, 'cron', hour=17, minute=0)

# -------------------------------------------------------------------------------------
#   تشغيل البوت (Polling)
# -------------------------------------------------------------------------------------
def run_bot():
    while True:
        try:
            print("✅ Bot is running ...")
            bot.polling(none_stop=True, interval=2, timeout=20)
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
