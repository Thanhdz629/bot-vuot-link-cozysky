# bot.py
# Discord bot + aiohttp webhook server
import os, json, random, string, asyncio, requests, datetime, pathlib
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord import app_commands
from aiohttp import web

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YEUMONEY_TOKEN = os.getenv("YEUMONEY_TOKEN")
LINKED_ROLE_ID = int(os.getenv("LINKED_ROLE_ID", "0"))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "2"))
REWARD = int(os.getenv("REWARD", "5"))
WEB_BASE = os.getenv("WEB_BASE", "https://example.com")  # domain for web.py
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_ENDPOINT = os.getenv("WEBHOOK_ENDPOINT", "/webhook/claim")

DATA_DIR = pathlib.Path("data")
USERS_DIR = DATA_DIR / "users"
CODES_FILE = DATA_DIR / "codes.json"
USERS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# helper IO
def load_json(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# init files
codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
save_json(CODES_FILE, codes)

def user_file(uid):
    return USERS_DIR / f"{uid}.json"

def load_user(uid):
    p = user_file(uid)
    return load_json(p, {"xu": 0, "logs": [], "last": "", "claims_today": 0})

def save_user(uid, data):
    save_json(user_file(uid), data)

def gen_short_link_for_code(code):
    """Call YeuMoney QL_api to shorten WEB_BASE/<code>, returns short link (text) or None."""
    try:
        original = f"{WEB_BASE.rstrip('/')}/{code}"
        api = f"https://yeumoney.com/QL_api.php?token={YEUMONEY_TOKEN}&format=text&url={requests.utils.quote(original, safe='')}"
        r = requests.get(api, timeout=10)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception as e:
        print("YeuMoney API error:", e)
    return None

def pick_code():
    codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    if not codes["available"]:
        return None
    code = codes["available"].pop(0)
    save_json(CODES_FILE, codes)
    return code

def mark_pending(code, user_id, yeu_link):
    codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    codes["pending"][code] = {"user_id": user_id, "created": datetime.datetime.utcnow().isoformat(), "yeu_link": yeu_link}
    save_json(CODES_FILE, codes)

def mark_used(code, user_id):
    codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    entry = codes["pending"].pop(code, None)
    if entry is None:
        # maybe expired returned to available earlier; still record usage
        codes["used"][code] = {"user_id": user_id, "time": datetime.datetime.utcnow().isoformat()}
    else:
        codes["used"][code] = {"user_id": user_id, "time": datetime.datetime.utcnow().isoformat(), "yeu_link": entry.get("yeu_link")}
    save_json(CODES_FILE, codes)

def return_code_to_available(code):
    codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    if code in codes["pending"]:
        codes["pending"].pop(code, None)
        codes["available"].append(code)
        save_json(CODES_FILE, codes)
        print(f"Returned code {code} to available list.")

# DISCORD bot
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("Bot ready:", bot.user)
    # start background cleanup task
    if not cleanup_pending.is_running():
        cleanup_pending.start()

# background: clean expired pending every 60s (if created > 10m return code)
@tasks.loop(seconds=60)
async def cleanup_pending():
    codes = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    now = datetime.datetime.utcnow()
    changed = False
    for code, info in list(codes["pending"].items()):
        created = datetime.datetime.fromisoformat(info["created"])
        if (now - created).total_seconds() > 600:  # 10 minutes
            # return to available
            print("Expiring pending code:", code)
            codes["pending"].pop(code, None)
            codes["available"].append(code)
            changed = True
            # notify user optionally: try DM
            try:
                uid = info.get("user_id")
                user = await bot.fetch_user(int(uid))
                await user.send(f"⏱ Mã `{code}` đã hết hạn (không được redeem sau 10 phút). Mã đã được trả lại.")
            except Exception:
                pass
    if changed:
        save_json(CODES_FILE, codes)

# /nhanxu command
@bot.tree.command(name="nhanxu", description="Nhận link YeuMoney (2 lần/ngày) — cần role Linked")
async def nhanxu(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    member = interaction.user
    # role check
    guild_member = interaction.guild.get_member(member.id)
    if LINKED_ROLE_ID and LINKED_ROLE_ID not in [r.id for r in getattr(guild_member, "roles", [])]:
        return await interaction.followup.send("❌ Bạn cần role Linked để dùng lệnh này.", ephemeral=True)

    user = load_user(member.id)
    today = datetime.date.today().isoformat()
    if user["last"] != today:
        user["last"] = today
        user["claims_today"] = 0

    if user["claims_today"] >= DAILY_LIMIT:
        return await interaction.followup.send(f"⚠️ Bạn đã nhận đủ {DAILY_LIMIT} lần hôm nay.", ephemeral=True)

    code = pick_code()
    if not code:
        return await interaction.followup.send("⚠️ Hiện không có mã sẵn, vui lòng quay lại sau.", ephemeral=True)

    # create yeumoney short link to WEB_BASE/code
    yeu_link = await asyncio.to_thread(gen_short_link_for_code, code)
    if not yeu_link:
        # return code
        codes_data = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
        codes_data["available"].insert(0, code)
        save_json(CODES_FILE, codes_data)
        return await interaction.followup.send("❌ Tạo link rút gọn thất bại. Vui lòng thử lại.", ephemeral=True)

    # mark pending
    mark_pending(code, str(member.id), yeu_link)
    user["claims_today"] += 1
    # log
    now = datetime.datetime.utcnow().isoformat(sep=' ')
    user["logs"].append(f"{now} | nhanxu | code={code} | link={yeu_link}")
    save_user(member.id, user)

    # send link to user (dm preferred)
    try:
        await member.send(f"🎁 Đây là link rút gọn của bạn:\n{yeu_link}\nSau khi vượt, bạn sẽ được redirect tới trang hiển thị mã và bot sẽ tự cộng {REWARD} xu (hãy nhập /checkxu để xem).")
        await interaction.followup.send("✅ Mã đã gửi vào DM. Kiểm tra tin nhắn riêng.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"⚠️ Không thể gửi DM — link của bạn:\n{yeu_link}", ephemeral=True)

# /redeem manual (optional fallback if web cannot notify)
@bot.tree.command(name="redeem", description="Nhập mã nếu web không tự báo (dự phòng)")
@app_commands.describe(code="Mã nhận được")
async def redeem_cmd(interaction: discord.Interaction, code: str):
    code = code.strip().upper()
    codes_data = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    # check pending where user is owner
    info = codes_data["pending"].get(code)
    if not info or info.get("user_id") != str(interaction.user.id):
        return await interaction.response.send_message("❌ Mã không hợp lệ hoặc không thuộc về bạn.", ephemeral=True)

    # mark used
    mark_used(code, str(interaction.user.id))
    # give reward
    user = load_user(interaction.user.id)
    user["xu"] += REWARD
    now = datetime.datetime.utcnow().isoformat(sep=' ')
    user["logs"].append(f"{now} | redeem(manual) | code={code} | +{REWARD}")
    save_user(interaction.user.id, user)
    await interaction.response.send_message(f"✅ Đã cộng {REWARD} xu cho bạn.", ephemeral=True)

# aiohttp webhook to accept POST from web when code page visited
async def handle_claim(request):
    try:
        data = await request.json()
        code = data.get("code", "").strip().upper()
    except:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    if not code:
        return web.json_response({"ok": False, "error": "missing code"}, status=400)

    codes_data = load_json(CODES_FILE, {"available": [], "pending": {}, "used": {}})
    info = codes_data["pending"].get(code)
    if not info:
        return web.json_response({"ok": False, "error": "code not pending"}, status=404)

    user_id = info.get("user_id")
    # mark used and reward
    mark_used(code, user_id)
    user = load_user(int(user_id))
    user["xu"] += REWARD
    now = datetime.datetime.utcnow().isoformat(sep=' ')
    user["logs"].append(f"{now} | redeem(web) | code={code} | +{REWARD}")
    save_user(int(user_id), user)
    # optionally notify user
    try:
        user_obj = await bot.fetch_user(int(user_id))
        await user_obj.send(f"🎉 Mã `{code}` đã được xác nhận — bạn nhận +{REWARD} xu. Tổng: {user['xu']}")
    except Exception:
        pass
    return web.json_response({"ok": True})

# run aiohttp app in background
async def start_webhook_app():
    app = web.Application()
    app.add_routes([web.post(WEBHOOK_ENDPOINT, handle_claim)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()
    print(f"Webhook server running on http://{WEBHOOK_HOST}:{WEBHOOK_PORT}{WEBHOOK_ENDPOINT}")

# start aiohttp when bot is ready
@bot.event
async def on_connect():
    # start webhook server in background via asyncio.create_task
    bot.loop.create_task(start_webhook_app())

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
