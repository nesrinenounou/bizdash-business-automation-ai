import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api, upload } from "./api";

export interface User {
  id: number; email: string; role: string; full_name?: string; phone?: string; avatar?: string;
  is_active: boolean; created_at: string; permissions: string[];
}
export const can = (u: User, perm: string) => u.permissions.includes(perm);
const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
const errMsg = (x: unknown) => (x as Error).message;

export function Avatar({ u, size = 32 }: { u: Pick<User, "email" | "full_name" | "avatar">; size?: number }) {
  return u.avatar
    ? <img className="avatar" src={`/api/avatars/${u.avatar}`} alt="" width={size} height={size} style={{ width: size, height: size }} />
    : <span className="avatar" aria-hidden="true" style={{ width: size, height: size, fontSize: size * 0.42 }}>{(u.full_name || u.email)[0].toUpperCase()}</span>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onClose={onClose} onClick={e => e.target === ref.current && ref.current?.close()}>
      <h2>{title}</h2>{children}
    </dialog>);
}

function Actions({ onClose, label = "Save changes" }: { onClose: () => void; label?: string }) {
  return <div className="actions"><button>{label}</button><button type="button" className="ghost" onClick={onClose}>Cancel</button></div>;
}

/** Shared submit logic: run `fn`, show the server error, close on success. */
function useSubmit(fn: (f: FormData) => Promise<unknown>, onDone: () => void) {
  const [err, setErr] = useState("");
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try { await fn(new FormData(e.currentTarget)); onDone(); } catch (x) { setErr(errMsg(x)); }
  };
  return { err, submit };
}

export function CustomerEditor({ c, onClose, onSaved }: { c: { id: number; name: string; email: string; phone?: string }; onClose: () => void; onSaved: () => void }) {
  const { err, submit } = useSubmit(f => api(`/customers/${c.id}`, { method: "PUT",
    body: JSON.stringify({ name: f.get("name"), email: f.get("email"), phone: f.get("phone") || null }) }), () => { onSaved(); onClose(); });
  return (
    <Modal title="Edit customer" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <input name="name" defaultValue={c.name} placeholder="Name" aria-label="Name" required />
        <input name="email" type="email" defaultValue={c.email} placeholder="Email" aria-label="Email" required />
        <input name="phone" defaultValue={c.phone ?? ""} placeholder="Phone" aria-label="Phone" />
        {err && <p className="error" role="alert">{err}</p>}<Actions onClose={onClose} />
      </form>
    </Modal>);
}

export function OrderEditor({ o, statuses, onClose, onSaved }: { o: { id: number; title: string; amount: number; status: string }; statuses: Record<string, string>; onClose: () => void; onSaved: () => void }) {
  const { err, submit } = useSubmit(f => api(`/orders/${o.id}`, { method: "PATCH",
    body: JSON.stringify({ title: f.get("title"), amount: Number(f.get("amount")), status: f.get("status") }) }), () => { onSaved(); onClose(); });
  return (
    <Modal title={`Edit order #${String(o.id).padStart(5, "0")}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <input name="title" defaultValue={o.title} aria-label="Title" required />
        <input name="amount" type="number" min="0" step="0.01" defaultValue={o.amount} aria-label="Amount" required />
        <select name="status" defaultValue={o.status} aria-label="Status">{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        {err && <p className="error" role="alert">{err}</p>}<Actions onClose={onClose} />
      </form>
    </Modal>);
}

/** Photo picker used for my own profile and by admins for any user. */
function PhotoField({ user, base, onChanged }: { user: User; base: string; onChanged: () => void }) {
  const [err, setErr] = useState("");
  const pick = async (file?: File) => { if (!file) return; try { await upload(base + "/avatar", file); setErr(""); onChanged(); } catch (x) { setErr(errMsg(x)); } };
  const remove = async () => { try { await api(base + "/avatar", { method: "DELETE" }); onChanged(); } catch (x) { setErr(errMsg(x)); } };
  return (
    <div className="photo">
      <Avatar u={user} size={72} />
      <div>
        <label className="ghost btn">Upload photo<input className="sr" type="file" accept="image/png,image/jpeg,image/webp" onChange={e => pick(e.target.files?.[0])} /></label>
        {user.avatar && <button type="button" className="link danger" onClick={remove}>Remove</button>}
        <p className="muted">PNG, JPEG or WebP, 2 MB max.</p>{err && <p className="error" role="alert">{err}</p>}
      </div>
    </div>);
}

export function Profile({ me, onChange }: { me: User; onChange: () => void }) {
  const [msg, setMsg] = useState(""); const [pwMsg, setPwMsg] = useState("");
  const prof = useSubmit(f => api("/users/me", { method: "PATCH", body: JSON.stringify({ full_name: f.get("full_name") || null, phone: f.get("phone") || null }) }),
    () => { setMsg("Profile saved."); onChange(); });
  const pw = useSubmit(f => api("/auth/password", { method: "POST", body: JSON.stringify({ current_password: f.get("current"), new_password: f.get("next") }) }),
    () => setPwMsg("Password changed."));
  return (
    <div className="split">
      <section className="card"><h2>My profile</h2>
        <PhotoField user={me} base="/users/me" onChanged={onChange} />
        <form className="form" onSubmit={prof.submit}>
          <input value={me.email} disabled aria-label="Email" />
          <input name="full_name" defaultValue={me.full_name ?? ""} placeholder="Full name" aria-label="Full name" />
          <input name="phone" defaultValue={me.phone ?? ""} placeholder="Phone" aria-label="Phone" />
          <p className="muted">Role: <span className="tag">{me.role}</span></p>
          {prof.err && <p className="error" role="alert">{prof.err}</p>}{msg && <p className="up">{msg}</p>}
          <button>Save profile</button>
        </form></section>
      <section className="card"><h2>Change password</h2>
        <form className="form" onSubmit={pw.submit}>
          <input name="current" type="password" placeholder="Current password" autoComplete="current-password" required />
          <input name="next" type="password" placeholder="New password (8+ characters)" minLength={8} autoComplete="new-password" required />
          {pw.err && <p className="error" role="alert">{pw.err}</p>}{pwMsg && <p className="up">{pwMsg}</p>}
          <button>Update password</button>
        </form></section>
    </div>);
}

function UserEditor({ u, me, onClose, onSaved }: { u: User | null; me: User; onClose: () => void; onSaved: () => void }) {
  const [live, setLive] = useState(u);   // refreshed after a photo change, so the preview updates in place
  const self = u?.id === me.id;
  const { err, submit } = useSubmit(f => u
    ? api(`/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ full_name: f.get("full_name") || null, phone: f.get("phone") || null,
        ...(self ? {} : { role: f.get("role"), is_active: f.get("is_active") === "on" }) }) })
    : api("/users", { method: "POST", body: JSON.stringify({ email: f.get("email"), password: f.get("password"), role: f.get("role"), full_name: f.get("full_name") || null }) }),
    () => { onSaved(); onClose(); });
  const refresh = async () => { if (u) setLive(await api<User[]>("/users?limit=500").then(l => l.find(x => x.id === u.id) ?? u)); onSaved(); };
  return (
    <Modal title={u ? "Edit user" : "New user"} onClose={onClose}>
      {live && <PhotoField user={live} base={`/users/${live.id}`} onChanged={refresh} />}
      <form className="form" onSubmit={submit}>
        {u ? <input value={u.email} disabled aria-label="Email" /> : <>
          <input name="email" type="email" placeholder="Email" required />
          <input name="password" type="password" placeholder="Temporary password (8+ characters)" minLength={8} required /></>}
        <input name="full_name" defaultValue={u?.full_name ?? ""} placeholder="Full name" aria-label="Full name" />
        {u && <input name="phone" defaultValue={u.phone ?? ""} placeholder="Phone" aria-label="Phone" />}
        <select name="role" defaultValue={u?.role ?? "agent"} disabled={self} aria-label="Role"><option value="agent">Agent</option><option value="admin">Admin</option></select>
        {u && <label className="check"><input type="checkbox" name="is_active" defaultChecked={u.is_active} disabled={self} /> Account active</label>}
        {self && <p className="muted">You cannot change your own role or deactivate yourself.</p>}
        {err && <p className="error" role="alert">{err}</p>}<Actions onClose={onClose} label={u ? "Save changes" : "Create user"} />
      </form>
    </Modal>);
}

export function Users({ me, q }: { me: User; q: string }) {
  const [list, setList] = useState<User[]>([]); const [err, setErr] = useState(""); const [edit, setEdit] = useState<User | "new">();
  const load = useCallback(() => { api<User[]>("/users?limit=500").then(setList).catch(x => setErr(errMsg(x))); }, []);
  useEffect(load, [load]);
  const shown = list.filter(u => !q || [u.email, u.full_name, u.role].some(f => f?.toLowerCase().includes(q.toLowerCase())));
  async function del(u: User) {
    if (!confirm(`Delete ${u.email}? This cannot be undone.`)) return;
    try { await api(`/users/${u.id}`, { method: "DELETE" }); load(); } catch (x) { setErr(errMsg(x)); }
  }
  return (
    <section className="card">
      <div className="row"><h2>Registered users ({list.length})</h2><button onClick={() => setEdit("new")}>New user</button></div>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="scroll"><table>
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Phone</th><th>Joined</th><th /></tr></thead>
        <tbody>{shown.map(u => (
          <tr key={u.id}>
            <td><div className="who"><Avatar u={u} /><div><b>{u.full_name || u.email.split("@")[0]}</b><br /><span className="muted">{u.email}</span></div></div></td>
            <td><span className={"tag" + (u.role === "admin" ? " high" : "")}>{u.role}</span></td>
            <td>{u.is_active ? <span className="up">Active</span> : <span className="down">Disabled</span>}</td>
            <td>{u.phone || "—"}</td><td>{when(u.created_at)}</td>
            <td className="r"><button className="link" onClick={() => setEdit(u)}>Edit</button>
              {u.id !== me.id && <button className="link danger" onClick={() => del(u)}>Delete</button>}</td>
          </tr>))}</tbody></table></div>
      {edit && <UserEditor u={edit === "new" ? null : edit} me={me} onClose={() => setEdit(undefined)} onSaved={load} />}
    </section>);
}

interface Audit { id: number; actor: string; action: string; target: string; detail: string; created_at: string }
export function AuditLog() {
  const [list, setList] = useState<Audit[]>([]); const [err, setErr] = useState("");
  useEffect(() => { api<Audit[]>("/audit?limit=200").then(setList).catch(x => setErr(errMsg(x))); }, []);
  return (
    <section className="card"><h2>Audit log</h2><p className="muted">Who did what, most recent first.</p>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="scroll"><table>
        <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th></tr></thead>
        <tbody>{list.map(a => <tr key={a.id}><td>{when(a.created_at)}</td><td>{a.actor}</td><td><span className="tag">{a.action}</span></td><td>{a.target}</td></tr>)}</tbody>
      </table></div></section>);
}
