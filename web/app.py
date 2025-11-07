from flask import Flask, render_template_string
import json, os

app = Flask(__name__)

# file lưu mã code
CODES_FILE = "../codes.json"

@app.route("/<code>")
def show_code(code):
    # kiểm tra file codes.json tồn tại
    if not os.path.exists(CODES_FILE):
        return "No code file found.", 404

    with open(CODES_FILE, "r") as f:
        codes = json.load(f)

    # tìm code
    for entry in codes:
        if entry["code"] == code:
            html = f"""
            <html>
            <head>
                <title>Redeem Code</title>
                <style>
                    body {{ font-family: sans-serif; text-align:center; margin-top:100px; }}
                    h1 {{ color: #333; }}
                    h2 {{ color: green; }}
                </style>
            </head>
            <body>
                <h1>MÃ CODE CỦA BẠN</h1>
                <h2>{code}</h2>
                <p>Sao chép mã này và nhập lệnh <b>/redeem {code}</b> trên Discord!</p>
            </body>
            </html>
            """
            return render_template_string(html)

    return "Code không tồn tại!", 404

if __name__ == "__main__":
    # lấy port Replit cấp, default 3000 nếu không có
    port = int(os.environ.get("PORT", 3000))
    # chạy web trên tất cả IP, port tự cấp
    app.run(host="0.0.0.0", port=port)
