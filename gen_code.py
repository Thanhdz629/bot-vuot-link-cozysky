# cogs/auto_gen_code.py
import discord
from discord.ext import commands, tasks
import json
import random
import string
import os

CODES_FILE = "codes.json"
MIN_CODES = 10       # Nếu số code ≤ 10 thì sinh thêm
NEW_CODES_COUNT = 40 # Số code sinh thêm

ADMIN_ID = 1176476598157967380  # user nhận DM

class AutoGenCodeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_gen_codes.start()  # start task khi cog load

    def cog_unload(self):
        self.auto_gen_codes.cancel()  # hủy task khi cog unload

    # ---------------- Helper ----------------
    def load_codes(self):
        if os.path.exists(CODES_FILE):
            with open(CODES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_codes(self, codes):
        with open(CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False, indent=2)

    def generate_code(self, length=8):
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=length))

    # ---------------- Task Loop ----------------
    @tasks.loop(minutes=1)  # chạy mỗi 1 phút
    async def auto_gen_codes(self):
        codes = self.load_codes()
        if len(codes) <= MIN_CODES:
            new_codes = set()
            while len(new_codes) < NEW_CODES_COUNT:
                code = self.generate_code()
                if code not in codes:
                    new_codes.add(code)
            codes.extend(list(new_codes))
            self.save_codes(codes)

            # gửi DM cho admin
            user = self.bot.get_user(ADMIN_ID)
            if not user:
                try:
                    user = await self.bot.fetch_user(ADMIN_ID)
                except:
                    user = None
            if user:
                try:
                    await user.send(f"🎉 Đã sinh {len(new_codes)} code mới! Tổng số code hiện tại: {len(codes)}")
                except discord.Forbidden:
                    print(f"Không thể gửi DM cho user {ADMIN_ID}")

    @auto_gen_codes.before_loop
    async def before_auto_gen(self):
        await self.bot.wait_until_ready()  # đợi bot ready

async def setup(bot):
    await bot.add_cog(AutoGenCodeCog(bot))