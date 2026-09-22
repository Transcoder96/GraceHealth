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
SECRET = os.getenv("SECRET_KEY", "CHANGE_ME")
DEVICE_KEY = os.getenv("DEVICE_KEY_HB_0001", "CHANGE_ME_DEVICE_KEY")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("ADMIN_NAME", "GraceHealth Admin")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET
CORS(app, resources={r"/api/*": {"origins": "*"}})


# -----------------------------
# Database
# -----------------------------

def conn():
    if "db" not in g:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()


def now():
    return datetime.now(timezone.utc)


def now_iso():
    return now().isoformat()


def init_db():
    db = psycopg.connect(DATABASE_URL)
    try:
        with db.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    health_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    age INTEGER,
                    weight DOUBLE PRECISION,
                    height DOUBLE PRECISION,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT,
                    password_hash TEXT NOT NULL,
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    assessment_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id BIGSERIAL PRIMARY KEY,
                    device_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    active_session_id TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS device_sessions (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    device_id TEXT NOT NULL,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    last_seen TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS health_readings (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    device_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    bpm DOUBLE PRECISION,
                    spo2 DOUBLE PRECISION,
                    temperature DOUBLE PRECISION,
                    recorded_at TIMESTAMPTZ NOT NULL
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS period_health_assessment (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    q1 INTEGER NOT NULL,
                    q2 INTEGER NOT NULL,
                    q3 INTEGER NOT NULL,
                    q4 INTEGER NOT NULL,
                    q5 INTEGER NOT NULL,
                    q6 INTEGER NOT NULL,
                    q7 INTEGER NOT NULL,
                    q8 INTEGER NOT NULL,
                    q9 INTEGER NOT NULL,
                    q10 INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    analysis TEXT,
                    date DATE NOT NULL DEFAULT CURRENT_DATE
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS period_cycles (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    start_date DATE NOT NULL,
                    end_date DATE,
                    avg_score DOUBLE PRECISION,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS daily_symptoms (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    cycle_id BIGINT REFERENCES period_cycles(id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    day_number INTEGER,
                    q1 INTEGER,
                    q2 INTEGER,
                    q3 INTEGER,
                    q4 INTEGER,
                    q5 INTEGER,
                    score INTEGER,
                    analysis TEXT,
                    tip TEXT,
                    notes TEXT,
                    pain_relief TEXT,
                    flow TEXT,
                    iron_taken TEXT,
                    water TEXT,
                    sleep_q TEXT,
                    exercise TEXT,
                    UNIQUE(user_id, cycle_id, date)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS doctor_visits (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    visit_date DATE,
                    diagnosis TEXT,
                    medication TEXT,
                    next_appt DATE,
                    notes TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS medication_logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    cycle_id BIGINT REFERENCES period_cycles(id) ON DELETE SET NULL,
                    date DATE NOT NULL,
                    pain_relief TEXT,
                    iron_supp TEXT,
                    vitamin_d TEXT,
                    other TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS pms_logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    mood TEXT,
                    bloating TEXT,
                    headache TEXT,
                    notes TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS admin_audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    admin_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    target_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            c.execute("""
                INSERT INTO devices(device_id, name, status)
                VALUES ('HB-0001', 'GraceHealth Health_Box', 'available')
                ON CONFLICT (device_id) DO NOTHING
            """)

            # If an admin is explicitly configured in Render, create/update
            # the admin account without hard-coding a password in source code.
            if ADMIN_EMAIL and ADMIN_PASSWORD:
                c.execute(
                    "SELECT id FROM users WHERE lower(email)=lower(%s)",
                    (ADMIN_EMAIL,)
                )
                existing = c.fetchone()

                if existing:
                    c.execute(
                        """
                        UPDATE users
                        SET is_admin=TRUE,
                            password_hash=%s,
                            name=%s
                        WHERE id=%s
                        """,
                        (
                            generate_password_hash(ADMIN_PASSWORD),
                            ADMIN_NAME,
                            existing["id"],
                        ),
                    )
                else:
                    c.execute(
                        "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM users"
                    )
                    # Health ID is generated below using the current maximum.
                    c.execute(
                        "SELECT COUNT(*) AS count FROM users"
                    )
                    count = c.fetchone()["count"]
                    health_id = f"GH-{1001 + count}"
                    c.execute(
                        """
                        INSERT INTO users
                        (health_id, name, email, password_hash, is_admin)
                        VALUES (%s, %s, %s, %s, TRUE)
                        ON CONFLICT (email) DO NOTHING
                        """,
                        (
                            health_id,
                            ADMIN_NAME,
                            ADMIN_EMAIL,
                            generate_password_hash(ADMIN_PASSWORD),
                        ),
                    )

        db.commit()
    finally:
        db.close()


# -----------------------------
# Authentication
# -----------------------------

def make_token(user_id, is_admin=False):
    payload = {
        "user_id": int(user_id),
        "is_admin": bool(is_admin),
        "exp": now() + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None

    try:
        payload = jwt.decode(
            header.split(" ", 1)[1],
            SECRET,
            algorithms=["HS256"],
        )
    except Exception:
        return None

    return conn().execute(
        "SELECT * FROM users WHERE id=%s",
        (payload.get("user_id"),),
    ).fetchone()


def auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if not g.user:
            return jsonify(error="Authentication required"), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if not g.user:
            return jsonify(error="Authentication required"), 401
        if not g.user["is_admin"]:
            return jsonify(error="Admin access required"), 403
        return fn(*args, **kwargs)
    return wrapper


def user_json(user):
    return {
        "id": user["id"],
        "health_id": user["health_id"],
        "name": user["name"],
        "age": user["age"],
        "weight": user["weight"],
        "height": user["height"],
        "email": user["email"],
        "phone": user["phone"],
        "is_admin": user["is_admin"],
        "assessment_completed": user["assessment_completed"],
        "created_at": user["created_at"],
    }


# -----------------------------
# Assessment content
# -----------------------------

ASSESSMENT_QUESTIONS = [
    "Irregular menstrual cycles",
    "Severe abdominal cramps",
    "Excessive fatigue or weakness",
    "Strong mood swings",
    "Headaches or migraines",
    "Heavy menstrual bleeding",
    "Bloating or stomach discomfort",
    "Acne breakouts before period",
    "Difficulty concentrating",
    "Symptoms affecting daily activities",
]

SCORE_LABELS = {
    0: "Never",
    1: "Sometimes",
    2: "Often",
    3: "Always",
}


def assessment_analysis(score):
    if score <= 8:
        return "Normal menstrual symptoms. Maintain a healthy diet and rest well."
    if score <= 16:
        return "Moderate PMS symptoms detected. Monitor your cycle and maintain good nutrition."
    if score <= 24:
        return "High symptom level detected. Continue tracking your symptoms and consider discussing persistent concerns with a healthcare professional."
    return "Very high symptom level detected. Consider discussing these symptoms with a healthcare professional, especially if they are persistent or affecting daily activities."


DAILY_QUESTIONS = [
    "Cramps",
    "Fatigue",
    "Bleeding",
    "Mood",
    "Daily Impact",
]


def daily_analysis(score):
    if score <= 4:
        return (
            "Mild",
            "Great day for light exercise and staying hydrated.",
        )
    if score <= 9:
        return (
            "Moderate",
            "Take it easy. Rest and try a warm compress.",
        )
    if score <= 12:
        return (
            "Severe",
            "Rest, eat iron-rich foods, and stay hydrated.",
        )
    return (
        "Critical",
        "Severe symptoms. Consider discussing them with a healthcare professional.",
    )


# -----------------------------
# Health
# -----------------------------

@app.get("/api/health")
def health():
    try:
        conn().execute("SELECT 1")
        return jsonify(ok=True, database="connected")
    except Exception as exc:
        return jsonify(ok=False, database="error", error=str(exc)), 500


# -----------------------------
# Authentication routes
# -----------------------------

@app.post("/api/auth/register")
def register():
    data = request.get_json() or {}

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not name or not email or not password:
        return jsonify(
            error="Name, email and password are required"
        ), 400

    db = conn()

    if db.execute(
        "SELECT 1 FROM users WHERE lower(email)=lower(%s)",
        (email,),
    ).fetchone():
        return jsonify(error="Email already registered"), 409

    count = db.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]

    health_id = f"GH-{1001 + count}"

    user_id = db.execute(
        """
        INSERT INTO users
        (health_id, name, age, weight, height, email, phone, password_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            health_id,
            name,
            data.get("age") or None,
            data.get("weight") or None,
            data.get("height") or None,
            email,
            data.get("phone") or None,
            generate_password_hash(password),
        ),
    ).fetchone()["id"]

    db.commit()

    user = db.execute(
        "SELECT * FROM users WHERE id=%s",
        (user_id,),
    ).fetchone()

    return jsonify(
        token=make_token(user["id"], user["is_admin"]),
        user=user_json(user),
    ), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}
    identifier = str(data.get("identifier") or "").strip().lower()
    password = str(data.get("password") or "")

    user = conn().execute(
        """
        SELECT * FROM users
        WHERE lower(email)=lower(%s)
           OR lower(health_id)=lower(%s)
        """,
        (identifier, identifier),
    ).fetchone()

    if not user or not check_password_hash(
        user["password_hash"], password
    ):
        return jsonify(error="Invalid login details"), 401

    return jsonify(
        token=make_token(user["id"], user["is_admin"]),
        user=user_json(user),
    )


@app.get("/api/me")
@auth
def me():
    return jsonify(user=user_json(g.user))


# -----------------------------
# Health_Box
# -----------------------------

def expire_stale_session(db):
    device = db.execute(
        "SELECT * FROM devices WHERE device_id='HB-0001'"
    ).fetchone()

    if not device or not device["active_session_id"]:
        return

    session = db.execute(
        """
        SELECT * FROM device_sessions
        WHERE session_id=%s AND status='active'
        """,
        (device["active_session_id"],),
    ).fetchone()

    if not session:
        db.execute(
            """
            UPDATE devices
            SET active_session_id=NULL, status='available'
            WHERE device_id='HB-0001'
            """
        )
        db.commit()
        return

    # A session is considered stale after 2 minutes without heartbeat.
    if session["last_seen"] < now() - timedelta(minutes=2):
        db.execute(
            """
            UPDATE device_sessions
            SET status='closed', ended_at=%s
            WHERE id=%s
            """,
            (now(), session["id"]),
        )
        db.execute(
            """
            UPDATE devices
            SET active_session_id=NULL, status='available'
            WHERE device_id='HB-0001'
            """
        )
        db.commit()


@app.get("/api/device/status")
@auth
def device_status():
    db = conn()
    expire_stale_session(db)

    device = db.execute(
        "SELECT * FROM devices WHERE device_id='HB-0001'"
    ).fetchone()

    active = None

    if device and device["active_session_id"]:
        active = db.execute(
            """
            SELECT * FROM device_sessions
            WHERE session_id=%s AND status='active'
            """,
            (device["active_session_id"],),
        ).fetchone()

    if active and active["user_id"] == g.user["id"]:
        status = "connected"
    elif active:
        status = "in_use"
    else:
        status = "available"

    return jsonify(
        device_id="HB-0001",
        status=status,
        connected=bool(
            active and active["user_id"] == g.user["id"]
        ),
    )


@app.post("/api/device/connect")
@auth
def device_connect():
    db = conn()
    expire_stale_session(db)

    device = db.execute(
        "SELECT * FROM devices WHERE device_id='HB-0001' FOR UPDATE"
    ).fetchone()

    if device["active_session_id"]:
        active = db.execute(
            """
            SELECT * FROM device_sessions
            WHERE session_id=%s AND status='active'
            """,
            (device["active_session_id"],),
        ).fetchone()

        if active and active["user_id"] != g.user["id"]:
            return jsonify(
                error="Health_Box is currently in use by another user"
            ), 409

        if active:
            db.execute(
                """
                UPDATE device_sessions
                SET last_seen=%s
                WHERE id=%s
                """,
                (now(), active["id"]),
            )
            db.commit()
            return jsonify(
                session_id=active["session_id"],
                status="connected",
            )

    session_id = "S-" + uuid.uuid4().hex[:12].upper()
    timestamp = now()

    db.execute(
        """
        INSERT INTO device_sessions
        (session_id, device_id, user_id, status, started_at, last_seen)
        VALUES (%s,'HB-0001',%s,'active',%s,%s)
        """,
        (session_id, g.user["id"], timestamp, timestamp),
    )

    db.execute(
        """
        UPDATE devices
        SET active_session_id=%s, status='in_use'
        WHERE device_id='HB-0001'
        """,
        (session_id,),
    )

    db.commit()

    return jsonify(
        session_id=session_id,
        status="connected",
    )


@app.post("/api/device/heartbeat")
@auth
def device_heartbeat():
    db = conn()

    session = db.execute(
        """
        SELECT * FROM device_sessions
        WHERE device_id='HB-0001'
          AND user_id=%s
          AND status='active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (g.user["id"],),
    ).fetchone()

    if not session:
        return jsonify(
            connected=False,
            error="No active Health_Box session",
        ), 409

    db.execute(
        """
        UPDATE device_sessions
        SET last_seen=%s
        WHERE id=%s
        """,
        (now(), session["id"]),
    )
    db.commit()

    return jsonify(
        connected=True,
        session_id=session["session_id"],
    )


@app.post("/api/device/disconnect")
@auth
def device_disconnect():
    db = conn()

    session = db.execute(
        """
        SELECT * FROM device_sessions
        WHERE device_id='HB-0001'
          AND user_id=%s
          AND status='active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (g.user["id"],),
    ).fetchone()

    if not session:
        return jsonify(status="already_disconnected")

    db.execute(
        """
        UPDATE device_sessions
        SET status='closed', ended_at=%s
        WHERE id=%s
        """,
        (now(), session["id"]),
    )

    db.execute(
        """
        UPDATE devices
        SET active_session_id=NULL, status='available'
        WHERE device_id='HB-0001'
          AND active_session_id=%s
        """,
        (session["session_id"],),
    )

    db.commit()

    return jsonify(status="disconnected")


# -----------------------------
# Device reading
# -----------------------------

@app.post("/api/device/reading")
def device_reading():
    data = request.get_json() or {}

    if data.get("device_id") != "HB-0001":
        return jsonify(error="Invalid device ID"), 401

    if data.get("device_key") != DEVICE_KEY:
        return jsonify(error="Invalid device credentials"), 401

    db = conn()
    expire_stale_session(db)

    device = db.execute(
        "SELECT * FROM devices WHERE device_id='HB-0001'"
    ).fetchone()

    if not device["active_session_id"]:
        return jsonify(error="No active user session"), 409

    session = db.execute(
        """
        SELECT * FROM device_sessions
        WHERE session_id=%s AND status='active'
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
        except (ValueError, TypeError):
            return None

    db.execute(
        """
        INSERT INTO health_readings
        (user_id, device_id, session_id, bpm, spo2, temperature, recorded_at)
        VALUES (%s,'HB-0001',%s,%s,%s,%s,%s)
        """,
        (
            session["user_id"],
            session["session_id"],
            number("bpm"),
            number("spo2"),
            number("temperature"),
            now(),
        ),
    )

    db.execute(
        """
        UPDATE device_sessions
        SET last_seen=%s
        WHERE id=%s
        """,
        (now(), session["id"]),
    )

    db.commit()

    return jsonify(ok=True)


@app.get("/api/readings")
@auth
def readings():
    rows = conn().execute(
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
        WHERE user_id=%s
        ORDER BY id DESC
        LIMIT 200
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(readings=rows)


@app.get("/api/readings/latest")
@auth
def latest_reading():
    row = conn().execute(
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
        WHERE user_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (g.user["id"],),
    ).fetchone()

    return jsonify(reading=row)


# -----------------------------
# Menstrual assessment
# -----------------------------

@app.get("/api/assessment/questions")
@auth
def assessment_questions():
    return jsonify(
        questions=[
            {"id": i + 1, "question": q}
            for i, q in enumerate(ASSESSMENT_QUESTIONS)
        ],
        options=SCORE_LABELS,
    )


@app.get("/api/assessment")
@auth
def get_assessment():
    row = conn().execute(
        """
        SELECT *
        FROM period_health_assessment
        WHERE user_id=%s
        """,
        (g.user["id"],),
    ).fetchone()

    return jsonify(
        completed=bool(row),
        assessment=row,
    )


@app.post("/api/assessment")
@auth
def save_assessment():
    data = request.get_json() or {}

    answers = []
    for i in range(1, 11):
        value = data.get(f"q{i}")

        try:
            value = int(value)
        except (ValueError, TypeError):
            return jsonify(
                error=f"Answer q{i} must be between 0 and 3"
            ), 400

        if value not in (0, 1, 2, 3):
            return jsonify(
                error=f"Answer q{i} must be between 0 and 3"
            ), 400

        answers.append(value)

    score = sum(answers)
    analysis = assessment_analysis(score)
    db = conn()

    db.execute(
        """
        INSERT INTO period_health_assessment
        (user_id,q1,q2,q3,q4,q5,q6,q7,q8,q9,q10,score,analysis)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            q1=EXCLUDED.q1,
            q2=EXCLUDED.q2,
            q3=EXCLUDED.q3,
            q4=EXCLUDED.q4,
            q5=EXCLUDED.q5,
            q6=EXCLUDED.q6,
            q7=EXCLUDED.q7,
            q8=EXCLUDED.q8,
            q9=EXCLUDED.q9,
            q10=EXCLUDED.q10,
            score=EXCLUDED.score,
            analysis=EXCLUDED.analysis,
            date=CURRENT_DATE
        """,
        (
            g.user["id"],
            *answers,
            score,
            analysis,
        ),
    )

    db.execute(
        """
        UPDATE users
        SET assessment_completed=TRUE
        WHERE id=%s
        """,
        (g.user["id"],),
    )

    db.commit()

    row = db.execute(
        """
        SELECT *
        FROM period_health_assessment
        WHERE user_id=%s
        """,
        (g.user["id"],),
    ).fetchone()

    return jsonify(
        ok=True,
        score=score,
        analysis=analysis,
        assessment=row,
    )


# -----------------------------
# Period cycles
# -----------------------------

@app.get("/api/cycles")
@auth
def cycles():
    rows = conn().execute(
        """
        SELECT
            id,
            start_date,
            end_date,
            avg_score,
            CASE
                WHEN end_date IS NOT NULL
                THEN (end_date - start_date + 1)
            END AS duration
        FROM period_cycles
        WHERE user_id=%s
        ORDER BY start_date DESC, id DESC
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(cycles=rows)


@app.post("/api/cycles")
@auth
def add_cycle():
    data = request.get_json() or {}
    start_date = data.get("start_date")

    if not start_date:
        return jsonify(error="start_date is required"), 400

    db = conn()

    cycle = db.execute(
        """
        INSERT INTO period_cycles(user_id,start_date)
        VALUES(%s,%s)
        RETURNING id,start_date,end_date,avg_score
        """,
        (g.user["id"], start_date),
    ).fetchone()

    db.commit()

    return jsonify(ok=True, cycle=cycle), 201


@app.put("/api/cycles/<int:cycle_id>")
@auth
def update_cycle(cycle_id):
    data = request.get_json() or {}
    db = conn()

    cycle = db.execute(
        """
        SELECT * FROM period_cycles
        WHERE id=%s AND user_id=%s
        """,
        (cycle_id, g.user["id"]),
    ).fetchone()

    if not cycle:
        return jsonify(error="Cycle not found"), 404

    db.execute(
        """
        UPDATE period_cycles
        SET start_date=COALESCE(%s,start_date),
            end_date=%s
        WHERE id=%s AND user_id=%s
        """,
        (
            data.get("start_date"),
            data.get("end_date"),
            cycle_id,
            g.user["id"],
        ),
    )

    db.commit()

    return jsonify(ok=True)


@app.delete("/api/cycles/<int:cycle_id>")
@auth
def delete_cycle(cycle_id):
    db = conn()

    db.execute(
        """
        DELETE FROM period_cycles
        WHERE id=%s AND user_id=%s
        """,
        (cycle_id, g.user["id"]),
    )

    db.commit()

    return jsonify(ok=True)


# -----------------------------
# Daily wellness questions
# -----------------------------

@app.get("/api/daily/questions")
@auth
def daily_questions():
    return jsonify(
        questions=[
            {"id": i + 1, "question": q}
            for i, q in enumerate(DAILY_QUESTIONS)
        ],
        options=SCORE_LABELS,
    )


@app.post("/api/daily")
@auth
def save_daily():
    data = request.get_json() or {}

    cycle_id = data.get("cycle_id")
    date_value = data.get("date") or now().date().isoformat()

    answers = []

    for i in range(1, 6):
        value = data.get(f"q{i}")

        try:
            value = int(value)
        except (ValueError, TypeError):
            return jsonify(
                error=f"Answer q{i} must be between 0 and 3"
            ), 400

        if value not in (0, 1, 2, 3):
            return jsonify(
                error=f"Answer q{i} must be between 0 and 3"
            ), 400

        answers.append(value)

    score = sum(answers)
    label, tip = daily_analysis(score)
    db = conn()

    day_number = None

    if cycle_id:
        cycle = db.execute(
            """
            SELECT * FROM period_cycles
            WHERE id=%s AND user_id=%s
            """,
            (cycle_id, g.user["id"]),
        ).fetchone()

        if not cycle:
            return jsonify(error="Cycle not found"), 404

        db.execute(
            "SELECT (%s::date - start_date + 1) AS day_number FROM period_cycles WHERE id=%s",
            (date_value, cycle_id),
        )
        day_number = db.fetchone()["day_number"]

    db.execute(
        """
        INSERT INTO daily_symptoms
        (
            user_id,cycle_id,date,day_number,
            q1,q2,q3,q4,q5,score,analysis,tip,
            notes,pain_relief,flow,iron_taken,water,sleep_q,exercise
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id,cycle_id,date)
        DO UPDATE SET
            day_number=EXCLUDED.day_number,
            q1=EXCLUDED.q1,
            q2=EXCLUDED.q2,
            q3=EXCLUDED.q3,
            q4=EXCLUDED.q4,
            q5=EXCLUDED.q5,
            score=EXCLUDED.score,
            analysis=EXCLUDED.analysis,
            tip=EXCLUDED.tip,
            notes=EXCLUDED.notes,
            pain_relief=EXCLUDED.pain_relief,
            flow=EXCLUDED.flow,
            iron_taken=EXCLUDED.iron_taken,
            water=EXCLUDED.water,
            sleep_q=EXCLUDED.sleep_q,
            exercise=EXCLUDED.exercise
        """,
        (
            g.user["id"],
            cycle_id,
            date_value,
            day_number,
            *answers,
            score,
            label,
            tip,
            data.get("notes"),
            data.get("pain_relief"),
            data.get("flow"),
            data.get("iron_taken"),
            data.get("water"),
            data.get("sleep_q"),
            data.get("exercise"),
        ),
    )

    db.commit()

    return jsonify(
        ok=True,
        score=score,
        analysis=label,
        tip=tip,
    )


@app.get("/api/daily")
@auth
def get_daily():
    cycle_id = request.args.get("cycle_id")

    if cycle_id:
        rows = conn().execute(
            """
            SELECT *
            FROM daily_symptoms
            WHERE user_id=%s AND cycle_id=%s
            ORDER BY date DESC
            """,
            (g.user["id"], cycle_id),
        ).fetchall()
    else:
        rows = conn().execute(
            """
            SELECT *
            FROM daily_symptoms
            WHERE user_id=%s
            ORDER BY date DESC
            LIMIT 100
            """,
            (g.user["id"],),
        ).fetchall()

    return jsonify(entries=rows)


# -----------------------------
# Doctor visits
# -----------------------------

@app.get("/api/doctor-visits")
@auth
def doctor_visits():
    rows = conn().execute(
        """
        SELECT *
        FROM doctor_visits
        WHERE user_id=%s
        ORDER BY visit_date DESC, id DESC
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(visits=rows)


@app.post("/api/doctor-visits")
@auth
def add_doctor_visit():
    data = request.get_json() or {}
    db = conn()

    row = db.execute(
        """
        INSERT INTO doctor_visits
        (user_id,visit_date,diagnosis,medication,next_appt,notes)
        VALUES(%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            g.user["id"],
            data.get("visit_date"),
            data.get("diagnosis"),
            data.get("medication"),
            data.get("next_appt"),
            data.get("notes"),
        ),
    ).fetchone()

    db.commit()

    return jsonify(visit=row), 201


@app.delete("/api/doctor-visits/<int:visit_id>")
@auth
def delete_doctor_visit(visit_id):
    db = conn()

    db.execute(
        """
        DELETE FROM doctor_visits
        WHERE id=%s AND user_id=%s
        """,
        (visit_id, g.user["id"]),
    )

    db.commit()

    return jsonify(ok=True)


# -----------------------------
# PMS
# -----------------------------

@app.get("/api/pms")
@auth
def get_pms():
    rows = conn().execute(
        """
        SELECT *
        FROM pms_logs
        WHERE user_id=%s
        ORDER BY date DESC, id DESC
        LIMIT 100
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(logs=rows)


@app.post("/api/pms")
@auth
def add_pms():
    data = request.get_json() or {}
    db = conn()

    row = db.execute(
        """
        INSERT INTO pms_logs
        (user_id,date,mood,bloating,headache,notes)
        VALUES(%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            g.user["id"],
            data.get("date") or now().date(),
            data.get("mood"),
            data.get("bloating"),
            data.get("headache"),
            data.get("notes"),
        ),
    ).fetchone()

    db.commit()

    return jsonify(log=row), 201


# -----------------------------
# Medications
# -----------------------------

@app.get("/api/medications")
@auth
def get_medications():
    rows = conn().execute(
        """
        SELECT *
        FROM medication_logs
        WHERE user_id=%s
        ORDER BY date DESC, id DESC
        LIMIT 100
        """,
        (g.user["id"],),
    ).fetchall()

    return jsonify(logs=rows)


@app.post("/api/medications")
@auth
def add_medication():
    data = request.get_json() or {}
    db = conn()

    row = db.execute(
        """
        INSERT INTO medication_logs
        (user_id,cycle_id,date,pain_relief,iron_supp,vitamin_d,other)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            g.user["id"],
            data.get("cycle_id"),
            data.get("date") or now().date(),
            data.get("pain_relief"),
            data.get("iron_supp"),
            data.get("vitamin_d"),
            data.get("other"),
        ),
    ).fetchone()

    db.commit()

    return jsonify(log=row), 201


# -----------------------------
# Admin
# -----------------------------

@app.get("/api/admin/overview")
@admin_auth
def admin_overview():
    db = conn()

    users = db.execute(
        """
        SELECT
            id,health_id,name,email,phone,age,weight,height,
            assessment_completed,is_admin,created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    device = db.execute(
        "SELECT * FROM devices WHERE device_id='HB-0001'"
    ).fetchone()

    active_session = None

    if device and device["active_session_id"]:
        active_session = db.execute(
            """
            SELECT
                s.session_id,s.started_at,s.last_seen,
                u.health_id,u.name,u.email
            FROM device_sessions s
            JOIN users u ON u.id=s.user_id
            WHERE s.session_id=%s AND s.status='active'
            """,
            (device["active_session_id"],),
        ).fetchone()

    return jsonify(
        users=users,
        device=device,
        active_session=active_session,
    )


@app.get("/api/admin/users/<int:user_id>")
@admin_auth
def admin_user_detail(user_id):
    db = conn()

    user = db.execute(
        """
        SELECT
            id,health_id,name,email,phone,age,weight,height,
            assessment_completed,is_admin,created_at
        FROM users
        WHERE id=%s
        """,
        (user_id,),
    ).fetchone()

    if not user:
        return jsonify(error="User not found"), 404

    assessment = db.execute(
        """
        SELECT *
        FROM period_health_assessment
        WHERE user_id=%s
        """,
        (user_id,),
    ).fetchone()

    readings = db.execute(
        """
        SELECT *
        FROM health_readings
        WHERE user_id=%s
        ORDER BY id DESC
        LIMIT 200
        """,
        (user_id,),
    ).fetchall()

    cycles = db.execute(
        """
        SELECT *
        FROM period_cycles
        WHERE user_id=%s
        ORDER BY start_date DESC
        """,
        (user_id,),
    ).fetchall()

    daily = db.execute(
        """
        SELECT *
        FROM daily_symptoms
        WHERE user_id=%s
        ORDER BY date DESC
        LIMIT 200
        """,
        (user_id,),
    ).fetchall()

    visits = db.execute(
        """
        SELECT *
        FROM doctor_visits
        WHERE user_id=%s
        ORDER BY visit_date DESC
        """,
        (user_id,),
    ).fetchall()

    medications = db.execute(
        """
        SELECT *
        FROM medication_logs
        WHERE user_id=%s
        ORDER BY date DESC
        """,
        (user_id,),
    ).fetchall()

    pms = db.execute(
        """
        SELECT *
        FROM pms_logs
        WHERE user_id=%s
        ORDER BY date DESC
        """,
        (user_id,),
    ).fetchall()

    return jsonify(
        user=user,
        assessment=assessment,
        readings=readings,
        cycles=cycles,
        daily= daily,
        doctor_visits=visits,
        medications=medications,
        pms=pms,
    )


# -----------------------------
# Application startup
# -----------------------------

if DATABASE_URL:
    try:
        init_db()
    except Exception as startup_error:
        print("Database initialization failed:", startup_error)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
