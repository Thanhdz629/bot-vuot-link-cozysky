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

# Ngrok
from pyngrok import ngrok, conf

load_dotenv()

# ---------------- CONFIG ----------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YEUMONEY_TOKEN = os.getenv("YEUMONEY_TOKEN")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
WEB_BASE = os.getenv("WEB_BASE", "https://example.com")  # must be public
PORT = int(os.getenv("PORT") or 5000)
REWARD = int(os.getenv("REWARD") or 5)
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT") or 2)
PENDING_EXPIRE_SECONDS = int(os.getenv("PENDING_EXPIRE_SECONDS") or 600)  # 600s = 10min

# Global variable to store ngrok URL
NGROK_URL = None

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
    from urllib.parse import quote
    if not WEB_BASE:
        print("WEB_BASE not configured")
        return None
    original = f"{WEB_BASE.rstrip('/')}/{code}"
    # URL encode
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

    # DM user with embed
    try:
        embed = discord.Embed(
            title="🎁 NHẬN XU MIỄN PHÍ",
            description="Vượt link bên dưới để nhận xu!",
            color=0x00ff00
        )
        embed.add_field(
            name="📋 Hướng dẫn",
            value="1️⃣ Click vào link bên dưới\n2️⃣ Hoàn thành vượt link\n3️⃣ Sao chép mã code hiển thị\n4️⃣ Dùng lệnh `/redeem` + mã để nhận xu",
            inline=False
        )
        embed.add_field(
            name="🔗 Link vượt",
            value=f"[👉 Click vào đây để vượt link]({yeu_link})",
            inline=False
        )
        embed.add_field(
            name="💰 Phần thưởng",
            value=f"**+{REWARD} xu** sau khi hoàn thành",
            inline=True
        )
        embed.add_field(
            name="⏰ Thời gian",
            value=f"Có hiệu lực trong {PENDING_EXPIRE_SECONDS // 60} phút",
            inline=True
        )
        embed.set_footer(text=f"Mã code: {code} • Chúc bạn may mắn!")
        embed.timestamp = datetime.datetime.utcnow()
        
        await interaction.user.send(embed=embed)
        await interaction.followup.send("✅ Link đã gửi vào DM của bạn.", ephemeral=True)
    except discord.Forbidden:
        # cannot DM, send ephemeral with embed
        embed = discord.Embed(
            title="⚠️ Không thể gửi DM",
            description="Hãy bật DM từ thành viên server để nhận link!",
            color=0xff0000
        )
        embed.add_field(
            name="🔗 Link của bạn",
            value=f"[Click vào đây]({yeu_link})",
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

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
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redeem Code</title>
<style>
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    text-align: center;
    margin: 0;
    padding: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
}
.container {
    background: white;
    border-radius: 20px;
    padding: 40px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    max-width: 500px;
    width: 100%;
}
h1 {
    color: #333;
    margin-bottom: 30px;
    font-size: 28px;
}
.code-box {
    background: #f0f8ff;
    border: 3px solid #4CAF50;
    border-radius: 15px;
    padding: 30px 20px;
    margin: 20px 0;
}
.code {
    font-size: 48px;
    font-weight: bold;
    color: #4CAF50;
    letter-spacing: 5px;
    margin: 10px 0;
    font-family: 'Courier New', monospace;
}
.copy-btn {
    background: #4CAF50;
    color: white;
    border: none;
    padding: 15px 40px;
    font-size: 18px;
    border-radius: 10px;
    cursor: pointer;
    margin-top: 20px;
    transition: all 0.3s;
    font-weight: bold;
}
.copy-btn:hover {
    background: #45a049;
    transform: scale(1.05);
}
.copy-btn:active {
    transform: scale(0.95);
}
.message {
    color: #666;
    margin-top: 20px;
    font-size: 16px;
}
.success {
    color: #4CAF50;
    font-weight: bold;
}
</style>
</head>
<body>
<div class="container">
    <h1>🎁 MÃ CODE CỦA BẠN</h1>
    <div class="code-box">
        <div class="code" id="codeText">{{code}}</div>
    </div>
    <button class="copy-btn" onclick="copyCode()">📋 COPY MÃ</button>
    <p class="message success">{{msg}}</p>
    <p class="message">Sao chép mã và nhập lệnh <b>/redeem {{code}}</b> trên Discord!</p>
</div>
<script>
function copyCode() {
    const code = document.getElementById('codeText').innerText;
    navigator.clipboard.writeText(code).then(() => {
        const btn = document.querySelector('.copy-btn');
        btn.innerText = '✅ ĐÃ COPY!';
        setTimeout(() => {
            btn.innerText = '📋 COPY MÃ';
        }, 2000);
    });
}
</script>
</body>
</html>
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

# Setup ngrok tunnel
def setup_ngrok():
    global NGROK_URL, WEB_BASE
    if NGROK_AUTH_TOKEN:
        try:
            conf.get_default().auth_token = NGROK_AUTH_TOKEN
            public_url = ngrok.connect(str(PORT), bind_tls=True)
            NGROK_URL = public_url.public_url
            WEB_BASE = NGROK_URL
            print("=" * 70)
            print("🌐 NGROK TUNNEL ACTIVE")
            print("=" * 70)
            print(f"📡 Public URL: {NGROK_URL}")
            print(f"📡 Local:      http://localhost:{PORT}")
            print("=" * 70)
            print(f"✅ WEB_BASE automatically set to: {WEB_BASE}")
            print("=" * 70)
        except Exception as e:
            print(f"❌ Ngrok failed: {e}")
            print("⚠️  Continuing with WEB_BASE from .env")
    else:
        print("⚠️  NGROK_AUTH_TOKEN not found. Using WEB_BASE from .env")

# ---------------- Startup ----------------
if __name__ == "__main__":
    # setup ngrok first
    setup_ngrok()
    
    # start pending cleanup thread
    t = threading.Thread(target=pending_cleanup_loop, daemon=True)
    t.start()
    # start flask thread
    fthread = threading.Thread(target=run_flask, daemon=True)
    fthread.start()
    
    # wait for flask to start
    time.sleep(2)
    
    # run discord bot (blocking)
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not found in environment!")
        exit(1)
    bot.run(DISCORD_TOKEN)
