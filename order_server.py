from datetime import datetime, timezone
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'change-this-in-env')
jwt = JWTManager(app)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError('請先在 .env 設定 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CART_ITEM_FIELDS = 'id,product_id,quantity,created_at,updated_at,products(id,name,price,image_url,stock,is_active)'
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
    'payment_failed': {'pending_payment', 'cancelled'},
    'paid': {'processing', 'cancelled'},
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


def get_current_member():
    current_user = get_jwt_identity()
    if not current_user:
        return None

    result = supabase.table('members') \
        .select('id,email') \
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
        .select('id,member_id,status,total_amount,created_at,updated_at') \
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
            if not product.get('is_active'):
                return jsonify({'success': False, 'message': '選取的商品包含未上架商品'}), 400

            quantity = int(cart_item.get('quantity') or 1)
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

        for product_id in product_ids:
            supabase.table('cart_items') \
                .delete() \
                .eq('member_id', member['id']) \
                .eq('product_id', product_id) \
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
            .select('id,member_id,status,total_amount,created_at,updated_at') \
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

    result = supabase.table('orders') \
        .update({'status': next_status, 'updated_at': utc_now_iso()}) \
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
    if not can_change_status(current_status, 'cancelled'):
        return jsonify({'success': False, 'message': f'{current_status} 狀態不能取消'}), 400

    result = supabase.table('orders') \
        .update({'status': 'cancelled', 'updated_at': utc_now_iso()}) \
        .eq('id', order_id) \
        .eq('member_id', member['id']) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({'success': True, 'message': '訂單已取消', 'order': updated_order})


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
    next_status = 'paid' if payment_result == 'success' else 'payment_failed'

    if not can_change_status(current_status, next_status):
        return jsonify({
            'success': False,
            'message': f'訂單狀態不能從 {current_status} 改成 {next_status}'
        }), 400

    result = supabase.table('orders') \
        .update({'status': next_status, 'updated_at': utc_now_iso()}) \
        .eq('id', order_id) \
        .eq('member_id', member['id']) \
        .execute()

    updated_order = attach_order_items(result.data[0]) if result.data else None
    return jsonify({'success': True, 'message': '模擬付款完成', 'order': updated_order})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
