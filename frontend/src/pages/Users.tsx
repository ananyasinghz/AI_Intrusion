import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { usersApi } from "../api/client";
import { Card } from "../components/UI/Card";
import { Plus, Trash2, ShieldCheck, Eye } from "lucide-react";
import toast from "react-hot-toast";
import { format } from "date-fns";

interface UserForm {
  username: string;
  email: string;
  password: string;
  role: "admin" | "viewer";
}

export default function Users() {
  const [showForm, setShowForm] = useState(false);
  const qc = useQueryClient();

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => usersApi.list().then((r) => r.data),
  });

  const { register, handleSubmit, reset } = useForm<UserForm>({
    defaultValues: { role: "viewer" },
  });

  const createMut = useMutation({
    mutationFn: (d: UserForm) => usersApi.create(d),
    onSuccess: () => {
      toast.success("User created");
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
      reset();
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Error"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: () => {
      toast.success("User deleted");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Cannot delete user"),
  });

  const toggleActiveMut = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      usersApi.update(id, { is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold" style={{ color: "var(--text)" }}>User Management</h1>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
          style={{ background: "var(--accent)", color: "#000" }}>
          <Plus size={16} /> Add User
        </button>
      </div>

      {showForm && (
        <Card title="New User">
          <form onSubmit={handleSubmit((d) => createMut.mutate(d))} className="p-4 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {([
                { name: "username", label: "Username", type: "text", required: true },
                { name: "email", label: "Email", type: "email", required: true },
                { name: "password", label: "Password", type: "password", required: true },
              ] as const).map(({ name, label, type, required }) => (
                <div key={name}>
                  <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>{label}</label>
                  <input {...register(name, { required })} type={type}
                    className="w-full rounded-lg px-3 py-2 text-sm"
                    style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Role</label>
                <select {...register("role")}
                  className="w-full rounded-lg px-3 py-2 text-sm"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }}>
                  <option value="viewer">Viewer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <div className="flex gap-3">
              <button type="submit" className="px-5 py-2 rounded-lg text-sm font-semibold"
                style={{ background: "var(--accent)", color: "#000" }}>Create</button>
              <button type="button" onClick={() => { setShowForm(false); reset(); }}
                className="px-5 py-2 rounded-lg text-sm" 
                style={{ background: "var(--bg3)", color: "var(--text)", border: "1px solid var(--border)" }}>Cancel</button>
            </div>
          </form>
        </Card>
      )}

      <Card title="Users">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--bg3)" }}>
                {["Username","Email","Role","Status","Last Login","Actions"].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={6} className="px-4 py-6 text-center" style={{ color: "var(--muted)" }}>Loading…</td></tr>
              )}
              {users?.map((u: any) => (
                <tr key={u.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-4 py-3 font-medium" style={{ color: "var(--text)" }}>
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                           style={{ background: "var(--accent)", color: "#000" }}>
                        {u.username[0].toUpperCase()}
                      </div>
                      {u.username}
                    </div>
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{u.email}</td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1 text-xs w-fit px-2 py-1 rounded-full"
                          style={{
                            background: u.role === "admin" ? "rgba(88,166,255,.15)" : "var(--bg3)",
                            color: u.role === "admin" ? "var(--accent)" : "var(--muted)",
                          }}>
                      {u.role === "admin" ? <ShieldCheck size={11} /> : <Eye size={11} />}
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleActiveMut.mutate({ id: u.id, is_active: !u.is_active })}
                      className="text-xs px-2.5 py-1 rounded-full"
                      style={{
                        background: u.is_active ? "rgba(63,185,80,.15)" : "rgba(248,81,73,.15)",
                        color: u.is_active ? "var(--motion)" : "var(--person)",
                      }}>
                      {u.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--muted)" }}>
                    {u.last_login ? format(new Date(u.last_login + "Z"), "MM/dd HH:mm") : "Never"}
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => deleteMut.mutate(u.id)}
                      className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg"
                      style={{ background: "rgba(248,81,73,.1)", color: "var(--person)", border: "1px solid var(--person)" }}>
                      <Trash2 size={11} /> Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
