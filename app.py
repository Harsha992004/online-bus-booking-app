from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, Response
import smtplib
from email.message import EmailMessage
import sqlite3
import os
from datetime import datetime, timedelta
import csv
import io
try:
    import mysql.connector as mysql
except Exception:
    mysql = None

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# -------------------- DATABASE CONNECTION --------------------
def is_mysql_enabled():
    return (
        mysql is not None and
        os.getenv('MYSQL_HOST') and os.getenv('MYSQL_DB') and os.getenv('MYSQL_USER')
    )

def get_db_connection():
    if is_mysql_enabled():
        return mysql.connect(
            host=os.getenv('MYSQL_HOST'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            database=os.getenv('MYSQL_DB'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            autocommit=True,
        )
    conn = sqlite3.connect('bus_booking.db')
    conn.row_factory = sqlite3.Row
    return conn

def to_mysql_placeholders(query: str) -> str:
    return query.replace('?', '%s')

def db_fetch_all(query: str, params=()):
    conn = get_db_connection()
    try:
        if is_mysql_enabled():
            cur = conn.cursor(dictionary=True)
            cur.execute(to_mysql_placeholders(query), params)
            rows = cur.fetchall()
            cur.close()
            return rows
        else:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return rows
    finally:
        conn.close()

def db_fetch_one(query: str, params=()):
    conn = get_db_connection()
    try:
        if is_mysql_enabled():
            cur = conn.cursor(dictionary=True)
            cur.execute(to_mysql_placeholders(query), params)
            row = cur.fetchone()
            cur.close()
            return row
        else:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return row
    finally:
        conn.close()

def db_execute(query: str, params=()):
    conn = get_db_connection()
    try:
        if is_mysql_enabled():
            cur = conn.cursor()
            cur.execute(to_mysql_placeholders(query), params)
            conn.commit()
            cur.close()
        else:
            conn.execute(query, params)
            conn.commit()
    finally:
        conn.close()

# -------------------- ROUTES --------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.before_request
def require_login():
    allowed_endpoints = {'login', 'register', 'logout'}
    if request.endpoint in allowed_endpoints:
        return
    if request.path.startswith('/static/'):
        return
    if 'user_id' not in session:
        return redirect(url_for('login'))

def ensure_booking_status_column():
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE bookings ADD COLUMN status VARCHAR(16) DEFAULT 'confirmed'")
        else:
            db_execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'confirmed'")
    except Exception:
        pass

    # Payment columns (mock payment flow)
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE bookings ADD COLUMN payment_status VARCHAR(16) DEFAULT 'unpaid'")
        else:
            db_execute("ALTER TABLE bookings ADD COLUMN payment_status TEXT DEFAULT 'unpaid'")
    except Exception:
        pass
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE bookings ADD COLUMN payment_ref VARCHAR(64)")
        else:
            db_execute("ALTER TABLE bookings ADD COLUMN payment_ref TEXT")
    except Exception:
        pass

# Ensure schema tweak at startup (compatible across Flask versions)
ensure_booking_status_column()

def ensure_booking_user_column():
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE bookings ADD COLUMN user_id INT NULL")
        else:
            db_execute("ALTER TABLE bookings ADD COLUMN user_id INTEGER NULL")
    except Exception:
        pass

ensure_booking_user_column()

def ensure_user_profile_and_roles():
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'customer'")
        else:
            db_execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'customer'")
    except Exception:
        pass
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE users ADD COLUMN name VARCHAR(255)")
        else:
            db_execute("ALTER TABLE users ADD COLUMN name TEXT")
    except Exception:
        pass
    try:
        if is_mysql_enabled():
            db_execute("ALTER TABLE users ADD COLUMN phone VARCHAR(32)")
        else:
            db_execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except Exception:
        pass

ensure_user_profile_and_roles()

# Seed an admin user if ENV provided
def ensure_admin_seed():
    admin_email = (os.getenv('ADMIN_EMAIL') or '').strip().lower()
    admin_pwd = os.getenv('ADMIN_PASSWORD') or ''
    if not admin_email or not admin_pwd:
        return
    try:
        row = db_fetch_one('SELECT id FROM users WHERE email = ?', (admin_email,))
        if row:
            # ensure role is admin
            db_execute('UPDATE users SET role = ? WHERE email = ?', ('admin', admin_email))
            return
        from werkzeug.security import generate_password_hash
        db_execute('INSERT INTO users (email, password_hash, created_at, role, name, phone) VALUES (?, ?, ?, ?, ?, ?)', (
            admin_email, generate_password_hash(admin_pwd), datetime.now(), 'admin', 'Admin', None
        ))
    except Exception:
        pass

ensure_admin_seed()

@app.route('/api/buses')
def list_buses():
    from_city = request.args.get('from', '').strip()
    to_city = request.args.get('to', '').strip()
    date = request.args.get('date', '').strip()
    operator = request.args.get('operator', '').strip()
    bus_type = (request.args.get('type', '') or '').strip().lower()  # ac, nonac, sleeper, seater, luxury
    fare_min = request.args.get('fare_min', '').strip()
    fare_max = request.args.get('fare_max', '').strip()

    query = 'SELECT * FROM buses WHERE 1=1'
    params = []
    if from_city:
        query += ' AND LOWER(from_city) LIKE LOWER(?)'
        params.append(f"%{from_city}%")
    if to_city:
        query += ' AND LOWER(to_city) LIKE LOWER(?)'
        params.append(f"%{to_city}%")
    # Optional: if depart_time contains a date string, naive filter
    if date:
        query += ' AND depart_time LIKE ?'
        params.append(f"%{date}%")
    if operator:
        query += ' AND LOWER(name) LIKE LOWER(?)'
        params.append(f"%{operator}%")
    # Fare range
    if fare_min:
        try:
            float(fare_min)
            query += ' AND CAST(fare AS REAL) >= ?'
            params.append(fare_min)
        except Exception:
            pass
    if fare_max:
        try:
            float(fare_max)
            query += ' AND CAST(fare AS REAL) <= ?'
            params.append(fare_max)
        except Exception:
            pass
    # Type keyword filters on name (best-effort)
    if bus_type in {'ac','nonac','sleeper','seater','luxury'}:
        if bus_type == 'ac':
            query += " AND (LOWER(name) LIKE '%ac%' OR LOWER(name) LIKE '%a/c%' OR LOWER(name) LIKE '%garuda%' OR LOWER(name) LIKE '%rajadhani%' OR LOWER(name) LIKE '%lux%')"
        elif bus_type == 'nonac':
            query += " AND (LOWER(name) NOT LIKE '%ac%' AND LOWER(name) NOT LIKE '%a/c%' AND LOWER(name) NOT LIKE '%garuda%' AND LOWER(name) NOT LIKE '%rajadhani%')"
        elif bus_type == 'sleeper':
            query += " AND (LOWER(name) LIKE '%sleeper%' OR LOWER(name) LIKE '%berth%' OR LOWER(name) LIKE '%rajadhani%')"
        elif bus_type == 'seater':
            query += " AND (LOWER(name) LIKE '%seater%' OR LOWER(name) LIKE '%express%' OR LOWER(name) LIKE '%super%')"
        elif bus_type == 'luxury':
            query += " AND (LOWER(name) LIKE '%lux%' OR LOWER(name) LIKE '%garuda%' OR LOWER(name) LIKE '%rajadhani%' OR LOWER(name) LIKE '%volvo%')"
    rows = db_fetch_all(query, params)
    return jsonify([
        {
            'id': r['id'],
            'name': r['name'],
            'from_city': r['from_city'],
            'to_city': r['to_city'],
            'depart_time': r['depart_time'],
            'arrive_time': r['arrive_time'],
            'fare': r['fare']
        } for r in rows
    ])

@app.route('/api/buses/<int:bus_id>/seats')
def get_seats(bus_id: int):
    date = (request.args.get('date') or '').strip()
    # Fallback to date part of depart_time if not provided
    if not date:
        row = db_fetch_one('SELECT depart_time FROM buses WHERE id = ?', (bus_id,))
        if row:
            dt = row['depart_time'] if isinstance(row, dict) else row['depart_time']
            date = (str(dt)[:10])
    # Determine total seats
    bus = db_fetch_one('SELECT seats_total, fare FROM buses WHERE id = ?', (bus_id,))
    seats_total = int((bus['seats_total'] if isinstance(bus, dict) else bus['seats_total']) or 40)
    fare = float((bus['fare'] if isinstance(bus, dict) else bus['fare']) or 0)
    # Build seat labels 1..seats_total
    seats = [str(i) for i in range(1, seats_total + 1)]
    # Fetch booked seats for that date
    rows = db_fetch_all('SELECT seat_no FROM booked_seats WHERE bus_id = ? AND journey_date = ?', (bus_id, date))
    booked = set([(r['seat_no'] if isinstance(r, dict) else r['seat_no']) for r in rows])
    return jsonify({
        'layout': '2x2',
        'date': date,
        'fare': fare,
        'seats_total': seats_total,
        'booked': sorted(list(booked)),
        'seats': seats,
    })

@app.route('/api/locations')
def list_locations():
    q = (request.args.get('q') or '').strip().lower()
    if q:
        rows = db_fetch_all(
            '''
            SELECT DISTINCT from_city AS city FROM buses WHERE LOWER(from_city) LIKE ?
            UNION
            SELECT DISTINCT to_city   AS city FROM buses WHERE LOWER(to_city) LIKE ?
            ORDER BY city
            ''', (f"{q}%", f"{q}%")
        )
    else:
        rows = db_fetch_all(
            '''
            SELECT DISTINCT from_city AS city FROM buses
            UNION
            SELECT DISTINCT to_city   AS city FROM buses
            ORDER BY city
            '''
        )
    # rows may be list of dicts (MySQL) or sqlite3.Row
    return jsonify([ (r['city'] if isinstance(r, dict) else r['city']) for r in rows ])

# ---------------- Notifications (Email via SMTP) ----------------
def send_email(to_email: str, subject: str, body: str):
    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT') or 0) or 587
    user = os.getenv('SMTP_USER')
    pwd = os.getenv('SMTP_PASS')
    from_addr = os.getenv('SMTP_FROM') or (user or '')
    if not host or not user or not pwd or not to_email:
        return  # silently skip if not configured
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_email
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
    except Exception:
        pass

def _get_booking_snapshot(booking_id: int):
    row = db_fetch_one('''
        SELECT b.id, b.user_id, b.passenger_name, b.passenger_phone, b.seats_booked, b.booked_at,
               b.status, b.payment_status, b.payment_ref,
               bu.name AS bus_name, bu.from_city, bu.to_city, bu.depart_time, bu.arrive_time, bu.fare,
               u.email AS user_email,
               COALESCE(b.discount_amount, 0) AS discount_amount, b.coupon_code
        FROM bookings b
        JOIN buses bu ON b.bus_id = bu.id
        LEFT JOIN users u ON u.id = b.user_id
        WHERE b.id = ?
    ''', (booking_id,))
    if not row:
        return None
    get = (lambda k: row[k] if isinstance(row, dict) else row[k])
    # Safely extract user_email across dict/sqlite row
    try:
        cols = row.keys() if hasattr(row, 'keys') else []
    except Exception:
        cols = []
    if isinstance(row, dict):
        _user_email = row.get('user_email')
    else:
        _user_email = row['user_email'] if ('user_email' in cols) else None
    return {
        'id': get('id'),
        'user_email': _user_email,
        'passenger_name': get('passenger_name'),
        'passenger_phone': get('passenger_phone'),
        'seats_booked': get('seats_booked'),
        'booked_at': get('booked_at'),
        'status': get('status'),
        'payment_status': get('payment_status'),
        'payment_ref': get('payment_ref'),
        'bus_name': get('bus_name'),
        'from_city': get('from_city'),
        'to_city': get('to_city'),
        'depart_time': get('depart_time'),
        'arrive_time': get('arrive_time'),
        'fare': get('fare'),
        'discount_amount': (row.get('discount_amount') if isinstance(row, dict) else (row['discount_amount'] if 'discount_amount' in (row.keys() if hasattr(row,'keys') else []) else 0)),
        'coupon_code': (row.get('coupon_code') if isinstance(row, dict) else (row['coupon_code'] if 'coupon_code' in (row.keys() if hasattr(row,'keys') else []) else None)),
    }

def notify_booking(event: str, booking_id: int):
    # event in {'created','confirmed','cancelled','paid','refunded','unpaid'}
    snap = _get_booking_snapshot(booking_id)
    if not snap:
        return
    to_email = snap.get('user_email')
    if not to_email:
        return
    # Telugu transliteration subjects
    subjects = {
        'created': f"Mee Booking Srushtinchabadindi – Ticket #{snap['id']}",
        'confirmed': f"Mee Booking Confirm ayyindi – Ticket #{snap['id']}",
        'cancelled': f"Mee Booking Cancel ayyindi – Ticket #{snap['id']}",
        'paid': f"Mee Payment Vijayavantam – Ticket #{snap['id']}",
        'refunded': f"Mee Refund Process ayyindi – Ticket #{snap['id']}",
        'unpaid': f"Mee Payment Unpaid ga set chesam – Ticket #{snap['id']}",
    }
    subject = subjects.get(event, f"Booking Update – #{snap['id']}")
    body = (
        f"Namaskaram {snap.get('passenger_name') or ''},\n\n"
        f"Mee booking #{snap['id']} gurinchi update: {event}.\n"
        f"Bus: {snap['bus_name']}\n"
        f"Prayanam: {snap['from_city']} → {snap['to_city']}\n"
        f"Departure: {snap['depart_time']}\n"
        f"Seats: {snap.get('seats_booked')}\n"
        f"Payment: {snap.get('payment_status')}"
        + (f" (Ref: {snap.get('payment_ref')})" if snap.get('payment_ref') else '') + "\n\n"
        f"Mee ticket ni ikkadachi chudavachu: {request.host_url.rstrip('/')}/ticket/{snap['id']}\n"
        f"Dhanyavadalu,\nTripWheels"
    )
    send_email(to_email, subject, body)

@app.route('/bookings')
def view_bookings():
    # Admin: show all
    if session.get('role') == 'admin':
        bookings = db_fetch_all('''
            SELECT b.id, b.passenger_name, b.passenger_phone, b.seats_booked, b.status,
                   b.payment_status, b.payment_ref,
                   bus.name AS bus_name, bus.from_city, bus.to_city, bus.depart_time
            FROM bookings b
            JOIN buses bus ON b.bus_id = bus.id
            ORDER BY b.id DESC
        ''')
        return render_template('bookings.html', bookings=bookings)
    # Customer: show own bookings (by user_id, with phone fallback for legacy rows)
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db_fetch_one('SELECT phone FROM users WHERE id = ?', (session['user_id'],))
    phone = (user['phone'] if isinstance(user, dict) else (user['phone'] if user else None)) or ''
    # Backfill user_id for historic bookings made without login
    if phone:
        try:
            db_execute('UPDATE bookings SET user_id = ? WHERE user_id IS NULL AND passenger_phone = ?', (session['user_id'], phone))
        except Exception:
            pass
    # Fetch rows for this user
    if phone:
        bookings = db_fetch_all('''
            SELECT b.id, b.passenger_name, b.passenger_phone, b.seats_booked, b.status,
                   b.payment_status, b.payment_ref,
                   bus.name AS bus_name, bus.from_city, bus.to_city, bus.depart_time
            FROM bookings b
            JOIN buses bus ON b.bus_id = bus.id
            WHERE b.user_id = ? OR b.passenger_phone = ?
            ORDER BY b.id DESC
        ''', (session['user_id'], phone))
    else:
        bookings = db_fetch_all('''
            SELECT b.id, b.passenger_name, b.passenger_phone, b.seats_booked, b.status,
                   b.payment_status, b.payment_ref,
                   bus.name AS bus_name, bus.from_city, bus.to_city, bus.depart_time
            FROM bookings b
            JOIN buses bus ON b.bus_id = bus.id
            WHERE b.user_id = ?
            ORDER BY b.id DESC
        ''', (session['user_id'],))
    return render_template('bookings.html', bookings=bookings)

@app.route('/ticket/<int:booking_id>')
def view_ticket(booking_id: int):
    # Fetch booking + bus
    row = db_fetch_one('''
        SELECT b.id, b.bus_id, b.passenger_name, b.passenger_phone, b.seats_booked, b.booked_at,
               b.status, b.payment_status, b.payment_ref, b.user_id,
               bus.name AS bus_name, bus.from_city, bus.to_city, bus.depart_time, bus.arrive_time, bus.fare,
               COALESCE(b.discount_amount, 0) AS discount_amount, b.coupon_code
        FROM bookings b JOIN buses bus ON b.bus_id = bus.id
        WHERE b.id = ?
    ''', (booking_id,))
    if not row:
        flash('Ticket not found', 'error')
        return redirect(url_for('index'))
    # Access check: admin or owner (by user_id or phone fallback)
    is_admin = session.get('role') == 'admin'
    owner_ok = False
    if 'user_id' in session:
        bid_uid = row['user_id'] if isinstance(row, dict) else row['user_id']
        if bid_uid and bid_uid == session['user_id']:
            owner_ok = True
        else:
            # fallback match by phone
            u = db_fetch_one('SELECT phone FROM users WHERE id = ?', (session['user_id'],))
            uphone = (u['phone'] if isinstance(u, dict) else (u['phone'] if u else None))
            bphone = row['passenger_phone'] if isinstance(row, dict) else row['passenger_phone']
            if uphone and bphone and uphone == bphone:
                owner_ok = True
    if not (is_admin or owner_ok):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    # Get seat numbers if present
    seats = db_fetch_all('SELECT seat_no FROM booked_seats WHERE booking_id = ? ORDER BY CAST(seat_no AS INT)', (booking_id,))
    seat_list = [ (s['seat_no'] if isinstance(s, dict) else s['seat_no']) for s in seats ]
    # Get passengers list if present
    passengers_rows = db_fetch_all('SELECT seat_no, name, phone, email, age, gender FROM bookings_passengers WHERE booking_id = ? ORDER BY id', (booking_id,)) or []
    passengers = []
    for pr in passengers_rows:
        if isinstance(pr, dict):
            passengers.append({
                'seat_no': pr.get('seat_no'),
                'name': pr.get('name'),
                'phone': pr.get('phone'),
                'email': pr.get('email'),
                'age': pr.get('age'),
                'gender': pr.get('gender'),
            })
        else:
            passengers.append({
                'seat_no': pr['seat_no'],
                'name': pr['name'],
                'phone': pr['phone'],
                'email': pr['email'],
                'age': pr['age'],
                'gender': pr['gender'],
            })
    # Normalize dict for template
    get = (lambda k: row[k] if isinstance(row, dict) else row[k])
    # Amounts
    base_amount = float((row['seats_booked'] if isinstance(row, dict) else row['seats_booked']) or 0) * float((row['fare'] if isinstance(row, dict) else row['fare']) or 0)
    discount_amount = float((row['discount_amount'] if isinstance(row, dict) else (row['discount_amount'] if hasattr(row,'keys') and 'discount_amount' in row.keys() else 0)) or 0)
    total_amount = max(0.0, base_amount - discount_amount)
    booking = {
        'id': get('id'),
        'bus_name': get('bus_name'),
        'from_city': get('from_city'),
        'to_city': get('to_city'),
        'depart_time': get('depart_time'),
        'arrive_time': get('arrive_time'),
        'fare': get('fare'),
        'passenger_name': get('passenger_name'),
        'passenger_phone': get('passenger_phone'),
        'seats_booked': get('seats_booked'),
        'booked_at': get('booked_at'),
        'status': get('status'),
        'payment_status': get('payment_status'),
        'payment_ref': get('payment_ref'),
        'seat_numbers': seat_list,
        'passengers': passengers,
        'coupon_code': (row['coupon_code'] if isinstance(row, dict) else (row['coupon_code'] if hasattr(row,'keys') and 'coupon_code' in row.keys() else None)),
        'base_amount': base_amount,
        'discount_amount': discount_amount,
        'total_amount': total_amount,
    }
    return render_template('ticket.html', b=booking)

@app.route('/api/bookings', methods=['POST'])
def save_booking():
    try:
        data = request.get_json(force=True, silent=False)
        bus_id = int(data.get('bus_id'))
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        seat_numbers = data.get('seat_numbers') or []
        coupon_code = (data.get('coupon_code') or '').strip().upper()
        discount_amount = 100.0 if coupon_code == 'TRIP100' else 0.0
        passengers = data.get('passengers') or []
        if isinstance(seat_numbers, str):
            seat_numbers = [s.strip() for s in seat_numbers.split(',') if s.strip()]
        seats = int(data.get('seats') or (len(seat_numbers) if seat_numbers else 0))
        journey_date = (data.get('date') or '').strip()
        if not bus_id or seats <= 0:
            return jsonify({'status': 'error', 'message': 'Invalid input'}), 400
        # Validate seat availability if seat_numbers provided
        if seat_numbers and journey_date:
            # Check if any requested seat already booked
            placeholders = ','.join(['?'] * len(seat_numbers))
            conflict_query = f"SELECT seat_no FROM booked_seats WHERE bus_id = ? AND journey_date = ? AND seat_no IN ({placeholders})"
            rows = db_fetch_all(conflict_query, (bus_id, journey_date, *seat_numbers))
            if rows:
                taken = [r['seat_no'] if isinstance(r, dict) else r['seat_no'] for r in rows]
                return jsonify({'status': 'error', 'message': f'Seats already booked: {", ".join(taken)}'}), 409

        # Create booking
        booking_created = False
        try:
            # Try insert with user_id if logged in
            uid = session.get('user_id')
            if uid:
                try:
                    db_execute(
                        'INSERT INTO bookings (bus_id, passenger_name, passenger_phone, seats_booked, booked_at, status, payment_status, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (bus_id, name, phone, seats, datetime.now(), 'confirmed', 'unpaid', uid)
                    )
                    booking_created = True
                except Exception:
                    pass
            if not booking_created:
                db_execute(
                    'INSERT INTO bookings (bus_id, passenger_name, passenger_phone, seats_booked, booked_at, status, payment_status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (bus_id, name, phone, seats, datetime.now(), 'confirmed', 'unpaid')
                )
                booking_created = True
        except Exception:
            db_execute(
                'INSERT INTO bookings (bus_id, passenger_name, passenger_phone, seats_booked, booked_at) VALUES (?, ?, ?, ?, ?)',
                (bus_id, name, phone, seats, datetime.now())
            )
            booking_created = True

        # Retrieve last inserted booking id (SQLite last_insert_rowid or MySQL last insert id)
        # Simple approach: get max id for this passenger & time window
        row = db_fetch_one(
            'SELECT id FROM bookings WHERE passenger_name = ? AND passenger_phone = ? ORDER BY id DESC LIMIT 1',
            (name, phone)
        )
        booking_id = (row['id'] if isinstance(row, dict) else row['id']) if row else None

        # Try to persist coupon and discount (add columns if missing)
        try:
            db_execute('ALTER TABLE bookings ADD COLUMN coupon_code TEXT')
        except Exception:
            pass
        try:
            db_execute('ALTER TABLE bookings ADD COLUMN discount_amount REAL DEFAULT 0')
        except Exception:
            pass
        if booking_id:
            try:
                db_execute('UPDATE bookings SET coupon_code = ?, discount_amount = ? WHERE id = ?', (coupon_code or None, discount_amount or 0.0, booking_id))
            except Exception:
                pass
        # Persist per-passenger details
        try:
            db_execute('''
                CREATE TABLE IF NOT EXISTS bookings_passengers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    booking_id INTEGER NOT NULL,
                    seat_no TEXT,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    age INTEGER,
                    gender TEXT
                )
            ''')
        except Exception:
            pass
        # Add phone column if table already existed without it
        try:
            db_execute('ALTER TABLE bookings_passengers ADD COLUMN phone TEXT')
        except Exception:
            pass
        if booking_id and passengers:
            try:
                # Map seat numbers if provided; else None
                for idx, p in enumerate(passengers):
                    s_no = None
                    try:
                        s_no = str(seat_numbers[idx]) if idx < len(seat_numbers) else None
                    except Exception:
                        s_no = None
                    db_execute(
                        'INSERT INTO bookings_passengers (booking_id, seat_no, name, phone, email, age, gender) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (
                            booking_id,
                            s_no,
                            (p.get('name') or None),
                            (p.get('phone') or None),
                            (p.get('email') or None),
                            (int(p.get('age')) if p.get('age') else None),
                            (p.get('gender') or None)
                        )
                    )
            except Exception:
                pass

        # Persist seat selections
        if seat_numbers and journey_date and booking_id:
            for s in seat_numbers:
                try:
                    db_execute('INSERT INTO booked_seats (bus_id, journey_date, seat_no, booking_id) VALUES (?, ?, ?, ?)', (bus_id, journey_date, str(s), booking_id))
                except Exception:
                    pass
        # Notify booking created (and effectively confirmed in current flow)
        try:
            if booking_id:
                notify_booking('created', booking_id)
        except Exception:
            pass
        return jsonify({'status': 'success', 'booking_id': booking_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/bookings/<int:booking_id>/pay', methods=['POST'])
def mock_pay_booking(booking_id: int):
    """Mock payment endpoint: marks the booking as paid with a fake reference."""
    try:
        ref = f"TXN{int(datetime.now().timestamp())}{booking_id}"
        db_execute('UPDATE bookings SET payment_status = ?, payment_ref = ? WHERE id = ?', ('paid', ref, booking_id))
        try:
            notify_booking('paid', booking_id)
        except Exception:
            pass
        return jsonify({'status': 'success', 'payment_ref': ref})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id: int):
    try:
        db_execute('UPDATE bookings SET status = ? WHERE id = ?', ('cancelled', booking_id))
        try:
            notify_booking('cancelled', booking_id)
        except Exception:
            pass
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/account')
def account_page():
    user_email = session.get('user_email')
    if user_email:
        role = session.get('role', 'customer')
        return f"<div style='padding:20px;color:#fff;font-family:Segoe UI'>Signed in as {user_email} ({role}). <a href='{url_for('profile')}' style='color:#00d9ff;margin-left:12px'>Profile</a> <a href='{url_for('logout')}' style='color:#00d9ff;margin-left:12px'>Logout</a></div>"
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    from werkzeug.security import generate_password_hash
    if request.method == 'GET':
        return render_template('register.html')
    data = request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not email or not password or '@' not in email:
        return render_template('register.html', error='Enter a valid email and password', email=email, name=name, phone=phone)
    existing = db_fetch_one('SELECT id FROM users WHERE email = ?', (email,))
    if existing:
        return render_template('register.html', error='Email already registered', email=email, name=name, phone=phone)
    pwd_hash = generate_password_hash(password)
    # Default role is customer; admins can be set manually in DB
    try:
        db_execute('INSERT INTO users (email, password_hash, created_at, role, name, phone) VALUES (?, ?, ?, ?, ?, ?)', (email, pwd_hash, datetime.now(), 'customer', name or None, phone or None))
    except Exception:
        # Fallback if columns not present
        db_execute('INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)', (email, pwd_hash, datetime.now()))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    from werkzeug.security import check_password_hash
    if request.method == 'GET':
        return render_template('login.html')
    data = request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    user = db_fetch_one('SELECT id, email, password_hash, role, name, phone FROM users WHERE email = ?', (email,))
    if not user:
        return render_template('login.html', error='Invalid email or password', email=email)
    pwd_hash = user['password_hash'] if isinstance(user, dict) else user['password_hash']
    from werkzeug.security import check_password_hash
    if not check_password_hash(pwd_hash, password):
        return render_template('login.html', error='Invalid email or password', email=email)
    session['user_id'] = (user['id'] if isinstance(user, dict) else user['id'])
    session['user_email'] = (user['email'] if isinstance(user, dict) else user['email'])
    session['role'] = (user.get('role') if isinstance(user, dict) else None) or 'customer'
    flash('Logged in successfully', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'GET':
        # Load current profile data
        row = db_fetch_one('SELECT email, role, name, phone FROM users WHERE id = ?', (session['user_id'],))
        if row:
            if not isinstance(row, dict):
                row = {'email': row['email'], 'role': row['role'] if 'role' in row.keys() else 'customer', 'name': row['name'] if 'name' in row.keys() else None, 'phone': row['phone'] if 'phone' in row.keys() else None}
        return render_template('profile.html', user=row)
    # POST: update name and phone
    name = (request.form.get('name') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    try:
        db_execute('UPDATE users SET name = ?, phone = ? WHERE id = ?', (name or None, phone or None, session['user_id']))
    except Exception:
        pass
    return redirect(url_for('profile'))

# ---------------- Admin: Dashboard and CSV Exports ----------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    date_from = (request.args.get('from') or '').strip()
    date_to = (request.args.get('to') or '').strip()
    where = ''
    params = []
    if date_from:
        where += ' AND booked_at >= ?'
        params.append(date_from)
    if date_to:
        where += ' AND booked_at <= ?'
        params.append(date_to)
    rows = db_fetch_all(f'''
        SELECT b.id, b.bus_id, b.passenger_name, b.seats_booked, b.booked_at, b.status,
               b.payment_status, b.payment_ref, bu.fare,
               COALESCE(b.discount_amount, 0) AS discount_amount, b.coupon_code
        FROM bookings b JOIN buses bu ON b.bus_id = bu.id
        WHERE 1=1 {where}
        ORDER BY b.id DESC
    ''', tuple(params))
    # Compute metrics
    total_bookings = len(rows)
    confirmed = sum(1 for r in rows if (r['status'] if isinstance(r, dict) else r['status']) == 'confirmed')
    cancelled = sum(1 for r in rows if (r['status'] if isinstance(r, dict) else r['status']) == 'cancelled')
    revenue = 0.0
    for r in rows:
        status = r['payment_status'] if isinstance(r, dict) else r['payment_status']
        if status == 'paid':
            seats = r['seats_booked'] if isinstance(r, dict) else r['seats_booked']
            fare = r['fare'] if isinstance(r, dict) else r['fare']
            disc = (r['discount_amount'] if isinstance(r, dict) else (r['discount_amount'] if 'discount_amount' in r.keys() else 0)) if r is not None else 0
            revenue += max(0.0, float(seats or 0) * float(fare or 0) - float(disc or 0))
    return render_template('admin_dashboard.html',
                           rows=rows,
                           total_bookings=total_bookings,
                           confirmed=confirmed,
                           cancelled=cancelled,
                           revenue=revenue,
                           date_from=date_from,
                           date_to=date_to)

@app.route('/admin/export/buses.csv')
def export_buses_csv():
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    buses = db_fetch_all('SELECT id, name, from_city, to_city, depart_time, arrive_time, seats_total, fare FROM buses ORDER BY id')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','name','from_city','to_city','depart_time','arrive_time','seats_total','fare'])
    for b in buses:
        get = (lambda k: b[k] if isinstance(b, dict) else b[k])
        writer.writerow([get('id'), get('name'), get('from_city'), get('to_city'), get('depart_time'), get('arrive_time'), get('seats_total'), get('fare')])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=buses.csv'})

@app.route('/admin/export/bookings.csv')
def export_bookings_csv():
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    rows = db_fetch_all('''
        SELECT b.id, bu.name AS bus_name, bu.from_city, bu.to_city, b.passenger_name, b.passenger_phone,
               b.seats_booked, b.booked_at, b.status, b.payment_status, b.payment_ref, bu.fare,
               COALESCE(b.discount_amount, 0) AS discount_amount, b.coupon_code
        FROM bookings b JOIN buses bu ON b.bus_id = bu.id
        ORDER BY b.id DESC
    ''')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','bus_name','from_city','to_city','passenger_name','passenger_phone','seats_booked','booked_at','status','payment_status','payment_ref','fare','discount','coupon','amount'])
    for r in rows:
        get = (lambda k: r[k] if isinstance(r, dict) else r[k])
        seats = int(get('seats_booked') or 0)
        fare = float(get('fare') or 0)
        disc = float((get('discount_amount') if 'discount_amount' in r.keys() else 0) if not isinstance(r, dict) else r.get('discount_amount') or 0)
        amt = max(0.0, seats*fare - disc)
        writer.writerow([get('id'), get('bus_name'), get('from_city'), get('to_city'), get('passenger_name'), get('passenger_phone'), seats, get('booked_at'), get('status'), get('payment_status'), get('payment_ref'), fare, disc, (r.get('coupon_code') if isinstance(r, dict) else (r['coupon_code'] if 'coupon_code' in r.keys() else None)), amt])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=bookings.csv'})

# ---------------- Admin: Booking actions ----------------
@app.route('/admin/bookings')
def admin_bookings():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    q = (request.args.get('q') or '').strip().lower()
    status = (request.args.get('status') or '').strip().lower()
    pstat = (request.args.get('payment') or '').strip().lower()
    date_from = (request.args.get('from') or '').strip()
    date_to = (request.args.get('to') or '').strip()
    where = 'WHERE 1=1'
    params = []
    if q:
        where += ' AND (LOWER(b.passenger_name) LIKE ? OR LOWER(b.passenger_phone) LIKE ? OR LOWER(bu.name) LIKE ? OR LOWER(bu.from_city) LIKE ? OR LOWER(bu.to_city) LIKE ? )'
        like = f"%{q}%"
        params += [like, like, like, like, like]
    if status in {'confirmed','cancelled'}:
        where += ' AND b.status = ?'
        params.append(status)
    if pstat in {'paid','unpaid','refunded'}:
        where += ' AND b.payment_status = ?'
        params.append(pstat)
    if date_from:
        where += ' AND b.booked_at >= ?'
        params.append(date_from)
    if date_to:
        where += ' AND b.booked_at <= ?'
        params.append(date_to)
    rows = db_fetch_all(f'''
        SELECT b.id, b.passenger_name, b.passenger_phone, b.seats_booked, b.booked_at, b.status,
               b.payment_status, b.payment_ref,
               bu.name AS bus_name, bu.from_city, bu.to_city, bu.depart_time
        FROM bookings b JOIN buses bu ON b.bus_id = bu.id
        {where}
        ORDER BY b.id DESC
        LIMIT 200
    ''', tuple(params))
    return render_template('admin_bookings.html', rows=rows, q=q, status=status, payment=pstat, date_from=date_from, date_to=date_to)
@app.route('/admin/bookings/<int:booking_id>/status', methods=['POST'])
def admin_booking_status(booking_id: int):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip()
    if status not in {'confirmed', 'cancelled'}:
        return jsonify({'status': 'error', 'message': 'Invalid status'}), 400
    try:
        db_execute('UPDATE bookings SET status = ? WHERE id = ?', (status, booking_id))
        try:
            notify_booking('confirmed' if status == 'confirmed' else 'cancelled', booking_id)
        except Exception:
            pass
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/bookings/<int:booking_id>/payment', methods=['POST'])
def admin_booking_payment(booking_id: int):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    data = request.get_json(silent=True) or {}
    pstat = (data.get('payment_status') or '').strip()
    if pstat not in {'paid', 'refunded', 'unpaid'}:
        return jsonify({'status': 'error', 'message': 'Invalid payment status'}), 400
    try:
        ref = None
        if pstat == 'paid':
            ref = f"TXN{int(datetime.now().timestamp())}{booking_id}"
        db_execute('UPDATE bookings SET payment_status = ?, payment_ref = ? WHERE id = ?', (pstat, ref, booking_id))
        try:
            notify_booking('paid' if pstat == 'paid' else ('refunded' if pstat == 'refunded' else 'unpaid'), booking_id)
        except Exception:
            pass
        return jsonify({'status': 'success', 'payment_ref': ref})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/bookings/<int:booking_id>/release-seats', methods=['POST'])
def admin_booking_release_seats(booking_id: int):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    try:
        db_execute('DELETE FROM booked_seats WHERE booking_id = ?', (booking_id,))
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ---------------- Password reset (mock OTP) ----------------
RESET_TOKENS = {}

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html')
    email = (request.form.get('email') or '').strip().lower()
    if not email:
        flash('Email ivvandi', 'error')
        return render_template('forgot_password.html')
    user = db_fetch_one('SELECT id FROM users WHERE email = ?', (email,))
    if not user:
        flash('Email kanipinchaledu', 'error')
        return render_template('forgot_password.html', email=email)
    code = str(int(datetime.now().timestamp()))[-6:]
    RESET_TOKENS[email] = {'code': code, 'exp': datetime.now() + timedelta(minutes=10)}
    flash(f'OTP code (demo): {code}', 'show')
    return redirect(url_for('reset_password', email=email))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        email = (request.args.get('email') or '').strip().lower()
        return render_template('reset_password.html', email=email)
    email = (request.form.get('email') or '').strip().lower()
    code = (request.form.get('code') or '').strip()
    new1 = request.form.get('new_password') or ''
    new2 = request.form.get('confirm_password') or ''
    token = RESET_TOKENS.get(email)
    if not token or token['exp'] < datetime.now() or token['code'] != code:
        flash('OTP tappu leda expiry ayindi', 'error')
        return render_template('reset_password.html', email=email)
    if not new1 or new1 != new2:
        flash('Passwords match avvaledu', 'error')
        return render_template('reset_password.html', email=email)
    from werkzeug.security import generate_password_hash
    db_execute('UPDATE users SET password_hash = ? WHERE email = ?', (generate_password_hash(new1), email))
    RESET_TOKENS.pop(email, None)
    flash('Password reset ayindi. Daya chesi login avvandi.', 'success')
    return redirect(url_for('login'))

# ---------------- Admin: Buses CRUD ----------------
@app.route('/admin/buses')
def admin_buses():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    buses = db_fetch_all('SELECT id, name, from_city, to_city, depart_time, arrive_time, seats_total, fare FROM buses ORDER BY id DESC')
    return render_template('admin_buses.html', buses=buses)

@app.route('/admin/buses/new', methods=['GET', 'POST'])
def admin_bus_new():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template('bus_form.html', bus=None, mode='new')
    data = request.form
    try:
        db_execute(
            'INSERT INTO buses (name, from_city, to_city, depart_time, arrive_time, seats_total, fare) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                (data.get('name') or '').strip(),
                (data.get('from_city') or '').strip(),
                (data.get('to_city') or '').strip(),
                (data.get('depart_time') or '').strip(),
                (data.get('arrive_time') or '').strip(),
                int(data.get('seats_total') or 40),
                float(data.get('fare') or 0),
            ),
        )
        flash('Bus created successfully', 'success')
        return redirect(url_for('admin_buses'))
    except Exception as e:
        flash(f'Failed to create bus: {e}', 'error')
        return render_template('bus_form.html', bus=data, mode='new')

@app.route('/admin/buses/<int:bus_id>/edit', methods=['GET', 'POST'])
def admin_bus_edit(bus_id: int):
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    if request.method == 'GET':
        row = db_fetch_one('SELECT * FROM buses WHERE id = ?', (bus_id,))
        return render_template('bus_form.html', bus=row, mode='edit')
    data = request.form
    try:
        db_execute(
            'UPDATE buses SET name=?, from_city=?, to_city=?, depart_time=?, arrive_time=?, seats_total=?, fare=? WHERE id=?',
            (
                (data.get('name') or '').strip(),
                (data.get('from_city') or '').strip(),
                (data.get('to_city') or '').strip(),
                (data.get('depart_time') or '').strip(),
                (data.get('arrive_time') or '').strip(),
                int(data.get('seats_total') or 40),
                float(data.get('fare') or 0),
                bus_id,
            ),
        )
        flash('Bus updated', 'success')
        return redirect(url_for('admin_buses'))
    except Exception as e:
        flash(f'Failed to update bus: {e}', 'error')
        row = db_fetch_one('SELECT * FROM buses WHERE id = ?', (bus_id,))
        return render_template('bus_form.html', bus=row, mode='edit')

@app.route('/admin/buses/<int:bus_id>/delete', methods=['POST'])
def admin_bus_delete(bus_id: int):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403
    try:
        db_execute('DELETE FROM buses WHERE id = ?', (bus_id,))
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# -------------- Change Password --------------
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'GET':
        return render_template('change_password.html')
    from werkzeug.security import check_password_hash, generate_password_hash
    curr = request.form.get('current_password') or ''
    new1 = request.form.get('new_password') or ''
    new2 = request.form.get('confirm_password') or ''
    if not new1 or new1 != new2:
        flash('New passwords do not match', 'error')
        return render_template('change_password.html')
    row = db_fetch_one('SELECT password_hash FROM users WHERE id = ?', (session['user_id'],))
    pwd_hash = row['password_hash'] if isinstance(row, dict) else row['password_hash']
    if not check_password_hash(pwd_hash, curr):
        flash('Current password incorrect', 'error')
        return render_template('change_password.html')
    db_execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new1), session['user_id']))
    flash('Password updated', 'success')
    return redirect(url_for('profile'))

if __name__ == '__main__':
    app.run(debug=True)
