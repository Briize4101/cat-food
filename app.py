from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timezone
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

def get_current_member():
    current_user = get_jwt_identity()

    if not current_user:
        return None

    result = supabase.table("members") \
        .select("id,email") \
        .eq("email", current_user) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


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


@app.route('/api/member/profile', methods=['GET'])
@jwt_required()
def get_member_profile():
    current_user = get_jwt_identity()

    result = supabase.table("members") \
        .select("id,email,name,phone,address,created_at") \
        .eq("email", current_user) \
        .limit(1) \
        .execute()

    if not result.data:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    return jsonify({"success": True, "profile": result.data[0]})


@app.route('/api/member/profile', methods=['PUT'])
@jwt_required()
def update_member_profile():
    current_user = get_jwt_identity()
    data = request.get_json() or {}

    allowed_fields = ["name", "phone", "address"]
    update_data = {
        field: data.get(field)
        for field in allowed_fields
        if field in data
    }

    if not update_data:
        return jsonify({"success": False, "message": "沒有可更新的會員資料"}), 400

    try:
        result = supabase.table("members") \
            .update(update_data) \
            .eq("email", current_user) \
            .select("id,email,name,phone,address,created_at") \
            .execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"會員資料更新失敗：{error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    return jsonify({"success": True, "message": "會員資料已更新", "profile": result.data[0]})

PRODUCT_FIELDS = "id,name,description,category,feature,price,stock,image_url,is_active,created_at"


@app.route('/api/products', methods=['GET'])
def get_products():
    category = request.args.get('category')
    include_inactive = request.args.get('include_inactive') == 'true'

    query = supabase.table("products").select(PRODUCT_FIELDS).order("id")

    if category:
        query = query.eq("category", category)

    if not include_inactive:
        query = query.eq("is_active", True)

    try:
        result = query.execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"商品資料讀取失敗：{error}"}), 500

    return jsonify({"success": True, "products": result.data})


@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        result = supabase.table("products").select(PRODUCT_FIELDS).eq("id", product_id).limit(1).execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"商品資料讀取失敗：{error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "找不到商品資料"}), 404

    return jsonify({"success": True, "product": result.data[0]})

CART_ITEM_FIELDS = "id,product_id,quantity,created_at,updated_at,products(id,name,price,image_url,stock,is_active)"


def format_cart_item(item):
    product = item.get("products") or {}
    quantity = int(item.get("quantity") or 1)
    price = product.get("price") or 0

    return {
        "id": item.get("id"),
        "product_id": item.get("product_id"),
        "quantity": quantity,
        "product": product,
        "line_total": int(price) * quantity if isinstance(price, int) else float(price or 0) * quantity,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at")
    }


def build_cart_response(member_id):
    result = supabase.table("cart_items") \
        .select(CART_ITEM_FIELDS) \
        .eq("member_id", member_id) \
        .order("id") \
        .execute()

    items = [format_cart_item(item) for item in (result.data or [])]
    total = sum(item["line_total"] for item in items)

    return {"success": True, "items": items, "total": total}


@app.route('/api/cart', methods=['GET'])
@jwt_required()
def get_cart():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    try:
        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"購物車讀取失敗：{error}"}), 500


@app.route('/api/cart/items', methods=['POST'])
@jwt_required()
def add_cart_item():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    data = request.get_json() or {}

    try:
        product_id = int(data.get("product_id"))
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "商品或數量格式錯誤"}), 400

    if quantity < 1:
        return jsonify({"success": False, "message": "數量至少要是 1"}), 400

    try:
        product_result = supabase.table("products") \
            .select("id,is_active") \
            .eq("id", product_id) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()

        if not product_result.data:
            return jsonify({"success": False, "message": "找不到可加入購物車的商品"}), 404

        existing_result = supabase.table("cart_items") \
            .select("id,quantity") \
            .eq("member_id", member["id"]) \
            .eq("product_id", product_id) \
            .limit(1) \
            .execute()

        if existing_result.data:
            existing_item = existing_result.data[0]
            supabase.table("cart_items") \
                .update({"quantity": existing_item["quantity"] + quantity, "updated_at": utc_now_iso()}) \
                .eq("id", existing_item["id"]) \
                .execute()
        else:
            supabase.table("cart_items") \
                .insert({"member_id": member["id"], "product_id": product_id, "quantity": quantity}) \
                .execute()

        cart = build_cart_response(member["id"])
        cart["message"] = "已加入購物車"
        return jsonify(cart)
    except Exception as error:
        return jsonify({"success": False, "message": f"加入購物車失敗：{error}"}), 500


@app.route('/api/cart/items/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_cart_item(product_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    data = request.get_json() or {}

    try:
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "數量格式錯誤"}), 400

    if quantity < 1:
        return jsonify({"success": False, "message": "數量至少要是 1"}), 400

    try:
        result = supabase.table("cart_items") \
            .update({"quantity": quantity, "updated_at": utc_now_iso()}) \
            .eq("member_id", member["id"]) \
            .eq("product_id", product_id) \
            .execute()

        if not result.data:
            return jsonify({"success": False, "message": "購物車內沒有這項商品"}), 404

        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"購物車更新失敗：{error}"}), 500


@app.route('/api/cart/items/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_cart_item(product_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    try:
        supabase.table("cart_items") \
            .delete() \
            .eq("member_id", member["id"]) \
            .eq("product_id", product_id) \
            .execute()

        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"購物車刪除失敗：{error}"}), 500


@app.route('/api/cart', methods=['DELETE'])
@jwt_required()
def clear_cart():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    try:
        supabase.table("cart_items") \
            .delete() \
            .eq("member_id", member["id"]) \
            .execute()

        return jsonify({"success": True, "items": [], "total": 0})
    except Exception as error:
        return jsonify({"success": False, "message": f"購物車清空失敗：{error}"}), 500

@app.route('/api/cat-food', methods=['GET'])
def get_cat_food():
    try:
        result = supabase.table("products") \
            .select(PRODUCT_FIELDS) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"商品資料讀取失敗：{error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "目前沒有商品資料"}), 404

    return jsonify(result.data[0])


if __name__ == '__main__':
    app.run(debug=True, port=5000)





