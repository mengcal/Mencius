"use client";

/**
 * AuthPage — 登录/注册合一页面（09-26 爸爸令："看看 OWUI 的界面"）
 * 已配置密钥 → 默认显示登录 tab；未配置 → 默认显示注册 tab。
 * 有账号就登录，没账号就注册，一个页面搞定。
 */
import { useEffect, useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders, clearAdminToken, tokenStatus, getSettings } from "@/lib/providerApi";
import { Button } from "@/components/ui/button";

/** 登录/注册成功后的放行：轮询等 Cookie 落定再放行（r32 F13，Qoder P2——
 *  固定 setTimeout 1200/2500 在慢机器上 reload 早于 Cookie 生效→探测 401→
 *  登录成功却被弹回登录页）。最多等 5 秒，拿到 configured=true 即放行。 */
async function probeUntilAuthed(): Promise<void> {
  // r32c P1#4b（Qoder）：旧探针探 tokenStatus 的 configured——注册成功后它本来就 true，
  // 第一轮即返回=零等待，Cookie 没落定就 reload 仍会弹回登录页。改探 getSettings()：
  // 401=Cookie 未生效继续等，200=登录态真成立才放行。
  for (let i = 0; i < 16; i++) {
    try {
      await getSettings();
      return;
    } catch { /* 401=Cookie 未落定，继续等 */ }
    await new Promise((r) => setTimeout(r, 300));
  }
}

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
        await probeUntilAuthed();
        onDone();
      } else {
        // r32 CB F14：兜底文案与后端同款泛化——"密码不正确"会向探测者确认"用户名存在"
        setMsg(j?.error || "登录名或密码不正确");
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
      // r32 F8（Qoder）：后端注册路径已不回吐明文 token，成功判据只看 ok
      if (!j1?.ok) {
        setMsg(j1?.error || "注册失败");
        return;
      }
      clearAdminToken();
      setDone(true);
      await probeUntilAuthed();
      onDone();
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
          {/* r32 F7（五家合流）：去内部路径/去黑话——爸爸在登录页不该看到宿主目录结构，
              "HttpOnly Cookie" 是术语；找回动作=找管理员跑部署目录里的重置脚本 */}
          登录状态保存在本机浏览器里，不上传。忘记密码？请在部署目录的 guard 文件夹中找到密码重置脚本，在宿主机上运行。
        </div>
      </div>
    </div>
  );
}

/** 全局闸门：根据后端状态自动选 login/register/ok/unreachable */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "ok" | "login" | "register" | "unreachable">("checking");

  useEffect(() => {
    let alive = true;
    tokenStatus().then((s: any) => {
      if (!alive) return;
      // r32 F10（Qoder P2#9）：守卫/后端不可达 ≠ 未配置——显示"服务暂时不可用"，
      // 绝不把已注册管理员送进注册页（再注册必失败=往坑里引）
      if (s.unreachable) { setState("unreachable"); return; }
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
    }).catch(() => { if (alive) setState("unreachable"); });
    return () => { alive = false; };
  }, []);

  if (state === "checking") return null;
  if (state === "unreachable")
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-lg">
          <div className="mb-3 text-4xl">🛠</div>
          <h1 className="mb-2 text-xl font-semibold">服务暂时不可用</h1>
          <p className="text-sm text-muted-foreground">后台服务没有应答，请稍后刷新重试。</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>刷新重试</Button>
        </div>
      </div>
    );
  if (state === "login" || state === "register")
    return <AuthPage onDone={() => window.location.reload()} defaultMode={state === "register" ? "register" : "login"} />;
  return <>{children}</>;
}

/** 登出（清 cookie + 刷新）——r32 F7（Qoder P2"谎报登出"）：必须读响应，
 * 登出失败（网络断/后端炸）时 Cookie 其实还在，静默 reload 会让人以为登出了
 * 实际仍是登录态（共用机器上是真问题）；失败如实出声、不刷新。 */
export async function authLogout(): Promise<void> {
  try {
    const r = await apiFetch(`${API}/auth/logout`, { method: "POST" });
    if (!r.ok) {
      window.alert(`登出失败（HTTP ${r.status}），请稍后再试——当前可能仍处于登录状态`);
      return;
    }
    clearAdminToken();
    window.location.reload();
  } catch {
    window.alert("登出失败：无法连接后端——当前可能仍处于登录状态");
  }
}
