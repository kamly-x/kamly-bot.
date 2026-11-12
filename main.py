# -*- coding: utf-8 -*-
"""
KAMLY HUB bot  |  RU / EN  |  чат + супергруппа с темами
Настройки берутся из переменных окружения хостинга (токен в коде НЕ хранится).
"""
import asyncio
import html
import io
import json
import logging
import os
import random
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from telegram import (
    Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb,
    ChatPermissions, LinkPreviewOptions, ReplyParameters, BotCommand,
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import BadRequest
from telegram.ext import (
    Application, ApplicationHandlerStop, CallbackQueryHandler, ChatMemberHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

# ============================ НАСТРОЙКИ ============================
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATABASE_URL="postgresql://postgres.gfcpzdrjccdwthkbyjst:KamlyHub2026@aws-0-eu-west-3.pooler.supabase.com:6543/postgres"
DATA_FILE = os.environ.get("DATA_FILE", "data.json")

OLD_ID = int(os.environ.get("OLD_CHAT_ID", "-1004465245585"))   # старый чат (RU)
HUB_ID = int(os.environ.get("HUB_CHAT_ID", "-1004440981561"))   # новая супергруппа с темами
REF_CHAT_ID = int(os.environ.get("REF_CHAT_ID", str(HUB_ID)))   # куда ведёт реф-ссылка

CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/kam1ly_x")
OLD_CHAT_LINK = os.environ.get("OLD_CHAT_LINK", "https://t.me/+IGHOWiHXO-swMGIy")
HUB_LINK = os.environ.get("HUB_LINK", "")      # инвайт-ссылка на новую группу (по желанию)
TIKTOK_LINK = os.environ.get("TIKTOK_LINK", "")

UTC_OFFSET = int(os.environ.get("UTC_OFFSET", "3"))   # Москва = 3
CONTEST_DAY, CONTEST_HOUR = 6, 20      # итоги недели: воскресенье 20:00
CHALLENGE_DAY, CHALLENGE_HOUR = 0, 12  # челлендж: понедельник 12:00
BACKUP_HOUR = 4                        # автобэкап админам в личку
BAN_ON_AD = True                       # бан за рекламу (t.me, профили)
MAX_WARNS = 3                          # варнов до мута на сутки
REF_FIRE = 2                           # 🔥 за каждого приглашённого
DUEL_HOURS = 24
DUEL_VOTE_HOURS = 24
ANON_COOLDOWN = 600
WINNER_TAG_RU, WINNER_TAG_EN = "Креатор недели", "Creator of Week"   # до 16 символов

CHATS = {
    OLD_ID: {"name": "RU chat", "link": OLD_CHAT_LINK, "forum": False},
    HUB_ID: {"name": "KAMLY HUB", "link": HUB_LINK or OLD_CHAT_LINK, "forum": True},
}
ROLES = ["rules", "announce", "chat_ru", "chat_en", "review", "duels", "leaderboard"]
ROLE_NAMES = {"rules": "Rules", "announce": "Announcements", "chat_ru": "Chat RU",
              "chat_en": "Chat ENG", "review": "Review & Sources",
              "duels": "Duels & Challenges", "leaderboard": "Leaderboard & Ranks"}
# где работают хештеги (если нужные темы ещё не привязаны — работает везде)
FEATURE_ROLES = {"edit": ("chat_ru", "chat_en", "review"),
                 "review": ("review",), "duel": ("duels",)}

# Ранги: (мин. 🔥, RU, EN, описание RU, описание EN)
RANKS = [
    (0, "Новичок", "Novice",
     "Только зашёл в хаб, учится накладывать первые ключевые кадры и разбирается с софтом.",
     "Just joined the hub, learning first keyframes and the software."),
    (11, "Практик", "Editor",
     "Стабильно кидает работы в чат, пробует новые стили и шрифты.",
     "Posts works regularly, tries new styles and fonts."),
    (31, "Скилловый", "Skilled",
     "Набивает руку, эдиты собирают хорошие оценки, понимает тайминги и музыку.",
     "Getting sharper, edits get good ratings, understands timing and music."),
    (71, "Мастер", "Master",
     "Опытный тип в чате, работы стабильно залетают в топ и участвуют в дуэлях.",
     "Experienced editor, works regularly hit the top and join duels."),
    (151, "Андеграунд", "Underground",
     "Элита чата со своим узнаваемым стилем и жёстким визуалом.",
     "Chat elite with a recognizable style and hard visuals."),
    (301, "Легенда", "Legend",
     "Верхушка комьюнити, авторитетный креатор, на которого равняются новички.",
     "Top of the community, an authority newcomers look up to."),
]

GENRES = {
    "shoegaze": {"short": "Shoegaze", "title": "Dark Shoegaze / Alternative",
                 "vibe": ("мрачные, атмосферные эдиты", "dark, atmospheric edits"),
                 "styles": [("Dark manga atmosphere", "Dark manga atmosphere"),
                            ("Slow zoom + плёночное зерно", "Slow zoom + film grain"),
                            ("Ч/Б с мягким свечением", "B&W with soft glow")]},
    "phonk": {"short": "Phonk / Rap", "title": "Underground Rap / Phonk",
              "vibe": ("жёсткий динамичный монтаж", "hard dynamic montage"),
              "styles": [("Быстрые переходы + shake", "Fast transitions + shake"),
                         ("Ритм-монтаж под бит", "Beat-synced montage"),
                         ("Агрессивные глитчи + красные акценты", "Aggressive glitches + red accents")]},
    "witch": {"short": "Witch House", "title": "Witch House",
              "vibe": ("медленный темп, глитчи и мистический вайб", "slow tempo, glitches, mystic vibe"),
              "styles": [("Глитчи + VHS", "Glitches + VHS"),
                         ("Мистика и ghost-эффекты", "Mystic + ghost effects"),
                         ("Замедление + искажения", "Slowdown + distortion")]},
    "ambient": {"short": "Ambient", "title": "Ambient / Slowed & Reverb",
                "vibe": ("плавный, медитативный монтаж", "smooth, meditative montage"),
                "styles": [("Плавные переходы", "Smooth transitions"),
                           ("Frame by frame в слоу", "Slow frame by frame"),
                           ("Минимализм + типографика", "Minimalism + typography")]},
}
LENGTHS = [("10 секунд", "10 seconds"), ("15 секунд", "15 seconds"),
           ("20 секунд", "20 seconds"), ("30 секунд", "30 seconds")]
DUEL_STYLES = [("Light animation", "Light animation"), ("Dark manga glitch", "Dark manga glitch"),
               ("Типографика", "Typography"), ("Ч/Б + один цвет", "B&W + one color"),
               ("Slow zoom", "Slow zoom"), ("VHS-хоррор", "VHS horror"),
               ("Ритм-монтаж", "Rhythm cut"), ("Глитчи", "Glitches")]
# ===================================================================

if ":" not in TOKEN:
    print("❌ Не задана переменная окружения BOT_TOKEN (токен из @BotFather).")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

NOPREV = LinkPreviewOptions(is_disabled=True)
HTML = ParseMode.HTML
TZ = timezone(timedelta(hours=UTC_OFFSET))
ADMIN_STATUSES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
HT_EDIT = re.compile(r"#edit\b", re.I)
HT_REVIEW = re.compile(r"#review\b", re.I)
HT_DUEL = re.compile(r"#duel\b", re.I)
FLOOD = defaultdict(deque)
STAT_KEYS = ["edits", "votes", "contests", "links", "bans", "mutes", "warns",
             "reviews", "duels", "anon", "ratings", "comments"]


# ============================ ЯЗЫК ============================
def L(lang, ru, en):
    """ru / en / bi (двуязычный вариант для тем без языка)."""
    if lang == "ru":
        return ru
    if lang == "en":
        return en
    if "\n" not in ru and len(ru) + len(en) <= 100:
        return f"{ru} / {en}"
    return f"{ru}\n\n━━━━━━━━━━\n\n🇬🇧 {en}"


def guess_lang(tg_user):
    code = (getattr(tg_user, "language_code", "") or "").lower()
    return "ru" if code[:2] in ("ru", "uk", "be", "kk") else "en"


# ============================ ДАННЫЕ ============================
def fresh_defaults():
    return {"gif": None, "warns": {}, "edits": {}, "last_week": "", "last_challenge_week": "",
            "users": {}, "known": {}, "stats": {}, "hall": [], "tracks": [], "winner_uid": None,
            "challenge": None, "duels": {}, "anon": {}, "anon_msgs": {}, "anon_last": {},
            "counters": {}, "topics": {}, "ref_links": {}, "ref_owner": {}, "ref_joined": {},
            "backup_to": [], "last_backup": ""}


def ensure(d):
    for k, v in fresh_defaults().items():
        d.setdefault(k, v)
    for k in STAT_KEYS:
        d["stats"].setdefault(k, 0)
    for k in ("anon", "duel"):
        d["counters"].setdefault(k, 0)
    return d


def _db_load():
    import psycopg
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        row = c.execute("SELECT v FROM kv WHERE k='data'").fetchone()
    return json.loads(row[0]) if row else None


def _db_save(s):
    import psycopg
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute("INSERT INTO kv(k, v) VALUES ('data', %s) "
                  "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v", (s,))


def load():
    d = None
    if DATABASE_URL:
        try:
            d = _db_load()
            print("✅ База данных подключена" + ("" if d else " (пока пустая)"))
        except Exception as e:
            print("❌ Не удалось подключиться к базе данных:", e)
            sys.exit(1)   # не стартуем, чтобы не затереть данные пустыми
    if d is None and os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            print("⚠️ data.json повреждён:", e)
            d = None
    return ensure(d or {})


DATA = load()
DIRTY = {"v": bool(DATABASE_URL)}   # при старте с БД сразу сохраним (на случай импорта из файла)
SAVE_LOCK = None


def save():
    DIRTY["v"] = True


def _write_sync(s):
    if DATABASE_URL:
        _db_save(s)
    else:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(s)
        os.replace(tmp, DATA_FILE)


async def flush():
    if not DIRTY["v"]:
        return
    DIRTY["v"] = False
    try:
        await asyncio.to_thread(_write_sync, json.dumps(DATA, ensure_ascii=False))
    except Exception as e:
        DIRTY["v"] = True
        print("save error:", e)


async def flusher():
    while True:
        await asyncio.sleep(5)
        await flush()


def new_user(name="Участник", username=""):
    return {"name": name, "username": username or "", "edits": 0, "fire": 0, "wins": 0,
            "duel_wins": 0, "rank": 0, "tagged": False, "refs": 0, "lang": None}

def get_user(uid, name=None, username=None):
    key = str(uid)
    u = DATA["users"].get(key)
    if u is None:
        u = new_user(name or "Участник", username or "")
        DATA["users"][key] = u
    for k, v in new_user().items():
        u.setdefault(k, v)
    if name:
        u["name"] = name
    if username:
        u["username"] = username
        DATA["known"][username.lower()] = uid
    save()
    return u


def ulang(uid):
    u = DATA["users"].get(str(uid))
    return (u or {}).get("lang")


# ============================ ХЕЛПЕРЫ ============================
BG = set()


def bg(coro):
    t = asyncio.create_task(coro)
    BG.add(t)
    t.add_done_callback(BG.discard)


def esc(s):
    return html.escape(str(s or ""))


def mention(uid, name):
    return f'<a href="tg://user?id={uid}">{esc(name)}</a>'


def now_local():
    return datetime.now(timezone.utc).astimezone(TZ)


def fmt_ts(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m %H:%M")


def post_link(cid, mid):
    return f"https://t.me/c/{str(cid)[4:]}/{mid}"


def thread_of(m):
    if m is not None and getattr(m, "is_topic_message", False):
        return m.message_thread_id
    return None


def role_of(cid, thread):
    if not CHATS.get(cid, {}).get("forum"):
        return "main"
    if thread is None:
        return "general"
    for r, t in DATA["topics"].get(str(cid), {}).items():
        if t == thread:
            return r
    return "other"


def lang_of(cid, role):
    if CHATS.get(cid, {}).get("forum"):
        return {"chat_ru": "ru", "chat_en": "en"}.get(role, "bi")
    return "ru"


def place(m):
    cid, th = m.chat_id, thread_of(m)
    role = role_of(cid, th)
    return cid, th, role, lang_of(cid, role)


def real_reply(m):
    r = getattr(m, "reply_to_message", None)
    if r is None or getattr(r, "forum_topic_created", None):
        return None
    return r


def lab(lang, emoji, ru, en):
    return f"{emoji} {L(lang, ru, en)}: "


def cl(update):
    """Язык ответа: в личке — выбор человека, в чате — по теме."""
    if update.effective_chat.type == "private":
        return ulang(update.effective_user.id) or guess_lang(update.effective_user)
    return place(update.effective_message)[3]


async def say(bot, m, text, **kw):
    kw.setdefault("parse_mode", HTML)
    kw.setdefault("link_preview_options", NOPREV)
    th = thread_of(m)
    if th:
        kw["message_thread_id"] = th
    return await bot.send_message(m.chat_id, text, **kw)


async def send_to(bot, cid, role, text, **kw):
    kw.setdefault("parse_mode", HTML)
    kw.setdefault("link_preview_options", NOPREV)
    th = DATA["topics"].get(str(cid), {}).get(role) if role else None
    if th:
        kw["message_thread_id"] = th
    return await bot.send_message(cid, text, **kw)


async def delete_later(msg, sec):
    await asyncio.sleep(sec)
    try:
        await msg.delete()
    except Exception:
        pass


async def notice(bot, cid, text, sec=20, role=None):
    try:
        msg = await send_to(bot, cid, role, text)
        bg(delete_later(msg, sec))
    except Exception as e:
        print("notice error:", e)


async def notice_m(bot, m, text, sec=20):
    try:
        msg = await say(bot, m, text)
        bg(delete_later(msg, sec))
    except Exception as e:
        print("notice error:", e)


async def safe_delete(m):
    try:
        await m.delete()
    except Exception:
        pass


async def safe_edit(q, text, kb=None):
    try:
        await q.edit_message_text(text, parse_mode=HTML, reply_markup=kb, link_preview_options=NOPREV)
    except BadRequest:
        pass


async def edit_by_id(bot, cid, mid, text, kb=None):
    try:
        await bot.edit_message_text(text, chat_id=cid, message_id=mid, parse_mode=HTML,
                                    reply_markup=kb, link_preview_options=NOPREV)
    except Exception as e:
        print("edit error:", e)


ADMIN_CACHE = {}


async def is_admin(bot, uid):
    c = ADMIN_CACHE.get(uid)
    if c and time.time() - c[1] < 60:
        return c[0]
    ok = False
    for cid in CHATS:
        try:
            mm = await bot.get_chat_member(cid, uid)
            if mm.status in ADMIN_STATUSES:
                ok = True
                break
        except Exception:
            pass
    ADMIN_CACHE[uid] = (ok, time.time())
    return ok


async def member_chat(bot, uid):
    """В каком чате состоит человек (приоритет — новая группа)."""
    for cid in (HUB_ID, OLD_ID):
        try:
            mm = await bot.get_chat_member(cid, uid)
            if mm.status == ChatMemberStatus.RESTRICTED and not getattr(mm, "is_member", True):
                continue
            if mm.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR,
                             ChatMemberStatus.OWNER, ChatMemberStatus.RESTRICTED):
                return cid
        except Exception:
            pass
    return None


async def mute(bot, cid, uid, seconds):
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await bot.restrict_chat_member(cid, uid, ChatPermissions(can_send_messages=False), until_date=until)
    DATA["stats"]["mutes"] += 1
    save()


async def unmute(bot, cid, uid):
    await bot.restrict_chat_member(cid, uid, ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True))


async def do_ban(bot, cid, uid):
    await bot.ban_chat_member(cid, uid)
    DATA["stats"]["bans"] += 1
    save()


async def add_warn(bot, m, user, reason_ru, reason_en):
    lang = place(m)[3]
    key = str(user.id)
    DATA["warns"][key] = DATA["warns"].get(key, 0) + 1
    DATA["stats"]["warns"] += 1
    n = DATA["warns"][key]
    if n >= MAX_WARNS:
        DATA["warns"][key] = 0
        save()
        try:
            await mute(bot, m.chat_id, user.id, 24 * 3600)
        except Exception as e:
            print("mute error:", e)
        await notice_m(bot, m, "🔇 " + L(lang, f"{user.mention_html()} получил {MAX_WARNS} предупреждения — мут на 24 часа.",
                                         f"{user.mention_html()} got {MAX_WARNS} warnings — muted for 24h."))
    else:
        save()
        await notice_m(bot, m, "⚠️ " + L(lang, f"{user.mention_html()}, предупреждение {n}/{MAX_WARNS}: {reason_ru}",
                                         f"{user.mention_html()}, warning {n}/{MAX_WARNS}: {reason_en}"))


# ============================ ССЫЛКИ ============================
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>]+"
    r"|\b[a-z0-9][a-z0-9\-\.]*\.(?:com|ru|me|org|net|io|gg|ly|app|link|xyz|tv|fm|be|to|co|su|ua|by)/[^\s<>]*",
    re.I)
MUSIC_HOSTS = ("open.spotify.com", "spotify.link", "music.apple.com", "soundcloud.com", "on.soundcloud.com",
               "music.yandex.ru", "music.yandex.com", "deezer.com", "tidal.com", "music.youtube.com",
               "genius.com", "bandcamp.com", "audiomack.com", "vk.com/audio", "zvuk.com", "song.link", "pin.it")
OK_TG_WORDS = ["kam1ly_x", "kamly_helper_bot"]


def classify(url):
    """ok — можно, ad — реклама (бан), other — чужая ссылка (варн)."""
    u = url.strip().rstrip(".,);]>")
    low = u.lower()
    if not re.match(r"https?://", low):
        u = "https://" + u
    try:
        p = urlparse(u)
    except Exception:
        return "other"
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = p.path or ""
    if host in ("t.me", "telegram.me", "telegram.dog"):
        slug = path.strip("/").lower()
        own = list(DATA["ref_owner"]) + [CHATS[c]["link"] for c in CHATS if CHATS[c]["link"]] + [CHANNEL_LINK]
        for link in own + OK_TG_WORDS:
            sl = link.lower().split("t.me/")[-1].strip("/")
            if sl and slug and (slug == sl or slug.startswith(sl)):
                return "ok"
        return "ad"
    if host.endswith("tiktok.com"):
        if host in ("vt.tiktok.com", "vm.tiktok.com") or path.startswith("/t/") \
                or re.search(r"/(video|photo)/\d+", path):
            return "ok"
        return "ad"
    if host.endswith("instagram.com"):
        return "ok" if re.match(r"/(reel|reels|p|tv)/", path) else "ad"
    if host == "youtu.be":
        return "ok"
    if host.endswith("youtube.com") and host != "music.youtube.com":
        return "ok" if re.match(r"/(watch|shorts|live|playlist|embed)", path) else "ad"
    if host in MUSIC_HOSTS or any(host.endswith("." + h) for h in MUSIC_HOSTS) \
            or (host == "vk.com" and path.startswith("/audio")):
        return "ok"
    if host.endswith("pinterest.com") and path.startswith("/pin/"):
        return "ok"
    return "other"


def extract_links(m):
    text = m.text or m.caption or ""
    links = [x.rstrip(".,);]") for x in URL_RE.findall(text)]
    for e in (m.entities or m.caption_entities or []):
        if e.type == "text_link" and e.url:
            links.append(e.url)
    return links


def has_content(m):
    text = m.text or m.caption or ""
    return bool(m.video or m.animation or m.photo or m.document or m.video_note or URL_RE.search(text))


# ============================ РАНГИ И ТЕГИ ============================
def rank_idx(fire):
    idx = 0
    for i, r in enumerate(RANKS):
        if fire >= r[0]:
            idx = i
    return idx


def rname(i, lang):
    r = RANKS[i]
    return {"ru": f"{r[1]} ({r[2]})", "en": r[2]}.get(lang, f"{r[1]} / {r[2]}")


def desired_tag(uid, cid):
    en = CHATS.get(cid, {}).get("forum", False)
    if DATA.get("winner_uid") == uid:
        return WINNER_TAG_EN if en else WINNER_TAG_RU
    u = DATA["users"].get(str(uid))
    i = rank_idx(u["fire"]) if u else 0
    return RANKS[i][2] if en else RANKS[i][1]


async def set_tag(cid, uid, tag):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"https://api.telegram.org/bot{TOKEN}/setChatMemberTag",
                             json={"chat_id": cid, "user_id": uid, "tag": tag[:16]})
        j = r.json()
        if not j.get("ok") and "not found" not in str(j.get("description", "")).lower():
            print("tag error:", cid, uid, j.get("description"))
    except Exception as e:
        print("tag error:", e)


async def apply_tag(bot, uid):
    for cid in CHATS:
        await set_tag(cid, uid, desired_tag(uid, cid))


async def refresh_rank(bot, uid, announce=True):
    u = DATA["users"].get(str(uid))
    if not u:
        return
    new, old = rank_idx(u["fire"]), u.get("rank", 0)
    if new != old or not u.get("tagged"):
        u["rank"], u["tagged"] = new, True
        save()
        await apply_tag(bot, uid)
        if announce and new > old:
            for cid in CHATS:
                lang = lang_of(cid, "leaderboard")
                await notice(bot, cid, "🎉 " + L(lang,
                             f"{mention(uid, u['name'])} получает ранг <b>{rname(new, 'ru')}</b>!",
                             f"{mention(uid, u['name'])} reached rank <b>{rname(new, 'en')}</b>!"),
                             30, role="leaderboard")


def ranking():
    arr = [(k, u) for k, u in DATA["users"].items()
           if u["fire"] > 0 or u["wins"] > 0 or u["edits"] > 0 or u.get("duel_wins", 0) > 0]
    arr.sort(key=lambda x: (x[1]["fire"], x[1]["wins"], x[1]["edits"]), reverse=True)
    return arr


# ============================ ТЕКСТЫ ============================

def rules_text(lang):
    ru = ("📜 <b>Правила KAMLY HUB</b>\n\n<b>Запрещается:</b>\n\n"
          "🔞 Контент 18+ | 🚫 Бан навсегда\n\n"
          "⚔️ Любые конфликты, токсичность и буллинг | 🔇 1-й раз — мут, 2-й — бан\n\n"
          "📢 Сторонняя реклама (ТГК, профили TikTok, чужие каналы и бренды) | 🚫 Бан\n\n"
          "💬 Спам и бессмысленный флуд | ⚠️ Предупреждение / Мут\n\n"
          "ℹ️ Ссылки на TikTok-видео, музыку и YouTube-ролики (поиск исходников) разрешены.")
    en = ("📜 <b>KAMLY HUB Rules</b>\n\n<b>Forbidden:</b>\n\n"
          "🔞 18+ content | 🚫 Permanent ban\n\n"
          "⚔️ Conflicts, toxicity, bullying | 🔇 1st time — mute, 2nd — ban\n\n"
          "📢 Third-party ads (channels, TikTok profiles, brands) | 🚫 Ban\n\n"
          "💬 Spam and senseless flood | ⚠️ Warning / Mute\n\n"
          "ℹ️ Links to TikTok videos, music and YouTube videos (source search) are allowed.")
    return L(lang, ru, en)


def welcome_text(lang, name):
    ru = (f"Welcome to <b>KAMLY HUB</b>, {name} ⛓️\n\n"
          "Главное комьюнити для эдиторов и ценителей манги.\n\n"
          "🎬 <code>#edit</code> — еженедельный конкурс эдитов (🔥/👎)\n"
          "🔍 <code>#review</code> — разбор твоей работы\n"
          "⚔️ <code>/duel</code> — дуэли эдиторов\n"
          "🏅 <code>/me</code>, <code>/top</code> — ранги и рейтинг\n"
          "🤝 Партнёрка: приглашай друзей — забирай админку и бонусы\n\n"
          "Жми кнопки ниже 👇")
    en = (f"Welcome to <b>KAMLY HUB</b>, {name} ⛓️\n\n"
          "The main community for editors and manga fans.\n\n"
          "🎬 <code>#edit</code> — weekly edit contest (🔥/👎)\n"
          "🔍 <code>#review</code> — get feedback on your work\n"
          "⚔️ <code>/duel</code> — editor duels\n"
          "🏅 <code>/me</code>, <code>/top</code> — ranks and leaderboard\n"
          "🤝 Referral program: invite friends — win admin spots and bonuses\n\n"
          "Use the buttons below 👇")
    return L(lang, ru, en)


def welcome_kb(bot_username, lang):
    base = f"https://t.me/{bot_username}?start="
    return Kb([
        [Btn(L(lang, "📜 Правила", "📜 Rules"), url=base + "rules"),
         Btn(L(lang, "📖 Команды", "📖 Commands"), url=base + "cmds")],
        [Btn(L(lang, "🤝 Партнёрка", "🤝 Referral"), url=base + "ref"),
         Btn("🌐 Language", url=base + "lang")],
        [Btn(L(lang, "⚡ Канал", "⚡ Channel"), url=CHANNEL_LINK)],
    ])


def guide_text(lang):
    ru = ("📚 <b>Гайд по KAMLY HUB</b>\n\n"
          "<b>Куда что писать:</b>\n"
          "💬 <b>Chat RU / Chat ENG</b> — общение, эдиты с <code>#edit</code>\n"
          "🎬 <b>Review &amp; Sources</b> — <code>#review</code>, анонимная оценка, поиск исходников\n"
          "⚔️ <b>Duels &amp; Challenges</b> — дуэли и челлендж недели\n"
          "🏆 <b>Leaderboard &amp; Ranks</b> — рейтинг и ранги\n"
          "📣 <b>Announcements</b> — итоги недели и новости\n"
          "📝 <b>Rules</b> — правила\n\n"
          "<b>Как это работает:</b>\n"
          "1. Кидай эдит с <code>#edit</code> — чат голосует 🔥/👎, 🔥 дают ранг.\n"
          "2. Каждое воскресенье бот подводит итоги и выдаёт тег «Креатор недели».\n"
          "3. Каждый понедельник — челлендж: стиль, длина, трек.\n"
          "4. <code>/duel</code> — вызови эдитора, выберите трек и стиль.\n"
          "5. В личке бота «Оценить эдит» — анонимная оценка 1–10.\n"
          "6. Партнёрка: зови друзей по своей ссылке — топ получает админку.\n\n"
          "Все команды: <code>/commands</code>")
    en = ("📚 <b>KAMLY HUB Guide</b>\n\n"
          "<b>Where to post:</b>\n"
          "💬 <b>Chat RU / Chat ENG</b> — chatting, edits with <code>#edit</code>\n"
          "🎬 <b>Review &amp; Sources</b> — <code>#review</code>, anonymous rating, source search\n"
          "⚔️ <b>Duels &amp; Challenges</b> — duels and the weekly challenge\n"
          "🏆 <b>Leaderboard &amp; Ranks</b> — leaderboard and ranks\n"
          "📣 <b>Announcements</b> — weekly results and news\n"
          "📝 <b>Rules</b> — rules\n\n"
          "<b>How it works:</b>\n"
          "1. Post an edit with <code>#edit</code> — the chat votes 🔥/👎, 🔥 raise your rank.\n"
          "2. Every Sunday the bot picks the winner and gives the “Creator of Week” tag.\n"
          "3. Every Monday — a challenge: style, length, track.\n"
          "4. <code>/duel</code> — challenge an editor, pick a track and a style.\n"
          "5. In the bot's DM press “Rate edit” — anonymous 1–10 rating.\n"
          "6. Referral: invite friends with your link — the top gets admin spots.\n\n"
          "All commands: <code>/commands</code>")
    return L(lang, ru, en)


def commands_text(lang):
    ru = ("📖 <b>Команды KAMLY HUB</b>\n\n"
          "<b>Для всех:</b>\n"
          "/me — твоя карточка и ранг\n/top — рейтинг креаторов\n/ranks — все ранги\n"
          "/stats — статистика хаба\n/hall — зал славы\n/contest — топ эдитов недели\n"
          "/challenge — челлендж недели\n/duel — вызвать на дуэль (ответом или @ник)\n"
          "/invite — партнёрка и твоя ссылка\n/reftop — топ пригласивших\n"
          "/guide — гайд по хабу\n/rules — правила\n/commands — этот список\n\n"
          "<b>Хештеги:</b>\n<code>#edit</code> — эдит в конкурс\n<code>#review</code> — запрос фидбека\n"
          "<code>#duel</code> — сдать эдит в дуэль\n\n"
          "<b>В личке бота:</b> оценка эдита анонимно, язык, партнёрка.\n\n"
          "<b>Админам</b> (ответом на сообщение): /warn /mute 30 /unmute /ban /unban /who\n"
          "/winner /newchallenge /endduel /settopic /topics /postguide /postrules")
    en = ("📖 <b>KAMLY HUB commands</b>\n\n"
          "<b>For everyone:</b>\n"
          "/me — your card and rank\n/top — creators leaderboard\n/ranks — all ranks\n"
          "/stats — hub stats\n/hall — hall of fame\n/contest — this week's top edits\n"
          "/challenge — weekly challenge\n/duel — challenge someone (reply or @name)\n"
          "/invite — referral program and your link\n/reftop — top inviters\n"
          "/guide — hub guide\n/rules — rules\n/commands — this list\n\n"
          "<b>Hashtags:</b>\n<code>#edit</code> — enter the contest\n<code>#review</code> — ask for feedback\n"
          "<code>#duel</code> — submit your duel edit\n\n"
          "<b>In the bot's DM:</b> anonymous edit rating, language, referral.\n\n"
          "<b>Admins</b> (reply to a message): /warn /mute 30 /unmute /ban /unban /who\n"
          "/winner /newchallenge /endduel /settopic /topics /postguide /postrules")
    return L(lang, ru, en)


# ============================ КАНАЛ: ГИФКА ============================
async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m or not m.is_automatic_forward:
        return
    kb = Kb([[Btn("Channel Chat", url=CHATS[m.chat_id]["link"] or OLD_CHAT_LINK)]])
    try:
        if DATA["gif"]:
            await m.reply_animation(animation=DATA["gif"], reply_markup=kb)
        else:
            await m.reply_text("Наш чат 👇", reply_markup=kb)
    except Exception as e:
        print("ОШИБКА гифки:", e)


# ============================ ПРИВЕТСТВИЕ ============================
async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m, u = update.message, update.effective_user
    if not m or not u or u.is_bot or m.sender_chat:
        return
    get_user(u.id, u.full_name, u.username)


async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m:
        return
    lang = place(m)[3]
    for u in m.new_chat_members:
        if u.is_bot:
            continue
        get_user(u.id, u.full_name, u.username)
        name = f"@{u.username}" if u.username else mention(u.id, u.full_name)
        try:
            sent = await say(context.bot, m, welcome_text(lang, name),
                             reply_markup=welcome_kb(context.bot.username, lang))
            bg(delete_later(sent, 600))
        except Exception as e:
            print("welcome error:", e)
        bg(refresh_rank(context.bot, u.id, announce=False))


async def cmd_rules(update, context):
    await say(context.bot, update.effective_message, rules_text(cl(update)))


async def cmd_guide(update, context):
    await say(context.bot, update.effective_message, guide_text(cl(update)))


async def cmd_commands(update, context):
    await say(context.bot, update.effective_message, commands_text(cl(update)))


# ============================ АНТИСПАМ ============================
async def antispam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m, u = update.effective_message, update.effective_user
    if not m or not u or u.is_bot or m.sender_chat or m.chat_id not in CHATS:
        return
    bot = context.bot
    if await is_admin(bot, u.id):
        return
    cid, th, role, lang = place(m)

    if update.message:
        now = time.time()
        dq = FLOOD[u.id]
        dq.append(now)
        while dq and now - dq[0] > 10:
            dq.popleft()
        if len(dq) >= 7:
            dq.clear()
            await safe_delete(m)
            try:
                await mute(bot, cid, u.id, 600)
            except Exception as e:
                print("mute error:", e)
            await notice_m(bot, m, "🔇 " + L(lang, f"{u.mention_html()} — мут на 10 минут за флуд.",
                                             f"{u.mention_html()} — muted for 10 minutes for flooding."))
            raise ApplicationHandlerStop

    kinds = [classify(l) for l in extract_links(m)]
    kinds = [k for k in kinds if k != "ok"]
    if kinds and set(kinds) == {"other"} and role == "review":
        kinds = []     # в Review & Sources можно делиться источниками
    if kinds:
        await safe_delete(m)
        DATA["stats"]["links"] += 1
        save()
        if BAN_ON_AD and "ad" in kinds:
            try:
                await do_ban(bot, cid, u.id)
                await notice_m(bot, m, "🚫 " + L(lang, f"{u.mention_html()} забанен за рекламу.",
                                                 f"{u.mention_html()} banned for advertising."))
            except Exception as e:
                print("ban error:", e)
        else:
            await add_warn(bot, m, u, "чужие ссылки запрещены", "third-party links are not allowed")
        raise ApplicationHandlerStop


# ============================ КОМАНДЫ АДМИНОВ ============================

async def get_target(update, context):
    m = update.message
    if not await is_admin(context.bot, update.effective_user.id):
        return None
    await safe_delete(m)
    r = real_reply(m)
    if not r or not r.from_user or r.from_user.is_bot:
        await notice_m(context.bot, m, "Ответь командой на сообщение пользователя. / Reply to a user's message.")
        return None
    return r.from_user


async def cmd_warn(update, context):
    u = await get_target(update, context)
    if u:
        await add_warn(context.bot, update.message, u, "нарушение правил", "rule violation")


async def cmd_mute(update, context):
    u = await get_target(update, context)
    if not u:
        return
    m = update.message
    minutes = int(context.args[0]) if context.args and context.args[0].isdigit() else 60
    await mute(context.bot, m.chat_id, u.id, minutes * 60)
    lang = place(m)[3]
    await notice_m(context.bot, m, "🔇 " + L(lang, f"{u.mention_html()} — мут на {minutes} мин.",
                                             f"{u.mention_html()} — muted for {minutes} min."))


async def cmd_unmute(update, context):
    u = await get_target(update, context)
    if u:
        await unmute(context.bot, update.message.chat_id, u.id)
        await notice_m(context.bot, update.message, f"🔊 {u.mention_html()}")


async def cmd_ban(update, context):
    u = await get_target(update, context)
    if u:
        await do_ban(context.bot, update.message.chat_id, u.id)
        await notice_m(context.bot, update.message, f"🚫 {u.mention_html()}")


async def cmd_unban(update, context):
    u = await get_target(update, context)
    if u:
        await context.bot.unban_chat_member(update.message.chat_id, u.id, only_if_banned=True)
        await notice_m(context.bot, update.message, f"✅ {u.mention_html()}")


async def cmd_settopic(update, context):
    m = update.message
    if not await is_admin(context.bot, update.effective_user.id):
        return
    th = thread_of(m)
    role = (context.args[0].lower() if context.args else "")
    if m.chat_id != HUB_ID or th is None or role not in ROLES:
        await m.reply_text("Напиши команду ВНУТРИ нужной темы новой группы: /settopic <роль>\n"
                           "Роли: " + ", ".join(ROLES) + "\n(General настраивать не нужно.)")
        return
    DATA["topics"].setdefault(str(m.chat_id), {})[role] = th
    save()
    await m.reply_text(f"✅ Тема привязана: {ROLE_NAMES[role]} (id {th})")


async def cmd_topics(update, context):
    if not await is_admin(context.bot, update.effective_user.id):
        return
    t = DATA["topics"].get(str(HUB_ID), {})
    lines = ["🧭 Привязанные темы:"] + [f"• {ROLE_NAMES[r]}: {t.get(r, '— не привязана')}" for r in ROLES]
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_id(update, context):
    m = update.effective_message
    th = m.message_thread_id if m.is_topic_message else None
    await m.reply_text(f"chat_id: {m.chat_id}\nthread_id: {th}")


async def cmd_postguide(update, context):
    m = update.message
    if not await is_admin(context.bot, update.effective_user.id):
        return
    await safe_delete(m)
    sent = await say(context.bot, m, guide_text(place(m)[3]))
    try:
        await context.bot.pin_chat_message(m.chat_id, sent.message_id, disable_notification=True)
    except Exception as e:
        print("pin error:", e)


async def cmd_postrules(update, context):
    m = update.message
    if not await is_admin(context.bot, update.effective_user.id):
        return
    await safe_delete(m)
    sent = await say(context.bot, m, rules_text(place(m)[3]))
    try:
        await context.bot.pin_chat_message(m.chat_id, sent.message_id, disable_notification=True)
    except Exception as e:
        print("pin error:", e)


# ============================ ХЕШТЕГИ ============================
def allowed_here(feature, cid, role):
    if not CHATS.get(cid, {}).get("forum"):
        return True
    roles = FEATURE_ROLES[feature]
    bound = DATA["topics"].get(str(cid), {})
    if not any(r in bound for r in roles):
        return True
    return role in roles


async def gate(m, context, feature, cid, role, lang):
    if allowed_here(feature, cid, role):
        return True
    names = " / ".join(ROLE_NAMES[r] for r in FEATURE_ROLES[feature])
    tag = {"edit": "#edit", "review": "#review", "duel": "#duel"}[feature]
    await notice_m(context.bot, m, L(lang, f"{tag} работает в темах: {names}",
                                     f"{tag} works in topics: {names}"), 15)
    return False


def vote_kb(key, up, down):
    return Kb([[Btn(f"🔥 {up}", callback_data=f"v|up|{key}"),
                Btn(f"👎 {down}", callback_data=f"v|down|{key}")]])


async def on_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m or not m.from_user or m.from_user.is_bot or m.sender_chat:
        return
    text = m.text or m.caption or ""
    cid, th, role, lang = place(m)
    if HT_DUEL.search(text):
        if await gate(m, context, "duel", cid, role, lang):
            await handle_duel_sub(m, context)
        return
    if HT_REVIEW.search(text) and await gate(m, context, "review", cid, role, lang):
        await handle_review(m, context, lang)
    if HT_EDIT.search(text) and await gate(m, context, "edit", cid, role, lang):
        await handle_edit(m, context, lang)


async def handle_edit(m, context, lang):
    if not has_content(m):
        return
    u = m.from_user
    key = f"{m.chat_id}:{m.message_id}"
    try:
        await m.reply_text(L(lang, "🎥 Эдит участвует в конкурсе! Голосуй 👇", "🎥 Edit entered the contest! Vote 👇"),
                           reply_markup=vote_kb(key, 0, 0))
    except Exception as e:
        print("contest error:", e)
        return
    DATA["edits"][key] = {"author_id": u.id, "name": u.full_name, "up": [], "down": [],
                          "ts": time.time(), "chat": m.chat_id}
    get_user(u.id, u.full_name, u.username)["edits"] += 1
    DATA["stats"]["edits"] += 1
    save()
    await refresh_rank(context.bot, u.id)


def edit_cid(e):
    return e.get("chat", OLD_ID)


def edit_mid(key):
    return int(key.split(":")[-1])


async def on_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        _, kind, key = q.data.split("|", 2)
    except ValueError:
        await q.answer()
        return
    lang = ulang(q.from_user.id) or place(q.message)[3]
    e = DATA["edits"].get(key)
    if not e:
        await q.answer(L(lang, "Голосование закрыто.", "Voting is closed."), show_alert=True)
        return
    uid = q.from_user.id
    if uid == e["author_id"]:
        await q.answer(L(lang, "За свой эдит голосовать нельзя 😏", "You can't vote for your own edit 😏"),
                       show_alert=True)
        return
    author = get_user(e["author_id"], e["name"])
    other = "down" if kind == "up" else "up"
    if uid in e[kind]:
        e[kind].remove(uid)
        if kind == "up":
            author["fire"] = max(0, author["fire"] - 1)
        msg = L(lang, "Голос убран", "Vote removed")
    else:
        e[kind].append(uid)
        DATA["stats"]["votes"] += 1
        if kind == "up":
            author["fire"] += 1
        if uid in e[other]:
            e[other].remove(uid)
            if other == "up":
                author["fire"] = max(0, author["fire"] - 1)
        msg = L(lang, "Голос принят ✅", "Vote counted ✅")
    save()
    try:
        await q.edit_message_reply_markup(vote_kb(key, len(e["up"]), len(e["down"])))
    except BadRequest:
        pass
    await q.answer(msg)
    await refresh_rank(context.bot, e["author_id"])


async def handle_review(m, context, lang):
    if not has_content(m):
        return
    u = m.from_user
    kb = Kb([[Btn(L(lang, "🛠 Что улучшить", "🛠 What to improve"), callback_data="rv|tip"),
              Btn(L(lang, "✅ Фидбек получен", "✅ Feedback received"), callback_data=f"rv|done|{u.id}")]])
    try:
        await m.reply_text(L(lang,
                             "🔍 <b>Запрос фидбека!</b>\nОтветь реплаем на эту работу своей критикой: что зашло, что улучшить 🤝",
                             "🔍 <b>Feedback request!</b>\nReply to this work with your critique: what worked, what to improve 🤝"),
                           parse_mode=HTML, reply_markup=kb)
        DATA["stats"]["reviews"] += 1
        save()
    except Exception as e:
        print("review error:", e)


async def on_review_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split("|")
    lang = ulang(q.from_user.id) or place(q.message)[3]
    if parts[1] == "tip":
        await q.answer(L(lang, "Смотри: тайминг, переходы, цвет, шрифты, звук, вайб. Пиши конкретно.",
                         "Check: timing, transitions, color, fonts, sound, vibe. Be specific."), show_alert=True)
        return
    if parts[1] == "done":
        if q.from_user.id != int(parts[2]) and not await is_admin(context.bot, q.from_user.id):
            await q.answer(L(lang, "Закрыть может только автор.", "Only the author can close it."), show_alert=True)
            return
        await safe_edit(q, L(lang, "✅ <b>Ревью закрыто.</b> Спасибо за фидбек!", "✅ <b>Review closed.</b> Thanks for the feedback!"))
        await q.answer()


# ============================ КОНКУРС НЕДЕЛИ ============================
def top_lines(items, lang, n=3):
    medals = ["🥇", "🥈", "🥉"]
    out = []
    for i, (k, e) in enumerate(items[:n]):
        score = len(e["up"]) - len(e["down"])
        out.append(f'{medals[i]} <a href="{post_link(edit_cid(e), edit_mid(k))}">{esc(e["name"])}</a> — '
                   f'{score} (🔥 {len(e["up"])} / 👎 {len(e["down"])})')
    return out

async def announce_winner(bot):
    items = list(DATA["edits"].items())
    if not items:
        for cid in CHATS:
            lang = lang_of(cid, "announce")
            try:
                await send_to(bot, cid, "announce", L(lang, "На этой неделе эдитов в конкурсе не было 😴",
                                                      "No edits in the contest this week 😴"))
            except Exception as e:
                print("announce error:", e)
        return
    items.sort(key=lambda x: (len(x[1]["up"]) - len(x[1]["down"]), len(x[1]["up"])), reverse=True)
    DATA["stats"]["contests"] += 1
    key, top = items[0]
    top_score = len(top["up"]) - len(top["down"])
    old = DATA.get("winner_uid")
    has_winner = top_score > 0
    if has_winner:
        get_user(top["author_id"], top["name"])["wins"] += 1
        DATA["hall"].append({"date": now_local().strftime("%d.%m.%Y"), "uid": top["author_id"],
                             "name": top["name"], "score": top_score, "up": len(top["up"]),
                             "link": post_link(edit_cid(top), edit_mid(key))})
        DATA["winner_uid"] = top["author_id"]
    snapshot = list(items)
    DATA["edits"] = {}
    save()
    for cid in CHATS:
        lang = lang_of(cid, "announce")
        lines = ["🏆 " + L(lang, "<b>Итоги недели!</b>", "<b>Weekly results!</b>"), ""] + top_lines(snapshot, lang)
        if has_winner:
            lines.append("\n👑 " + L(lang, f"Победитель недели — {mention(top['author_id'], top['name'])}! Тег «{WINNER_TAG_RU}» у него.",
                                    f"Winner of the week — {mention(top['author_id'], top['name'])}! They get the “{WINNER_TAG_EN}” tag."))
        else:
            lines.append("\n" + L(lang, "Голосов маловато — победителя нет.", "Not enough votes — no winner this week."))
        lines.append("\n" + L(lang, "Новый конкурс начался — кидай эдиты с #edit 🔥", "A new contest has started — post edits with #edit 🔥"))
        try:
            sent = await send_to(bot, cid, "announce", "\n".join(lines))
            await bot.pin_chat_message(cid, sent.message_id, disable_notification=True)
        except Exception as e:
            print("announce/pin error:", e)
    if old and old != DATA.get("winner_uid"):
        await apply_tag(bot, old)
    if DATA.get("winner_uid"):
        await apply_tag(bot, DATA["winner_uid"])


async def cmd_winner(update, context):
    if await is_admin(context.bot, update.effective_user.id):
        await safe_delete(update.effective_message)
        await announce_winner(context.bot)


async def cmd_contest(update, context):
    lang = cl(update)
    items = sorted(DATA["edits"].items(), key=lambda x: len(x[1]["up"]) - len(x[1]["down"]), reverse=True)
    if not items:
        await say(context.bot, update.effective_message,
                  L(lang, "Пока нет эдитов. Кидай с хештегом #edit 🎥", "No edits yet. Post with #edit 🎥"))
        return
    lines = ["📊 " + L(lang, "<b>Топ эдитов недели:</b>", "<b>Top edits of the week:</b>"), ""] + top_lines(items, lang, 3)
    await say(context.bot, update.effective_message, "\n".join(lines))


# ============================ СТАТИСТИКА ============================
async def cmd_stats(update, context):
    lang = cl(update)
    s = DATA["stats"]
    refs = sum(u.get("refs", 0) for u in DATA["users"].values())
    ru = ("📊 <b>Статистика KAMLY HUB</b>\n\n"
          f"🎬 Эдитов в конкурсе: <b>{s['edits']}</b>\n🗳 Голосов: <b>{s['votes']}</b>\n"
          f"🏆 Конкурсов: <b>{s['contests']}</b>\n⚔️ Дуэлей: <b>{s['duels']}</b>\n"
          f"🎭 Анонимных эдитов: <b>{s['anon']}</b> (оценок {s['ratings']}, комментариев {s['comments']})\n"
          f"🔍 Запросов #review: <b>{s['reviews']}</b>\n🤝 Приглашено по реф. ссылкам: <b>{refs}</b>\n\n"
          f"🛡 Ссылок удалено: <b>{s['links']}</b>\n🚫 Банов: <b>{s['bans']}</b>\n"
          f"🔇 Мутов: <b>{s['mutes']}</b>\n⚠️ Предупреждений: <b>{s['warns']}</b>")
    en = ("📊 <b>KAMLY HUB stats</b>\n\n"
          f"🎬 Contest edits: <b>{s['edits']}</b>\n🗳 Votes: <b>{s['votes']}</b>\n"
          f"🏆 Contests: <b>{s['contests']}</b>\n⚔️ Duels: <b>{s['duels']}</b>\n"
          f"🎭 Anonymous edits: <b>{s['anon']}</b> (ratings {s['ratings']}, comments {s['comments']})\n"
          f"🔍 #review requests: <b>{s['reviews']}</b>\n🤝 Invited via referral links: <b>{refs}</b>\n\n"
          f"🛡 Links removed: <b>{s['links']}</b>\n🚫 Bans: <b>{s['bans']}</b>\n"
          f"🔇 Mutes: <b>{s['mutes']}</b>\n⚠️ Warnings: <b>{s['warns']}</b>")
    await say(context.bot, update.effective_message, L(lang, ru, en))


async def cmd_top(update, context):
    lang = cl(update)
    arr = ranking()[:10]
    if not arr:
        await say(context.bot, update.effective_message,
                  L(lang, "Рейтинг пока пуст. Кидай эдиты с #edit 🎥", "Leaderboard is empty. Post edits with #edit 🎥"))
        return
    nums = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = ["🏅 " + L(lang, "<b>Топ креаторов за всё время</b>", "<b>All-time top creators</b>"), ""]
    for i, (k, u) in enumerate(arr):
        lines.append(f"{nums[i]} {esc(u['name'])} — 🔥 {u['fire']} · {rname(rank_idx(u['fire']), 'en' if lang == 'en' else 'ru').split(' (')[0]} · 🏆 {u['wins']}")
    await say(context.bot, update.effective_message, "\n".join(lines))


def profile_text(uid, lang, tg_user=None):
    d = get_user(uid, getattr(tg_user, "full_name", None), getattr(tg_user, "username", None))
    ri = rank_idx(d["fire"])
    arr = ranking()
    place_n = next((i + 1 for i, (k, _) in enumerate(arr) if k == str(uid)), None)
    out = [f"👤 <b>{esc(d['name'])}</b>",
           lab(lang, "🏅", "Ранг", "Rank") + f"<b>{rname(ri, lang)}</b>",
           lab(lang, "🔥", "Огоньков", "Fire") + f"<b>{d['fire']}</b>",
           lab(lang, "🎬", "Эдитов", "Edits") + f"<b>{d['edits']}</b>",
           lab(lang, "🏆", "Побед в конкурсах", "Contest wins") + f"<b>{d['wins']}</b>",
           lab(lang, "⚔️", "Побед в дуэлях", "Duel wins") + f"<b>{d.get('duel_wins', 0)}</b>",
           lab(lang, "🤝", "Приглашено", "Invited") + f"<b>{d.get('refs', 0)}</b>",
           lab(lang, "📍", "Место в рейтинге", "Leaderboard place") + f"<b>{place_n or '—'}</b>"]
    if ri + 1 < len(RANKS):
        nxt = RANKS[ri + 1]
        out.append("\n" + L(lang, f"⬆️ До ранга «{nxt[1]}»: ещё {nxt[0] - d['fire']} 🔥",
                            f"⬆️ To rank “{nxt[2]}”: {nxt[0] - d['fire']} more 🔥"))
    else:
        out.append("\n" + L(lang, "👑 Максимальный ранг!", "👑 Max rank!"))
    return "\n".join(out)


async def cmd_me(update, context):
    tu = update.effective_user
    await say(context.bot, update.effective_message, profile_text(tu.id, cl(update), tu))


async def cmd_hall(update, context):
    lang = cl(update)
    hall = DATA["hall"][-15:][::-1]
    if not hall:
        await say(context.bot, update.effective_message,
                  L(lang, "🏛 Зал славы пока пуст.", "🏛 Hall of fame is empty so far."))
        return
    lines = ["🏛 " + L(lang, "<b>Зал славы KAMLY HUB</b>", "<b>KAMLY HUB Hall of Fame</b>"), ""]
    for h in hall:
        lines.append(f'👑 {h["date"]} — <a href="{h["link"]}">{esc(h["name"])}</a> (🔥 {h["up"]})')
    await say(context.bot, update.effective_message, "\n".join(lines))


def ranks_text(lang):
    lines = ["🏅 " + L(lang, "<b>Система рангов KAMLY HUB ⛓️</b>", "<b>KAMLY HUB rank system ⛓️</b>"), ""]
    for i, r in enumerate(RANKS):
        hi = RANKS[i + 1][0] - 1 if i + 1 < len(RANKS) else None
        rng = f"{r[0]}–{hi}" if hi is not None else f"{r[0]}+"
        lines.append(f"<b>{rng} 🔥 | {rname(i, lang)}</b>\n{L(lang, r[3], r[4])}\n")
    return "\n".join(lines)


async def cmd_ranks(update, context):
    await say(context.bot, update.effective_message, ranks_text(cl(update)))


# ============================ ЧЕЛЛЕНДЖ ============================
def challenge_text(c, lang):
    g = GENRES[c["g"]]
    style = g["styles"][c["s"] % len(g["styles"])]
    ln = LENGTHS[c["len"] % len(LENGTHS)]
    ru = (f"⚡ <b>ЧЕЛЛЕНДЖ НЕДЕЛИ</b>\n\n🎨 Стиль: <b>{style[0]}</b>\n⏱ Длина: <b>{ln[0]}</b>\n"
          f"🎧 Жанр: <b>{g['title']}</b> — {g['vibe'][0]}\n")
    en = (f"⚡ <b>WEEKLY CHALLENGE</b>\n\n🎨 Style: <b>{style[1]}</b>\n⏱ Length: <b>{ln[1]}</b>\n"
          f"🎧 Genre: <b>{g['title']}</b> — {g['vibe'][1]}\n")
    if c.get("track"):
        ru += f"🎵 Трек: <b>{esc(c['track'])}</b>\n"
        en += f"🎵 Track: <b>{esc(c['track'])}</b>\n"
    ru += f"\nКидай эдит с <code>#edit</code> до воскресенья {CONTEST_HOUR}:00 — тег «{WINNER_TAG_RU}» ждёт лучшего 🔥"
    en += f"\nPost your edit with <code>#edit</code> before Sunday {CONTEST_HOUR}:00 — the “{WINNER_TAG_EN}” tag awaits the best 🔥"
    return L(lang, ru, en)


async def post_challenge(bot):
    tracks = DATA["tracks"]
    genres = list({t["genre"] for t in tracks if t["genre"] in GENRES}) or list(GENRES)
    gk = random.choice(genres)
    track = None
    pool = [t for t in tracks if t["genre"] == gk]
    if pool:
        track = random.choice(pool)
    c = {"g": gk, "s": random.randint(0, 9), "len": random.randint(0, 9),
         "track": track["title"] if track else None, "file_id": track["file_id"] if track else None}
    DATA["challenge"] = c
    save()
    for cid in CHATS:
        lang = lang_of(cid, "duels")
        text = challenge_text(c, lang)
        try:
            th = DATA["topics"].get(str(cid), {}).get("duels")
            kw = {"message_thread_id": th} if th else {}
            if track:
                sent = await bot.send_audio(cid, track["file_id"], caption=text, parse_mode=HTML, **kw)
            else:
                sent = await send_to(bot, cid, "duels", text)
            await bot.pin_chat_message(cid, sent.message_id, disable_notification=True)
        except Exception as e:
            print("challenge error:", e)


async def cmd_challenge(update, context):
    lang = cl(update)
    c = DATA.get("challenge")
    await say(context.bot, update.effective_message,
              challenge_text(c, lang) if c else L(lang, "Челлендж выходит каждый понедельник ⚡",
                                                  "The challenge drops every Monday ⚡"))


async def cmd_newchallenge(update, context):
    if await is_admin(context.bot, update.effective_user.id):
        await safe_delete(update.effective_message)
        await post_challenge(context.bot)


# ============================ ДУЭЛИ ============================
BUSY = ("pending", "setup", "active", "voting")


def duel_busy(uid):
    return any(d["state"] in BUSY and uid in (d["a"]["id"], d["b"]["id"]) for d in DATA["duels"].values())


def duel_names(d):
    return f"{mention(d['a']['id'], d['a']['name'])} 🆚 {mention(d['b']['id'], d['b']['name'])}"

def duel_kb(did):
    d = DATA["duels"][did]
    lang = d.get("lang", "ru")
    end_btn = Btn(L(lang, f"🤝 Завершить досрочно ({len(d.get('end', []))}/2)",
                    f"🤝 End early ({len(d.get('end', []))}/2)"), callback_data=f"de|{did}")
    if d["state"] == "voting":
        na, nb = len(d["votes"]["a"]), len(d["votes"]["b"])
        return Kb([[Btn(f"🅰 {d['a']['name'][:12]} · {na}", callback_data=f"dv|a|{did}"),
                    Btn(f"🅱 {d['b']['name'][:12]} · {nb}", callback_data=f"dv|b|{did}")], [end_btn]])
    return Kb([[end_btn]])


def track_kb(did, page):
    lang = DATA["duels"][did].get("lang", "ru")
    tr, per = DATA["tracks"], 6
    rows = []
    for i, t in enumerate(tr[page * per:(page + 1) * per]):
        rows.append([Btn("🎵 " + t["title"][:40], callback_data=f"dt|{did}|{page * per + i}")])
    nav = []
    if page > 0:
        nav.append(Btn("◀️", callback_data=f"dp|{did}|{page - 1}"))
    if (page + 1) * per < len(tr):
        nav.append(Btn("▶️", callback_data=f"dp|{did}|{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([Btn("🎲 Random", callback_data=f"dt|{did}|r"),
                 Btn(L(lang, "🆓 Любой трек", "🆓 Any track"), callback_data=f"dt|{did}|f")])
    return Kb(rows)


def style_kb(did):
    lang = DATA["duels"][did].get("lang", "ru")
    rows, row = [], []
    for i, s in enumerate(DUEL_STYLES):
        row.append(Btn(L(lang, s[0], s[1]) if lang != "bi" else s[1] if s[0] == s[1] else f"{s[0]} / {s[1]}",
                       callback_data=f"ds|{did}|{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Btn("🎲 Random", callback_data=f"ds|{did}|r")])
    return Kb(rows)


async def cmd_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m:
        return
    cid, th, role, lang = place(m)
    if not allowed_here("duel", cid, role):
        await gate(m, context, "duel", cid, role, lang)
        return
    a = m.from_user
    opp, theme = None, ""
    r = real_reply(m)
    if r and r.from_user and not r.from_user.is_bot:
        opp = (r.from_user.id, r.from_user.full_name)
    else:
        for e in m.entities or []:
            if e.type == "text_mention" and e.user and not e.user.is_bot:
                opp = (e.user.id, e.user.full_name)
        if not opp and context.args and context.args[0].startswith("@"):
            uid = DATA["known"].get(context.args[0][1:].lower())
            if uid:
                opp = (uid, DATA["users"][str(uid)]["name"])
    if not opp:
        await m.reply_text(L(lang,
                             "⚔️ Вызови соперника: <code>/duel @ник</code> или ответь командой на его сообщение.\n"
                             "Если бот не знает ник — соперник должен хоть раз написать в чат.",
                             "⚔️ Challenge someone: <code>/duel @name</code> or reply to their message.\n"
                             "If the bot doesn't know the name — they must write in the chat once."),
                           parse_mode=HTML)
        return
    if opp[0] == a.id:
        await m.reply_text(L(lang, "С самим собой драться нельзя 😏", "You can't duel yourself 😏"))
        return
    if duel_busy(a.id) or duel_busy(opp[0]):
        await m.reply_text(L(lang, "Один из вас уже в дуэли. Дождитесь конца или завершите досрочно.",
                             "One of you is already in a duel. Wait for it to end or finish it early."))
        return
    DATA["counters"]["duel"] += 1
    did = str(DATA["counters"]["duel"])
    d = {"a": {"id": a.id, "name": a.full_name}, "b": {"id": opp[0], "name": opp[1]},
         "state": "pending", "created": time.time(), "subs": {}, "votes": {"a": [], "b": []},
         "end": [], "chat": cid, "thread": th, "lang": lang, "track": None, "style": None}
    kb = Kb([[Btn(L(lang, "✅ Принять", "✅ Accept"), callback_data=f"d|acc|{did}"),
              Btn(L(lang, "❌ Отказаться", "❌ Decline"), callback_data=f"d|dec|{did}")]])
    sent = await m.reply_text(
        f"⚔️ <b>{L(lang, 'Вызов на дуэль', 'Duel challenge')} #{did}!</b>\n"
        + L(lang, f"{mention(a.id, a.full_name)} вызывает {mention(opp[0], opp[1])}.\nУ соперника есть час, чтобы принять.",
            f"{mention(a.id, a.full_name)} challenges {mention(opp[0], opp[1])}.\nThey have one hour to accept."),
        parse_mode=HTML, reply_markup=kb)
    d["msg_id"] = sent.message_id
    DATA["duels"][did] = d
    save()


async def on_duel_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, act, did = q.data.split("|")
    d = DATA["duels"].get(did)
    lang = (d or {}).get("lang", "ru")
    if not d or d["state"] != "pending":
        await q.answer(L(lang, "Вызов уже неактуален.", "This challenge is no longer valid."), show_alert=True)
        return
    if q.from_user.id != d["b"]["id"]:
        await q.answer(L(lang, "Это вызов не для тебя 🙂", "This challenge isn't for you 🙂"), show_alert=True)
        return
    if act == "dec":
        d["state"], d["ended"] = "cancelled", time.time()
        save()
        await safe_edit(q, f"❌ {esc(d['b']['name'])} " + L(lang, f"отказался от дуэли #{did}.", f"declined duel #{did}."))
        await q.answer()
        return
    d["state"], d["setup_ts"] = "setup", time.time()
    save()
    await q.answer()
    head = f"⚔️ <b>{L(lang, 'Дуэль', 'Duel')} #{did}</b>\n{duel_names(d)}\n\n"
    if DATA["tracks"]:
        await safe_edit(q, head + L(lang, "🎵 <b>Шаг 1/2:</b> выберите трек для эдита (любой из дуэлянтов).",
                                    "🎵 <b>Step 1/2:</b> pick the track for the edit (either duelist)."), track_kb(did, 0))
    else:
        d["track"] = "free"
        await safe_edit(q, head + L(lang, "🎨 <b>Выберите стиль эдита</b> (любой из дуэлянтов):",
                                    "🎨 <b>Pick the edit style</b> (either duelist):"), style_kb(did))


async def on_duel_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    kind, did, val = q.data.split("|")
    d = DATA["duels"].get(did)
    lang = (d or {}).get("lang", "ru")
    if not d or d["state"] != "setup":
        await q.answer(L(lang, "Уже неактуально.", "No longer valid."), show_alert=True)
        return
    if q.from_user.id not in (d["a"]["id"], d["b"]["id"]):
        await q.answer(L(lang, "Выбирают только участники дуэли.", "Only duelists can choose."), show_alert=True)
        return
    head = f"⚔️ <b>{L(lang, 'Дуэль', 'Duel')} #{did}</b>\n{duel_names(d)}\n\n"
    if kind == "dp":
        try:
            await q.edit_message_reply_markup(track_kb(did, int(val)))
        except BadRequest:
            pass
        await q.answer()
        return
    if kind == "dt":
        if val == "f":
            d["track"] = "free"
        else:
            tr = DATA["tracks"]
            if not tr:
                d["track"] = "free"
            else:
                idx = random.randrange(len(tr)) if val == "r" else int(val)
                if idx >= len(tr):
                    await q.answer("?", show_alert=True)
                    return
                d["track"] = {"title": tr[idx]["title"], "file_id": tr[idx]["file_id"]}
        save()
        await q.answer()
        await safe_edit(q, head + L(lang, "🎨 <b>Шаг 2/2:</b> выберите стиль эдита:", "🎨 <b>Step 2/2:</b> pick the edit style:"),
                        style_kb(did))
        return
    if kind == "ds":
        idx = random.randrange(len(DUEL_STYLES)) if val == "r" else int(val)
        d["style"] = list(DUEL_STYLES[idx])
        await q.answer()
        await start_duel(context.bot, did)


async def start_duel(bot, did):
    d = DATA["duels"][did]
    lang = d.get("lang", "ru")
    d["state"] = "active"
    d["deadline"] = time.time() + DUEL_HOURS * 3600
    save()
    tr = d.get("track")
    track_ru = tr["title"] if isinstance(tr, dict) else "любой / свободный выбор"
    track_en = tr["title"] if isinstance(tr, dict) else "any / free choice"
    st = d["style"]
    text = (f"⚔️ <b>{L(lang, 'Дуэль', 'Duel')} #{did} {L(lang, 'началась!', 'has started!')}</b>\n\n{duel_names(d)}\n"
            + L(lang, f"🎵 Трек: <b>{esc(track_ru)}</b>\n🎨 Стиль: <b>{st[0]}</b>\n⏳ Дедлайн: <b>{fmt_ts(d['deadline'])}</b>\n\n"
                      "Кидайте эдит в чат с хештегом <code>#duel</code>. Когда оба эдита будут готовы — откроется голосование.",
                f"🎵 Track: <b>{esc(track_en)}</b>\n🎨 Style: <b>{st[1]}</b>\n⏳ Deadline: <b>{fmt_ts(d['deadline'])}</b>\n\n"
                "Post your edit in the chat with <code>#duel</code>. When both edits are in, voting opens."))
    await edit_by_id(bot, d["chat"], d["msg_id"], text, duel_kb(did))
    if isinstance(tr, dict):
        try:
            kw = {"message_thread_id": d["thread"]} if d.get("thread") else {}
            await bot.send_audio(d["chat"], tr["file_id"], caption="🎵 " + tr["title"], **kw)
        except Exception as e:
            print("duel audio error:", e)


async def handle_duel_sub(m, context):
    uid = m.from_user.id
    for did, d in DATA["duels"].items():
        if d["state"] == "active" and uid in (d["a"]["id"], d["b"]["id"]) and d.get("chat", OLD_ID) == m.chat_id:
            if not has_content(m):
                return
            lang = d.get("lang", "ru")
            d["subs"][str(uid)] = m.message_id
            save()
            if len(d["subs"]) == 2:
                await start_voting(context.bot, did)
            else:
                await m.reply_text(L(lang, "✅ Эдит для дуэли принят! Ждём соперника.", "✅ Duel edit received! Waiting for the opponent."))
            return


async def start_voting(bot, did):
    d = DATA["duels"][did]
    lang = d.get("lang", "ru")
    d["state"] = "voting"
    d["vote_deadline"] = time.time() + DUEL_VOTE_HOURS * 3600
    d["end"] = []
    la = post_link(d["chat"], d["subs"][str(d["a"]["id"])])
    lb = post_link(d["chat"], d["subs"][str(d["b"]["id"])])
    st = d.get("style") or ["", ""]
    text = (f"🗳 <b>{L(lang, 'Голосование дуэли', 'Duel voting')} #{did}</b>\n🎨 {L(lang, st[0], st[1])}\n\n"
            f'🅰 {esc(d["a"]["name"])} — <a href="{la}">{L(lang, "эдит", "edit")}</a>\n'
            f'🅱 {esc(d["b"]["name"])} — <a href="{lb}">{L(lang, "эдит", "edit")}</a>\n\n'
            + L(lang, f"Голосование до <b>{fmt_ts(d['vote_deadline'])}</b>. Участникам голосовать нельзя.",
                f"Voting until <b>{fmt_ts(d['vote_deadline'])}</b>. Duelists can't vote."))
    kw = {"message_thread_id": d["thread"]} if d.get("thread") else {}
    sent = await bot.send_message(d["chat"], text, parse_mode=HTML, link_preview_options=NOPREV,
                                  reply_markup=duel_kb(did), **kw)
    d["vote_msg"] = sent.message_id
    save()

async def on_duel_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, side, did = q.data.split("|")
    d = DATA["duels"].get(did)
    lang = (d or {}).get("lang", "ru")
    if not d or d["state"] != "voting":
        await q.answer(L(lang, "Голосование закрыто.", "Voting is closed."), show_alert=True)
        return
    uid = q.from_user.id
    if uid in (d["a"]["id"], d["b"]["id"]):
        await q.answer(L(lang, "Участники дуэли не голосуют 😏", "Duelists can't vote 😏"), show_alert=True)
        return
    other = "b" if side == "a" else "a"
    if uid in d["votes"][side]:
        d["votes"][side].remove(uid)
        msg = L(lang, "Голос убран", "Vote removed")
    else:
        d["votes"][side].append(uid)
        if uid in d["votes"][other]:
            d["votes"][other].remove(uid)
        msg = L(lang, "Голос принят ✅", "Vote counted ✅")
    save()
    try:
        await q.edit_message_reply_markup(duel_kb(did))
    except BadRequest:
        pass
    await q.answer(msg)


async def on_duel_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    did = q.data.split("|")[1]
    d = DATA["duels"].get(did)
    lang = (d or {}).get("lang", "ru")
    if not d or d["state"] not in ("active", "voting"):
        await q.answer(L(lang, "Дуэль уже завершена.", "The duel is already over."), show_alert=True)
        return
    uid = q.from_user.id
    if uid not in (d["a"]["id"], d["b"]["id"]):
        await q.answer(L(lang, "Только участники дуэли.", "Duelists only."), show_alert=True)
        return
    d.setdefault("end", [])
    if uid in d["end"]:
        await q.answer(L(lang, "Ты уже согласился. Ждём соперника.", "You already agreed. Waiting for the opponent."), show_alert=True)
        return
    d["end"].append(uid)
    save()
    if len(d["end"]) >= 2:
        await q.answer(L(lang, "Дуэль завершена по согласию.", "Duel ended by mutual agreement."))
        if d["state"] == "voting":
            await finish_duel(context.bot, did, early=True)
        else:
            d["state"], d["ended"] = "cancelled", time.time()
            save()
            await edit_by_id(context.bot, d["chat"], d["msg_id"],
                             f"🤝 <b>{L(lang, 'Дуэль', 'Duel')} #{did}</b>: "
                             + L(lang, "завершена досрочно по согласию обоих эдиторов.", "ended early by mutual agreement of both editors."))
        return
    try:
        await q.edit_message_reply_markup(duel_kb(did))
    except BadRequest:
        pass
    await q.answer(L(lang, "Согласие принято 1/2. Нужно согласие соперника.", "Agreement 1/2. The opponent must agree too."))


async def finish_duel(bot, did, walkover=None, early=False):
    d = DATA["duels"][did]
    lang = d.get("lang", "ru")
    na, nb = len(d["votes"]["a"]), len(d["votes"]["b"])
    if walkover:
        winner = d[walkover]
        res = "🏆 " + L(lang, f"Победа по неявке соперника: {mention(winner['id'], winner['name'])}!",
                        f"Win by forfeit: {mention(winner['id'], winner['name'])}!")
    elif na == nb:
        winner = None
        res = "🤝 " + L(lang, "Ничья! Оба молодцы.", "Draw! Both did great.")
    else:
        winner = d["a"] if na > nb else d["b"]
        res = "🏆 " + L(lang, f"Победитель: {mention(winner['id'], winner['name'])}!", f"Winner: {mention(winner['id'], winner['name'])}!")
    if winner:
        get_user(winner["id"], winner["name"])["duel_wins"] += 1
    d["state"], d["ended"] = "done", time.time()
    DATA["stats"]["duels"] += 1
    save()
    if d.get("vote_msg"):
        try:
            await bot.edit_message_reply_markup(d["chat"], d["vote_msg"], reply_markup=None)
        except Exception:
            pass
    extra = L(lang, "\n(завершена досрочно по согласию)", "\n(ended early by agreement)") if early else ""
    kw = {"message_thread_id": d["thread"]} if d.get("thread") else {}
    await bot.send_message(d["chat"], f"⚔️ <b>{L(lang, 'Итоги дуэли', 'Duel results')} #{did}</b>\n\n"
                                      f"{esc(d['a']['name'])} — 🔥 {na}\n{esc(d['b']['name'])} — 🔥 {nb}\n\n{res}{extra}",
                           parse_mode=HTML, link_preview_options=NOPREV, **kw)


async def duels_tick(bot):
    now = time.time()
    for did, d in list(DATA["duels"].items()):
        st, lang = d["state"], d.get("lang", "ru")
        cid = d.get("chat", OLD_ID)
        try:
            if st == "pending" and now > d["created"] + 3600:
                d["state"], d["ended"] = "cancelled", now
                save()
                await edit_by_id(bot, cid, d["msg_id"], f"⌛ " + L(lang, f"Дуэль #{did} не принята вовремя.", f"Duel #{did} wasn't accepted in time."))
            elif st == "setup" and now > d.get("setup_ts", d["created"]) + 7200:
                d["state"], d["ended"] = "cancelled", now
                save()
                await edit_by_id(bot, cid, d["msg_id"], "⌛ " + L(lang, f"Дуэль #{did} отменена: не выбрали трек/стиль.", f"Duel #{did} cancelled: track/style not chosen."))
            elif st == "active" and now > d.get("deadline", now + 1):
                subs = d["subs"]
                if len(subs) == 1:
                    await finish_duel(bot, did, walkover="a" if str(d["a"]["id"]) in subs else "b")
                else:
                    d["state"], d["ended"] = "cancelled", now
                    save()
                    await edit_by_id(bot, cid, d["msg_id"], "⌛ " + L(lang, f"Дуэль #{did} отменена: никто не успел.", f"Duel #{did} cancelled: nobody made it."))
            elif st == "voting" and now > d.get("vote_deadline", now + 1):
                await finish_duel(bot, did)
            elif st in ("done", "cancelled") and now > d.get("ended", now) + 7 * 86400:
                del DATA["duels"][did]
                save()
        except Exception as e:
            print("duel tick error:", e)


async def cmd_endduel(update, context):
    if not await is_admin(context.bot, update.effective_user.id):
        return
    await safe_delete(update.effective_message)
    for did, d in list(DATA["duels"].items()):
        if d["state"] == "voting":
            await finish_duel(context.bot, did, early=True)


# ============================ АНОНИМНАЯ ОЦЕНКА ============================
def anon_avg(a):
    r = list(a["ratings"].values())
    return (sum(r) / len(r), len(r)) if r else (0, 0)


def anon_text(aid, a, lang):
    avg, n = anon_avg(a)
    star = L(lang, f"⭐ Средняя: <b>{avg:.1f}</b> ({n} оц.)", f"⭐ Average: <b>{avg:.1f}</b> ({n} ratings)") if n \
        else L(lang, "⭐ Оценок пока нет", "⭐ No ratings yet")
    return (f"🎬 <b>{L(lang, 'Анонимный эдит', 'Anonymous edit')} #{aid}</b>\n{star}\n\n"
            + L(lang, "Оцени от 1 до 10 👇\n💬 Комментарий: ответь реплаем — бот перешлёт его автору.",
                "Rate from 1 to 10 👇\n💬 Comment: reply to this message — the bot forwards it to the author."))


def anon_kb(aid, lang):
    rows = [[Btn(str(i), callback_data=f"r|{aid}|{i}") for i in range(1, 6)],
            [Btn(str(i), callback_data=f"r|{aid}|{i}") for i in range(6, 11)],
            [Btn(L(lang, "💬 Как комментировать", "💬 How to comment"), callback_data=f"rc|{aid}"),
             Btn("🗑", callback_data=f"rd|{aid}")]]
    return Kb(rows)


async def ask_edit(message, context, user):
    lang = ulang(user.id) or guess_lang(user)
    context.user_data["awaiting_edit"] = True
    await message.reply_text(L(lang,
                               "🎬 <b>Анонимная оценка эдита</b>\n\nПришли эдит: видео, гифку, фото или ссылку на TikTok-видео. "
                               "Я выложу его в чат без твоего имени, а оценки и комментарии пришлю сюда.\n\nОтмена: /cancel",
                               "🎬 <b>Anonymous edit rating</b>\n\nSend your edit: video, gif, photo or a TikTok video link. "
                               "I'll post it in the chat without your name and send ratings and comments here.\n\nCancel: /cancel"),
                             parse_mode=HTML)


async def submit_anon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m, u, bot = update.message, update.effective_user, context.bot
    lang = ulang(u.id) or guess_lang(u)
    last = DATA["anon_last"].get(str(u.id), 0)
    if time.time() - last < ANON_COOLDOWN:
        wait = int((ANON_COOLDOWN - (time.time() - last)) / 60) + 1
        await m.reply_text(L(lang, f"⏳ Подожди ещё ~{wait} мин.", f"⏳ Wait ~{wait} more min."))
        context.user_data["awaiting_edit"] = False
        return
    target = await member_chat(bot, u.id)
    if not target:
        link = CHATS[HUB_ID]["link"]
        await m.reply_text(L(lang, "Сначала вступи в чат KAMLY HUB 👇", "Join KAMLY HUB first 👇"),
                           reply_markup=Kb([[Btn("💬 KAMLY HUB", url=link)]]))
        return
    kinds = [classify(l) for l in extract_links(m)]
    if any(k != "ok" for k in kinds):
        await m.reply_text(L(lang, "❌ Чужие ссылки нельзя. Ссылка на TikTok-видео или файл — можно.",
                             "❌ Third-party links aren't allowed. TikTok video links or files are fine."))
        return
    text = m.text or m.caption or ""
    media = m.video or m.animation or m.photo or m.document or m.video_note
    if not media and not (m.text and URL_RE.search(text)):
        await m.reply_text(L(lang, "Пришли видео, гифку, фото или ссылку на TikTok-видео. Отмена: /cancel",
                             "Send a video, gif, photo or TikTok video link. Cancel: /cancel"))
        return
    clang = lang_of(target, "review")
    th = DATA["topics"].get(str(target), {}).get("review")
    kw = {"message_thread_id": th} if th else {}
    try:
        cm = await bot.copy_message(target, m.chat_id, m.message_id, **kw)
        DATA["counters"]["anon"] += 1
        aid = str(DATA["counters"]["anon"])
        a = {"author_id": u.id, "ts": time.time(), "ratings": {}, "msg_id": cm.message_id, "chat": target, "lang": clang}
        card = await bot.send_message(target, anon_text(aid, a, clang), parse_mode=HTML,
                                      reply_markup=anon_kb(aid, clang),
                                      reply_parameters=ReplyParameters(message_id=cm.message_id), **kw)
    except Exception as e:
        await m.reply_text(f"⚠️ {e}")
        return
    a["card_id"] = card.message_id
    DATA["anon"][aid] = a
    DATA["anon_msgs"][f"{target}:{cm.message_id}"] = aid
    DATA["anon_msgs"][f"{target}:{card.message_id}"] = aid
    DATA["anon_last"][str(u.id)] = time.time()
    DATA["stats"]["anon"] += 1
    save()
    context.user_data["awaiting_edit"] = False
    await m.reply_text(L(lang, f"✅ Эдит #{aid} анонимно отправлен в чат! Оценки и комментарии придут сюда.",
                         f"✅ Edit #{aid} was posted anonymously! Ratings and comments will arrive here."))

async def on_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, aid, score = q.data.split("|")
    a = DATA["anon"].get(aid)
    lang = ulang(q.from_user.id) or place(q.message)[3]
    if not a:
        await q.answer(L(lang, "Оценка закрыта.", "Rating closed."), show_alert=True)
        return
    uid = q.from_user.id
    if uid == a["author_id"]:
        await q.answer(L(lang, "Свой эдит оценивать нельзя 🙂", "You can't rate your own edit 🙂"), show_alert=True)
        return
    new = str(uid) not in a["ratings"]
    a["ratings"][str(uid)] = int(score)
    if new:
        DATA["stats"]["ratings"] += 1
    save()
    clang = a.get("lang", "ru")
    await safe_edit(q, anon_text(aid, a, clang), anon_kb(aid, clang))
    await q.answer(L(lang, f"Оценка {score}/10 принята ✅", f"Rating {score}/10 counted ✅"))
    avg, n = anon_avg(a)
    alang = ulang(a["author_id"]) or "ru"
    try:
        await context.bot.send_message(a["author_id"], L(alang,
                                       f"⭐ Твой эдит #{aid} получил оценку <b>{score}/10</b>\nСредняя: <b>{avg:.1f}</b> ({n} оц.)",
                                       f"⭐ Your edit #{aid} got <b>{score}/10</b>\nAverage: <b>{avg:.1f}</b> ({n} ratings)"),
                                       parse_mode=HTML)
    except Exception:
        pass


async def on_rate_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = ulang(update.callback_query.from_user.id) or "bi"
    await update.callback_query.answer(L(lang, "Ответь реплаем на этот эдит — бот перешлёт текст автору.",
                                         "Reply to this edit — the bot forwards your text to the author."), show_alert=True)


async def on_rate_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await is_admin(context.bot, q.from_user.id):
        await q.answer("Admins only", show_alert=True)
        return
    aid = q.data.split("|")[1]
    a = DATA["anon"].pop(aid, None)
    if a:
        cid = a.get("chat", OLD_ID)
        for mid in (a.get("msg_id"), a.get("card_id")):
            DATA["anon_msgs"].pop(f"{cid}:{mid}", None)
            DATA["anon_msgs"].pop(str(mid), None)
            try:
                await context.bot.delete_message(cid, mid)
            except Exception:
                pass
        save()
    await q.answer("OK")


async def on_reply_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m or not m.reply_to_message or not m.text or not m.from_user or m.from_user.is_bot:
        return
    rid = m.reply_to_message.message_id
    aid = DATA["anon_msgs"].get(f"{m.chat_id}:{rid}") or (DATA["anon_msgs"].get(str(rid)) if m.chat_id == OLD_ID else None)
    a = DATA["anon"].get(aid) if aid else None
    if not a or m.from_user.id == a["author_id"]:
        return
    alang = ulang(a["author_id"]) or "ru"
    try:
        await context.bot.send_message(a["author_id"], L(alang,
                                       f"💬 <b>Комментарий к эдиту #{aid}</b>\nот {esc(m.from_user.full_name)}:\n\n{esc(m.text)}",
                                       f"💬 <b>Comment on edit #{aid}</b>\nfrom {esc(m.from_user.full_name)}:\n\n{esc(m.text)}"),
                                       parse_mode=HTML)
        DATA["stats"]["comments"] += 1
        save()
        await notice_m(context.bot, m, L(place(m)[3], f"✅ Комментарий отправлен автору эдита #{aid}", f"✅ Comment sent to the author of edit #{aid}"), 8)
    except Exception as e:
        print("comment error:", e)


async def cmd_who(update, context):
    m = update.message
    if not await is_admin(context.bot, update.effective_user.id):
        return
    await safe_delete(m)
    r = real_reply(m)
    if not r:
        return
    aid = DATA["anon_msgs"].get(f"{m.chat_id}:{r.message_id}") or (DATA["anon_msgs"].get(str(r.message_id)) if m.chat_id == OLD_ID else None)
    a = DATA["anon"].get(aid) if aid else None
    if not a:
        return
    info = get_user(a["author_id"])
    try:
        await context.bot.send_message(update.effective_user.id,
                                       f"🕵️ #{aid}: {mention(a['author_id'], info['name'])} (id <code>{a['author_id']}</code>)",
                                       parse_mode=HTML)
    except Exception:
        pass


# ============================ ПАРТНЁРКА ============================
def ref_main_text(lang):
    ru = ("🤝 <b>ПАРТНЁРСКАЯ ПРОГРАММА KAMLY HUB</b>\n\n"
          "Хочешь не просто сидеть в KAMLY HUB, а качать наше комьюнити и расширять аудиторию андеграундных эдиторов? "
          "Залетай в реферальную программу!\n\n"
          "Приглашай единомышленников, занимай топ креаторов, забирай админки и эксклюзивные бонусы от основателя.\n\n"
          "👇 Получить свою персональную реферальную ссылку:")
    en = ("🤝 <b>KAMLY HUB PARTNER PROGRAM</b>\n\n"
          "Want to do more than sit in KAMLY HUB — grow our community and expand the audience of underground editors? "
          "Join the referral program!\n\n"
          "Invite like-minded people, climb the top creators, and win admin spots and exclusive bonuses from the founder.\n\n"
          "👇 Get your personal referral link:")
    return L(lang, ru, en)


def ref_kb(lang, back=True):
    rows = [[Btn(L(lang, "🔗 Сгенерировать ссылку", "🔗 Generate link"), callback_data="ref|gen")],
            [Btn(L(lang, "📊 Моя статистика", "📊 My stats"), callback_data="ref|stat"),
             Btn(L(lang, "🏆 Топ", "🏆 Top"), callback_data="ref|top")],
            [Btn(L(lang, "❓ Как пригласить больше людей?", "❓ How to invite more people?"), callback_data="ref|guide")]]
    if back:
        rows.append([Btn(L(lang, "◀️ Назад", "◀️ Back"), callback_data="m|main")])
    return Kb(rows)


async def get_ref_link(bot, uid):
    link = DATA["ref_links"].get(str(uid))
    if link:
        return link
    obj = await bot.create_chat_invite_link(REF_CHAT_ID, name=f"ref_{uid}"[:32])
    DATA["ref_links"][str(uid)] = obj.invite_link
    DATA["ref_owner"][obj.invite_link] = uid
    save()
    return obj.invite_link


def ref_place(uid):
    arr = sorted(((k, u) for k, u in DATA["users"].items() if u.get("refs", 0) > 0),
                 key=lambda x: x[1]["refs"], reverse=True)
    return next((i + 1 for i, (k, _) in enumerate(arr) if k == str(uid)), None)


def ref_stat_text(uid, lang):
    d = get_user(uid)
    joined = [k for k, o in DATA["ref_joined"].items() if o == uid][-5:]
    names = ", ".join(esc(DATA["users"].get(k, {}).get("name", k)) for k in reversed(joined)) or "—"
    return (L(lang, "📊 <b>Твоя реферальная статистика</b>", "📊 <b>Your referral stats</b>") + "\n\n"
            + lab(lang, "👥", "Пришло людей", "People joined") + f"<b>{d.get('refs', 0)}</b>\n"
            + lab(lang, "📍", "Место в топе", "Place in top") + f"<b>{ref_place(uid) or '—'}</b>\n"
            + lab(lang, "🔥", "Получено за рефералов", "Earned from referrals") + f"<b>{d.get('refs', 0) * REF_FIRE}</b>\n"
            + lab(lang, "🆕", "Последние", "Latest") + names)


def ref_top_text(lang):
    arr = sorted(((k, u) for k, u in DATA["users"].items() if u.get("refs", 0) > 0),
                 key=lambda x: x[1]["refs"], reverse=True)[:10]
    if not arr:
        return L(lang, "Пока никто никого не пригласил. Будь первым! 🔗", "Nobody has invited anyone yet. Be the first! 🔗")
    lines = ["🏆 " + L(lang, "<b>Топ пригласивших</b>", "<b>Top inviters</b>"), ""]
    for i, (k, u) in enumerate(arr, 1):
        lines.append(f"{i}. {esc(u['name'])} — {u['refs']}")
    return "\n".join(lines)


def ref_guide_text(lang, link):
    ru = ("❓ <b>Как пригласить больше людей</b>\n\n"
          "Твоя ссылка:\n" + link + "\n\n"
          "🎵 <b>TikTok</b>\n• Добавь ссылку в профиль (описание/поле ссылки, если доступно) и напиши «наш чат эдиторов — по ссылке в профиле».\n"
          "• Сними сторис/видео: «Хочешь оценку своих эдитов? Заходи в KAMLY HUB» и закрепи комментарий со ссылкой.\n"
          "• Отвечай на вопросы «где исходник / как сделать такой эдит» и зови в чат.\n\n"
          "📲 <b>Telegram и другие соцсети</b>\n• Выложи ссылку в свой канал, сторис и био.\n"
          "• Поделись в профильных чатах там, где это разрешено правилами.\n• Пиши лично друзьям-эдиторам.\n\n"
          "💡 <b>Шаблон текста:</b>\n«Андеграундное комьюнити эдиторов KAMLY HUB ⛓️ Конкурсы, дуэли, ранги и разбор работ. Залетай: "
          + link + "»\n\n"
          "⚠️ Не спамь по чужим чатам и не накручивай — боты и фейки не засчитываются при выдаче админок.")
    en = ("❓ <b>How to invite more people</b>\n\n"
          "Your link:\n" + link + "\n\n"
          "🎵 <b>TikTok</b>\n• Put the link in your profile (bio/link field if available) and say “our editors chat — link in bio”.\n"
          "• Make a story/video: “Want feedback on your edits? Join KAMLY HUB” and pin a comment with the link.\n"
          "• Answer “where's the source / how to make this edit” questions and invite people to the chat.\n\n"
          "📲 <b>Telegram and other socials</b>\n• Post the link in your channel, stories and bio.\n"
          "• Share it in relevant chats where the rules allow it.\n• Message editor friends directly.\n\n"
          "💡 <b>Text template:</b>\n“Underground editors community KAMLY HUB ⛓️ Contests, duels, ranks and feedback. Join: "
          + link + "”\n\n"
          "⚠️ Don't spam other chats or cheat — bots and fake accounts don't count for admin spots.")
    return L(lang, ru, en)

async def on_ref_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    lang = ulang(uid) or guess_lang(q.from_user)
    act = q.data.split("|")[1]
    await q.answer()
    back = Kb([[Btn(L(lang, "◀️ К партнёрке", "◀️ To referral"), callback_data="m|ref")]])
    if act == "gen":
        try:
            link = await get_ref_link(context.bot, uid)
        except Exception as e:
            await q.message.reply_text(L(lang, f"Не получилось создать ссылку: {e}\n(боту нужны права админа с приглашением участников)",
                                         f"Couldn't create the link: {e}\n(the bot needs admin rights to invite users)"))
            return
        d = get_user(uid)
        await q.message.reply_text(
            L(lang, "🔗 <b>Твоя персональная ссылка</b>\n\n", "🔗 <b>Your personal link</b>\n\n") + link + "\n\n"
            + L(lang, f"👥 Приглашено: <b>{d.get('refs', 0)}</b> · за каждого +{REF_FIRE} 🔥",
                f"👥 Invited: <b>{d.get('refs', 0)}</b> · +{REF_FIRE} 🔥 for each"),
            parse_mode=HTML, link_preview_options=NOPREV, reply_markup=ref_kb(lang, back=False))
    elif act == "stat":
        await safe_edit(q, ref_stat_text(uid, lang), back)
    elif act == "top":
        await safe_edit(q, ref_top_text(lang), back)
    elif act == "guide":
        try:
            link = await get_ref_link(context.bot, uid)
        except Exception:
            link = "—"
        await safe_edit(q, ref_guide_text(lang, link), back)


async def cmd_invite(update, context):
    if update.effective_chat.type != "private":
        lang = cl(update)
        kb = Kb([[Btn(L(lang, "🤝 Партнёрка", "🤝 Referral"), url=f"https://t.me/{context.bot.username}?start=ref")]])
        await say(context.bot, update.effective_message, L(lang, "Партнёрка и твоя ссылка — в личке 👇", "Referral program and your link — in DM 👇"), reply_markup=kb)
        return
    lang = ulang(update.effective_user.id) or guess_lang(update.effective_user)
    await update.message.reply_text(ref_main_text(lang), parse_mode=HTML, reply_markup=ref_kb(lang))


async def cmd_reftop(update, context):
    await say(context.bot, update.effective_message, ref_top_text(cl(update)))


async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm or cm.chat.id not in CHATS:
        return
    old, new = cm.old_chat_member.status, cm.new_chat_member.status
    if old not in ("left", "kicked") or new not in ("member", "restricted"):
        return
    user = cm.new_chat_member.user
    if user.is_bot or not cm.invite_link:
        return
    owner = DATA["ref_owner"].get(cm.invite_link.invite_link)
    if not owner or owner == user.id or str(user.id) in DATA["ref_joined"]:
        return
    DATA["ref_joined"][str(user.id)] = owner
    get_user(user.id, user.full_name, user.username)
    o = get_user(owner)
    o["refs"] = o.get("refs", 0) + 1
    o["fire"] += REF_FIRE
    save()
    lang = lang_of(cm.chat.id, "general")
    await notice(context.bot, cm.chat.id, "🔗 " + L(lang,
                 f"{mention(owner, o['name'])} пригласил(а) {mention(user.id, user.full_name)} (+{REF_FIRE} 🔥)",
                 f"{mention(owner, o['name'])} invited {mention(user.id, user.full_name)} (+{REF_FIRE} 🔥)"), 30)
    await refresh_rank(context.bot, owner)


# ============================ ЛИЧКА: МЕНЮ ============================
def lang_kb():
    return Kb([[Btn("🇷🇺 Русский", callback_data="lg|ru"), Btn("🇬🇧 English", callback_data="lg|en")]])


def main_text(lang, name):
    return L(lang,
             f"👋 Привет, <b>{esc(name)}</b>! Я — бот <b>KAMLY HUB</b> ⛓️\n\nСлежу за порядком в чатах эдиторов, веду конкурсы, дуэли, ранги и партнёрку.\n\n"
             "🎬 Хочешь честную оценку? Жми «Оценить эдит» — работа уйдёт в чат анонимно, а оценки 1–10 и комментарии придут тебе.",
             f"👋 Hi, <b>{esc(name)}</b>! I'm the <b>KAMLY HUB</b> bot ⛓️\n\nI keep editor chats in order and run contests, duels, ranks and the referral program.\n\n"
             "🎬 Want honest feedback? Press “Rate edit” — your work goes to the chat anonymously, ratings 1–10 and comments come back to you.")


def main_kb(lang):
    rows = [[Btn(L(lang, "🎬 Оценить эдит", "🎬 Rate edit"), callback_data="m|rate")],
            [Btn(L(lang, "🤝 Партнёрка", "🤝 Referral"), callback_data="m|ref"),
             Btn(L(lang, "🏅 Мой профиль", "🏅 My profile"), callback_data="m|me")],
            [Btn(L(lang, "📖 Команды", "📖 Commands"), callback_data="m|cmds"),
             Btn(L(lang, "📚 Гайд", "📚 Guide"), callback_data="m|guide")]]
    links = []
    if HUB_LINK:
        links.append(Btn("💬 KAMLY HUB", url=HUB_LINK))
    links.append(Btn(L(lang, "💬 Чат RU", "💬 RU chat"), url=OLD_CHAT_LINK))
    rows.append(links)
    row = [Btn(L(lang, "⚡ Канал", "⚡ Channel"), url=CHANNEL_LINK)]
    if TIKTOK_LINK:
        row.append(Btn("🎵 TikTok", url=TIKTOK_LINK))
    rows.append(row)
    rows.append([Btn(L(lang, "📜 Правила", "📜 Rules"), callback_data="m|rules"),
                 Btn("🌐 Language", callback_data="m|lang")])
    return Kb(rows)


def back_kb(lang):
    return Kb([[Btn(L(lang, "◀️ Назад", "◀️ Back"), callback_data="m|main")]])


async def show_screen(message, context, user, arg):
    lang = ulang(user.id) or guess_lang(user)
    if arg == "rules":
        await message.reply_text(rules_text(lang), parse_mode=HTML, reply_markup=back_kb(lang))
    elif arg in ("cmds", "help"):
        await message.reply_text(commands_text(lang), parse_mode=HTML, reply_markup=back_kb(lang))
    elif arg in ("ref", "admin", "invite"):
        await message.reply_text(ref_main_text(lang), parse_mode=HTML, reply_markup=ref_kb(lang))
    elif arg == "rate":
        await ask_edit(message, context, user)
    elif arg == "lang":
        await message.reply_text("🌐 Выбери язык / Choose language:", reply_markup=lang_kb())
    else:
        await message.reply_text(main_text(lang, user.first_name), parse_mode=HTML, reply_markup=main_kb(lang))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    u = update.effective_user
    get_user(u.id, u.full_name, u.username)
    arg = context.args[0] if context.args else ""
    if not ulang(u.id):
        context.user_data["after"] = arg
        await update.message.reply_text("🌐 Выбери язык / Choose your language:", reply_markup=lang_kb())
        return
    await show_screen(update.message, context, u, arg)


async def on_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    lang = q.data.split("|")[1]
    get_user(q.from_user.id, q.from_user.full_name, q.from_user.username)["lang"] = lang
    save()
    await q.answer("✅")
    arg = context.user_data.pop("after", "")
    try:
        await q.message.delete()
    except Exception:
        pass
    await show_screen(q.message, context, q.from_user, arg)


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    act = q.data.split("|")[1]
    u = q.from_user
    lang = ulang(u.id) or guess_lang(u)
    await q.answer()
    if act == "main":
        await safe_edit(q, main_text(lang, u.first_name), main_kb(lang))
    elif act == "rate":
        await ask_edit(q.message, context, u)
    elif act == "ref":
        await safe_edit(q, ref_main_text(lang), ref_kb(lang))
    elif act == "me":
        await safe_edit(q, profile_text(u.id, lang, u), back_kb(lang))
    elif act == "cmds":
        await safe_edit(q, commands_text(lang), back_kb(lang))
    elif act == "guide":
        await safe_edit(q, guide_text(lang), back_kb(lang))
    elif act == "rules":
        await safe_edit(q, rules_text(lang), back_kb(lang))
    elif act == "lang":
        await safe_edit(q, "🌐 Выбери язык / Choose language:", lang_kb())


async def cmd_language(update, context):
    await update.effective_message.reply_text("🌐 Выбери язык / Choose language:", reply_markup=lang_kb())


async def cmd_cancel(update, context):
    context.user_data["awaiting_edit"] = False
    context.user_data.pop("pending_track", None)
    await update.message.reply_text("✅")


async def cmd_rate(update, context):
    if update.effective_chat.type == "private":
        await ask_edit(update.message, context, update.effective_user)


# ---------- личка: админ-функции ----------
async def on_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m, u = update.message, update.effective_user
    if not m or not u:
        return
    if context.user_data.get("awaiting_edit"):
        await submit_anon(update, context)
        return
    if not await is_admin(context.bot, u.id):
        if m.text:
            await m.reply_text("/start")
        return
    doc = m.document
    mime = (doc.mime_type or "") if doc else ""
    fname = (doc.file_name or "") if doc else ""
    if doc and (fname.lower().endswith(".json") or mime == "application/json"):
        try:
            f = await context.bot.get_file(doc.file_id)
            raw = bytes(await f.download_as_bytearray())
            new = ensure(json.loads(raw.decode("utf-8")))
            DATA.clear()
            DATA.update(new)
            save()
            await flush()
            await m.reply_text(f"✅ Данные восстановлены: пользователей {len(DATA['users'])}, "
                               f"эдитов в конкурсе {len(DATA['edits'])}, побед в зале славы {len(DATA['hall'])}.")
        except Exception as e:
            await m.reply_text(f"❌ Не получилось прочитать файл: {e}")
        return
    if m.audio or (doc and mime.startswith("audio")):
        a = m.audio or doc
        title = ""
        if m.audio:
            title = " — ".join(x for x in (m.audio.performer, m.audio.title) if x)
        title = title or getattr(a, "file_name", None) or "Track"
        context.user_data["pending_track"] = {"file_id": a.file_id, "title": title}
        kb = Kb([[Btn(g["short"], callback_data=f"tg|{k}")] for k, g in GENRES.items()])
        await m.reply_text(f"🎵 «{title}»\nЖанр / Genre:", reply_markup=kb)
    elif m.animation or (doc and mime in ("video/mp4", "image/gif")):
        DATA["gif"] = m.animation.file_id if m.animation else doc.file_id
        save()
        await m.reply_text("✅ Гифка сохранена — будет под каждым постом канала.")


async def on_track_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await is_admin(context.bot, q.from_user.id):
        await q.answer("Admins only", show_alert=True)
        return
    p = context.user_data.pop("pending_track", None)
    if not p:
        await q.answer("Send the track again", show_alert=True)
        return
    gk = q.data.split("|")[1]
    DATA["tracks"].append({"file_id": p["file_id"], "title": p["title"], "genre": gk})
    save()
    await safe_edit(q, f"✅ «{esc(p['title'])}» → <b>{GENRES[gk]['title']}</b>\nВсего треков: {len(DATA['tracks'])}")
    await q.answer()

async def cmd_tracks(update, context):
    if not await is_admin(context.bot, update.effective_user.id):
        return
    if not DATA["tracks"]:
        await update.message.reply_text("Треков нет. Пришли аудиофайл — добавлю.")
        return
    lines = ["🎵 <b>Треки:</b>\n"] + [f"{i}. {esc(t['title'])} — {GENRES[t['genre']]['short']}"
                                      for i, t in enumerate(DATA["tracks"], 1)]
    lines.append("\nУдалить: <code>/deltrack номер</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=HTML)


async def cmd_deltrack(update, context):
    if not await is_admin(context.bot, update.effective_user.id):
        return
    if context.args and context.args[0].isdigit() and 1 <= int(context.args[0]) <= len(DATA["tracks"]):
        t = DATA["tracks"].pop(int(context.args[0]) - 1)
        save()
        await update.message.reply_text(f"🗑 «{t['title']}»")
    else:
        await update.message.reply_text("/deltrack 2  (список: /tracks)")


async def send_backup(bot, chat_id, caption="💾 Backup"):
    buf = io.BytesIO(json.dumps(DATA, ensure_ascii=False).encode("utf-8"))
    buf.name = "kamly_data_backup.json"
    await bot.send_document(chat_id, buf, caption=caption)


async def cmd_backup(update, context):
    if await is_admin(context.bot, update.effective_user.id):
        await send_backup(context.bot, update.effective_chat.id)


async def cmd_autobackup(update, context):
    if not await is_admin(context.bot, update.effective_user.id):
        return
    uid = update.effective_user.id
    if uid in DATA["backup_to"]:
        DATA["backup_to"].remove(uid)
        await update.message.reply_text("🔕 Автобэкап выключен.")
    else:
        DATA["backup_to"].append(uid)
        await update.message.reply_text("🔔 Автобэкап включён: раз в сутки пришлю файл с данными.")
    save()


# ============================ ПЛАНИРОВЩИК ============================
async def scheduler(app):
    while True:
        await asyncio.sleep(60)
        try:
            now = now_local()
            wk = now.strftime("%G-%V")
            if now.weekday() == CONTEST_DAY and now.hour >= CONTEST_HOUR and DATA.get("last_week") != wk:
                DATA["last_week"] = wk
                save()
                await announce_winner(app.bot)
            if now.weekday() == CHALLENGE_DAY and now.hour >= CHALLENGE_HOUR and DATA.get("last_challenge_week") != wk:
                DATA["last_challenge_week"] = wk
                save()
                await post_challenge(app.bot)
            today = now.strftime("%Y-%m-%d")
            if now.hour >= BACKUP_HOUR and DATA.get("last_backup") != today:
                DATA["last_backup"] = today
                save()
                for uid in list(DATA["backup_to"]):
                    try:
                        await send_backup(app.bot, uid, "💾 Daily backup " + today)
                    except Exception as e:
                        print("backup error:", e)
            await duels_tick(app.bot)
        except Exception as e:
            print("scheduler error:", e)


async def health_server():
    port = os.environ.get("PORT")
    if not port:
        return

    async def handle(reader, writer):
        try:
            await asyncio.wait_for(reader.read(1024), 5)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
    server = await asyncio.start_server(handle, "0.0.0.0", int(port))
    async with server:
        await server.serve_forever()


async def on_error(update, context):
    logging.error("Ошибка:", exc_info=context.error)


async def post_init(app):
    bg(scheduler(app))
    bg(flusher())
    bg(health_server())
    if DATABASE_URL:
        await flush()
    en = [("me", "My card and rank"), ("top", "Creators leaderboard"), ("stats", "Hub stats"),
          ("hall", "Hall of fame"), ("ranks", "All ranks"), ("contest", "Top edits of the week"),
          ("challenge", "Weekly challenge"), ("duel", "Challenge to a duel"), ("invite", "Referral program"),
          ("reftop", "Top inviters"), ("guide", "Hub guide"), ("commands", "All commands"),
          ("rules", "Rules"), ("language", "Language")]
    ru = [("me", "Моя карточка и ранг"), ("top", "Рейтинг креаторов"), ("stats", "Статистика хаба"),
          ("hall", "Зал славы"), ("ranks", "Все ранги"), ("contest", "Топ эдитов недели"),
          ("challenge", "Челлендж недели"), ("duel", "Вызвать на дуэль"), ("invite", "Партнёрка"),
          ("reftop", "Топ пригласивших"), ("guide", "Гайд по хабу"), ("commands", "Все команды"),
          ("rules", "Правила"), ("language", "Язык")]
    try:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in en])
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in ru], language_code="ru")
    except Exception as e:
        print("set commands error:", e)


async def post_shutdown(app):
    await flush()


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    GRP = filters.Chat(chat_id=list(CHATS))
    PRIV = filters.ChatType.PRIVATE
    H = app.add_handler

    # везде
    for name, fn in [("id", cmd_id), ("rules", cmd_rules), ("guide", cmd_guide), ("commands", cmd_commands),
                     ("cmds", cmd_commands), ("help", cmd_commands), ("contest", cmd_contest),
                     ("stats", cmd_stats), ("top", cmd_top), ("me", cmd_me), ("hall", cmd_hall),
                     ("ranks", cmd_ranks), ("challenge", cmd_challenge), ("invite", cmd_invite),
                     ("reftop", cmd_reftop), ("language", cmd_language)]:
        H(CommandHandler(name, fn))
    # личка
    H(CommandHandler("start", start, filters=PRIV))
    H(CommandHandler("cancel", cmd_cancel, filters=PRIV))
    H(CommandHandler("rate", cmd_rate, filters=PRIV))
    H(CommandHandler("tracks", cmd_tracks, filters=PRIV))
    H(CommandHandler("deltrack", cmd_deltrack, filters=PRIV))
    H(CommandHandler("backup", cmd_backup, filters=PRIV))
    H(CommandHandler("autobackup", cmd_autobackup, filters=PRIV))
    # чаты
    for name, fn in [("warn", cmd_warn), ("mute", cmd_mute), ("unmute", cmd_unmute), ("ban", cmd_ban),
                     ("unban", cmd_unban), ("winner", cmd_winner), ("newchallenge", cmd_newchallenge),
                     ("endduel", cmd_endduel), ("duel", cmd_duel), ("who", cmd_who),
                     ("settopic", cmd_settopic), ("topics", cmd_topics),
                     ("postguide", cmd_postguide), ("postrules", cmd_postrules)]:
        H(CommandHandler(name, fn, filters=GRP))

    # кнопки
    for pat, fn in [(r"^v\|", on_vote), (r"^rv\|", on_review_btn), (r"^d\|", on_duel_btn),
                    (r"^(dt|dp|ds)\|", on_duel_pick), (r"^dv\|", on_duel_vote), (r"^de\|", on_duel_end),
                    (r"^r\|", on_rate), (r"^rc\|", on_rate_help), (r"^rd\|", on_rate_delete),
                    (r"^m\|", on_menu), (r"^lg\|", on_lang), (r"^ref\|", on_ref_btn),
                    (r"^tg\|", on_track_genre)]:
        H(CallbackQueryHandler(fn, pattern=pat))
    H(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))

    # сообщения в чатах
    H(MessageHandler(GRP & ~filters.COMMAND, track), -1)
    H(MessageHandler(GRP & filters.IS_AUTOMATIC_FORWARD, on_channel_post), 0)
    H(MessageHandler(GRP & filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members), 0)
    H(MessageHandler(GRP & ~filters.COMMAND & ~filters.StatusUpdate.ALL & ~filters.IS_AUTOMATIC_FORWARD, antispam), 1)
    H(MessageHandler(GRP & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_hashtags), 2)
    H(MessageHandler(GRP & filters.REPLY & filters.TEXT & ~filters.COMMAND, on_reply_comment), 3)
    # личка
    H(MessageHandler(PRIV & ~filters.COMMAND, on_private))

        app.add_error_handler(on_error)

    # --- МИНИ-СЕРВЕР ДЛЯ RENDER И UPTIMEROBOT ---
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive!")
        def log_message(self, format, *args):
            pass

    def run_web():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), SimpleHandler)
        server.serve_forever()

    threading.Thread(target=run_web, daemon=True).start()
    # ---------------------------------------------

    print("✅ Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
