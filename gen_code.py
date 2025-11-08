# gen_code.py
import json
import random
import string
import os

CODES_FILE = "codes.json"
MIN_CODES = 10   # nếu số code ≤ 10 thì sinh thêm
NEW_CODES_COUNT = 40  # số code sinh thêm

# ---------------- Helper ----------------
def load_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_codes(codes):
    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)

def generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

# ---------------- Main ----------------
def ensure_codes():
    codes = load_codes()
    if len(codes) <= MIN_CODES:
        print(f"⚠️ Số code hiện tại: {len(codes)} ≤ {MIN_CODES}, sẽ sinh thêm {NEW_CODES_COUNT} code mới...")
        new_codes = set()
        while len(new_codes) < NEW_CODES_COUNT:
            code = generate_code()
            if code not in codes:
                new_codes.add(code)
        codes.extend(list(new_codes))
        save_codes(codes)
        print(f"✅ Đã thêm {len(new_codes)} code mới. Tổng số code hiện tại: {len(codes)}")
    else:
        print(f"✅ Số code hiện tại: {len(codes)} > {MIN_CODES}, không cần sinh thêm.")

if __name__ == "__main__":
    ensure_codes()
