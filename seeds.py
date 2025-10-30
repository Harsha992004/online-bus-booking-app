import os
from datetime import datetime
from werkzeug.security import generate_password_hash

# Reuse DB helpers from database.py to avoid importing Flask app
import database as dbmod

def seed_users():
    conn = dbmod.get_conn()
    try:
        # Ensure schema exists
        dbmod.setup_schema(conn)

        cur = conn.cursor()
        # Admin
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com').strip().lower()
        admin_pwd = os.getenv('ADMIN_PASSWORD', 'admin123')
        cur.execute("SELECT id FROM users WHERE email=?", (admin_email,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO users (email, password_hash, created_at, role, name, phone) VALUES (?,?,?,?,?,?)",
                (admin_email, generate_password_hash(admin_pwd), datetime.now().isoformat(), 'admin', 'Admin', None)
            )
            print(f"Seeded admin: {admin_email} / {admin_pwd}")
        else:
            cur.execute("UPDATE users SET role='admin' WHERE email=?", (admin_email,))
            print(f"Ensured admin role for: {admin_email}")

        # Customer
        cust_email = os.getenv('CUSTOMER_EMAIL', 'customer@example.com').strip().lower()
        cust_pwd = os.getenv('CUSTOMER_PASSWORD', 'cust123')
        cur.execute("SELECT id FROM users WHERE email=?", (cust_email,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO users (email, password_hash, created_at, role, name, phone) VALUES (?,?,?,?,?,?)",
                (cust_email, generate_password_hash(cust_pwd), datetime.now().isoformat(), 'customer', 'Customer', '9000000000')
            )
            print(f"Seeded customer: {cust_email} / {cust_pwd}")
        else:
            print(f"Customer exists: {cust_email}")

        conn.commit()
    finally:
        conn.close()

if __name__ == '__main__':
    seed_users()
