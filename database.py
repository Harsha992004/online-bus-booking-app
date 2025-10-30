import os
import sqlite3
try:
    import mysql.connector as mysql
except Exception:
    mysql = None


def is_mysql_enabled():
    return (
        mysql is not None and
        os.getenv('MYSQL_HOST') and os.getenv('MYSQL_DB') and os.getenv('MYSQL_USER')
    )


def get_conn():
    if is_mysql_enabled():
        return mysql.connect(
            host=os.getenv('MYSQL_HOST'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            database=os.getenv('MYSQL_DB'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD', ''),
        )
    conn = sqlite3.connect('bus_booking.db')
    conn.row_factory = sqlite3.Row
    return conn


def setup_schema(conn):
    if is_mysql_enabled():
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS buses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                from_city VARCHAR(255) NOT NULL,
                to_city VARCHAR(255) NOT NULL,
                depart_time VARCHAR(64) NOT NULL,
                arrive_time VARCHAR(64) NOT NULL,
                seats_total INT,
                fare DECIMAL(10,2)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                bus_id INT NOT NULL,
                passenger_name VARCHAR(255) NOT NULL,
                passenger_phone VARCHAR(32) NOT NULL,
                seats_booked INT NOT NULL,
                booked_at VARCHAR(64) NOT NULL,
                CONSTRAINT fk_bus FOREIGN KEY (bus_id) REFERENCES buses(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS booked_seats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                bus_id INT NOT NULL,
                journey_date VARCHAR(10) NOT NULL,
                seat_no VARCHAR(8) NOT NULL,
                booking_id INT,
                UNIQUE KEY uniq_bus_date_seat (bus_id, journey_date, seat_no)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'customer',
                name VARCHAR(255),
                phone VARCHAR(32)
            )
            """
        )
        conn.commit()
        cur.close()
    else:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS buses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                from_city TEXT NOT NULL,
                to_city TEXT NOT NULL,
                depart_time TEXT NOT NULL,
                arrive_time TEXT NOT NULL,
                seats_total INTEGER,
                fare REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_id INTEGER NOT NULL,
                passenger_name TEXT NOT NULL,
                passenger_phone TEXT NOT NULL,
                seats_booked INTEGER NOT NULL,
                booked_at TEXT NOT NULL,
                FOREIGN KEY (bus_id) REFERENCES buses (id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS booked_seats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bus_id INTEGER NOT NULL,
                journey_date TEXT NOT NULL,
                seat_no TEXT NOT NULL,
                booking_id INTEGER,
                UNIQUE (bus_id, journey_date, seat_no)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'customer',
                name TEXT,
                phone TEXT
            )
            """
        )
        conn.commit()


def seed_if_empty(conn):
    if is_mysql_enabled():
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM buses")
        (count,) = cur.fetchone()
    else:
        cur = conn.execute("SELECT COUNT(*) FROM buses")
        (count,) = cur.fetchone()
    if count and count > 0:
        return
    buses = [
        ('Orange Travels', 'Hyderabad', 'Bengaluru', '2025-10-30 08:00', '2025-10-30 14:00', 40, 599),
        ('SRS Travels', 'Chennai', 'Coimbatore', '2025-10-31 09:00', '2025-10-31 14:30', 45, 499),
        ('VRL Travels', 'Bengaluru', 'Chennai', '2025-11-01 07:30', '2025-11-01 13:30', 50, 650),
        ('Kaveri Travels', 'Hyderabad', 'Vijayawada', '2025-11-02 06:00', '2025-11-02 11:00', 40, 550),
        ('Sri Krishna Travels', 'Chennai', 'Bengaluru', '2025-11-03 08:15', '2025-11-03 14:15', 42, 600),
        ('Megha Travels', 'Vijayawada', 'Hyderabad', '2025-11-04 09:00', '2025-11-04 14:00', 38, 580),
        ('Neeta Travels', 'Bengaluru', 'Coimbatore', '2025-11-05 10:00', '2025-11-05 15:30', 45, 620)
    ]
    if is_mysql_enabled():
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO buses (name, from_city, to_city, depart_time, arrive_time, seats_total, fare) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            buses
        )
        conn.commit()
        cur.close()
    else:
        conn.executemany(
            "INSERT INTO buses (name, from_city, to_city, depart_time, arrive_time, seats_total, fare) VALUES (?, ?, ?, ?, ?, ?, ?)",
            buses
        )
        conn.commit()


# ---------- Extra seeders ----------
def seed_popular_ap_ts(conn):
    buses = [
        ('APSRTC Express', 'Hyderabad', 'Vijayawada', '2025-11-06 06:00', '2025-11-06 11:00', 48, 650),
        ('Kaveri Travels', 'Hyderabad', 'Vijayawada', '2025-11-06 18:00', '2025-11-06 23:00', 40, 700),
        ('Orange Travels', 'Hyderabad', 'Visakhapatnam', '2025-11-07 19:30', '2025-11-08 06:30', 40, 1100),
        ('Morning Star', 'Vijayawada', 'Visakhapatnam', '2025-11-05 07:00', '2025-11-05 12:00', 40, 550),
        ('V Kaveri', 'Tirupati', 'Hyderabad', '2025-11-04 20:30', '2025-11-05 07:00', 36, 900),
        ('TSRTC Super Luxury', 'Warangal', 'Hyderabad', '2025-11-03 06:30', '2025-11-03 09:30', 50, 350),
        ('TSRTC Rajadhani', 'Karimnagar', 'Hyderabad', '2025-11-03 07:00', '2025-11-03 10:30', 44, 400),
        ('Jabbar Travels', 'Kurnool', 'Hyderabad', '2025-11-02 05:30', '2025-11-02 09:45', 40, 520),
        ('Diwakar Travels', 'Guntur', 'Hyderabad', '2025-11-02 21:00', '2025-11-03 03:30', 40, 600),
        ('Komitla', 'Rajahmundry', 'Visakhapatnam', '2025-11-01 08:00', '2025-11-01 11:30', 38, 420),
        ('APSRTC Garuda', 'Nellore', 'Tirupati', '2025-11-05 06:30', '2025-11-05 09:00', 45, 300),
        ('SVKDT Travels', 'Vijayawada', 'Hyderabad', '2025-11-07 22:00', '2025-11-08 04:30', 40, 700)
    ]
    if is_mysql_enabled():
        cur = conn.cursor()
        for bus in buses:
            cur.execute(
                "SELECT COUNT(*) FROM buses WHERE name=%s AND from_city=%s AND to_city=%s AND depart_time=%s",
                (bus[0], bus[1], bus[2], bus[3])
            )
            (count,) = cur.fetchone()
            if count == 0:
                cur.execute(
                    "INSERT INTO buses (name, from_city, to_city, depart_time, arrive_time, seats_total, fare) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    bus
                )
        conn.commit()
        cur.close()
    else:
        cur = conn.cursor()
        for bus in buses:
            cur.execute(
                "SELECT COUNT(1) FROM buses WHERE name=? AND from_city=? AND to_city=? AND depart_time=?",
                (bus[0], bus[1], bus[2], bus[3])
            )
            (count,) = cur.fetchone()
            if count == 0:
                cur.execute(
                    "INSERT INTO buses (name, from_city, to_city, depart_time, arrive_time, seats_total, fare) VALUES (?,?,?,?,?,?,?)",
                    bus
                )
        conn.commit()


def main():
    conn = get_conn()
    try:
        setup_schema(conn)
        seed_if_empty(conn)
        seed_popular_ap_ts(conn)
        print("✅ Database ready. Sample data ensured (no data loss).")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
