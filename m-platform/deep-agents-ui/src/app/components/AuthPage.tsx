"use client";

/**
 * AuthPage — 登录/注册合一页面（09-26 爸爸令："看看 OWUI 的界面"）
 * 已配置密钥 → 默认显示登录 tab；未配置 → 默认显示注册 tab。
 * 有账号就登录，没账号就注册，一个页面搞定。
 */
import { useEffect, useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders, clearAdminToken, tokenStatus } from "@/lib/providerApi";
import { Button } from "@/components/ui/button";

export function AuthPage({ onDone, defaultMode }: { onDone: () => void; defaultMode: "login" | "register" }) {
  const [mode, setMode] = useState<"login" | "register">(defaultMode);
  const [uname, setUname] = useState("");
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(false);

  const submitLogin = async () => {
    if (!uname.trim()) return setMsg("请输入用户名");
    if (!pwd) return setMsg("请输入密码");
    setBusy(true); setMsg("");
    try {
      const r = await apiFetch(`${API}/auth/login`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ username: uname.trim(), password: pwd }),
      });
      const j = await r.json();
      if (j?.ok) {
        clearAdminToken();
        setMsg("登录成功，正在进入平台…");
        setTimeout(onDone, 1200);
      } else {
        setMsg(j?.error || "密码不正确");
      }
    } catch { setMsg("无法连接后端"); }
    finally { setBusy(false); }
  };

  const submitRegister = async () => {
    const u = uname.trim();
    if (u.length < 2 || u.length > 32) return setMsg("用户名需 2-32 个字符");
    if (pwd.length < 8) return setMsg("密码至少 8 位");
    if (pwd !== pwd2) return setMsg("两次输入的密码不一致");
    setBusy(true); setMsg("");
    try {
      const r1 = await apiFetch(`${API}/settings/token`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ token: "", username: u, password: pwd }),
      });
      const j1 = await r1.json();
      if (!j1?.ok || !j1?.token) {
        setMsg(j1?.error || "注册失败");
        return;
      }
      clearAdminToken();
      setDone(true);
      setTimeout(onDone, 2500);
    } catch { setMsg("无法连接后端"); }
    finally { setBusy(false); }
  };

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-8 text-center shadow-lg">
          <div className="mb-3 text-4xl">🎉</div>
          <h1 className="mb-2 text-xl font-semibold">注册成功</h1>
          <p className="text-sm text-muted-foreground">正在进入平台…</p>
        </div>
      </div>
    );
  }

  const inputCls = "mb-4 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-lg">
        {/* Tab 切换 */}
        <div className="mb-6 flex rounded-xl border border-border overflow-hidden">
          <button
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              mode === "login" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
            }`}
            onClick={() => { setMode("login"); setMsg(""); }}
          >登录</button>
          <button
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              mode === "register" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
            }`}
            onClick={() => { setMode("register"); setMsg(""); }}
          >注册</button>
        </div>

        {mode === "login" ? (
          <>
            <h1 className="mb-1 text-2xl font-semibold">登录 M 平台</h1>
            <p className="mb-6 text-sm text-muted-foreground">输入用户名和密码。</p>
            <input type="text" autoFocus value={uname} onChange={(e) => setUname(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitLogin(); }}
              placeholder="用户名" className={inputCls} />
            <input type="password" value={pwd} onChange={(e) => setPwd(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitLogin(); }}
              placeholder="密码" className={inputCls} />
            <Button className="mb-3 w-full rounded-xl" size="lg" disabled={busy} onClick={submitLogin}>
              {busy ? "登录中…" : "登录"}
            </Button>
          </>
        ) : (
          <>
            <h1 className="mb-1 text-2xl font-semibold">注册管理员</h1>
            <p className="mb-6 text-sm text-muted-foreground">设一个用户名和密码，谁先注册谁是这台机器的主人。</p>
            <input type="text" autoFocus value={uname} onChange={(e) => setUname(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitRegister(); }}
              placeholder="用户名（2-32 个字符）" className={inputCls} />
            <input type="password" value={pwd} onChange={(e) => setPwd(e.target.value)}
              placeholder="密码（至少 8 位）" className={inputCls} />
            <input type="password" value={pwd2} onChange={(e) => setPwd2(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitRegister(); }}
              placeholder="确认密码" className="mb-5 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm" />
            <Button className="mb-3 w-full rounded-xl" size="lg" disabled={busy} onClick={submitRegister}>
              {busy ? "注册中…" : "完成注册"}
            </Button>
          </>
        )}

        {msg && <div className="text-xs leading-relaxed text-red-500">{msg}</div>}
        <div className="mt-4 text-[0.68rem] leading-relaxed text-muted-foreground">
          凭证以 HttpOnly Cookie 保存在本机，不上传。忘记密码？运行 <code className="rounded bg-muted px-1">guard\reset_password.cmd</code>
        </div>
      </div>
    </div>
  );
}

/** 全局闸门：根据后端状态自动选 login/register/ok */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "ok" | "login" | "register">("checking");

  useEffect(() => {
    let alive = true;
    tokenStatus().then((s) => {
      if (!alive) return;
      if (!s.configured) { setState("register"); return; }
      import("@/lib/providerApi").then(({ getSettings }) => {
        getSettings().then(() => {
          if (alive) setState("ok");
        }).catch((e: any) => {
          if (alive) {
            if (String(e?.message || e).includes("401")) setState("login");
            else setState("ok");
          }
        });
      });
    }).catch(() => { if (alive) setState("ok"); });
    return () => { alive = false; };
  }, []);

  if (state === "checking") return null;
  if (state === "login" || state === "register")
    return <AuthPage onDone={() => window.location.reload()} defaultMode={state === "register" ? "register" : "login"} />;
  return <>{children}</>;
}

/** 登出（清 cookie + 刷新） */
export async function authLogout(): Promise<void> {
  try {
    await apiFetch(`${API}/auth/logout`, { method: "POST" });
  } catch { /* cookie 清除失败不影响前端 */ }
  clearAdminToken();
  window.location.reload();
}
