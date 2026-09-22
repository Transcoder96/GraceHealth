import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
import psycopg
from psycopg.rows import dict_row
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET = os.getenv("SECRET_KEY")
DEVICE_KEY = os.getenv("DEVICE_KEY_HB_0001")
PORT = int(os.getenv("PORT", "10000"))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")
if not SECRET:
    raise RuntimeError("SECRET_KEY is required")
if not DEVICE_KEY:
    raise RuntimeError("DEVICE_KEY_HB_0001 is required")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET
CORS(app, resources={r"/api/*": {"origins": "*"}})


def db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def now():
    return datetime.now(timezone.utc)


def init_db():
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                health_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER,
                weight DOUBLE PRECISION,
                height DOUBLE PRECISION,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS devices (
                id BIGSERIAL PRIMARY KEY,
                device_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available',
                active_session_id TEXT
            );

            CREATE TABLE IF NOT EXISTS device_sessions (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT UNIQUE NOT NULL,
                device_id TEXT NOT NULL,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                last_seen TIMESTAMPTZ NOT NULL,
                ended_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS health_readings (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                bpm DOUBLE PRECISION,
                spo2 DOUBLE PRECISION,
                temperature DOUBLE PRECISION,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS period_cycles (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                start_date DATE NOT NULL,
                end_date DATE,
                avg_score DOUBLE PRECISION
            );

            CREATE TABLE IF NOT EXISTS doctor_visits (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                visit_date DATE NOT NULL,
                diagnosis TEXT,
                medication TEXT,
                next_appt DATE,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS pms_logs (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date DATE NOT NULL,
                mood TEXT,
                bloating TEXT,
                headache TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS medication_logs (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date DATE NOT NULL,
                pain_relief TEXT,
                iron_supp TEXT,
                vitamin_d TEXT,
                other TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_readings_user
                ON health_readings(user_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_cycles_user
                ON period_cycles(user_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_visits_user
                ON doctor_visits(user_id, visit_date DESC);

            INSERT INTO devices(device_id, name, status)
            VALUES ('HB-0001', 'GraceHealth Health_Box', 'available')
            ON CONFLICT (device_id) DO NOTHING;
        """)


def make_token(user_id):
    return jwt.encode(
        {
            "user_id": user_id,
            "exp": now() + timedelta(days=7),
        },
        SECRET,
        algorithm="HS256",
    )


def current_user():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    try:
        payload = jwt.decode(
            auth_header.split(" ", 1)[1],
            SECRET,
            algorithms=["HS256"],
        )
        return db().execute(
            "SELECT * FROM users WHERE id = %s",
            (payload["user_id"],),
        ).fetchone()
    except Exception:
        return None


def auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if not g.user:
            return jsonify(error="Authentication required"), 401
        return fn(*args, **kwargs)

    return wrapper


def serialize_user(row):
    return {
        "id": row["id"],
        "health_id": row["health_id"],
        "name": row["name"],
        "age": row["age"],
        "weight": row["weight"],
        "height": row["height"],
        "email": row["email"],
    }


@app.get("/api/health")
def health():
    try:
        db().execute("SELECT 1")
        return jsonify(ok=True, database="connected")
    except Exception:
        return jsonify(ok=False, database="error"), 503


@app.post("/api/auth/register")
def register():
    data = request.get_json() or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not name or not email or not password:
        return jsonify(
            error="Name, email and password are required"
        ), 400

    if len(password) < 8:
        return jsonify(
            error="Password must contain at least 8 characters"
        ), 400

    c = db()

    if c.execute(
        "SELECT 1 FROM users WHERE email = %s",
        (email,),
    ).fetchone():
        return jsonify(error="Email already registered"), 409

    next_number = c.execute(
        """
        SELECT COALESCE(
            MAX(CAST(SUBSTRING(health_id FROM 4) AS INTEGER)),
            1000
        ) + 1 AS next_id
        FROM users
        WHERE health_id ~ '^GH-[0-9]+$'
        """
    ).fetchone()["next_id"]

    health_id = f"GH-{next_number}"

    try:
        user_id = c.execute(
            """
            INSERT INTO users
                (health_id, name, age, weight, height, email,
                 password_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                health_id,
                name,
                data.get("age") or None,
                data.get("weight") or None,
                data.get("height") or None,
                email,
                generate_password_hash(password),
                now(),
            ),
        ).fetchone()["id"]

        c.commit()
    except Exception as exc:
        c.rollback()
        if "users_email_key" in str(exc):
            return jsonify(error="Email already registered"), 409
        raise

    user_row = c.execute(
        "SELECT * FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()

    return jsonify(
        token=make_token(user_row["id"]),
        user=serialize_user(user_row),
    ), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}

    identifier = str(data.get("identifier", "")).strip().lower()
    password = str(data.get("password", ""))

    user_row = db().execute(
        """
        SELECT * FROM users
        WHERE LOWER(email) = %s
           OR LOWER(health_id) = %s
        """,
        (identifier, identifier),
    ).fetchone()

    if not user_row or not check_password_hash(
        user_row["password_hash"], password
    ):
        return jsonify(error="Invalid login details"), 401

    return jsonify(
        token=make_token(user_row["id"]),
        user=serialize_user(user_row),
    )


@app.get("/api/me")
@auth
def me():
    return jsonify(user=serialize_user(g.user))


@app.get("/api/device/status")
@auth
def device_status():
    c = db()

    device = c.execute(
        "SELECT * FROM devices WHERE device_id = 'HB-0001'"
    ).fetchone()

    active = None

    if device and device["active_session_id"]:
        active = c.execute(
            """
            SELECT * FROM device_sessions
            WHERE session_id = %s AND status = 'active'
            """,
            (device["active_session_id"],),
        ).fetchone()

    if not active:
        status = "available"
    elif active["user_id"] == g.user["id"]:
        status = "connected"
    else:
        status = "in_use"

    return jsonify(
        device_id="HB-0001",
        status=status,
    )


@app.post("/api/device/connect")
@auth
def connect_device():
    c = db()

    device = c.execute(
        "SELECT * FROM devices WHERE device_id = 'HB-0001' FOR UPDATE"
    ).fetchone()

    if device["active_session_id"]:
        active = c.execute(
            """
            SELECT * FROM device_sessions
            WHERE session_id = %s AND status = 'active'
            """,
            (device["active_session_id"],),
        ).fetchone()

        if active and active["user_id"] != g.user["id"]:
            return jsonify(
                error="Health_Box is currently in use by another user"
            ), 409

        if active:
            return jsonify(
                session_id=active["session_id"],
                status="connected",
            )

    session_id = "S-" + uuid.uuid4().hex[:12].upper()
    timestamp = now()

    c.execute(
        """
        INSERT INTO device_sessions
            (session_id, device_id, user_id, status,
             started_at, last_seen)
        VALUES (%s, %s, %s, 'active', %s, %s)
        """,
        (
            session_id,
            "HB-0001",
            g.user["id"],
            timestamp,
            timestamp,
        ),
    )

    c.execute(
        """
        UPDATE devices
        SET active_session_id = %s, status = 'in_use'
        WHERE device_id = 'HB-0001'
        """,
        (session_id,),
    )

    c.commit()

    return jsonify(
        session_id=session_id,
        status="connected",
    )


@app.post("/api/device/disconnect")
@auth
def disconnect_device():
    c = db()

    active = c.execute(
        """
        SELECT * FROM device_sessions
        WHERE device_id = 'HB-0001'
          AND user_id = %s
          AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (g.user["id"],),
    ).fetchone()

    if not active:
        return jsonify(status="already_disconnected")

    timestamp = now()

    c.execute(
        """
        UPDATE device_sessions
        SET status = 'closed', ended_at = %s
        WHERE id = %s
        """,
        (timestamp, active["id"]),
    )

    c.execute(
        """
        UPDATE devices
        SET active_session_id = NULL, status = 'available'
        WHERE device_id = 'HB-0001'
        """,
    )

    c.commit()

    return jsonify(status="disconnected")


@app.post("/api/device/reading")
def device_reading():
    data = request.get_json() or {}

    if (
        data.get("device_id") != "HB-0001"
        or data.get("device_key") != DEVICE_KEY
    ):
        return jsonify(error="Invalid device credentials"), 401

    c = db()

    device = c.execute(
        "SELECT * FROM devices WHERE device_id = 'HB-0001'"
    ).fetchone()

    if not device or not device["active_session_id"]:
        return jsonify(error="No active user session"), 409

    session = c.execute(
        """
        SELECT * FROM device_sessions
        WHERE session_id = %s AND status = 'active'
        """,
        (device["active_session_id"],),
    ).fetchone()

    if not session:
        return jsonify(error="Session not found"), 409

    def number(key):
        value = data.get(key)
        if value in (None, "", "null"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    timestamp = now()

    c.execute(
        """
        INSERT INTO health_readings
            (user_id, device_id, session_id, bpm, spo2,
             temperature, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session["user_id"],
            "HB-0001",
            session["session_id"],
            number("bpm"),
            number("spo2"),
            number("temperature"),
            timestamp,
        ),
    )

    c.execute(
        """
        UPDATE device_sessions
        SET last_seen = %s
        WHERE id = %s
        """,
        (timestamp, session["id"]),
    )

    c.commit()

    return jsonify(ok=True)


@app.get("/api/readings")
@auth
def readings():
    rows = db().execute(
        """
        SELECT
            id,
            bpm,
            spo2,
            temperature,
            recorded_at AS time,
            device_id,
            session_id
        FROM health_readings
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT 200
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(readings=[dict(row) for row in rows])


@app.get("/api/cycles")
@auth
def cycles():
    rows = db().execute(
        """
        SELECT
            id,
            start_date,
            end_date,
            avg_score,
            CASE
                WHEN end_date IS NOT NULL
                THEN (end_date - start_date + 1)
                ELSE NULL
            END AS duration
        FROM period_cycles
        WHERE user_id = %s
        ORDER BY id DESC
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(cycles=[dict(row) for row in rows])


@app.post("/api/cycles")
@auth
def add_cycle():
    data = request.get_json() or {}

    if not data.get("start_date"):
        return jsonify(error="Start date is required"), 400

    c = db()

    c.execute(
        """
        INSERT INTO period_cycles(user_id, start_date)
        VALUES (%s, %s)
        """,
        (g.user["id"], data["start_date"]),
    )

    c.commit()

    return jsonify(ok=True), 201


@app.get("/api/doctor-visits")
@auth
def visits():
    rows = db().execute(
        """
        SELECT * FROM doctor_visits
        WHERE user_id = %s
        ORDER BY visit_date DESC
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(visits=[dict(row) for row in rows])


@app.post("/api/doctor-visits")
@auth
def add_visit():
    data = request.get_json() or {}

    if not data.get("visit_date"):
        return jsonify(error="Visit date is required"), 400

    c = db()

    c.execute(
        """
        INSERT INTO doctor_visits
            (user_id, visit_date, diagnosis, medication,
             next_appt, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            g.user["id"],
            data["visit_date"],
            data.get("diagnosis"),
            data.get("medication"),
            data.get("next_appt") or None,
            data.get("notes"),
        ),
    )

    c.commit()

    return jsonify(ok=True), 201


@app.delete("/api/doctor-visits/<int:visit_id>")
@auth
def delete_visit(visit_id):
    c = db()

    c.execute(
        """
        DELETE FROM doctor_visits
        WHERE id = %s AND user_id = %s
        """,
        (visit_id, g.user["id"]),
    )

    c.commit()

    return jsonify(ok=True)


@app.post("/api/pms")
@auth
def add_pms():
    data = request.get_json() or {}

    c = db()

    c.execute(
        """
        INSERT INTO pms_logs
            (user_id, date, mood, bloating, headache, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            g.user["id"],
            data.get("date", now().date()),
            data.get("mood"),
            data.get("bloating"),
            data.get("headache"),
            data.get("notes"),
        ),
    )

    c.commit()

    return jsonify(ok=True), 201


@app.post("/api/medications")
@auth
def add_medication():
    data = request.get_json() or {}

    c = db()

    c.execute(
        """
        INSERT INTO medication_logs
            (user_id, date, pain_relief, iron_supp,
             vitamin_d, other)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            g.user["id"],
            data.get("date", now().date()),
            data.get("pain_relief"),
            data.get("iron_supp"),
            data.get("vitamin_d"),
            data.get("other"),
        ),
    )

    c.commit()

    return jsonify(ok=True), 201


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unhandled error")
    return jsonify(error="Server error"), 500


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
    )
