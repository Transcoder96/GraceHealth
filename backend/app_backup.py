
import os,sqlite3,uuid
from datetime import datetime,timedelta,timezone
from functools import wraps
import jwt
from flask import Flask,g,jsonify,request
from flask_cors import CORS
from werkzeug.security import generate_password_hash,check_password_hash
from dotenv import load_dotenv
load_dotenv()
BASE=os.path.dirname(os.path.abspath(__file__)); DB=os.path.join(BASE,"gracehealth.db")
SECRET=os.getenv("SECRET_KEY","CHANGE_ME"); DEVICE_KEY=os.getenv("DEVICE_KEY_HB_0001","CHANGE_ME_DEVICE_KEY")
app=Flask(__name__);app.config["SECRET_KEY"]=SECRET;CORS(app,resources={r"/api/*":{"origins":"*"}})
def conn():
    if "db" not in g:g.db=sqlite3.connect(DB);g.db.row_factory=sqlite3.Row;g.db.execute("PRAGMA foreign_keys=ON")
    return g.db
@app.teardown_appcontext
def close(e):
    x=g.pop("db",None)
    if x:x.close()
def now():return datetime.now(timezone.utc).isoformat()
def init():
    c=sqlite3.connect(DB);c.execute("PRAGMA foreign_keys=ON")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,health_id TEXT UNIQUE,name TEXT NOT NULL,age INTEGER,weight REAL,height REAL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT);
    CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY AUTOINCREMENT,device_id TEXT UNIQUE,name TEXT,status TEXT DEFAULT 'available',active_session_id TEXT);
    CREATE TABLE IF NOT EXISTS device_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT UNIQUE,device_id TEXT,user_id INTEGER,status TEXT,started_at TEXT,last_seen TEXT,ended_at TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS health_readings(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,device_id TEXT,session_id TEXT,bpm REAL,spo2 REAL,temperature REAL,recorded_at TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS period_cycles(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,start_date TEXT,end_date TEXT,avg_score REAL,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS doctor_visits(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,visit_date TEXT,diagnosis TEXT,medication TEXT,next_appt TEXT,notes TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS pms_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,date TEXT,mood TEXT,bloating TEXT,headache TEXT,notes TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS medication_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,date TEXT,pain_relief TEXT,iron_supp TEXT,vitamin_d TEXT,other TEXT,FOREIGN KEY(user_id) REFERENCES users(id));
    """)
    c.execute("INSERT OR IGNORE INTO devices(device_id,name,status) VALUES('HB-0001','GraceHealth Health_Box','available')")
    c.commit();c.close()
def token(uid):return jwt.encode({"user_id":uid,"exp":datetime.now(timezone.utc)+timedelta(days=7)},SECRET,algorithm="HS256")
def user():
    a=request.headers.get("Authorization","")
    try:
        p=jwt.decode(a.split(" ",1)[1],SECRET,algorithms=["HS256"]);return conn().execute("SELECT * FROM users WHERE id=?",(p["user_id"],)).fetchone()
    except:return None
def auth(fn):
    @wraps(fn)
    def w(*a,**k):
        g.user=user()
        if not g.user:return jsonify(error="Authentication required"),401
        return fn(*a,**k)
    return w
def U(x):return {"id":x["id"],"health_id":x["health_id"],"name":x["name"],"age":x["age"],"weight":x["weight"],"height":x["height"],"email":x["email"]}
@app.get("/api/health")
def health():return jsonify(ok=True)
@app.post("/api/auth/register")
def register():
    d=request.get_json() or {}
    if not d.get("name") or not d.get("email") or not d.get("password"):return jsonify(error="Name, email and password are required"),400
    c=conn();email=d["email"].strip().lower()
    if c.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():return jsonify(error="Email already registered"),409
    n=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]+1;hid=f"GH-{1000+n}"
    cur=c.execute("INSERT INTO users(health_id,name,age,weight,height,email,password_hash,created_at) VALUES(?,?,?,?,?,?,?,?)",(hid,d["name"],d.get("age") or None,d.get("weight") or None,d.get("height") or None,email,generate_password_hash(d["password"]),now()))
    c.commit();u=c.execute("SELECT * FROM users WHERE id=?",(cur.lastrowid,)).fetchone()
    return jsonify(token=token(u["id"]),user=U(u)),201
@app.post("/api/auth/login")
def login():
    d=request.get_json() or {};i=(d.get("identifier") or "").lower().strip();u=conn().execute("SELECT * FROM users WHERE lower(email)=? OR lower(health_id)=?",(i,i)).fetchone()
    if not u or not check_password_hash(u["password_hash"],d.get("password","")):return jsonify(error="Invalid login details"),401
    return jsonify(token=token(u["id"]),user=U(u))
@app.get("/api/me")
@auth
def me():return jsonify(user=U(g.user))
@app.get("/api/device/status")
@auth
def ds():
    d=conn().execute("SELECT * FROM devices WHERE device_id='HB-0001'").fetchone();a=None
    if d["active_session_id"]:a=conn().execute("SELECT * FROM device_sessions WHERE session_id=? AND status='active'",(d["active_session_id"],)).fetchone()
    return jsonify(device_id="HB-0001",status="connected" if a and a["user_id"]==g.user["id"] else ("in_use" if a else "available"))
@app.post("/api/device/connect")
@auth
def dc():
    c=conn();d=c.execute("SELECT * FROM devices WHERE device_id='HB-0001'").fetchone()
    if d["active_session_id"]:
        a=c.execute("SELECT * FROM device_sessions WHERE session_id=? AND status='active'",(d["active_session_id"],)).fetchone()
        if a and a["user_id"]!=g.user["id"]:return jsonify(error="Health_Box is currently in use by another user"),409
        return jsonify(session_id=d["active_session_id"],status="connected")
    sid="S-"+uuid.uuid4().hex[:12].upper();t=now()
    c.execute("INSERT INTO device_sessions(session_id,device_id,user_id,status,started_at,last_seen) VALUES(?,?,?,?,?,?)",(sid,"HB-0001",g.user["id"],"active",t,t))
    c.execute("UPDATE devices SET active_session_id=?,status='in_use' WHERE device_id='HB-0001'",(sid,));c.commit()
    return jsonify(session_id=sid,status="connected")
@app.post("/api/device/disconnect")
@auth
def dd():
    c=conn();a=c.execute("SELECT * FROM device_sessions WHERE device_id='HB-0001' AND user_id=? AND status='active' ORDER BY id DESC LIMIT 1",(g.user["id"],)).fetchone()
    if not a:return jsonify(status="already_disconnected")
    c.execute("UPDATE device_sessions SET status='closed',ended_at=? WHERE id=?",(now(),a["id"]));c.execute("UPDATE devices SET active_session_id=NULL,status='available' WHERE device_id='HB-0001'");c.commit()
    return jsonify(status="disconnected")
@app.post("/api/device/reading")
def reading():
    d=request.get_json() or {}
    if d.get("device_id")!="HB-0001" or d.get("device_key")!=DEVICE_KEY:return jsonify(error="Invalid device credentials"),401
    c=conn();dev=c.execute("SELECT * FROM devices WHERE device_id='HB-0001'").fetchone()
    if not dev["active_session_id"]:return jsonify(error="No active user session"),409
    s=c.execute("SELECT * FROM device_sessions WHERE session_id=? AND status='active'",(dev["active_session_id"],)).fetchone()
    if not s:return jsonify(error="Session not found"),409
    def num(k):
        try:return None if d.get(k) in (None,"","null") else float(d[k])
        except:return None
    c.execute("INSERT INTO health_readings(user_id,device_id,session_id,bpm,spo2,temperature,recorded_at) VALUES(?,?,?,?,?,?,?)",(s["user_id"],"HB-0001",s["session_id"],num("bpm"),num("spo2"),num("temperature"),now()));c.commit()
    return jsonify(ok=True)
@app.get("/api/readings")
@auth
def readings():
    r=conn().execute("SELECT id,bpm,spo2,temperature,recorded_at time,device_id,session_id FROM health_readings WHERE user_id=? ORDER BY id DESC LIMIT 200",(g.user["id"],)).fetchall();return jsonify(readings=[dict(x) for x in r])
@app.get("/api/cycles")
@auth
def cycles():
    r=conn().execute("SELECT *,CASE WHEN end_date IS NOT NULL THEN CAST(julianday(end_date)-julianday(start_date)+1 AS INTEGER) END duration FROM period_cycles WHERE user_id=? ORDER BY id DESC",(g.user["id"],)).fetchall();return jsonify(cycles=[dict(x) for x in r])
@app.post("/api/cycles")
@auth
def addcycle():
    d=request.get_json() or {};c=conn();c.execute("INSERT INTO period_cycles(user_id,start_date) VALUES(?,?)",(g.user["id"],d.get("start_date")));c.commit();return jsonify(ok=True),201
@app.get("/api/doctor-visits")
@auth
def visits():
    r=conn().execute("SELECT * FROM doctor_visits WHERE user_id=? ORDER BY visit_date DESC",(g.user["id"],)).fetchall();return jsonify(visits=[dict(x) for x in r])
@app.post("/api/doctor-visits")
@auth
def addvisit():
    d=request.get_json() or {};c=conn();c.execute("INSERT INTO doctor_visits(user_id,visit_date,diagnosis,medication,next_appt,notes) VALUES(?,?,?,?,?,?)",(g.user["id"],d.get("visit_date"),d.get("diagnosis"),d.get("medication"),d.get("next_appt"),d.get("notes")));c.commit();return jsonify(ok=True),201
@app.delete("/api/doctor-visits/<int:i>")
@auth
def delvisit(i):
    c=conn();c.execute("DELETE FROM doctor_visits WHERE id=? AND user_id=?",(i,g.user["id"]));c.commit();return jsonify(ok=True)
@app.post("/api/pms")
@auth
def pms():
    d=request.get_json() or {};c=conn();c.execute("INSERT INTO pms_logs(user_id,date,mood,bloating,headache,notes) VALUES(?,?,?,?,?,?)",(g.user["id"],d.get("date",now()[:10]),d.get("mood"),d.get("bloating"),d.get("headache"),d.get("notes")));c.commit();return jsonify(ok=True),201
@app.post("/api/medications")
@auth
def meds():
    d=request.get_json() or {};c=conn();c.execute("INSERT INTO medication_logs(user_id,date,pain_relief,iron_supp,vitamin_d,other) VALUES(?,?,?,?,?,?)",(g.user["id"],d.get("date",now()[:10]),d.get("pain_relief"),d.get("iron_supp"),d.get("vitamin_d"),d.get("other")));c.commit();return jsonify(ok=True),201
if __name__=="__main__":
    init();app.run(host="0.0.0.0",port=5000,debug=True)
