import discord
from discord.ext import commands
from discord import app_commands
import asyncio

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

TOKEN = "YOUR_TOKEN_HERE"
DANH_MUC_DON_HANG = 1366628630607822868  # ID danh mục tạo kênh

user_data = {}  # Lưu dữ liệu đơn hàng theo user

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tree.command(name="dathang", description="Đặt hàng cày thuê Roblox")
@app_commands.describe(goihang="Nhập gói dịch vụ bạn muốn đặt (ví dụ: Farm trái ác quỷ, Cày Level...)")
async def dathang(interaction: discord.Interaction, goihang: str):
    await interaction.response.send_message("✅ Đơn hàng đã được ghi nhận! Vui lòng nhập thông tin tài khoản bằng lệnh /thongtintaikhoan", ephemeral=True)

    user_data[interaction.user.id] = {
        "goihang": goihang,
        "channel_id": None,
        "taikhoan": None
    }

    await interaction.user.send(f"💬 Bạn vừa đặt gói **{goihang}**.\n💵 Giá: (chèn giá tương ứng)\n⏳ Đang đợi nhân viên tiếp nhận đơn...")

@tree.command(name="thongtintaikhoan", description="Nhập thông tin tài khoản để nhân viên xử lý đơn hàng")
@app_commands.describe(thongtin="Nhập user/pass hoặc cách đăng nhập vào tài khoản của bạn")
async def thongtintaikhoan(interaction: discord.Interaction, thongtin: str):
    if interaction.user.id not in user_data:
        await interaction.response.send_message("❌ Bạn chưa đặt đơn hàng nào!", ephemeral=True)
        return

    user_data[interaction.user.id]["taikhoan"] = thongtin

    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=DANH_MUC_DON_HANG)
    index = len([c for c in category.text_channels if c.name.startswith("don-")]) + 1
    channel = await guild.create_text_channel(
        name=f"don-{index}",
        category=category
    )

    user_data[interaction.user.id]["channel_id"] = channel.id

    # Nút nhận và không nhận
    class NhanDonView(discord.ui.View):
        @discord.ui.button(label="✅ Nhận", style=discord.ButtonStyle.green)
        async def nhan(self, interaction_nhan: discord.Interaction, button: discord.ui.Button):
            await channel.send(f"👤 Đơn hàng từ <@{interaction.user.id}> được nhận bởi <@{interaction_nhan.user.id}>")
            await interaction.user.send(f"🎉 Đơn hàng **{user_data[interaction.user.id]['goihang']}** đã được nhân viên <@{interaction_nhan.user.id}> tiếp nhận.")
            await channel.send(f"🔐 Thông tin tài khoản: `{thongtin}`")
            self.clear_items()
            await interaction_nhan.response.edit_message(view=self)

        @discord.ui.button(label="❌ Không nhận", style=discord.ButtonStyle.red)
        async def khongnhan(self, interaction_ko: discord.Interaction, button: discord.ui.Button):
            await channel.send(f"❌ <@{interaction_ko.user.id}> đã từ chối nhận đơn hàng này.")
            self.clear_items()
            await interaction_ko.response.edit_message(view=self)

    await channel.send(
        f"📥 Đơn hàng từ <@{interaction.user.id}>:\n💼 Gói: `{user_data[interaction.user.id]['goihang']}`\n\n👉 Nhấn nút bên dưới để nhận hoặc từ chối.",
        view=NhanDonView()
    )
    await interaction.response.send_message("✅ Đã gửi thông tin vào kênh xử lý đơn.", ephemeral=True)

client.run(TOKEN)
