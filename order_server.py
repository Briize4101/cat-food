from datetime import datetime, timezone
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'change-this-in-env')
jwt = JWTManager(app)

PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
ORDER_ADMIN_PASSWORD = os.getenv('ORDER_ADMIN_PASSWORD')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError('請先在 .env 設定 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CART_ITEM_FIELDS = 'id,product_id,quantity,created_at,updated_at,products(id,name,price,image_url,stock,is_active)'
ORDER_FIELDS = 'id,member_id,status,total_amount,recipient_name,recipient_address,created_at,updated_at'
ORDER_ITEM_FIELDS = 'id,order_id,product_id,quantity,unit_price,line_total,created_at,products(id,name,image_url)'
VALID_ORDER_STATUSES = {
    'pending_payment',
    'paid',
    'processing',
    'shipped',
    'completed',
    'cancelled',
    'payment_failed'
}
ALLOWED_STATUS_TRANSITIONS = {
    'pending_payment': {'paid', 'payment_failed', 'cancelled'},
    'payment_failed': {'pending_payment', 'paid', 'cancelled'},
    'paid': {'processing'},
    'processing': {'shipped'},
    'shipped': {'completed'},
    'completed': set(),
    'cancelled': set()
}


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:5000'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def deactivate_product_if_out_of_stock(product_id, stock):
    if stock <= 0:
        supabase.table('products') \
            .update({'stock': 0, 'is_active': False}) \
            .eq('id', product_id) \
            .execute()


def apply_successful_payment_stock_update(order_id):
    items_result = supabase.table('order_items') \
        .select('product_id,quantity') \
        .eq('order_id', order_id) \
        .execute()

    for item in items_result.data or []:
        product_id = item.get('product_id')
        quantity = int(item.get('quantity') or 0)
        product_result = supabase.table('products') \
            .select('id,stock') \
            .eq('id', product_id) \
            .limit(1) \
            .execute()

        if not product_result.data:
            continue

        current_stock = int(product_result.data[0].get('stock') or 0)
        next_stock = max(0, current_stock - quantity)
        supabase.table('products') \
            .update({'stock': next_stock, 'is_active': next_stock > 0}) \
            .eq('id', product_id) \
            .execute()


def remove_paid_order_items_from_cart(member_id, order_id):
    items_result = supabase.table('order_items') \
        .select('product_id') \
        .eq('order_id', order_id) \
        .execute()

    for item in items_result.data or []:
        product_id = item.get('product_id')
        if product_id is None:
            continue

        supabase.table('cart_items') \
            .delete() \
            .eq('member_id', member_id) \
            .eq('product_id', product_id) \
            .execute()

def get_current_member():
    current_user = get_jwt_identity()
    if not current_user:
        return None

    result = supabase.table('members') \
        .select('id,email,name,address') \
        .eq('email', current_user) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def format_cart_item(item):
    product = item.get('products') or {}
    quantity = int(item.get('quantity') or 1)
    price = int(product.get('price') or 0)

    return {
        'id': item.get('id'),
        'product_id': item.get('product_id'),
        'quantity': quantity,
        'product': product,
        'line_total': price * quantity,
        'created_at': item.get('created_at'),
        'updated_at': item.get('updated_at')
    }


def build_cart_response(member_id):
    result = supabase.table('cart_items') \
        .select(CART_ITEM_FIELDS) \
        .eq('member_id', member_id) \
        .order('id') \
        .execute()

    items = [format_cart_item(item) for item in (result.data or [])]
    total = sum(item['line_total'] for item in items)
    return {'success': True, 'items': items, 'total': total}


def get_member_order(member_id, order_id):
    result = supabase.table('orders') \
        .select(ORDER_FIELDS) \
        .eq('id', order_id) \
        .eq('member_id', member_id) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def attach_order_items(order):
    items_result = supabase.table('order_items') \
        .select(ORDER_ITEM_FIELDS) \
        .eq('order_id', order['id']) \
        .execute()
    order['items'] = items_result.data or []
    return order


def can_change_status(current_status, next_status):
    if next_status not in VALID_ORDER_STATUSES:
        return False
    return next_status in ALLOWED_STATUS_TRANSITIONS.get(current_status, set())

def require_admin_password():
    if not ORDER_ADMIN_PASSWORD:
        return False, jsonify({
            'success': False,
            'message': 'Please set ORDER_ADMIN_PASSWORD in .env'
        }), 500

    provided_password = request.headers.get('X-Admin-Password')
    if provided_password != ORDER_ADMIN_PASSWORD:
        return False, jsonify({'success': False, 'message': 'Invalid admin password'}), 401

    return True, None, None


def get_admin_order(order_id):
    result = supabase.table('orders') \
        .select(ORDER_FIELDS) \
        .eq('id', order_id) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def attach_member(order):
    member_result = supabase.table('members') \
        .select('id,email,name') \
        .eq('id', order['member_id']) \
        .limit(1) \
        .execute()

    order['member'] = member_result.data[0] if member_result.data else None
    return order


@app.route('/')
def order_admin_home():
    return send_from_directory(PUBLIC_DIR, 'order_admin.html')


@app.route('/admin/orders')
def order_admin_page():
    return send_from_directory(PUBLIC_DIR, 'order_admin.html')


@app.route('/JS/<path:path>')
def order_admin_js(path):
    return send_from_directory(os.path.join(PUBLIC_DIR, 'JS'), path)


@app.route('/api/admin/orders', methods=['GET'])
def admin_get_orders():
    is_allowed, response, status_code = require_admin_password()
    if not is_allowed:
        return response, status_code

    status = request.args.get('status')

    if status and status not in VALID_ORDER_STATUSES:
        return jsonify({'success': False, 'message': 'Invalid order status'}), 400

    try:
        query = supabase.table('orders') \
            .select(ORDER_FIELDS) \
            .order('id', desc=True)

        if status:
            query = query.eq('status', status)

        orders_result = query.execute()
        orders = []
        for order in orders_result.data or []:
            orders.append(attach_member(attach_order_items(order)))

        return jsonify({'success': True, 'orders': orders})
    except Exception as error:
        return jsonify({'success': False, 'message': f'Admin order load failed: {error}'}), 500


@app.route('/api/admin/orders/<int:order_id>/status', methods=['PUT'])
def admin_update_order_status(order_id):
    is_allowed, response, status_code = require_admin_password()
    if not is_allowed:
        return response, status_code

    data = request.get_json() or {}
    next_status = data.get('status')

    if next_status not in VALID_ORDER_STATUSES:
        return jsonify({'success': False, 'message': 'Invalid order status'}), 400

    order = get_admin_order(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    try:
        current_status = order.get('status')
        if current_status != 'paid' and next_status == 'paid':
            apply_successful_payment_stock_update(order_id)
            remove_paid_order_items_from_cart(order['member_id'], order_id)

        result = supabase.table('orders') \
            .update({'status': next_status, 'updated_at': utc_now_iso()}) \
            .eq('id', order_id) \
            .execute()

        if not result.data:
            return jsonify({'success': False, 'message': 'Order update failed'}), 500

        updated_order = attach_member(attach_order_items(result.data[0]))
        return jsonify({'success': True, 'order': updated_order})
    except Exception as error:
        return jsonify({'success': False, 'message': f'Admin order update failed: {error}'}), 500


@app.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    data = request.get_json() or {}
    product_ids = data.get('product_ids') or []

    if not isinstance(product_ids, list) or not product_ids:
        return jsonify({'success': False, 'message': '請先選擇要結帳的商品'}), 400

    try:
        product_ids = [int(product_id) for product_id in product_ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '商品格式錯誤'}), 400

    try:
        cart_result = supabase.table('cart_items') \
            .select(CART_ITEM_FIELDS) \
            .eq('member_id', member['id']) \
            .in_('product_id', product_ids) \
            .execute()

        cart_items = cart_result.data or []
        if not cart_items:
            return jsonify({'success': False, 'message': '購物車內沒有選取的商品'}), 404

        order_items = []
        total_amount = 0

        for cart_item in cart_items:
            product = cart_item.get('products') or {}
            quantity = int(cart_item.get('quantity') or 1)
            stock = int(product.get('stock') or 0)
            if not product.get('is_active') or stock <= 0:
                deactivate_product_if_out_of_stock(cart_item.get('product_id'), stock)
                return jsonify({'success': False, 'message': 'Selected product is not available'}), 400

            if quantity > stock:
                return jsonify({'success': False, 'message': f'Only {stock} item(s) in stock'}), 400

            unit_price = int(product.get('price') or 0)
            line_total = unit_price * quantity
            total_amount += line_total
            order_items.append({
                'product_id': cart_item.get('product_id'),
                'quantity': quantity,
                'unit_price': unit_price,
                'line_total': line_total
            })

        order_result = supabase.table('orders') \
            .insert({
                'member_id': member['id'],
                'status': 'pending_payment',
                'total_amount': total_amount
            }) \
            .execute()

        if not order_result.data:
            return jsonify({'success': False, 'message': '訂單建立失敗'}), 500

        order = order_result.data[0]
        for item in order_items:
            item['order_id'] = order['id']

        item_result = supabase.table('order_items') \
            .insert(order_items) \
            .execute()

        supabase.table('cart_items') \
            .delete() \
            .eq('member_id', member['id']) \
            .in_('product_id', product_ids) \
            .execute()

        order['items'] = item_result.data or []
        cart = build_cart_response(member['id'])
        return jsonify({
            'success': True,
            'message': '訂單已建立，等待付款',
            'order': order,
            'cart': cart
        })
    except Exception as error:
        return jsonify({'success': False, 'message': f'訂單建立失敗：{error}'}), 500


@app.route('/api/orders', methods=['GET'])
@jwt_required()
def get_orders():
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    try:
        orders_result = supabase.table('orders') \
            .select(ORDER_FIELDS) \
            .eq('member_id', member['id']) \
            .order('id', desc=True) \
            .execute()

        orders = [attach_order_items(order) for order in (orders_result.data or [])]
        return jsonify({'success': True, 'orders': orders})
    except Exception as error:
        return jsonify({'success': False, 'message': f'訂單讀取失敗：{error}'}), 500


@app.route('/api/orders/<int:order_id>', methods=['GET'])
@jwt_required()
def get_order(order_id):
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    order = get_member_order(member['id'], order_id)
    if not order:
        return jsonify({'success': False, 'message': '找不到訂單'}), 404

    return jsonify({'success': True, 'order': attach_order_items(order)})


@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@jwt_required()
def update_order_status(order_id):
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    data = request.get_json() or {}
    next_status = data.get('status')

    order = get_member_order(member['id'], order_id)
    if not order:
        return jsonify({'success': False, 'message': '找不到訂單'}), 404

    current_status = order.get('status')
    if not can_change_status(current_status, next_status):
        return jsonify({
            'success': False,
            'message': f'訂單狀態不能從 {current_status} 改成 {next_status}'
        }), 400

    update_data = {'status': next_status, 'updated_at': utc_now_iso()}

    if current_status != 'paid' and next_status == 'paid':
        recipient_name = (data.get('recipient_name') or order.get('recipient_name') or '').strip()
        recipient_address = (data.get('recipient_address') or order.get('recipient_address') or '').strip()

        if not recipient_name or not recipient_address:
            return jsonify({
                'success': False,
                'message': 'Please enter recipient name and recipient address before payment success'
            }), 400

        update_data['recipient_name'] = recipient_name
        update_data['recipient_address'] = recipient_address
        apply_successful_payment_stock_update(order_id)
        remove_paid_order_items_from_cart(member['id'], order_id)

    result = supabase.table('orders') \
        .update(update_data) \
        .eq('id', order_id) \
        .eq('member_id', member['id']) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({'success': True, 'order': updated_order})


@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_order(order_id):
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    order = get_member_order(member['id'], order_id)
    if not order:
        return jsonify({'success': False, 'message': '找不到訂單'}), 404

    current_status = order.get('status')
    if current_status not in {'pending_payment', 'payment_failed'}:
        return jsonify({
            'success': False,
            'message': 'Only unpaid orders can be cancelled'
        }), 400

    result = supabase.table('orders') \
        .update({'status': 'cancelled', 'updated_at': utc_now_iso()}) \
        .eq('id', order_id) \
        .eq('member_id', member['id']) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({'success': True, 'message': 'Order cancelled', 'order': updated_order})


@app.route('/api/orders/<int:order_id>/mock-payment', methods=['POST'])
@jwt_required()
def mock_payment(order_id):
    member = get_current_member()
    if not member:
        return jsonify({'success': False, 'message': '找不到會員資料'}), 404

    data = request.get_json() or {}
    payment_result = data.get('result')

    if payment_result not in {'success', 'failed'}:
        return jsonify({'success': False, 'message': '付款結果只能是 success 或 failed'}), 400

    order = get_member_order(member['id'], order_id)
    if not order:
        return jsonify({'success': False, 'message': '找不到訂單'}), 404

    current_status = order.get('status')
    next_status = 'paid' if payment_result == 'success' else 'pending_payment'

    if payment_result == 'success' and not can_change_status(current_status, next_status):
        return jsonify({
            'success': False,
            'message': f'Cannot change order status from {current_status} to {next_status}'
        }), 400

    update_data = {'status': next_status, 'updated_at': utc_now_iso()}

    if current_status != 'paid' and next_status == 'paid':
        recipient_name = (data.get('recipient_name') or order.get('recipient_name') or '').strip()
        recipient_address = (data.get('recipient_address') or order.get('recipient_address') or '').strip()

        if not recipient_name or not recipient_address:
            return jsonify({
                'success': False,
                'message': 'Please enter recipient name and recipient address before payment success'
            }), 400

        update_data['recipient_name'] = recipient_name
        update_data['recipient_address'] = recipient_address
        apply_successful_payment_stock_update(order_id)
        remove_paid_order_items_from_cart(member['id'], order_id)

    result = supabase.table('orders') \
        .update(update_data) \
        .eq('id', order_id) \
        .eq('member_id', member['id']) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    message = 'Payment success' if payment_result == 'success' else 'Payment failed, please try again'
    return jsonify({'success': True, 'message': message, 'order': updated_order})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
