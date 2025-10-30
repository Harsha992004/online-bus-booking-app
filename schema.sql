DROP TABLE IF EXISTS buses;
DROP TABLE IF EXISTS bookings;

CREATE TABLE buses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    from_city TEXT NOT NULL,
    to_city TEXT NOT NULL,
    depart_time TEXT NOT NULL,
    arrive_time TEXT NOT NULL,
    seats_total INTEGER,
    fare REAL
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id INTEGER NOT NULL,
    passenger_name TEXT NOT NULL,
    passenger_phone TEXT NOT NULL,
    seats_booked INTEGER NOT NULL,
    booked_at TEXT NOT NULL,
    FOREIGN KEY (bus_id) REFERENCES buses (id)
);
