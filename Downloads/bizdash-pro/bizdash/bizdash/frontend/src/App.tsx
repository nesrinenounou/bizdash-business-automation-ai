import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, download, hasToken, setToken } from "./api";
import { Avatar, AuditLog, CustomerEditor, OrderEditor, Profile, Users, can, type User } from "./extra";

interface Customer { id: number; name: string; email: string; phone?: string; created_at: string }
interface Order { id: number; customer_name: string; title: string; amount: number; status: string;
  created_at: string; message?: string; summary?: string; category?: string; priority?: string }
interface Stats { customers: number; orders: number; revenue: number; avg_order_value: number;
  by_status: Record<string, number>; monthly_revenue: number[];
  revenue_this_month: number; revenue_last_month: number; orders_this_month: number; orders_last_month: number;
  customers_this_month: number; customers_last_month: number }

const STATUS: Record<string, { label: string; color: string }> = {
  new: { label: "Pending", color: "#a16207" }, in_progress: { label: "Processing", color: "#1d63b8" },
  done: { label: "Delivered", color: "#13794b" }, cancelled: { label: "Cancelled", color: "#b42318" },
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const ICONS: Record<string, string> = {
  users: "M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0zM4 21a8 8 0 0 1 16 0",
  audit: "M9 5h10v14H5V5h4M9 9h6M9 13h6",
  dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  orders: "M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0",
  customers: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  revenue: "M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  average: "M3 3v18h18M7 14l4-4 4 4 5-6",
};
const num = (n: number) => Math.round(n).toLocaleString("en-US");
const date = (d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function Icon({ name }: { name: string }) {
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[name]} /></svg>;
}

function Pill({ status }: { status: string }) {
  const s = STATUS[status];
  return <span className="pill" style={{ background: s.color + "26", color: s.color }}>{s.label}</span>;
}

function Trend({ cur, prev }: { cur: number; prev: number }) {
  if (!prev) return <small className="muted">{cur ? "first activity this month" : "no data last month"}</small>;
  const p = ((cur - prev) / prev) * 100;
  return <small><b className={p >= 0 ? "up" : "down"}>{p >= 0 ? "▲" : "▼"} {Math.abs(p).toFixed(1)}%</b> <span className="muted">vs last month</span></small>;
}

function Kpi({ icon, label, value, children }: { icon: string; color?: string; label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="card kpi">
      <div className="kpi-head"><span className="ico" aria-hidden="true"><Icon name={icon} /></span>{label}</div>
      <strong>{value}</strong>{children}
    </div>
  );
}

function SalesChart({ data }: { data: number[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const month = new Date().getMonth();
  const max = Math.max(1, ...data) * 1.15, H = 220, W = 640, bw = 28;
  const shown = hover ?? month;
  return (
    <div>
      <p className="chart-note">{MONTHS[shown]}: <b>{num(data[shown])}</b></p>
      <svg viewBox={`0 0 ${W} ${H + 24}`} className="chart" role="img" aria-label="Revenue by month this year">
        {[0, 1, 2, 3].map(i => <line key={i} x1="0" x2={W} y1={H - (H * i) / 4} y2={H - (H * i) / 4} stroke="var(--line)" />)}
        {data.map((v, i) => {
          const x = i * (W / 12) + (W / 12 - bw) / 2, h = (v / max) * H;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={i * (W / 12)} y="0" width={W / 12} height={H} fill="transparent" />
              <rect x={x} y={H - h} width={bw} height={Math.max(h, 2)} rx="4" fill={i === shown ? "var(--accent)" : "#b7d9d6"} />
              <text x={x + bw / 2} y={H + 16} textAnchor="middle" fontSize="11" fill="var(--muted)">{MONTHS[i]}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function OrdersTable({ orders, onStatus, ai, onEdit, onDelete }: { orders: Order[]; onStatus?: (id: number, s: string) => void; ai?: boolean; onEdit?: (o: Order) => void; onDelete?: (id: number) => void }) {
  if (!orders.length) return <p className="empty">No orders to show. Create an order from the Orders page.</p>;
  return (
    <div className="scroll"><table>
      <thead><tr><th>Order ID</th><th>Product</th><th>Customer</th><th>Order date</th><th>Status</th><th className="r">Price</th>{ai && <th>AI triage</th>}{(onEdit || onDelete) && <th />}</tr></thead>
      <tbody>{orders.map(o => (
        <tr key={o.id}>
          <td>#{String(o.id).padStart(5, "0")}</td><td>{o.title}</td><td>{o.customer_name}</td><td>{date(o.created_at)}</td>
          <td>{onStatus ? (
            <select className="pill-select" value={o.status} aria-label="Order status" onChange={e => onStatus(o.id, e.target.value)}
              style={{ background: STATUS[o.status].color + "26", color: STATUS[o.status].color }}>
              {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>) : <Pill status={o.status} />}</td>
          <td className="r">{num(o.amount)}</td>
          {ai && <td>{o.category ? <><span className={`tag ${o.priority}`}>{o.category}</span> {o.summary}</> :
            <span className="muted">{o.message ? "analysing…" : "—"}</span>}</td>}
          {(onEdit || onDelete) && <td className="r">{onEdit && <button className="link" onClick={() => onEdit(o)}>Edit</button>}
            {onDelete && <button className="link danger" onClick={() => onDelete(o.id)}>Delete</button>}</td>}
        </tr>))}
      </tbody></table></div>
  );
}

const match = (q: string, ...fields: (string | undefined)[]) => !q || fields.some(f => f?.toLowerCase().includes(q.toLowerCase()));

function Dashboard({ q }: { q: string }) {
  const [s, setS] = useState<Stats>();
  const [orders, setOrders] = useState<Order[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => { Promise.all([api<Stats>("/stats"), api<Order[]>("/orders?limit=50")]).then(([st, os]) => { setS(st); setOrders(os); }).catch(x => setErr((x as Error).message)); }, []);
  if (err) return <p className="error" role="alert">Could not load the dashboard: {err}</p>;
  if (!s) return <div className="kpis" aria-busy="true">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton" />)}</div>;
  const shown = orders.filter(o => match(q, o.title, o.customer_name, o.status)).slice(0, 6);
  return (
    <>
      <div className="kpis">
        <Kpi icon="revenue" color="#6366f1" label="Total revenue" value={num(s.revenue)}><Trend cur={s.revenue_this_month} prev={s.revenue_last_month} /></Kpi>
        <Kpi icon="orders" color="#22c55e" label="Total orders" value={num(s.orders)}><Trend cur={s.orders_this_month} prev={s.orders_last_month} /></Kpi>
        <Kpi icon="customers" color="#8b5cf6" label="Customers" value={num(s.customers)}><Trend cur={s.customers_this_month} prev={s.customers_last_month} /></Kpi>
        <Kpi icon="average" color="#0ea5a4" label="Avg. order value" value={num(s.avg_order_value)}><small className="muted">cancelled orders excluded</small></Kpi>
      </div>
      <div className="split">
        <section className="card"><h2>Sales performance</h2><p className="muted">Revenue by month, this year</p><SalesChart data={s.monthly_revenue} /></section>
        <section className="card"><h2>Order distribution</h2><p className="muted">Total orders</p><strong className="big">{s.orders}</strong>
          <div className="stack">{Object.entries(STATUS).map(([k, v]) => <i key={k} style={{ flex: s.by_status[k] || 0, background: v.color }} />)}</div>
          {Object.entries(STATUS).map(([k, v]) => (
            <div className="dist" key={k}><span><i className="dot" style={{ background: v.color }} />{v.label}</span><b>{s.by_status[k] || 0}</b></div>))}
        </section>
      </div>
      <section className="card"><h2>Recent orders</h2><OrdersTable orders={shown} /></section>
    </>
  );
}

function Orders({ q, me }: { q: string; me: User }) {
  const [editing, setEditing] = useState<Order>();
  const [list, setList] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [err, setErr] = useState("");
  const load = useCallback(() => { Promise.all([api<Order[]>("/orders"), api<Customer[]>("/customers")]).then(([o, c]) => { setList(o); setCustomers(c); }).catch(x => setErr((x as Error).message)); }, []);
  useEffect(load, [load]);
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget, f = new FormData(form);
    try {
      await api("/orders", { method: "POST", body: JSON.stringify({ customer_id: Number(f.get("customer")), title: f.get("title"),
        amount: Number(f.get("amount")), message: f.get("message") || null }) });
      form.reset(); setErr(""); load(); setTimeout(load, 3000);
    } catch (x) { setErr((x as Error).message); }
  }
  async function delOrder(id: number) { if (!confirm("Delete this order?")) return; try { await api(`/orders/${id}`, { method: "DELETE" }); load(); } catch (x) { setErr((x as Error).message); } }
  async function setStatus(id: number, status: string) { try { await api(`/orders/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }); load(); } catch (x) { setErr((x as Error).message); } }
  const shown = useMemo(() => list.filter(o => match(q, o.title, o.customer_name, o.category, STATUS[o.status].label)), [list, q]);
  return (
    <>
      <form className="card form" onSubmit={add}>
        <h2>New order</h2>
        <div className="fields">
          <select name="customer" required defaultValue="" aria-label="Customer"><option value="" disabled>Choose a customer</option>
            {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <input name="title" placeholder="What was ordered" required />
          <input name="amount" type="number" min="0" step="0.01" placeholder="Amount" required />
        </div>
        <textarea name="message" placeholder="Customer message (optional): the AI summarises and sorts it" />
        {err && <p className="error" role="alert">{err}</p>}
        <button>Create order</button>
      </form>
      <section className="card"><div className="row"><h2>Orders list</h2><button className="ghost" onClick={() => download("/export/orders.csv", "orders.csv")}>Export CSV</button></div>{err && <p className="error" role="alert">{err}</p>}<OrdersTable orders={shown} onStatus={setStatus} ai onEdit={can(me, "orders:write") ? setEditing : undefined} onDelete={can(me, "orders:delete") ? delOrder : undefined} />
        {editing && <OrderEditor o={editing} statuses={Object.fromEntries(Object.entries(STATUS).map(([k, v]) => [k, v.label]))} onClose={() => setEditing(undefined)} onSaved={load} />}</section>
    </>
  );
}

function Customers({ me, q }: { me: User; q: string }) {
  const [editing, setEditing] = useState<Customer>();
  const [list, setList] = useState<Customer[]>([]);
  const [err, setErr] = useState("");
  const load = useCallback(() => { api<Customer[]>("/customers").then(setList).catch(x => setErr((x as Error).message)); }, []);
  useEffect(load, [load]);
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget, f = new FormData(form);
    try {
      await api("/customers", { method: "POST", body: JSON.stringify({ name: f.get("name"), email: f.get("email"), phone: f.get("phone") || null }) });
      form.reset(); setErr(""); load();
    } catch (x) { setErr((x as Error).message); }
  }
  async function del(id: number) { if (!confirm("Delete this customer and all their orders?")) return; try { await api(`/customers/${id}`, { method: "DELETE" }); load(); } catch (x) { setErr((x as Error).message); } }
  const shown = list.filter(c => match(q, c.name, c.email, c.phone));
  return (
    <>
      <form className="card form" onSubmit={add}>
        <h2>New customer</h2>
        <div className="fields">
          <input name="name" placeholder="Name" required /><input name="email" type="email" placeholder="Email" required />
          <input name="phone" placeholder="Phone (optional)" />
        </div>
        {err && <p className="error" role="alert">{err}</p>}
        <button>Add customer</button>
      </form>
      <section className="card">{editing && <CustomerEditor c={editing} onClose={() => setEditing(undefined)} onSaved={load} />}
      <div className="row"><h2>Customer list</h2><button className="ghost" onClick={() => download("/export/customers.csv", "customers.csv")}>Export CSV</button></div>
        {!shown.length ? <p className="empty">No customers to show. Add the first one above.</p> : (
          <div className="scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Added</th><th /></tr></thead><tbody>
            {shown.map(c => <tr key={c.id}><td>{c.name}</td><td>{c.email}</td><td>{c.phone}</td><td>{date(c.created_at)}</td>
              <td className="r">{can(me, "customers:write") && <button className="link" onClick={() => setEditing(c)}>Edit</button>}
                {can(me, "customers:delete") && <button className="link danger" onClick={() => del(c.id)}>Delete</button>}</td></tr>)}
          </tbody></table></div>)}
      </section>
    </>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [register, setRegister] = useState(false);
  const [err, setErr] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget), email = String(f.get("email")), password = String(f.get("password"));
    try {
      if (register) await api("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
      const r = await api<{ access_token: string }>("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password }) });
      setToken(r.access_token); onDone();
    } catch (x) { setErr((x as Error).message); }
  }
  return (
    <div className="auth">
    <section className="auth-hero"><div className="brand"><span className="logo">B</span>BizDash</div>
      <div><h2>Every order, triaged before you open it.</h2><p>Customer messages are summarised and sorted by topic and urgency, and your team is notified automatically.</p></div>
      <p>Customers · Orders · Revenue</p></section>
    <div className="auth-form"><main>
      <h1>{register ? "Create account" : "Sign in"}</h1>
      <p className="muted">{register ? "New accounts start with the agent role." : "Use the email and password your admin gave you."}</p>
      <form onSubmit={submit}>
        <input name="email" type="email" placeholder="Email" autoComplete="email" required />
        <input name="password" type="password" placeholder="Password (8+ characters)" minLength={8} autoComplete={register ? "new-password" : "current-password"} required />
        {err && <p className="error" role="alert">{err}</p>}
        <button>{register ? "Create account" : "Sign in"}</button>
      </form>
      <button className="link" onClick={() => setRegister(!register)}>{register ? "I already have an account" : "Create an account"}</button>
    </main></div></div>
  );
}

type Tab = "dashboard" | "orders" | "customers" | "users" | "audit" | "profile";

export default function App() {
  const [me, setMe] = useState<User>();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [q, setQ] = useState("");
  const boot = useCallback(() => { if (hasToken()) api<User>("/auth/me").then(setMe).catch(() => setToken("")); }, []);
  useEffect(boot, [boot]);
  if (!me) return <Login onDone={boot} />;
  const title = { dashboard: "Overview", orders: "Orders", customers: "Customers", users: "Users", audit: "Audit log", profile: "My profile" }[tab];
  const tabs: Tab[] = ["dashboard", "orders", "customers"];
  const adminTabs: Tab[] = can(me, "users:manage") ? ["users", "audit"] : [];
  return (
    <div className="app">
      <aside>
        <div className="brand"><span className="logo">B</span>BizDash</div>
        <p className="group">Operations</p>
        {tabs.map(t => (
          <button key={t} className={"nav" + (t === tab ? " on" : "")} aria-current={t === tab ? "page" : undefined} onClick={() => setTab(t)}><Icon name={t} />{t[0].toUpperCase() + t.slice(1)}</button>))}
        {adminTabs.length > 0 && <p className="group">Administration</p>}
        {adminTabs.map(t => (
          <button key={t} className={"nav" + (t === tab ? " on" : "")} aria-current={t === tab ? "page" : undefined} onClick={() => setTab(t)}><Icon name={t} />{t[0].toUpperCase() + t.slice(1)}</button>))}
        <div className="me"><button className="plain" onClick={() => setTab("profile")} title="My profile" aria-label="My profile"><Avatar u={me} /></button>
          <div><b>{me.full_name || me.email.split("@")[0]}</b><small className="muted">{me.role}</small></div>
          <button className="link" onClick={() => { setToken(""); setMe(undefined); }}>Sign out</button></div>
      </aside>
      <div className="content">
        <header><h1>{title}</h1>
          <input type="search" placeholder="Search" aria-label="Search" value={q} onChange={e => setQ(e.target.value)} /></header>
        {tab === "dashboard" ? <Dashboard q={q} /> : tab === "orders" ? <Orders q={q} me={me} /> : tab === "customers" ? <Customers me={me} q={q} />
          : tab === "users" ? <Users me={me} q={q} /> : tab === "audit" ? <AuditLog /> : <Profile me={me} onChange={boot} />}
      </div>
    </div>
  );
}
