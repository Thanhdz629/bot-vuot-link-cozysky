from flask import Flask, render_template_string
import json, os

app = Flask(__name__)

CODES_FILE = "../codes.json"

@app.route("/<code>")
def show_code(code):
    if not os.path.exists(CODES_FILE):
        return "No code file found.", 404
    with open(CODES_FILE, "r") as f:
        codes = json.load(f)

    for entry in codes:
        if entry["code"] == code:
            html = f"""
            <html><head><title>Redeem Code</title></head>
            <body style="font-family: sans-serif; text-align:center; margin-top:100px;">
                <h1>MÃ CODE CỦA BẠN</h1>
                <h2 style="color:green;">{code}</h2>
                <p>Sao chép mã này và nhập lệnh <b>/redeem {code}</b> trên Discord!</p>
            </body></html>
            """
            return render_template_string(html)

    return "Code không tồn tại!", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
