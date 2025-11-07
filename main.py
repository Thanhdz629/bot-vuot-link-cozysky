# main.py
# Bot Discord + Flask web + YeuMoney QL_api integration
# Run: python3 main.py

import os
import json
import random
import threading
import time
import datetime
import requests
from dotenv import load_dotenv

# Discord
import discord
from discord.ext import commands
from discord import app_commands

# Flask
from flask import Flask, render_template_string, request

load_dotenv()

# ---------------- CONFIG ----------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YEUMONEY_TOKEN = os.getenv("YEUMONEY_TOKEN")
WEB_BASE = os.getenv("WEB_BASE", "https://example.com")  # must be public
PORT = int(os.getenv("PORT", 5000))
REWARD = int(os.getenv("REWARD", 5))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", 2))
PENDING_EXPIRE_SECONDS = int(os.getenv("PENDING_EXPIRE_SECONDS", 600))  # 600s = 10min

# Files
CODES_FILE = "codes.json"      # ["ABC","XYZ",...]
PENDING_FILE = "pending.json"  # { "ABC": {"user_id": "...", "created":"iso", "yeu_link":"..."} }
USED_FILE = "used.json"        # { "ABC": {"user_id":"...", "time":"iso", "yeu_link":"..."} }
DATA_DIR = "data"              # per-user files: data/<user_id>.json

# Ensure folders and files
os.makedirs(DATA_DIR, exist_ok=True)
for fpath, default in [
    (CODES_FILE, []),
    (PENDING_FILE, {}),
    (USED_FILE, {}),
]:
    if not os.path.exists(fpath):
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

# Simple thread lock for file IO
io_lock = threading.Lock()

# ---------------- Helper IO ----------------
def load_json_file(path):
    with io_lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def save_json_file(path, data):
    with io_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def load_codes():
    return load_json_file(CODES_FILE)

def save_codes(codes):
    save_json_file(CODES_FILE, codes)

def load_pending():
    return load_json_file(PENDING_FILE)

def save_pending(pending):
    save_json_file(PENDING_FILE, pending)

def load_used():
    return load_json_file(USED_FILE)

def save_used(used):
    save_json_file(USED_FILE, used)

def get_user_file(uid):
    return os.path.join(DATA_DIR, f"{uid}.json")

def load_user(uid):
    p = get_user_file(uid)
    if os.path.exists(p):
        with io_lock:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {"xu": 0, "logs": []}

def save_user(uid, data):
    p = get_user_file(uid)
    with io_lock:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- YeuMoney API ----------------
def create_yeumoney_link(code):
    """
    Call YeuMoney QL_api to shorten WEB_BASE/<code>.
    Uses format=text to get raw shortened link.
    Returns shortened link (string) or None on failure.
    """
    original = f"{WEB_BASE.rstrip('/')}/{code}"
    # URL encode
    from requests.utils import quote
    target = quote(original, safe='')
    api = f"https://yeumoney.com/QL_api.php?token={YEUMONEY_TOKEN}&format=text&url={target}"
    try:
        r = requests.get(api, timeout=10)
        if r.status_code == 200:
            txt = r.text.strip()
            # QL_api returns empty string on error sometimes; check
            if txt and txt.startswith("http"):
                return txt
    except Exception as e:
        print("YeuMoney API error:", e)
    return None

# ---------------- Background expire task ----------------
def pending_cleanup_loop():
    # runs in background thread, checks every 30s for expired pending codes
    while True:
        try:
            pending = load_pending()
            changed = False
            now = datetime.datetime.utcnow()
            for code, info in list(pending.items()):
                created = datetime.datetime.fromisoformat(info["created"])
                if (now - created).total_seconds() > PENDING_EXPIRE_SECONDS:
                    # expire: move code back to codes.json and remove pending
                    print(f"[CLEANUP] Code expired: {code}")
                    codes = load_codes()
                    if code not in codes:
                        codes.append(code)
                        save_codes(codes)
                    pending.pop(code, None)
                    changed = True
                    # notify owner if possible
                    try:
                        uid = int(info.get("user_id"))
                        user = load_user(uid)
                        user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | expire | code={code}")
                        save_user(uid, user)
                    except Exception:
                        pass
            if changed:
                save_pending(pending)
        except Exception as e:
            print("pending_cleanup error:", e)
        time.sleep(30)

# ---------------- Discord bot ----------------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("Bot ready:", bot.user)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync failed:", e)

# /nhanxu
@bot.tree.command(name="nhanxu", description="Nhận xu — bot sẽ gửi link YeuMoney qua DM")
async def nhanxu(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    # Check daily limit per user
    uid = interaction.user.id
    user = load_user(uid)
    today = datetime.date.today().isoformat()
    if user.get("last_day") != today:
        user["last_day"] = today
        user["claims_today"] = 0
    if user.get("claims_today", 0) >= DAILY_LIMIT:
        return await interaction.followup.send(f"⚠️ Bạn đã nhận đủ {DAILY_LIMIT} lần hôm nay.", ephemeral=True)

    codes = load_codes()
    if not codes:
        return await interaction.followup.send("⚠️ Hiện không còn code.", ephemeral=True)

    # pop random code
    code = random.choice(codes)
    # remove it
    codes.remove(code)
    save_codes(codes)

    # create yeumoney link
    yeu_link = create_yeumoney_link(code)
    if not yeu_link:
        # if fail, return code back
        codes = load_codes()
        if code not in codes:
            codes.append(code)
            save_codes(codes)
        return await interaction.followup.send("❌ Lỗi khi tạo link YeuMoney. Vui lòng thử lại sau.", ephemeral=True)

    # mark pending
    pending = load_pending()
    pending[code] = {
        "user_id": str(uid),
        "created": datetime.datetime.utcnow().isoformat(),
        "yeu_link": yeu_link
    }
    save_pending(pending)

    # update user claims
    user["claims_today"] = user.get("claims_today", 0) + 1
    user["last_day"] = today
    user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | nhanxu | code={code} | link={yeu_link}")
    save_user(uid, user)

    # DM user
    try:
        await interaction.user.send(
            f"🎁 Link YeuMoney của bạn:\n{yeu_link}\n\nSau khi vượt link bạn sẽ được chuyển đến trang hiển thị mã: {WEB_BASE}/{code}"
        )
        await interaction.followup.send("✅ Link đã gửi vào DM của bạn.", ephemeral=True)
    except discord.Forbidden:
        # cannot DM, send ephemeral with link
        await interaction.followup.send(f"⚠️ Không thể gửi DM. Link của bạn:\n{yeu_link}", ephemeral=True)

# /redeem (fallback if user wants manual redeem)
@bot.tree.command(name="redeem", description="Nhập code để nhận xu (dự phòng)")
@app_commands.describe(code="Mã")
async def redeem(interaction: discord.Interaction, code: str):
    # Check used mapping
    used = load_used()
    # If code in used and user matches, already given
    if code in used:
        return await interaction.response.send_message("⚠️ Mã đã được dùng.", ephemeral=True)
    # Check pending — only owner can redeem via command
    pending = load_pending()
    if code not in pending:
        return await interaction.response.send_message("⚠️ Mã không tồn tại hoặc đã hết hạn.", ephemeral=True)
    owner = pending[code].get("user_id")
    if str(interaction.user.id) != str(owner):
        return await interaction.response.send_message("❌ Mã không thuộc về bạn.", ephemeral=True)
    # give reward and mark used
    # move pending->used
    used = load_used()
    used[code] = {
        "user_id": owner,
        "time": datetime.datetime.utcnow().isoformat(),
        "yeu_link": pending[code].get("yeu_link")
    }
    save_used(used)
    pending.pop(code, None)
    save_pending(pending)
    # add xu
    user = load_user(int(owner))
    user["xu"] = user.get("xu", 0) + REWARD
    user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | redeem(manual) | code={code} | +{REWARD}")
    save_user(int(owner), user)
    await interaction.response.send_message(f"✅ Đã cộng {REWARD} xu cho bạn. Tổng: {user['xu']}", ephemeral=True)

# admin commands: givexu, setxu, xoaxu, resetxu (use guild admin)
async def check_admin(interaction):
    return interaction.user.guild_permissions.administrator

@bot.tree.command(name="givexu", description="Admin: cộng xu cho user")
@app_commands.describe(member="Người nhận", amount="Số xu")
async def givexu(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await check_admin(interaction):
        return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
    u = load_user(member.id)
    u["xu"] = u.get("xu",0) + amount
    u["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | admin_givexu | +{amount}")
    save_user(member.id, u)
    await interaction.response.send_message(f"✅ Đã cộng {amount} xu cho {member.display_name}.", ephemeral=True)

@bot.tree.command(name="setxu", description="Admin: set xu cho user")
@app_commands.describe(member="Người nhận", amount="Số xu")
async def setxu(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await check_admin(interaction):
        return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
    u = load_user(member.id)
    u["xu"] = amount
    u["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | admin_setxu | = {amount}")
    save_user(member.id, u)
    await interaction.response.send_message(f"✅ Đã đặt {amount} xu cho {member.display_name}.", ephemeral=True)

@bot.tree.command(name="xoaxu", description="Admin: trừ xu của user")
@app_commands.describe(member="Người nhận", amount="Số xu")
async def xoaxu(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await check_admin(interaction):
        return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
    u = load_user(member.id)
    u["xu"] = max(0, u.get("xu",0) - amount)
    u["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | admin_xoaxu | -{amount}")
    save_user(member.id, u)
    await interaction.response.send_message(f"✅ Đã trừ {amount} xu của {member.display_name}.", ephemeral=True)

@bot.tree.command(name="resetxu", description="Admin: reset xu của user")
@app_commands.describe(member="Người nhận")
async def resetxu(interaction: discord.Interaction, member: discord.Member):
    if not await check_admin(interaction):
        return await interaction.response.send_message("Bạn không có quyền.", ephemeral=True)
    u = load_user(member.id)
    u["xu"] = 0
    u["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | admin_resetxu")
    save_user(member.id, u)
    await interaction.response.send_message(f"✅ Đã reset xu cho {member.display_name}.", ephemeral=True)

@bot.tree.command(name="checkxu", description="Xem số xu của bạn")
async def checkxu(interaction: discord.Interaction):
    u = load_user(interaction.user.id)
    await interaction.response.send_message(f"💰 Bạn có {u.get('xu',0)} xu.", ephemeral=True)

# ---------------- Flask web ----------------
flask_app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<title>Redeem</title>
<style>
body{font-family:sans-serif;text-align:center;margin-top:80px}
.code{font-size:36px;color:green}
</style>
<h1>MÃ CỦA BẠN</h1>
<p class="code">{{code}}</p>
<p>{{msg}}</p>
"""

HTML_USED = """
<!doctype html>
<title>Redeem - Đã dùng</title>
<h1>Mã đã được sử dụng hoặc không còn hiệu lực.</h1>
"""

@flask_app.route("/<code>")
def show_code(code):
    code = code.strip()
    # check used
    used = load_used()
    if code in used:
        return render_template_string(HTML_USED), 200

    pending = load_pending()
    if code in pending:
        info = pending[code]
        owner = info.get("user_id")
        yeu_link = info.get("yeu_link")
        # mark used, reward owner
        used = load_used()
        used[code] = {
            "user_id": owner,
            "time": datetime.datetime.utcnow().isoformat(),
            "yeu_link": yeu_link
        }
        save_used(used)
        # remove from pending
        pending.pop(code, None)
        save_pending(pending)
        # give reward
        try:
            uid = int(owner)
            user = load_user(uid)
            user["xu"] = user.get("xu",0) + REWARD
            user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | redeem(web) | code={code} | +{REWARD}")
            save_user(uid, user)
            msg = f"Bạn đã nhận +{REWARD} xu. Tổng: {user['xu']}"
        except Exception:
            msg = "Đã xác nhận mã. (Không thể cộng xu do lỗi nội bộ.)"
        return render_template_string(HTML_TEMPLATE, code=code, msg=msg), 200

    # if code still in available codes -> means not issued (admin left it)
    codes = load_codes()
    if code in codes:
        return render_template_string("""
            <!doctype html>
            <h1>Code chưa được cấp cho ai.</h1>
            <p>Code: {{c}}</p>
        """, c=code), 200

    # else not found
    return render_template_string(HTML_USED), 404

# Run flask in a separate thread
def run_flask():
    # allow replit or host port via PORT env
    flask_app.run(host="0.0.0.0", port=PORT)

# ---------------- Startup ----------------
if __name__ == "__main__":
    # start pending cleanup thread
    t = threading.Thread(target=pending_cleanup_loop, daemon=True)
    t.start()
    # start flask thread
    fthread = threading.Thread(target=run_flask, daemon=True)
    fthread.start()
    # run discord bot (blocking)
    bot.run(DISCORD_TOKEN)
