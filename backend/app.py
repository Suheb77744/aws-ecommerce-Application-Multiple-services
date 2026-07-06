import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random

app = Flask(__name__)
CORS(app) # Allows frontend pages from image_c3b686.png to query this API safely

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')

# Database connection helper
def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'cloud'),
        cursorclass=pymysql.cursors.DictCursor
    )

# --- USER AUTHENTICATION & SIGNUP ---

@app.route('/api/auth/signup-initiate', methods=['POST'])
def signup_initiate():
    data = request.json
    email = data.get('email')
    username = data.get('username')
    full_name = data.get('full_name')
    password = data.get('password')

    if not all([email, username, password]):
        return jsonify({"error": "Missing required fields"}), 400

    hashed_pw = generate_password_hash(password)
    otp = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=10)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO pending_signups (email, username, full_name, password_hash, otp_code, otp_expiry) 
                     VALUES (%s, %s, %s, %s, %s, %s)
                     ON DUPLICATE KEY UPDATE otp_code=%s, otp_expiry=%s, password_hash=%s"""
            cursor.execute(sql, (email, username, full_name, hashed_pw, otp, expiry, otp, expiry, hashed_pw))
        conn.commit()
        # In practice, send 'otp' via email service here
        return jsonify({"message": "OTP generated successfully", "otp_debug": otp}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/auth/signup-verify', methods=['POST'])
def signup_verify():
    data = request.json
    email = data.get('email')
    otp_code = data.get('otp_code')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM pending_signups WHERE email = %s", (email,))
            pending = cursor.fetchone()

            if not pending or pending['otp_code'] != otp_code or pending['otp_expiry'] < datetime.now():
                return jsonify({"error": "Invalid or expired OTP"}), 400

            # Insert into verified users
            sql_user = """INSERT INTO users (username, full_name, email, password) 
                          VALUES (%s, %s, %s, %s)"""
            cursor.execute(sql_user, (pending['username'], pending['full_name'], pending['email'], pending['password_hash']))
            
            # Delete from pending
            cursor.execute("DELETE FROM pending_signups WHERE email = %s", (email,))
            
        conn.commit()
        return jsonify({"message": "User verified and registered successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                return jsonify({
                    "message": "Login successful",
                    "user": {
                        "id": user['id'],
                        "username": user['username'],
                        "email": user['email'],
                        "full_name": user['full_name']
                    }
                }), 200
            return jsonify({"error": "Invalid credentials"}), 401
    finally:
        conn.close()


# --- CART MANAGEMENT ---

@app.route('/api/cart', methods=['POST'])
def add_to_cart():
    data = request.json
    user_id = data.get('user_id')
    product_id = data.get('product_id')
    product_name = data.get('product_name')
    product_image = data.get('product_image')
    product_description = data.get('product_description')
    price = data.get('price')
    quantity = data.get('quantity', 1)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO cart_items (user_id, product_id, product_name, product_image, product_description, price, quantity)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)
                     ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)"""
            cursor.execute(sql, (user_id, product_id, product_name, product_image, product_description, price, quantity))
        conn.commit()
        return jsonify({"message": "Item added to cart"}), 200
    finally:
        conn.close()

@app.route('/api/cart/<int:user_id>', methods=['GET'])
def get_cart(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM cart_items WHERE user_id = %s", (user_id,))
            items = cursor.fetchall()
        return jsonify(items), 200
    finally:
        conn.close()


# --- ORDERS & PAYMENTS ---

@app.route('/api/orders', methods=['POST'])
def place_order():
    data = request.json
    user_id = data.get('user_id')
    shipping_name = data.get('shipping_name')
    shipping_email = data.get('shipping_email')
    shipping_address = data.get('shipping_address')
    shipping_phone = data.get('shipping_phone')
    total_amount = data.get('total_amount')
    payment_method = data.get('payment_method', 'Credit Card')
    cart_items = data.get('items', []) # Expected list of items [{product_id, product_name, price, quantity, product_image}]

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Insert order
            sql_order = """INSERT INTO orders (user_id, shipping_name, shipping_email, shipping_address, shipping_phone, total_amount)
                           VALUES (%s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql_order, (user_id, shipping_name, shipping_email, shipping_address, shipping_phone, total_amount))
            order_id = cursor.lastrowid

            # 2. Insert items
            for item in cart_items:
                sql_item = """INSERT INTO order_items (order_id, product_id, product_name, product_image, price, quantity)
                              VALUES (%s, %s, %s, %s, %s, %s)"""
                cursor.execute(sql_item, (order_id, item['product_id'], item['product_name'], item.get('product_image'), item['price'], item['quantity']))

            # 3. Handle Payment log
            sql_payment = """INSERT INTO payments (user_id, order_id, payment_method, amount, status, transaction_reference)
                             VALUES (%s, %s, %s, %s, 'paid', %s)"""
            tx_ref = f"TXN-{random.randint(100000, 999999)}"
            cursor.execute(sql_payment, (user_id, order_id, payment_method, total_amount, tx_ref))

            # 4. Clear User's Cart
            cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))

        conn.commit()
        return jsonify({"message": "Order placed successfully!", "order_id": order_id, "transaction_reference": tx_ref}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# --- MULTI-SERVICE ACTIVITY LOGGING & RECHARGES ---

@app.route('/api/activity', methods=['POST'])
def log_activity():
    """Logs whenever a user switches services (e.g., computers, electronics, googlepay)"""
    data = request.json
    user_id = data.get('user_id')
    service_name = data.get('service_name')  # e.g., 'googlegrocery', 'googlemusic'
    service_path = data.get('service_path')  # e.g., '/frontend/googlegrocery'
    activity_type = data.get('activity_type', 'open')
    note = data.get('note')

    if not user_id or not service_name:
        return jsonify({"error": "Missing log parameters"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO service_activity (user_id, service_name, service_path, activity_type, note)
                     VALUES (%s, %s, %s, %s, %s)"""
            cursor.execute(sql, (user_id, service_name, service_path, activity_type, note))
        conn.commit()
        return jsonify({"status": "Activity logged"}), 200
    finally:
        conn.close()

@app.route('/api/recharge', methods=['POST'])
def process_recharge():
    """Handles mobile and utility simulation for the googlepay sub-module"""
    data = request.json
    user_id = data.get('user_id')
    mobile_number = data.get('mobile_number')
    operator_name = data.get('operator_name')
    plan_name = data.get('plan_name')
    amount = data.get('amount')
    payment_method = data.get('payment_method', 'Wallet')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            tx_ref = f"RCG-{random.randint(100000, 999999)}"
            sql = """INSERT INTO recharges (user_id, mobile_number, operator_name, plan_name, amount, payment_method, status, transaction_reference)
                     VALUES (%s, %s, %s, %s, %s, %s, 'success', %s)"""
            cursor.execute(sql, (user_id, mobile_number, operator_name, plan_name, amount, payment_method, tx_ref))
        conn.commit()
        return jsonify({"message": "Recharge completed successfully", "transaction_reference": tx_ref}), 200
    finally:
        conn.close()

if __name__ == '__main__':
    # Listens on all interfaces — perfect for access via AWS EC2 public IP or Nginx reverse-proxy
    app.run(host='0.0.0.0', port=5000, debug=True)