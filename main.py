import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv("token.env")

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")

if not TOKEN:
    print("ERROR: Discord token not found!")
    print("Please set DISCORD_TOKEN in your token.env file or TOKEN in Replit Secrets")
    exit(1)

DANH_MUC_DON_HANG = 1366628630607822868  # ID danh mục tạo kênh

user_data = {}  # Lưu dữ liệu đơn hàng theo user

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("=" * 50)
    print("IMPORTANT: Enable these privileged intents in Discord Developer Portal:")
    print("1. Go to https://discord.com/developers/applications/")
    print(f"2. Select your application (Bot ID: {client.user.id})")
    print("3. Go to 'Bot' section")
    print("4. Enable: SERVER MEMBERS INTENT and MESSAGE CONTENT INTENT")
    print("=" * 50)
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
        print("Bot is ready!")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tree.command(name="dathang", description="Đặt hàng cày thuê Roblox")
@app_commands.describe(goihang="Nhập gói dịch vụ bạn muốn đặt")
async def dathang(interaction: discord.Interaction, goihang: str):
    await interaction.response.send_message("✅ Đơn hàng đã được ghi nhận!", ephemeral=True)
    user_data[interaction.user.id] = {"goihang": goihang, "channel_id": None, "taikhoan": None}

@tree.command(name="thongtintaikhoan", description="Nhập thông tin tài khoản")
@app_commands.describe(thongtin="Nhập user/pass hoặc cách đăng nhập vào tài khoản của bạn")
async def thongtintaikhoan(interaction: discord.Interaction, thongtin: str):
    if interaction.user.id not in user_data:
        await interaction.response.send_message("❌ Bạn chưa đặt đơn hàng nào!", ephemeral=True)
        return
    user_data[interaction.user.id]["taikhoan"] = thongtin
    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=DANH_MUC_DON_HANG)
    index = len([c for c in category.text_channels if c.name.startswith("don-")]) + 1
    channel = await guild.create_text_channel(name=f"don-{index}", category=category)
    user_data[interaction.user.id]["channel_id"] = channel.id
    # Implement button logic...
    await interaction.response.send_message("✅ Đã gửi thông tin vào kênh xử lý đơn.", ephemeral=True)

if __name__ == "__main__":
    try:
        client.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("\n" + "=" * 70)
        print("ERROR: PRIVILEGED INTENTS NOT ENABLED")
        print("=" * 70)
        print("\nYour bot requires privileged intents to work properly.")
        print("\nTo fix this:")
        print("1. Go to: https://discord.com/developers/applications/")
        print("2. Select your bot application")
        print("3. Click on 'Bot' in the left sidebar")
        print("4. Scroll down to 'Privileged Gateway Intents'")
        print("5. Enable these two intents:")
        print("   - SERVER MEMBERS INTENT")
        print("   - MESSAGE CONTENT INTENT")
        print("6. Save changes and restart the bot")
        print("\n" + "=" * 70)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")