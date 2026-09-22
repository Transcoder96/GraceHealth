import React,{useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter,useNavigate,useLocation,NavLink} from "react-router-dom";
import {
  Home as HomeIcon,
  HeartPulse,
  CalendarDays,
  Clipboard,
  Stethoscope,
  FileText,
  UserRound,
  LogOut,
  Wifi,
  Menu,
  X,
  LockKeyhole,
  Activity,
  Thermometer,
  Plus,
  Trash2,
  ShieldCheck,
  Mail
} from "lucide-react";
import "./styles.css";

const API=import.meta.env.VITE_API_URL||"http://127.0.0.1:5000/api";

async function api(path,opt={}){
  const h={
    "Content-Type":"application/json",
    ...(opt.headers||{})
  };

  const t=localStorage.getItem("grace_token");

  if(t) h.Authorization=`Bearer ${t}`;

  const r=await fetch(API+path,{
    ...opt,
    headers:h
  });

  const d=await r.json().catch(()=>({}));

  if(!r.ok) throw Error(d.error||"Request failed");

  return d;
}

const post=(p,b)=>api(p,{
  method:"POST",
  body:JSON.stringify(b)
});


function Auth({register=false,setUser}){
  const nav=useNavigate();

  const [f,setF]=useState(
    register
      ? {
          name:"",
          email:"",
          password:"",
          age:"",
          weight:"",
          height:""
        }
      : {
          identifier:"",
          password:""
        }
  );

  const [err,setErr]=useState("");

  async function go(e){
    e.preventDefault();
    setErr("");

    try{
      const r=register
        ? await post("/auth/register",f)
        : await post("/auth/login",f);

      localStorage.setItem("grace_token",r.token);
      setUser(r.user);
      nav("/");
    }catch(x){
      setErr(x.message);
    }
  }

  return (
    <div className="auth">
      <div className="authcard">

        <img src="/gracehealth-logo.png"/>

        <div className="brand">
          GraceHealth
        </div>

        <h1>
          {register
            ? "Create your account"
            : "Welcome back"}
        </h1>

        <p>
          {register
            ? "Your personal health records stay separated by your Health ID."
            : "Sign in to your private health space."}
        </p>

        {err && (
          <div className="error">
            {err}
          </div>
        )}

        <form onSubmit={go} className="form">

          {register ? (
            <>
              <label>
                Full name
                <input
                  required
                  value={f.name}
                  onChange={e=>setF({
                    ...f,
                    name:e.target.value
                  })}
                />
              </label>

              <div className="tw">

                <label>
                  Age
                  <input
                    type="number"
                    value={f.age}
                    onChange={e=>setF({
                      ...f,
                      age:e.target.value
                    })}
                  />
                </label>

                <label>
                  Weight (kg)
                  <input
                    value={f.weight}
                    onChange={e=>setF({
                      ...f,
                      weight:e.target.value
                    })}
                  />
                </label>

              </div>

              <label>
                Height (cm)
                <input
                  value={f.height}
                  onChange={e=>setF({
                    ...f,
                    height:e.target.value
                  })}
                />
              </label>

              <label>
                Email
                <input
                  required
                  type="email"
                  value={f.email}
                  onChange={e=>setF({
                    ...f,
                    email:e.target.value
                  })}
                />
              </label>

              <label>
                Password
                <input
                  required
                  minLength="8"
                  type="password"
                  value={f.password}
                  onChange={e=>setF({
                    ...f,
                    password:e.target.value
                  })}
                />
              </label>
            </>
          ) : (
            <>
              <label>
                Email or Health ID
                <input
                  required
                  value={f.identifier}
                  onChange={e=>setF({
                    ...f,
                    identifier:e.target.value
                  })}
                />
              </label>

              <label>
                Password
                <input
                  required
                  type="password"
                  value={f.password}
                  onChange={e=>setF({
                    ...f,
                    password:e.target.value
                  })}
                />
              </label>
            </>
          )}

          <button className="primary">
            {register
              ? "Create account"
              : "Sign in"}
          </button>

        </form>

        <button
          className="link"
          onClick={()=>
            nav(register
              ? "/login"
              : "/register")
          }
        >
          {register
            ? "Already have an account? Sign in"
            : "New to GraceHealth? Create account"}
        </button>

      </div>
    </div>
  );
}


function Layout({user,setUser,children}){

  const [open,setOpen]=useState(false);
  const nav=useNavigate();

  const logout=()=>{
    localStorage.removeItem("grace_token");
    setUser(null);
    nav("/login");
  };

  const links=[
    ["/","Home",HomeIcon],
    ["/health","Health",HeartPulse],
    ["/period","Period",CalendarDays],
    ["/wellness","Wellness",Clipboard],
    ["/medical","Medical",Stethoscope],
    ["/reports","Reports",FileText],
    ["/profile","Profile",UserRound]
  ];

  return (
    <div className="shell">

      <aside className={open?"side open":"side"}>

        <div className="logo">

          <img src="/gracehealth-logo.png"/>

          <div>
            <b>GraceHealth</b>
            <small>Care. Track. Understand.</small>
          </div>

        </div>

        <nav>

          {links.map(([p,n,I])=>(
            <NavLink
              end={p==="/"}
              key={p}
              to={p}
              onClick={()=>setOpen(false)}
            >
              <I size={18}/>
              {n}
            </NavLink>
          ))}

        </nav>

        <div className="bottom">

          <div className="device">

            <Wifi size={17}/>

            <div>
              <b>Health_Box</b>
              <small>HB-0001</small>
            </div>

          </div>

          <button onClick={logout}>
            <LogOut size={17}/>
            Logout
          </button>

        </div>

      </aside>

      <main>

        <header>

          <button
            className="menubtn"
            onClick={()=>setOpen(!open)}
          >
            {open?<X/>:<Menu/>}
          </button>

          <div>
            <b>
              Hello, {user.name.split(" ")[0]}
            </b>

            <small>
              Your private health space
            </small>
          </div>

          <span className="id">
            {user.health_id}
          </span>

        </header>

        <section className="content">
          {children}
        </section>

        <footer>
          GraceHealth · Made by <b>Surya Prakash Jha</b> ·
          <a href="mailto:suryaprakashjha96@gmail.com">
            suryaprakashjha96@gmail.com
          </a>
        </footer>

      </main>

    </div>
  );
}


function Home({user}){

  const [s,setS]=useState(null);
  const [r,setR]=useState([]);
  const [busy,setBusy]=useState(false);

  const load=()=>Promise.all([
    api("/device/status"),
    api("/readings")
  ]).then(([a,b])=>{
    setS(a);
    setR(b.readings||[]);
  });

  useEffect(()=>{
    load();
  },[]);

  const connect=async()=>{
    setBusy(true);

    try{
      await post("/device/connect",{});
      await load();
    }catch(e){
      alert(e.message);
    }

    setBusy(false);
  };

  const disconnect=async()=>{
    setBusy(true);

    try{
      await post("/device/disconnect",{});
      await load();
    }catch(e){
      alert(e.message);
    }

    setBusy(false);
  };

  const x=r[0];

  return (
    <>
      <div className="hero">

        <div>

          <em>
            YOUR PERSONAL HEALTH SPACE
          </em>

          <h1>
            Hello, {user.name.split(" ")[0]}.
          </h1>

          <p>
            Track your health, cycle and wellness
            in one calm, private place.
          </p>

        </div>

        <img src="/gracehealth-logo.png"/>

      </div>


      <div className="devicebar">

        <span
          className={
            s?.status==="connected"
              ? "dot on"
              : "dot"
          }
        ></span>

        <div>

          <b>
            GraceHealth Health_Box · HB-0001
          </b>

          <small>
            {s?.status==="connected"
              ? "Connected to your account"
              : "Available for connection"}
          </small>

        </div>

        <div className="push">

          {s?.status==="connected" ? (

            <button
              className="secondary"
              disabled={busy}
              onClick={disconnect}
            >
              Disconnect
            </button>

          ) : (

            <button
              className="primary small"
              disabled={busy}
              onClick={connect}
            >
              {busy
                ? "Connecting…"
                : "Connect Health_Box"}
            </button>

          )}

        </div>

      </div>


      <Title
        t="Live health snapshot"
        sub="Latest values from your Health_Box."
      />

      <div className="metrics">

        <Metric
          I={HeartPulse}
          n="Heart rate"
          v={x?.bpm}
          u="BPM"
        />

        <Metric
          I={Activity}
          n="SpO₂"
          v={x?.spo2}
          u="%"
        />

        <Metric
          I={Thermometer}
          n="Temperature"
          v={x?.temperature}
          u="°C"
        />

      </div>


      <div className="cards">

        <Card
          icon={<LockKeyhole/>}
          title="Your account is separated"
        >
          <p>
            Your readings belong to
            <b> {user.health_id}</b>.
            Another person can use the same physical
            Health_Box with their own account and session.
          </p>
        </Card>


        <Card
          icon={<ShieldCheck/>}
          title="One box, one active user"
        >
          <p>
            The backend locks HB-0001 to one active session.
            Disconnecting releases it for the next user.
          </p>
        </Card>

      </div>


      <Title t="Quick actions"/>

      <div className="quick">

        <Q
          to="/period"
          t="Log period"
          s="Start or update your cycle"
          I={CalendarDays}
        />

        <Q
          to="/wellness"
          t="Daily wellness"
          s="Symptoms, sleep, water and exercise"
          I={Clipboard}
        />

        <Q
          to="/medical"
          t="Medical notes"
          s="Doctor visits and medication"
          I={Stethoscope}
        />

        <Q
          to="/reports"
          t="Reports"
          s="Review your health records"
          I={FileText}
        />

      </div>

    </>
  );
}


function Metric({I,n,v,u}){

  return (
    <div className="metric">

      <span>
        <I/>
      </span>

      <div>

        <small>{n}</small>

        <strong>
          {v??"—"} <i>{u}</i>
        </strong>

      </div>

    </div>
  );
}


function Title({t,sub}){

  return (
    <div className="title">

      <div>

        <h2>{t}</h2>

        {sub&&(
          <p>{sub}</p>
        )}

      </div>

    </div>
  );
}


function Card({icon,title,children}){

  return (
    <div className="card">

      <div className="cardtitle">
        {icon}
        <b>{title}</b>
      </div>

      {children}

    </div>
  );
}


function Q({to,t,s,I}){

  return (
    <NavLink
      to={to}
      className="q"
    >
      <I/>
      <b>{t}</b>
      <small>{s}</small>
    </NavLink>
  );
}


function Health(){

  const [r,setR]=useState([]);

  useEffect(()=>{
    api("/readings")
      .then(x=>setR(x.readings||[]));
  },[]);

  return (
    <>
      <Head
        k="HEALTH"
        t="Vitals & trends"
        s="Measurements recorded through your shared Health_Box."
      />

      <div className="metrics">

        <Metric
          I={HeartPulse}
          n="Heart rate"
          v={r[0]?.bpm}
          u="BPM"
        />

        <Metric
          I={Activity}
          n="SpO₂"
          v={r[0]?.spo2}
          u="%"
        />

        <Metric
          I={Thermometer}
          n="Temperature"
          v={r[0]?.temperature}
          u="°C"
        />

      </div>


      <Card
        title="Vitals history"
        icon={<Activity/>}
      >

        {r.length ? (

          <table>

            <thead>

              <tr>
                <th>Date</th>
                <th>BPM</th>
                <th>SpO₂</th>
                <th>Temp</th>
              </tr>

            </thead>

            <tbody>

              {r.map(x=>(
                <tr key={x.id}>

                  <td>
                    {new Date(x.time).toLocaleString()}
                  </td>

                  <td>
                    {x.bpm??"—"}
                  </td>

                  <td>
                    {x.spo2??"—"}
                  </td>

                  <td>
                    {x.temperature??"—"}
                  </td>

                </tr>
              ))}

            </tbody>

          </table>

        ) : (

          <Empty>
            No readings yet.
          </Empty>

        )}

      </Card>


      <div className="note">
        A waterproof DS18B20 on skin measures surface temperature;
        it should not automatically be described as core body temperature.
      </div>

    </>
  );
}


function Head({k,t,s}){

  return (
    <div className="head">

      <em>{k}</em>

      <h1>{t}</h1>

      <p>{s}</p>

    </div>
  );
}


function Empty({children}){

  return (
    <div className="empty">
      {children}
    </div>
  );
}


function Period(){

  const [c,setC]=useState([]);
  const [d,setD]=useState("");

  const load=()=>api("/cycles")
    .then(x=>setC(x.cycles||[]));

  useEffect(()=>{
    load();
  },[]);

  const add=async()=>{

    if(d){

      await post("/cycles",{
        start_date:d
      });

      setD("");

      load();
    }

  };

  return (
    <>
      <Head
        k="PERIOD"
        t="Your cycle space"
        s="Track dates, symptoms and cycle history."
      />

      <div className="cards">

        <Card
          icon={<CalendarDays/>}
          title="Start a period"
        >

          <label>
            Date

            <input
              type="date"
              value={d}
              onChange={e=>setD(e.target.value)}
            />

          </label>

          <button
            className="primary"
            onClick={add}
          >
            <Plus size={16}/>
            Start period
          </button>

        </Card>


        <Card
          icon={<HeartPulse/>}
          title="Cycle intelligence"
        >

          <p>
            Cycle length, variation, phases and symptom
            patterns can be calculated as your records grow.
          </p>

        </Card>

      </div>


      <Card
        icon={<CalendarDays/>}
        title="Cycle history"
      >

        {c.length ? (

          <table>

            <thead>

              <tr>
                <th>Start</th>
                <th>End</th>
                <th>Duration</th>
              </tr>

            </thead>

            <tbody>

              {c.map(x=>(
                <tr key={x.id}>

                  <td>{x.start_date}</td>

                  <td>
                    {x.end_date||"Active"}
                  </td>

                  <td>
                    {x.duration??"—"}
                  </td>

                </tr>
              ))}

            </tbody>

          </table>

        ) : (

          <Empty>
            No cycles recorded yet.
          </Empty>

        )}

      </Card>

    </>
  );
}


function Wellness(){

  const [p,setP]=useState({
    mood:"",
    bloating:"",
    headache:"",
    notes:""
  });

  const [m,setM]=useState({
    pain_relief:"",
    iron_supp:"",
    vitamin_d:"",
    other:""
  });

  const [msg,setMsg]=useState("");

  const saveP=async()=>{

    await post("/pms",{
      ...p,
      date:new Date()
        .toISOString()
        .slice(0,10)
    });

    setMsg("PMS log saved.");
  };

  const saveM=async()=>{

    await post("/medications",{
      ...m,
      date:new Date()
        .toISOString()
        .slice(0,10)
    });

    setMsg("Medication log saved.");
  };

  return (
    <>
      <Head
        k="WELLNESS"
        t="Daily wellness"
        s="Keep everyday health notes together."
      />

      {msg&&(
        <div className="success">
          {msg}
        </div>
      )}

      <div className="cards">

        <Card
          icon={<Clipboard/>}
          title="PMS log"
        >

          <Form
            fields={[
              ["Mood","mood"],
              ["Bloating","bloating"],
              ["Headache","headache"],
              ["Notes","notes","textarea"]
            ]}
            v={p}
            set={setP}
          />

          <button
            className="primary"
            onClick={saveP}
          >
            Save PMS log
          </button>

        </Card>


        <Card
          icon={<Activity/>}
          title="Medication log"
        >

          <Form
            fields={[
              ["Pain relief","pain_relief"],
              ["Iron supplement","iron_supp"],
              ["Vitamin D","vitamin_d"],
              ["Other","other"]
            ]}
            v={m}
            set={setM}
          />

          <button
            className="primary"
            onClick={saveM}
          >
            Save medication log
          </button>

        </Card>

      </div>

    </>
  );
}


function Form({fields,v,set}){

  return (
    <div className="form">

      {fields.map(([n,k,t])=>(
        <label key={k}>

          {n}

          {t==="textarea" ? (

            <textarea
              value={v[k]}
              onChange={e=>set({
                ...v,
                [k]:e.target.value
              })}
            />

          ) : (

            <input
              value={v[k]}
              onChange={e=>set({
                ...v,
                [k]:e.target.value
              })}
            />

          )}

        </label>
      ))}

    </div>
  );
}


function Medical(){

  const [v,setV]=useState([]);

  const [f,setF]=useState({
    visit_date:"",
    diagnosis:"",
    medication:"",
    next_appt:"",
    notes:""
  });

  const load=()=>api("/doctor-visits")
    .then(x=>setV(x.visits||[]));

  useEffect(()=>{
    load();
  },[]);

  const save=async e=>{

    e.preventDefault();

    await post("/doctor-visits",f);

    setF({
      visit_date:"",
      diagnosis:"",
      medication:"",
      next_appt:"",
      notes:""
    });

    load();
  };

  const del=async id=>{

    await api(
      "/doctor-visits/"+id,
      {
        method:"DELETE"
      }
    );

    load();
  };

  return (
    <>
      <Head
        k="MEDICAL"
        t="Medical records"
        s="Keep doctor visits and notes organized."
      />

      <Card
        icon={<Stethoscope/>}
        title="Add doctor visit"
      >

        <form
          onSubmit={save}
          className="form"
        >

          <label>
            Visit date

            <input
              required
              type="date"
              value={f.visit_date}
              onChange={e=>setF({
                ...f,
                visit_date:e.target.value
              })}
            />

          </label>

          <label>
            Diagnosis

            <input
              value={f.diagnosis}
              onChange={e=>setF({
                ...f,
                diagnosis:e.target.value
              })}
            />

          </label>

          <label>
            Medication

            <input
              value={f.medication}
              onChange={e=>setF({
                ...f,
                medication:e.target.value
              })}
            />

          </label>

          <label>
            Notes

            <textarea
              value={f.notes}
              onChange={e=>setF({
                ...f,
                notes:e.target.value
              })}
            />

          </label>

          <button className="primary">
            <Plus size={16}/>
            Save visit
          </button>

        </form>

      </Card>


      <Card
        icon={<Stethoscope/>}
        title="Visit history"
      >

        {v.length ? (

          v.map(x=>(
            <div
              className="row"
              key={x.id}
            >

              <div>

                <b>{x.visit_date}</b>

                <small>
                  {x.diagnosis||"No diagnosis entered"}
                </small>

              </div>

              <button
                onClick={()=>del(x.id)}
              >
                <Trash2 size={16}/>
              </button>

            </div>
          ))

        ) : (

          <Empty>
            No doctor visits recorded.
          </Empty>

        )}

      </Card>

    </>
  );
}


function Reports(){

  return (
    <>
      <Head
        k="REPORTS"
        t="Health reports"
        s="Reports are generated from records linked to your Health ID."
      />

      <div className="cards">

        <Card
          icon={<FileText/>}
          title="Personal health report"
        >

          <p>
            Profile, vitals history and health summary.
          </p>

          <button className="secondary">
            Generate report
          </button>

        </Card>


        <Card
          icon={<CalendarDays/>}
          title="Cycle report"
        >

          <p>
            Cycle dates, daily symptoms, patterns and summary.
          </p>

          <button className="secondary">
            Generate report
          </button>

        </Card>

      </div>

      <div className="note">
        PDF report generation is prepared as the next backend module.
      </div>

    </>
  );
}


function Profile({user}){

  const [s,setS]=useState(null);

  useEffect(()=>{
    api("/device/status")
      .then(setS);
  },[]);

  return (
    <>
      <Head
        k="PROFILE"
        t="Your profile"
        s="Account identity and Health_Box connection."
      />

      <div className="cards">

        <Card
          icon={<UserRound/>}
          title={user.name}
        >

          <p>
            {user.email}
          </p>

          <div className="healthid">
            Personal Health ID
            <b>{user.health_id}</b>
          </div>

        </Card>


        <Card
          icon={<Wifi/>}
          title="Health_Box connection"
        >

          <div className="connection">

            <ShieldCheck/>

            <div>

              <b>HB-0001</b>

              <small>
                {s?.status==="connected"
                  ? "Connected to your session"
                  : "Available"}
              </small>

            </div>

          </div>

          <p>
            Only one user session can occupy
            the shared Health_Box at a time.
          </p>

        </Card>

      </div>


      <Card
        icon={<Mail/>}
        title="Admin contact"
      >

        <p>
          GraceHealth was made by
          <b> Surya Prakash Jha</b>.
        </p>

        <a
          className="mail"
          href="mailto:suryaprakashjha96@gmail.com"
        >
          suryaprakashjha96@gmail.com
        </a>

      </Card>

    </>
  );
}


function App(){

  const [user,setUser]=useState(null);
  const [loading,setLoading]=useState(true);
  const loc=useLocation();

  useEffect(()=>{

    if(localStorage.getItem("grace_token")){

      api("/me")
        .then(x=>setUser(x.user))
        .catch(()=>{
          localStorage.removeItem("grace_token");
        })
        .finally(()=>{
          setLoading(false);
        });

    }else{

      setLoading(false);

    }

  },[]);

  if(loading){

    return (
      <div className="splash">

        <img src="/gracehealth-logo.png"/>

        <h1>
          GraceHealth
        </h1>

        <span>
          Loading your private health space…
        </span>

      </div>
    );
  }

  if(!user){

    return loc.pathname==="/register"
      ? <Auth register setUser={setUser}/>
      : <Auth setUser={setUser}/>;
  }

  let page=

    loc.pathname==="/health"
      ? <Health/>

    : loc.pathname==="/period"
      ? <Period/>

    : loc.pathname==="/wellness"
      ? <Wellness/>

    : loc.pathname==="/medical"
      ? <Medical/>

    : loc.pathname==="/reports"
      ? <Reports/>

    : loc.pathname==="/profile"
      ? <Profile user={user}/>

    : <Home user={user}/>;

  return (
    <Layout
      user={user}
      setUser={setUser}
    >
      {page}
    </Layout>
  );
}


createRoot(
  document.getElementById("root")
).render(
  <BrowserRouter>
    <App/>
  </BrowserRouter>
);