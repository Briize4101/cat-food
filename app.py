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
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_ANON_KEY
ORDER_ADMIN_PASSWORD = os.getenv("ORDER_ADMIN_PASSWORD")

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
        print("??撱箇?皜祈岫?嚗?23@test.com / 123")
    except Exception as error:
        print(f"撱箇?皜祈岫?憭望?嚗?蝣箄? Supabase members table ?臬撌脣遣蝡?{error}")


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


def require_admin_password():
    if not ORDER_ADMIN_PASSWORD:
        return False, jsonify({
            "success": False,
            "message": "Please set ORDER_ADMIN_PASSWORD in .env"
        }), 500

    provided_password = request.headers.get("X-Admin-Password")
    if provided_password != ORDER_ADMIN_PASSWORD:
        return False, jsonify({"success": False, "message": "Invalid admin password"}), 401

    return True, None, None


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


@app.route('/admin/products')
def product_admin_page():
    return send_from_directory(PUBLIC_DIR, 'product_admin.html')


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(PUBLIC_DIR, path)


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "Please enter email and password"})

    try:
        supabase.table("members").insert({
            "email": username,
            "password_hash": generate_password_hash(password)
        }).execute()
        success = True
        message = "Register success"
    except Exception:
        success = False
        message = "This email is already registered"

    return jsonify({"success": success, "message": message})


@app.route('/api/supabase-config', methods=['GET'])
def get_supabase_config():
    if not SUPABASE_ANON_KEY:
        return jsonify({
            "success": False,
            "message": "Please set SUPABASE_ANON_KEY in .env"
        }), 500

    return jsonify({
        "success": True,
        "supabaseUrl": SUPABASE_URL,
        "supabaseAnonKey": SUPABASE_ANON_KEY
    })


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

    return jsonify({"success": False, "message": "Invalid email or password"})


@app.route('/api/auth/google', methods=['POST'])
def google_login():
    data = request.get_json() or {}
    supabase_access_token = data.get('access_token')

    if not supabase_access_token:
        return jsonify({"success": False, "message": "Missing Google access token"}), 400

    try:
        auth_user = supabase.auth.get_user(supabase_access_token)
        user = getattr(auth_user, "user", None)
        email = getattr(user, "email", None) if user else None
        metadata = getattr(user, "user_metadata", {}) if user else {}

        if not email:
            return jsonify({"success": False, "message": "Google account has no email"}), 400

        existing = supabase.table("members") \
            .select("id,email") \
            .eq("email", email) \
            .limit(1) \
            .execute()

        if not existing.data:
            supabase.table("members").insert({
                "email": email,
                "password_hash": generate_password_hash(os.urandom(32).hex()),
                "name": metadata.get("full_name") or metadata.get("name") or ""
            }).execute()

        access_token = create_access_token(identity=email)
        return jsonify({"success": True, "token": access_token, "email": email})
    except Exception as error:
        return jsonify({"success": False, "message": f"Google login failed: {error}"}), 500


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
        return jsonify({"success": False, "message": "Member not found"}), 404

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
        return jsonify({"success": False, "message": "No member data to update"}), 400

    try:
        result = supabase.table("members") \
            .update(update_data) \
            .eq("email", current_user) \
            .select("id,email,name,phone,address,created_at") \
            .execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"Member profile update failed: {error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "Member not found"}), 404

    return jsonify({"success": True, "message": "Member profile updated", "profile": result.data[0]})

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
        return jsonify({"success": False, "message": f"Product data load failed: {error}"}), 500

    return jsonify({"success": True, "products": result.data})


@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        result = supabase.table("products").select(PRODUCT_FIELDS).eq("id", product_id).limit(1).execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"Product data load failed: {error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "Product not found"}), 404

    return jsonify({"success": True, "product": result.data[0]})

PRODUCT_ADMIN_FIELDS = ["name", "description", "category", "feature", "price", "stock", "image_url", "is_active"]


def clean_product_payload(data, require_name=False):
    payload = {}

    for field in ["name", "description", "category", "feature", "image_url"]:
        if field in data:
            payload[field] = (data.get(field) or "").strip()

    if "price" in data:
        payload["price"] = int(data.get("price") or 0)

    if "stock" in data:
        payload["stock"] = int(data.get("stock") or 0)

    if "is_active" in data:
        payload["is_active"] = bool(data.get("is_active"))

    if require_name and not payload.get("name"):
        raise ValueError("Product name is required")

    return payload


@app.route('/api/admin/products', methods=['GET'])
def admin_get_products():
    is_allowed, response, status_code = require_admin_password()
    if not is_allowed:
        return response, status_code

    try:
        result = supabase.table("products") \
            .select(PRODUCT_FIELDS) \
            .order("id") \
            .execute()
        return jsonify({"success": True, "products": result.data or []})
    except Exception as error:
        return jsonify({"success": False, "message": f"Admin product load failed: {error}"}), 500


@app.route('/api/admin/products', methods=['POST'])
def admin_create_product():
    is_allowed, response, status_code = require_admin_password()
    if not is_allowed:
        return response, status_code

    try:
        payload = clean_product_payload(request.get_json() or {}, require_name=True)
        result = supabase.table("products") \
            .insert(payload) \
            .execute()

        if not result.data:
            return jsonify({"success": False, "message": "Product create failed"}), 500

        return jsonify({"success": True, "product": result.data[0]})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        return jsonify({"success": False, "message": f"Admin product create failed: {error}"}), 500


@app.route('/api/admin/products/<int:product_id>', methods=['PUT'])
def admin_update_product(product_id):
    is_allowed, response, status_code = require_admin_password()
    if not is_allowed:
        return response, status_code

    try:
        payload = clean_product_payload(request.get_json() or {})
        if not payload:
            return jsonify({"success": False, "message": "No product data to update"}), 400

        result = supabase.table("products") \
            .update(payload) \
            .eq("id", product_id) \
            .execute()

        if not result.data:
            return jsonify({"success": False, "message": "Product not found"}), 404

        return jsonify({"success": True, "product": result.data[0]})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        return jsonify({"success": False, "message": f"Admin product update failed: {error}"}), 500


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
        return jsonify({"success": False, "message": "Member not found"}), 404

    try:
        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"Cart load failed: {error}"}), 500


@app.route('/api/cart/items', methods=['POST'])
@jwt_required()
def add_cart_item():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    data = request.get_json() or {}

    try:
        product_id = int(data.get("product_id"))
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Product ID format is invalid"}), 400

    if quantity < 1:
        return jsonify({"success": False, "message": "Quantity must be at least 1"}), 400

    try:
        product_result = supabase.table("products") \
            .select("id,is_active") \
            .eq("id", product_id) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()

        if not product_result.data:
            return jsonify({"success": False, "message": "Product cannot be added to cart"}), 404

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
        cart["message"] = "Added to cart"
        return jsonify(cart)
    except Exception as error:
        return jsonify({"success": False, "message": f"Add to cart failed: {error}"}), 500


@app.route('/api/cart/items/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_cart_item(product_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    data = request.get_json() or {}

    try:
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Quantity format is invalid"}), 400

    if quantity < 1:
        return jsonify({"success": False, "message": "Quantity must be at least 1"}), 400

    try:
        result = supabase.table("cart_items") \
            .update({"quantity": quantity, "updated_at": utc_now_iso()}) \
            .eq("member_id", member["id"]) \
            .eq("product_id", product_id) \
            .execute()

        if not result.data:
            return jsonify({"success": False, "message": "Cart item not found"}), 404

        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"Cart update failed: {error}"}), 500


@app.route('/api/cart/items/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_cart_item(product_id):
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    try:
        supabase.table("cart_items") \
            .delete() \
            .eq("member_id", member["id"]) \
            .eq("product_id", product_id) \
            .execute()

        return jsonify(build_cart_response(member["id"]))
    except Exception as error:
        return jsonify({"success": False, "message": f"Cart item delete failed: {error}"}), 500


@app.route('/api/cart', methods=['DELETE'])
@jwt_required()
def clear_cart():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    try:
        supabase.table("cart_items") \
            .delete() \
            .eq("member_id", member["id"]) \
            .execute()

        return jsonify({"success": True, "items": [], "total": 0})
    except Exception as error:
        return jsonify({"success": False, "message": f"Cart clear failed: {error}"}), 500
ORDER_ITEM_FIELDS = "id,order_id,product_id,quantity,unit_price,line_total,created_at,products(id,name,image_url)"


def format_order(order, items):
    return {
        "id": order.get("id"),
        "member_id": order.get("member_id"),
        "status": order.get("status"),
        "total_amount": order.get("total_amount"),
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at"),
        "items": items
    }


@app.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    data = request.get_json() or {}
    product_ids = data.get("product_ids") or []

    if not isinstance(product_ids, list) or not product_ids:
        return jsonify({"success": False, "message": "Please choose products to checkout"}), 400

    try:
        product_ids = [int(product_id) for product_id in product_ids]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Product format is invalid"}), 400

    try:
        cart_result = supabase.table("cart_items") \
            .select(CART_ITEM_FIELDS) \
            .eq("member_id", member["id"]) \
            .in_("product_id", product_ids) \
            .execute()

        cart_items = cart_result.data or []
        if not cart_items:
            return jsonify({"success": False, "message": "Selected cart items not found"}), 404

        order_items = []
        total_amount = 0

        for cart_item in cart_items:
            product = cart_item.get("products") or {}
            if not product.get("is_active"):
                return jsonify({"success": False, "message": "Selected product includes inactive product"}), 400

            quantity = int(cart_item.get("quantity") or 1)
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
            return jsonify({"success": False, "message": "Order create failed"}), 500

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
            "message": "Order created",
            "order": order,
            "cart": cart
        })
    except Exception as error:
        return jsonify({"success": False, "message": f"Order create failed: {error}"}), 500


@app.route('/api/orders', methods=['GET'])
@jwt_required()
def get_orders():
    member = get_current_member()
    if not member:
        return jsonify({"success": False, "message": "Member not found"}), 404

    try:
        orders_result = supabase.table("orders") \
            .select("id,member_id,status,total_amount,created_at,updated_at") \
            .eq("member_id", member["id"]) \
            .order("id", desc=True) \
            .execute()

        orders = orders_result.data or []
        for order in orders:
            items_result = supabase.table("order_items") \
                .select(ORDER_ITEM_FIELDS) \
                .eq("order_id", order["id"]) \
                .execute()
            order["items"] = items_result.data or []

        return jsonify({"success": True, "orders": orders})
    except Exception as error:
        return jsonify({"success": False, "message": f"Order load failed: {error}"}), 500

@app.route('/api/cat-food', methods=['GET'])
def get_cat_food():
    try:
        result = supabase.table("products") \
            .select(PRODUCT_FIELDS) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()
    except Exception as error:
        return jsonify({"success": False, "message": f"Product data load failed: {error}"}), 500

    if not result.data:
        return jsonify({"success": False, "message": "No product data"}), 404

    return jsonify(result.data[0])


if __name__ == '__main__':
    app.run(debug=True, port=5000)







