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
import uuid
from dotenv import load_dotenv

# Discord
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

# Flask
from flask import Flask, render_template_string, request

# Ngrok
from pyngrok import ngrok, conf

load_dotenv()

# ---------------- CONFIG ----------------
RUTXU_CHANNEL_ID = os.getenv("RUTXU_CHANNEL_ID")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YEUMONEY_TOKEN = os.getenv("YEUMONEY_TOKEN")
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
WEB_BASE = os.getenv("WEB_BASE", "https://example.com")
PORT = int(os.getenv("PORT") or 5000)
REWARD = int(os.getenv("REWARD") or 5)
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT") or 2)
PENDING_EXPIRE_SECONDS = int(os.getenv("PENDING_EXPIRE_SECONDS") or 600)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]


# Global variable to store ngrok URL
NGROK_URL = None

# Files
CODES_FILE = "codes.json"       # ["2102","3456",...]
PENDING_FILE = "pending.json"  # { "token-uuid": {"code": "2102", "user_id": "...", "created":"iso", "yeu_link":"...", "redeemed": false} }
USED_FILE = "used.json"        # { "code": {"user_id":"...", "time":"iso", "token":"..."} }
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

# Re-entrant lock for file IO (allows nested helper calls)
io_lock = threading.RLock()

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
                data = json.load(f)
    else:
        data = {"xu": 0, "logs": []}

    # Ensure required keys exist for backwards compatibility
    if "logs" not in data:
        data["logs"] = []
    if "xu" not in data:
        data["xu"] = 0

    return data

def save_user(uid, data):
    p = get_user_file(uid)
    with io_lock:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- Admin check helper ----------------
async def check_admin(interaction: discord.Interaction) -> bool:
    """Check if user is admin. Returns True if authorized, False otherwise."""
    if not ADMIN_IDS:
        print("⚠️  WARNING: ADMIN_IDS not configured in .env")
        return False
    if interaction.user.id not in ADMIN_IDS:
        return False
    return True

# ---------------- YeuMoney API ----------------
def create_yeumoney_link(token):
    """
    Call YeuMoney QL_api to shorten WEB_BASE/<token>.
    Uses format=text to get raw shortened link.
    Returns shortened link (string) or None on failure.
    """
    from urllib.parse import quote
    if not WEB_BASE:
        print("WEB_BASE not configured")
        return None
    original = f"{WEB_BASE.rstrip('/')}/{token}"
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
    # runs in background thread, checks every 30s for expired pending tokens
    while True:
        try:
            pending = load_pending()
            changed = False
            now = datetime.datetime.utcnow()
            for token, info in list(pending.items()):
                created = datetime.datetime.fromisoformat(info["created"])
                if (now - created).total_seconds() > PENDING_EXPIRE_SECONDS:
                    # expire: only return code if NOT redeemed
                    code = info.get("code")
                    redeemed = info.get("redeemed", False)
                    print(f"[CLEANUP] Token expired: {token}, code: {code}, redeemed: {redeemed}")

                    if not redeemed:
                        # Only return unredeemed codes to pool
                        codes = load_codes()
                        if code and code not in codes:
                            codes.append(code)
                            save_codes(codes)
                            print(f"[CLEANUP] Code {code} returned to pool")

                    # Remove token from pending
                    pending.pop(token, None)
                    changed = True

                    # notify owner if possible
                    try:
                        uid = int(info.get("user_id"))
                        user = load_user(uid)
                        user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | expire | code={code} | redeemed={redeemed}")
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

# /nhanxu - Helper function
async def nhanxu_logic(interaction: discord.Interaction):
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

    # create UUID token for security
    token = uuid.uuid4().hex

    # create yeumoney link with token
    yeu_link = create_yeumoney_link(token)
    if not yeu_link:
        # if fail, return code back
        codes = load_codes()
        if code not in codes:
            codes.append(code)
            save_codes(codes)
        return await interaction.followup.send("❌ Lỗi khi tạo link YeuMoney. Vui lòng thử lại sau.", ephemeral=True)

    # mark pending with token as key
    pending = load_pending()
    pending[token] = {
        "code": code,
        "user_id": str(uid),
        "created": datetime.datetime.utcnow().isoformat(),
        "yeu_link": yeu_link,
        "redeemed": False
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
            value="1️⃣ Click vào link bên dưới\n2️⃣ Hoàn thành vượt link để nhận xu tự động\n",
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
        embed.set_footer(text=f" • Chúc bạn may mắn!")
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

# Slash command wrapper
@bot.tree.command(name="nhanxu", description="Nhận xu — bot sẽ gửi link YeuMoney qua DM")
async def nhanxu(interaction: discord.Interaction):
    await nhanxu_logic(interaction)

# --------------------------
# Admin commands
# --------------------------
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


# --------------------------
# Prefix command !nhanxu
# --------------------------
@bot.command(name="nhanxu")
async def prefix_nhanxu(ctx):
    embed = discord.Embed(
        title="🎁 HỆ THỐNG NHẬN XU",
        description=(
            "Dùng các nút bên dưới để thao tác nhanh:\n"
            "• Nhận Xu: nhận link YeuMoney\n"
            "• Rút Xu: mở form rút xu\n"
            "• Check Xu: xem số xu hiện có"
        ),
        color=0x00FF00,
    )
    view = View()

    async def nhanxu_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            return await interaction.response.send_message("⚠️ Bạn không được phép dùng nút này.", ephemeral=True)
        await nhanxu_logic(interaction)

    btn_nhanxu = Button(label="Nhận Xu", style=discord.ButtonStyle.primary)
    btn_nhanxu.callback = nhanxu_callback
    view.add_item(btn_nhanxu)

    async def rutxu_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            return await interaction.response.send_message("⚠️ Bạn không được phép dùng nút này.", ephemeral=True)
        class RutXuModal(discord.ui.Modal, title="Rút xu"):
            name_in_game = discord.ui.TextInput(label="Tên người chơi trong game", placeholder="Nhập tên game", required=True)
            amount = discord.ui.TextInput(label="Số xu muốn rút", placeholder="Nhập số xu", required=True)

            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    amount_int = int(self.amount.value)
                except:
                    return await modal_interaction.response.send_message("⚠️ Số xu phải là số nguyên.", ephemeral=True)
                await rutxu_logic(modal_interaction, self.name_in_game.value, amount_int)
        await interaction.response.send_modal(RutXuModal())

    btn_rutxu = Button(label="Rút Xu", style=discord.ButtonStyle.secondary)
    btn_rutxu.callback = rutxu_callback
    view.add_item(btn_rutxu)

    async def checkxu_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            return await interaction.response.send_message("⚠️ Bạn không được phép dùng nút này.", ephemeral=True)
        await checkxu_logic(interaction)

    btn_checkxu = Button(label="Check Xu", style=discord.ButtonStyle.success)
    btn_checkxu.callback = checkxu_callback
    view.add_item(btn_checkxu)

    await ctx.send(embed=embed, view=view)

# --- checkxu - Helper function
async def checkxu_logic(interaction: discord.Interaction):
    u = load_user(interaction.user.id)
    await interaction.response.send_message(f"💰 Bạn có {u.get('xu',0)} xu.", ephemeral=True)

# Slash command wrapper
@bot.tree.command(name="checkxu", description="Xem số xu của bạn")
async def checkxu(interaction: discord.Interaction):
    await checkxu_logic(interaction)

# --------------------------
# /rutxu - Helper function
# --------------------------
async def rutxu_logic(interaction: discord.Interaction, name_in_game: str, amount: int, *, defer: bool = True):
    if defer:
        await interaction.response.defer(ephemeral=True)
    
    uid = interaction.user.id
    user = load_user(uid)
    current_xu = user.get("xu", 0)
    
    if amount <= 0:
        return await interaction.followup.send("⚠️ Số lượng xu phải lớn hơn 0.", ephemeral=True)
    if amount > current_xu:
        return await interaction.followup.send(f"⚠️ Bạn không đủ xu. Bạn hiện có: **{current_xu}** xu.", ephemeral=True)
    if not RUTXU_CHANNEL_ID:
        return await interaction.followup.send("❌ **LỖI CẤU HÌNH:** Chưa thiết lập ID kênh rút xu.", ephemeral=True)
    
    try:
        target_channel_id = int(RUTXU_CHANNEL_ID)
        channel = bot.get_channel(target_channel_id)
        if not channel:
            channel = await bot.fetch_channel(target_channel_id)
    except Exception:
        return await interaction.followup.send("❌ **LỖI CẤU HÌNH:** ID kênh rút xu không hợp lệ.", ephemeral=True)
    
    SERVER_STATUS_CHANNEL_ID = os.getenv("SERVER_STATUS_CHANNEL_ID")
    if not SERVER_STATUS_CHANNEL_ID:
        return await interaction.followup.send("⚠️ **Chưa cấu hình SERVER_STATUS_CHANNEL_ID trong .env.**", ephemeral=True)
    
    try:
        status_channel = bot.get_channel(int(SERVER_STATUS_CHANNEL_ID))
        if not status_channel:
            status_channel = await bot.fetch_channel(int(SERVER_STATUS_CHANNEL_ID))
    except Exception:
        return await interaction.followup.send("❌ **Lỗi:** Không tìm thấy kênh trạng thái server. Kiểm tra lại ID trong `.env`.", ephemeral=True)
    
    channel_name = status_channel.name or ""
    if "🔴" in channel_name:
        return await interaction.followup.send("🚫 **Hiện tại máy chủ đang tạm bảo trì (🔴).**\nVui lòng thử lại sau khi server mở lại.", ephemeral=True)
    if "🟢" not in channel_name:
        return await interaction.followup.send("⚠️ **Không xác định được trạng thái server.**\nTên kênh trạng thái phải chứa 🟢 (mở) hoặc 🔴 (bảo trì).", ephemeral=True)
    
    user["xu"] = current_xu - amount
    user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | rutxu | -{amount} | name={name_in_game} | channel_id={RUTXU_CHANNEL_ID}")
    save_user(uid, user)
    
    final_command = f"!playerpoint give {name_in_game} {amount}"
    await interaction.followup.send(f"✅ **Giao dịch hoàn tất!**\n**-{amount} xu** đã được trừ khỏi tài khoản của bạn. (Còn lại: **{user['xu']}** xu)\nLệnh chuyển điểm đã được gửi đến kênh quản lý.", ephemeral=True)
    
    try:
        await channel.send(final_command)
    except discord.Forbidden:
        await interaction.user.send(f"❌ **LỖI GỬI LỆNH:** Lệnh rút xu đã bị trừ nhưng bot không có quyền gửi lệnh tới kênh chuyển lệnh (<#{target_channel_id}>).\nVui lòng liên hệ quản trị viên với thông tin này.")
    except Exception as e:
        await interaction.user.send(f"❌ **LỖI NỘI BỘ:** Lệnh rút xu đã bị trừ nhưng bot không thể gửi lệnh tới kênh chuyển lệnh. (`{e}`).\nVui lòng liên hệ quản trị viên với thông tin này.")

# Slash command wrapper
@bot.tree.command(name="rutxu", description="Rút xu (xu được chuyển thành lệnh /playerpoint)")
@app_commands.describe(name_in_game="Tên người chơi trong game", amount="Số xu muốn rút")
async def rutxu(interaction: discord.Interaction, name_in_game: str, amount: int):
    await rutxu_logic(interaction, name_in_game, amount)

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
.success-icon {
    font-size: 64px;
    margin: 20px 0;
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
    line-height: 1.6;
}
.success {
    color: #4CAF50;
    font-weight: bold;
    font-size: 20px;
}
.highlight {
    background: #fff3cd;
    padding: 15px;
    border-radius: 10px;
    margin: 20px 0;
    border-left: 4px solid #4CAF50;
}
</style>
</head>
<body>
<div class="container">
    <div class="success-icon">✅</div>
    <h1>HOÀN THÀNH!</h1>
    <p class="message success">{{msg}}</p>
    <div class="highlight">
        <p class="message"><strong>✨ Xu đã được cộng TỰ ĐỘNG vào tài khoản Discord của bạn!</strong></p>
    </div>
    <p class="message">Mã code của bạn (chỉ để tham khảo):</p>
    <div class="code-box">
        <div class="code" id="codeText">{{code}}</div>
    </div>
    <button class="copy-btn" onclick="copyCode()">📋 COPY MÃ</button>
    <p class="message" style="color: #999; font-size: 14px; margin-top: 30px;">
        ℹ️ Bạn KHÔNG cần dùng lệnh /redeem nữa.<br>
        Xu đã được tự động thêm vào tài khoản của bạn!
    </p>
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

HTML_HOME = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Discord Bot - Hệ thống nhận xu</title>
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
    max-width: 600px;
    width: 100%;
}
h1 {
    color: #333;
    margin-bottom: 20px;
    font-size: 32px;
}
.status {
    background: #4CAF50;
    color: white;
    padding: 10px 20px;
    border-radius: 10px;
    display: inline-block;
    margin: 20px 0;
    font-weight: bold;
}
.info {
    color: #666;
    line-height: 1.8;
    margin: 20px 0;
}
.discord-icon {
    font-size: 64px;
    margin: 20px 0;
}
</style>
</head>
<body>
<div class="container">
    <div class="discord-icon">🤖</div>
    <h1>HỆ THỐNG NHẬN XU</h1>
    <div class="status">✅ ĐANG HOẠT ĐỘNG</div>
    <div class="info">
        <p><strong>Hệ thống Discord Bot đang chạy bình thường!</strong></p>
        <p>Để nhận xu, hãy sử dụng lệnh <code>/nhanxu</code> trên Discord server.</p>
        <p>Trang này chỉ hiển thị mã code sau khi bạn vượt link YeuMoney.</p>
    </div>
</div>
</body>
</html>
"""

@flask_app.route("/")
def home():
    return render_template_string(HTML_HOME), 200

@flask_app.route("/<token>")
def show_token(token):
    token = token.strip()

    # Atomic redemption with RLock (allows nested helper calls)
    with io_lock:
        # Load state once
        pending = load_pending()
        used = load_used()

        # Validate token exists
        if token not in pending:
            return render_template_string(HTML_USED), 404

        info = pending[token]
        code = info.get("code")
        owner = info.get("user_id")
        yeu_link = info.get("yeu_link")
        redeemed = info.get("redeemed", False)

        # Check if already redeemed
        # We check in 'used' for extra safety, though 'redeemed' in pending should catch it
        if redeemed or code in used:
            return render_template_string(HTML_USED), 200

        # Mark as redeemed and save
        used[code] = {
            "user_id": owner,
            "time": datetime.datetime.utcnow().isoformat(),
            "token": token,
            "yeu_link": yeu_link
        }
        save_used(used)

        pending[token]["redeemed"] = True
        save_pending(pending)

        # Give reward
        try:
            uid = int(owner)
            user = load_user(uid)
            user["xu"] = user.get("xu",0) + REWARD
            user["logs"].append(f"{datetime.datetime.utcnow().isoformat()} | redeem(web) | code={code} | +{REWARD}")
            save_user(uid, user)
            msg = f"Bạn đã nhận +{REWARD} xu. Tổng: {user['xu']}"
        except Exception as e:
            print(f"Error rewarding user: {e}")
            msg = "Đã xác nhận mã. (Không thể cộng xu do lỗi nội bộ.)"

    return render_template_string(HTML_TEMPLATE, code=code, msg=msg), 200

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
            
            # Kill all existing ngrok tunnels to avoid conflicts
            try:
                print("🔄 Closing all existing ngrok tunnels...")
                ngrok.kill()
                time.sleep(1)
            except Exception as cleanup_err:
                print(f"⚠️  Could not kill existing tunnels: {cleanup_err}")
            
            # Create new tunnel
            public_url = ngrok.connect(str(PORT), bind_tls=True)
            NGROK_URL = public_url.public_url
            WEB_BASE = NGROK_URL
            print("=" * 70)
            print("🌐 NGROK TUNNEL ACTIVE")
            print("=" * 70)
            print(f"📡 Public URL: {NGROK_URL}")
            print(f"📡 Local:       http://localhost:{PORT}")
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