import { Card } from "../components/UI/Card";
import { useAuthStore } from "../store/authStore";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import toast from "react-hot-toast";

interface PasswordForm {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export default function Settings() {
  const user = useAuthStore((s) => s.user);
  const { register, handleSubmit, reset } = useForm<PasswordForm>();

  const onChangePassword = async (data: PasswordForm) => {
    if (data.new_password !== data.confirm_password) {
      toast.error("Passwords do not match");
      return;
    }
    try {
      await api.put("/auth/me/password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      toast.success("Password updated");
      reset();
    } catch (e: any) {
      toast.error(e.response?.data?.detail ?? "Error");
    }
  };

  return (
    <div className="space-y-5 max-w-2xl">
      {/* Profile */}
      <Card title="Profile">
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs mb-1" style={{ color: "var(--muted)" }}>Username</p>
              <p style={{ color: "var(--text)" }}>{user?.username}</p>
            </div>
            <div>
              <p className="text-xs mb-1" style={{ color: "var(--muted)" }}>Email</p>
              <p style={{ color: "var(--text)" }}>{user?.email}</p>
            </div>
            <div>
              <p className="text-xs mb-1" style={{ color: "var(--muted)" }}>Role</p>
              <p className="capitalize" style={{ color: "var(--text)" }}>{user?.role}</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Change password */}
      <Card title="Change Password">
        <form onSubmit={handleSubmit(onChangePassword)} className="p-4 space-y-4">
          {[
            { name: "current_password", label: "Current Password" },
            { name: "new_password", label: "New Password" },
            { name: "confirm_password", label: "Confirm New Password" },
          ].map(({ name, label }) => (
            <div key={name}>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>{label}</label>
              <input {...register(name as keyof PasswordForm, { required: true })}
                type="password"
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)" }} />
            </div>
          ))}
          <button type="submit"
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: "var(--accent)", color: "#000" }}>
            Update Password
          </button>
        </form>
      </Card>

      {/* System info */}
      <Card title="System Information">
        <div className="p-4 space-y-2 text-sm">
          {[
            ["Backend", "FastAPI 2.0 + SQLite"],
            ["Detection", "YOLOv8 Nano (COCO 80-class)"],
            ["Privacy", "Persons blurred before storage"],
            ["Alerts", "Telegram + Email (optional)"],
            ["Input Source", "Configurable: webcam / video / ESP32-CAM"],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-4">
              <span className="w-36 text-xs" style={{ color: "var(--muted)" }}>{k}</span>
              <span style={{ color: "var(--text)" }}>{v}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
