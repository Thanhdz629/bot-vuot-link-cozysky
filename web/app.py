from flask import Flask, render_template_string, jsonify
import json, os, requests, pathlib
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATA_DIR = pathlib.Path("../data")
CODES_FILE = DATA_DIR / "codes.json"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")  # optional: webhook to bot

def load_codes():
    if not CODES_FILE.exists():
        return {"available": [], "pending": {}, "used": {}}
    with open(CODES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/")
def index():
    return render_template_string("""
    <html>
    <head>
        <title>YeuMoney Bot - Code Redemption</title>
        <meta charset="utf-8">
    </head>
    <body style="font-family: sans-serif; text-align:center; margin-top:100px;">
        <h1>🎁 YeuMoney Bot</h1>
        <p>Hệ thống nhận xu tự động qua Discord</p>
        <hr style="width: 50%; margin: 30px auto;">
        <h3>Hướng dẫn sử dụng:</h3>
        <ol style="text-align: left; max-width: 500px; margin: 0 auto;">
            <li>Dùng lệnh <code>/nhanxu</code> trên Discord để nhận link</li>
            <li>Vượt link YeuMoney</li>
            <li>Bạn sẽ được chuyển đến trang hiển thị mã</li>
            <li>Bot sẽ tự động cộng xu cho bạn</li>
            <li>Dùng <code>/checkxu</code> để kiểm tra số xu</li>
        </ol>
        <p style="margin-top: 30px; color: gray;">Mỗi người được nhận 2 lần/ngày</p>
    </body>
    </html>
    """)

@app.route("/<code>")
def show_code(code):
    code = code.strip().upper()
    codes = load_codes()
    
    # Check if code is in pending (meaning user has claimed it)
    if code in codes.get("pending", {}):
        info = codes["pending"][code]
        
        # Notify bot via webhook endpoint
        try:
            webhook_url = f"http://localhost:8080/webhook/claim"
            requests.post(webhook_url, json={"code": code}, timeout=5)
        except Exception as e:
            print(f"Failed to notify bot: {e}")
        
        html = f"""
        <html>
        <head>
            <title>Redeem Code</title>
            <meta charset="utf-8">
        </head>
        <body style="font-family: sans-serif; text-align:center; margin-top:100px;">
            <h1>🎉 MÃ CODE CỦA BẠN</h1>
            <h2 style="color:green;">{code}</h2>
            <p>Mã của bạn đã được xác nhận!</p>
            <p>Bot Discord sẽ tự động cộng xu cho bạn.</p>
            <p style="color: gray; font-size: 12px;">Nếu không nhận được xu, hãy dùng: <b>/redeem {code}</b></p>
        </body>
        </html>
        """
        return render_template_string(html)
    
    # Check if already used
    if code in codes.get("used", {}):
        return render_template_string("""
        <html>
        <head><title>Code đã sử dụng</title><meta charset="utf-8"></head>
        <body style="font-family: sans-serif; text-align:center; margin-top:100px;">
            <h1>⚠️ Code đã được sử dụng</h1>
            <p>Mã này đã được redeem trước đó.</p>
        </body>
        </html>
        """)
    
    return render_template_string("""
    <html>
    <head><title>Code không hợp lệ</title><meta charset="utf-8"></head>
    <body style="font-family: sans-serif; text-align:center; margin-top:100px;">
        <h1>❌ Code không tồn tại</h1>
        <p>Mã này không hợp lệ hoặc chưa được phát hành.</p>
    </body>
    </html>
    """), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
