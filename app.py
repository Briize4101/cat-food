from flask import Flask, request, jsonify, send_from_directory
import os

from dotenv import load_dotenv
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from supabase import create_client
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "change-this-in-env")
jwt = JWTManager(app)
revoked_tokens = set()


@jwt.token_in_blocklist_loader
def is_token_revoked(jwt_header, jwt_payload):
    return jwt_payload.get('jti') in revoked_tokens


PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("請先在 .env 設定 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def init_db():
    try:
        existing = supabase.table("members").select("id").eq("email", "123@test.com").limit(1).execute()
        if existing.data:
            return

        supabase.table("members").insert({
            "email": "123@test.com",
            "password_hash": generate_password_hash("123")
        }).execute()
        print("成功建立測試會員：123@test.com / 123")
    except Exception as error:
        print(f"建立測試會員失敗，請確認 Supabase members table 是否已建立：{error}")


init_db()


@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def home():
    return send_from_directory(PUBLIC_DIR, 'log_in.html')


@app.route('/member.html')
def member_page():
    return send_from_directory(PUBLIC_DIR, 'member.html')


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(PUBLIC_DIR, path)


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "請輸入完整的帳號密碼"})

    try:
        supabase.table("members").insert({
            "email": username,
            "password_hash": generate_password_hash(password)
        }).execute()
        success = True
        message = "註冊成功"
    except Exception:
        success = False
        message = "此 Email 已經被註冊過了！"

    return jsonify({"success": success, "message": message})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    result = supabase.table("members") \
        .select("id,email,password_hash") \
        .eq("email", username) \
        .limit(1) \
        .execute()

    user = result.data[0] if result.data else None

    if user and check_password_hash(user["password_hash"], password):
        access_token = create_access_token(identity=username)
        return jsonify({"success": True, "token": access_token})

    return jsonify({"success": False, "message": "帳號或密碼錯誤"})


@app.route('/api/logout', methods=['GET', 'POST'])
@jwt_required(optional=True)
def logout():
    token_data = get_jwt()
    token_id = token_data.get('jti')
    if token_id:
        revoked_tokens.add(token_id)

    return jsonify({"success": True})


@app.route('/api/check-auth', methods=['GET'])
@jwt_required(optional=True)
def check_auth():
    current_user = get_jwt_identity()

    if current_user:
        return jsonify({"loggedIn": True, "username": current_user})

    return jsonify({"loggedIn": False})


@app.route('/api/cat-food', methods=['GET'])
def get_cat_food():
    fake_cat_food = {
        "id": 1,
        "name": "Salmon Adult Cat Food",
        "price": 499,
        "category": "dry_food",
        "stock": 25
    }

    return jsonify(fake_cat_food)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
