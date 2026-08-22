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


@app.route('/api/supabase-config', methods=['GET'])
def supabase_config():
    anon_key = os.getenv("SUPABASE_ANON_KEY")

    if not SUPABASE_URL or not anon_key:
        return jsonify({
            "success": False,
            "message": "Please set SUPABASE_URL and SUPABASE_ANON_KEY in .env"
        }), 500

    return jsonify({
        "success": True,
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": anon_key
    })


@app.route('/api/auth/google', methods=['POST'])
def google_login():
    data = request.get_json() or {}
    access_token = data.get('access_token')

    if not access_token:
        return jsonify({"success": False, "message": "Missing Google access token"}), 400

    try:
        user_response = supabase.auth.get_user(access_token)
        google_user = user_response.user

        if not google_user or not google_user.email:
            return jsonify({"success": False, "message": "Google account email not found"}), 400

        email = google_user.email
        metadata = google_user.user_metadata or {}
        name = metadata.get("full_name") or metadata.get("name") or email

        existing = supabase.table("members") \
            .select("id,email,name") \
            .eq("email", email) \
            .limit(1) \
            .execute()

        if existing.data:
            member = existing.data[0]
            if name and not member.get("name"):
                supabase.table("members") \
                    .update({"name": name}) \
                    .eq("id", member["id"]) \
                    .execute()
        else:
            supabase.table("members").insert({
                "email": email,
                "name": name,
                "password_hash": generate_password_hash(os.urandom(24).hex())
            }).execute()

        website_token = create_access_token(identity=email)
        return jsonify({"success": True, "token": website_token})
    except Exception as error:
        print("Google login failed:", error)
        return jsonify({"success": False, "message": "Google login failed"}), 401


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "請輸入完整的帳號密碼"})

    existing = supabase.table("members") \
        .select("id") \
        .eq("email", username) \
        .limit(1) \
        .execute()

    if existing.data:
        return jsonify({
            "success": False,
            "message": "此 Email 已經被註冊過了！"
        })
    
    try:
        supabase.table("members").insert({
            "email": username,
            "password_hash": generate_password_hash(password)
        }).execute()
        success = True
        message = "註冊成功"
    except Exception as error:
        print(error)
        success = False
        message = "註冊失敗，請稍後再試"

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
ORDER_FIELDS = "id,member_id,status,total_amount,recipient_name,recipient_address,created_at,updated_at"
ORDER_ITEM_FIELDS = "id,order_id,product_id,quantity,unit_price,line_total,created_at,products(id,name,image_url)"


def get_member_order(member_id, order_id):
    result = supabase.table("orders") \
        .select(ORDER_FIELDS) \
        .eq("id", order_id) \
        .eq("member_id", member_id) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def attach_order_items(order):
    items_result = supabase.table("order_items") \
        .select(ORDER_ITEM_FIELDS) \
        .eq("order_id", order["id"]) \
        .execute()

    order["items"] = items_result.data or []
    return order


def deactivate_product_if_out_of_stock(product_id, stock):
    if stock <= 0:
        supabase.table("products") \
            .update({"stock": 0, "is_active": False}) \
            .eq("id", product_id) \
            .execute()


@app.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    data = request.get_json() or {}
    product_ids = data.get("product_ids") or []

    if not isinstance(product_ids, list) or not product_ids:
        return jsonify({"success": False, "message": "請先選擇要結帳的商品"}), 400

    try:
        product_ids = [int(product_id) for product_id in product_ids]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "商品格式錯誤"}), 400

    try:
        cart_result = supabase.table("cart_items") \
            .select(CART_ITEM_FIELDS) \
            .eq("member_id", member["id"]) \
            .in_("product_id", product_ids) \
            .execute()

        cart_items = cart_result.data or []
        if not cart_items:
            return jsonify({"success": False, "message": "購物車內沒有選取的商品"}), 404

        order_items = []
        total_amount = 0

        for cart_item in cart_items:
            product = cart_item.get("products") or {}
            quantity = int(cart_item.get("quantity") or 1)
            stock = int(product.get("stock") or 0)

            if not product.get("is_active") or stock <= 0:
                deactivate_product_if_out_of_stock(cart_item.get("product_id"), stock)
                return jsonify({"success": False, "message": "Selected product is not available"}), 400

            if quantity > stock:
                return jsonify({"success": False, "message": f"Only {stock} item(s) in stock"}), 400

            unit_price = int(product.get("price") or 0)
            line_total = unit_price * quantity
            total_amount += line_total
            order_items.append({
                "product_id": cart_item.get("product_id"),
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total
            })

        order_result = supabase.table("orders") \
            .insert({
                "member_id": member["id"],
                "status": "pending_payment",
                "total_amount": total_amount
            }) \
            .execute()

        if not order_result.data:
            return jsonify({"success": False, "message": "訂單建立失敗"}), 500

        order = order_result.data[0]
        for item in order_items:
            item["order_id"] = order["id"]

        item_result = supabase.table("order_items") \
            .insert(order_items) \
            .execute()

        for product_id in product_ids:
            supabase.table("cart_items") \
                .delete() \
                .eq("member_id", member["id"]) \
                .eq("product_id", product_id) \
                .execute()

        order["items"] = item_result.data or []
        cart = build_cart_response(member["id"])
        return jsonify({
            "success": True,
            "message": "訂單已建立",
            "order": order,
            "cart": cart
        })
    except Exception as error:
        return jsonify({"success": False, "message": f"訂單建立失敗：{error}"}), 500


@app.route('/api/orders', methods=['GET'])
@jwt_required()
def get_orders():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    try:
        orders_result = supabase.table("orders") \
            .select(ORDER_FIELDS) \
            .eq("member_id", member["id"]) \
            .order("id", desc=True) \
            .execute()

        orders = [attach_order_items(order) for order in (orders_result.data or [])]
        return jsonify({"success": True, "orders": orders})
    except Exception as error:
        return jsonify({"success": False, "message": f"訂單讀取失敗：{error}"}), 500


@app.route('/api/orders/<int:order_id>', methods=['GET'])
@jwt_required()
def get_order(order_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    order = get_member_order(member["id"], order_id)
    if not order:
        return jsonify({"success": False, "message": "找不到訂單"}), 404

    return jsonify({"success": True, "order": attach_order_items(order)})


@app.route('/api/orders/<int:order_id>/recipient', methods=['PUT'])
@jwt_required()
def update_order_recipient(order_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    data = request.get_json() or {}
    recipient_name = (data.get("recipient_name") or "").strip()
    recipient_address = (data.get("recipient_address") or "").strip()

    if not recipient_name or not recipient_address:
        return jsonify({
            "success": False,
            "message": "Please enter recipient name and recipient address"
        }), 400

    order = get_member_order(member["id"], order_id)
    if not order:
        return jsonify({"success": False, "message": "找不到訂單"}), 404

    if order.get("status") not in {"pending_payment", "payment_failed"}:
        return jsonify({
            "success": False,
            "message": "Recipient information can only be updated before payment is confirmed"
        }), 400

    result = supabase.table("orders") \
        .update({
            "recipient_name": recipient_name,
            "recipient_address": recipient_address,
            "updated_at": utc_now_iso()
        }) \
        .eq("id", order_id) \
        .eq("member_id", member["id"]) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({
        "success": True,
        "message": "Payment information submitted. Please wait for admin confirmation.",
        "order": updated_order
    })


@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_order(order_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "找不到會員資料"}), 404

    order = get_member_order(member["id"], order_id)
    if not order:
        return jsonify({"success": False, "message": "找不到訂單"}), 404

    if order.get("status") not in {"pending_payment", "payment_failed"}:
        return jsonify({
            "success": False,
            "message": "Only unpaid orders can be cancelled"
        }), 400

    result = supabase.table("orders") \
        .update({"status": "cancelled", "updated_at": utc_now_iso()}) \
        .eq("id", order_id) \
        .eq("member_id", member["id"]) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({"success": True, "message": "Order cancelled", "order": updated_order})

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



