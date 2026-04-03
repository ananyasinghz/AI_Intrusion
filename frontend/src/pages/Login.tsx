import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { ShieldAlert, Eye, EyeOff } from "lucide-react";
import { authApi } from "../api/client";
import { useAuthStore } from "../store/authStore";

interface LoginForm {
  username: string;
  password: string;
}

export default function Login() {
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginForm>();

  const onSubmit = async (data: LoginForm) => {
    setLoading(true);
    try {
      const res = await authApi.login(data.username, data.password);
      setAuth(res.data.user, res.data.access_token, res.data.refresh_token);
      toast.success(`Welcome, ${res.data.user.username}`);
      navigate("/");
    } catch (err: any) {
      toast.error(err.response?.data?.detail ?? "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
               style={{ background: "rgba(88,166,255,.15)", border: "1px solid rgba(88,166,255,.3)" }}>
            <ShieldAlert size={32} style={{ color: "var(--accent)" }} />
          </div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Intrusion Monitor</h1>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>Sign in to your account</p>
        </div>

        {/* Card */}
        <div className="rounded-xl p-6" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--muted)" }}>
                Username
              </label>
              <input
                {...register("username", { required: "Username is required" })}
                type="text"
                autoComplete="username"
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none focus:ring-2"
                style={{
                  background: "var(--bg3)",
                  border: `1px solid ${errors.username ? "var(--person)" : "var(--border)"}`,
                  color: "var(--text)",
                }}
                placeholder="admin"
              />
              {errors.username && (
                <p className="text-xs mt-1" style={{ color: "var(--person)" }}>{errors.username.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--muted)" }}>
                Password
              </label>
              <div className="relative">
                <input
                  {...register("password", { required: "Password is required" })}
                  type={showPass ? "text" : "password"}
                  autoComplete="current-password"
                  className="w-full rounded-lg px-3 py-2.5 pr-10 text-sm outline-none"
                  style={{
                    background: "var(--bg3)",
                    border: `1px solid ${errors.password ? "var(--person)" : "var(--border)"}`,
                    color: "var(--text)",
                  }}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--muted)" }}
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs mt-1" style={{ color: "var(--person)" }}>{errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg font-semibold text-sm transition-opacity disabled:opacity-60"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-xs text-center mt-4" style={{ color: "var(--muted)" }}>
            Default: <code className="font-mono">admin</code> / <code className="font-mono">changeme</code>
          </p>
        </div>
      </div>
    </div>
  );
}
