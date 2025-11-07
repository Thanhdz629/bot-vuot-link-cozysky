from flask import Flask, render_template_string, jsonify
import json, os, requests, pathlib
from dotenv import load_dotenv
from pyngrok import ngrok
import atexit

load_dotenv()

app = Flask(__name__)

DATA_DIR = pathlib.Path("../data")
CODES_FILE = DATA_DIR / "codes.json"
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "")

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
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                text-align: center;
                margin: 0;
                padding: 50px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
            }
            h1 { margin-bottom: 10px; font-size: 2.5em; }
            hr { border: 0; height: 1px; background: rgba(255,255,255,0.3); margin: 30px 0; }
            ol {
                text-align: left;
                background: rgba(255,255,255,0.1);
                padding: 30px 30px 30px 50px;
                border-radius: 10px;
                margin: 20px 0;
            }
            li { margin: 15px 0; line-height: 1.6; }
            code {
                background: rgba(0,0,0,0.3);
                padding: 4px 8px;
                border-radius: 4px;
                font-family: monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎁 YeuMoney Bot</h1>
            <p>Hệ thống nhận xu tự động qua Discord</p>
            <hr>
            <h3>📋 Hướng dẫn sử dụng:</h3>
            <ol>
                <li>Dùng lệnh <code>/nhanxu</code> trên Discord để nhận link</li>
                <li>Vượt link YeuMoney</li>
                <li>Bạn sẽ được chuyển đến trang hiển thị mã</li>
                <li>Bot sẽ tự động cộng xu cho bạn</li>
                <li>Dùng <code>/checkxu</code> để kiểm tra số xu</li>
            </ol>
            <p style="margin-top: 30px; opacity: 0.8;">⏰ Mỗi người được nhận 2 lần/ngày</p>
        </div>
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
            webhook_url = "http://localhost:8080/webhook/claim"
            requests.post(webhook_url, json={"code": code}, timeout=5)
        except Exception as e:
            print(f"Failed to notify bot: {e}")
        
        return render_template_string(f"""
        <html>
        <head>
            <title>Redeem Code</title>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    text-align: center;
                    margin: 0;
                    padding: 50px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                }}
                .container {{
                    max-width: 500px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 50px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
                }}
                h1 {{ font-size: 2.5em; margin-bottom: 20px; }}
                .code {{
                    background: rgba(255,255,255,0.2);
                    padding: 20px 30px;
                    border-radius: 10px;
                    font-size: 2em;
                    font-weight: bold;
                    margin: 30px 0;
                    letter-spacing: 2px;
                }}
                .note {{
                    opacity: 0.8;
                    font-size: 0.9em;
                    margin-top: 30px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎉 MÃ CODE CỦA BẠN</h1>
                <div class="code">{code}</div>
                <p>✅ Mã của bạn đã được xác nhận!</p>
                <p>Bot Discord sẽ tự động cộng xu cho bạn.</p>
                <p class="note">Nếu không nhận được xu, hãy dùng: <code>/redeem {code}</code></p>
            </div>
        </body>
        </html>
        """)
    
    # Check if already used
    if code in codes.get("used", {}):
        return render_template_string("""
        <html>
        <head>
            <title>Code đã sử dụng</title>
            <meta charset="utf-8">
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    text-align: center;
                    margin: 0;
                    padding: 50px 20px;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                    min-height: 100vh;
                }
                .container {
                    max-width: 500px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 50px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚠️ Code đã được sử dụng</h1>
                <p>Mã này đã được redeem trước đó.</p>
            </div>
        </body>
        </html>
        """)
    
    return render_template_string("""
    <html>
    <head>
        <title>Code không hợp lệ</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                text-align: center;
                margin: 0;
                padding: 50px 20px;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                max-width: 500px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                padding: 50px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>❌ Code không tồn tại</h1>
            <p>Mã này không hợp lệ hoặc chưa được phát hành.</p>
        </div>
    </body>
    </html>
    """), 404

if __name__ == "__main__":
    port = 5000
    
    # Start ngrok tunnel if auth token is available
    if NGROK_AUTH_TOKEN:
        try:
            ngrok.set_auth_token(NGROK_AUTH_TOKEN)
            # Open tunnel
            public_url = ngrok.connect(port, bind_tls=True)
            print("=" * 70)
            print("🌐 NGROK TUNNEL ACTIVE")
            print("=" * 70)
            print(f"📡 Public URL: {public_url}")
            print(f"📡 Local:      http://localhost:{port}")
            print("=" * 70)
            print("\n⚠️  IMPORTANT: Update WEB_BASE in .env with the ngrok URL above!")
            print(f"    WEB_BASE={public_url}\n")
            
            # Register cleanup
            atexit.register(lambda: ngrok.disconnect(public_url))
        except Exception as e:
            print(f"⚠️  Warning: Could not start ngrok tunnel: {e}")
            print(f"   Running on local port {port} only")
    else:
        print("=" * 70)
        print("⚠️  NGROK_AUTH_TOKEN not found!")
        print("=" * 70)
        print("To use ngrok:")
        print("1. Get your auth token from https://dashboard.ngrok.com/get-started/your-authtoken")
        print("2. Add to Replit Secrets: NGROK_AUTH_TOKEN=your_token_here")
        print("3. Restart the web server")
        print("=" * 70)
        print(f"\n📡 Running on local port {port} only\n")
    
    # Start Flask app
    app.run(host="0.0.0.0", port=port, debug=False)
