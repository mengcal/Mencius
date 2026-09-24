"use client";

/**
 * SetupWizard — 管理员注册向导（R10.408 爸爸 09-23 改版："注册之前不该上锁"）
 * ------------------------------------------------------------------
 * 未配置管理员时全屏展示：直接设【用户名 + 密码】→ 谁先注册谁是这台机器的主人。
 * 旧版"粘贴 .token_bootstrap 激活码"的带外锁已按爸爸产品直觉废除（单机软件
 * 就该像酒馆那样：打开就能建号，建完号才上锁）。残余防护=注册限频+全程审计 IP，
 * 注册成功后门立刻焊死（再首设需当前密钥）。
 * 密码 = 找回通道（PBKDF2 哈希存守卫；忘记 Cookie 时凭 用户名+密码 自助找回）。
 */
import { useEffect, useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders, clearAdminToken, getSettings, tokenStatus } from "@/lib/providerApi";
import { Button } from "@/components/ui/button";

export function SetupWizard({ onDone }: { onDone: () => void }) {
  const [uname, setUname] = useState("");
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(false);

  const submit = async () => {
    const u = uname.trim();
    if (u.length < 2 || u.length > 32) return setMsg("用户名需 2-32 个字符");
    if (pwd.length < 8) return setMsg("密码至少 8 位");
    if (pwd !== pwd2) return setMsg("两次输入的密码不一致");
    setBusy(true);
    setMsg("");
    try {
      // R10.7b 单请求原子化保留：用户名+密码+密钥随首设一并落定。
      const r1 = await apiFetch(`${API}/settings/token`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ token: "", username: u, password: pwd }),
      });
      const j1 = await r1.json();
      if (!j1?.ok || !j1?.token) {
        setMsg(j1?.error || "注册失败（检查后端状态）");
        return;
      }
      clearAdminToken(); // localStorage 退役：Cookie 才是凭证存放地
      setDone(true);
      setTimeout(onDone, 2500);
    } catch {
      setMsg("无法连接后端（2024 端口），请确认平台容器在跑");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-8 text-center shadow-lg">
          <div className="mb-3 text-4xl">🎉</div>
          <h1 className="mb-2 text-xl font-semibold">注册成功，欢迎回来</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            管理员凭证已种入 HttpOnly Cookie（恶意脚本读不到），正在进入平台…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-8 shadow-lg">
        <h1 className="mb-1 text-2xl font-semibold">欢迎来到 M 平台</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          首次使用请注册管理员：设一个用户名和密码，谁先注册谁是这台机器的主人。整个过程只需一分钟。
        </p>

        <label className="mb-1 block text-xs font-medium text-muted-foreground">用户名（以后登录用这个，设置页可改）</label>
        <input
          type="text"
          autoFocus
          value={uname}
          onChange={(e) => setUname(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="给你自己起个名字"
          className="mb-4 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm"
        />

        <label className="mb-1 block text-xs font-medium text-muted-foreground">管理员密码（用于找回，至少 8 位）</label>
        <input
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          placeholder="设置密码"
          className="mb-3 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm"
        />
        <input
          type="password"
          value={pwd2}
          onChange={(e) => setPwd2(e.target.value)}
          placeholder="再输一遍"
          className="mb-5 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm"
        />

        <Button className="mb-3 w-full rounded-xl" size="lg" disabled={busy} onClick={submit}>
          {busy ? "注册中…" : "完成管理员注册"}
        </Button>
        {msg && <div className="text-xs leading-relaxed text-red-500">{msg}</div>}
        <div className="mt-4 text-[0.68rem] leading-relaxed text-muted-foreground">
          安全说明：注册后，管理员凭证以 HttpOnly Cookie 保存（浏览器里的恶意脚本读不到）；
          忘记登录状态时，可在设置页用密码找回。密钥与密码只存在你本机的加密存储里，绝不上传。
        </div>
      </div>
    </div>
  );
}

/** 主界面挂载点用：未配置 → 返回向导（true）；已配置 → null（照常渲染）。 */
export async function needSetupWizard(): Promise<boolean> {
  try {
    const s = await tokenStatus();
    return !s.configured;
  } catch {
    return false;
  }
}

/**
 * LoginGate — R10.8e（爸爸："401 死锁，找回入口在进不去的设置页里"）：
 * 已配置密钥、但本浏览器没有有效凭证时（换电脑/清数据/密钥被轮换），
 * 主界面所有请求 401 → 显示密码登录层，验证通过自动进入。
 * 忘记密码 → 部署目录运行 guard\reset_guard.cmd 恢复出厂（数据不丢）。
 */
export function LoginGate({ onDone }: { onDone: () => void }) {
  // R10.408（爸爸 09-23："管理员连个名都没有？"）：用户名=注册时亲手所设，
  // office 层与 general.admin_name 真比对（不再是摆设），与密码构成双要素。
  const [uname, setUname] = useState("");
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const submit = async () => {
    if (!uname.trim()) return setMsg("请输入用户名");
    if (!pwd) return setMsg("请输入管理员密码");
    setBusy(true);
    setMsg("");
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
    } catch {
      setMsg("无法连接后端（2024 端口），请确认平台容器在跑");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-lg">
        <h1 className="mb-1 text-2xl font-semibold">M 平台</h1>
        <p className="mb-6 text-sm text-muted-foreground">请输入用户名和管理员密码登录本机平台。</p>
        <input
          type="text"
          autoFocus
          value={uname}
          onChange={(e) => setUname(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="用户名"
          className="mb-4 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm"
        />
        <input
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="管理员密码"
          className="mb-4 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner text-sm"
        />
        <Button className="mb-3 w-full rounded-xl" size="lg" disabled={busy} onClick={submit}>
          {busy ? "登录中…" : "登录"}
        </Button>
        {msg && <div className="text-xs leading-relaxed text-red-500">{msg}</div>}
        <div className="mt-4 text-[0.68rem] leading-relaxed text-muted-foreground">
          忘记密码？在本机运行 <code className="rounded bg-muted px-1">guard\reset_password.cmd</code>{" "}
          ——只改密码，设置与对话完全不动。（reset_guard.cmd 是全部重置、重走注册向导，平时用不到。）
        </div>
      </div>
    </div>
  );
}


/**
 * AuthGate — R10.8e（爸爸："401 死锁，找回入口在进不去的设置页里"）：
 * 全局登录闸门（layout 层挂载，覆盖所有页面，含 /settings）。
 * - checking：检测中（短暂空白）
 * - setup：未配置密钥 → 全屏 SetupWizard 注册向导
 * - login：已配置但本浏览器无有效凭证（换电脑/清数据/密钥被轮换）→ LoginGate 密码登录
 * - ok：凭证有效 → 渲染平台
 * 忘记密码 → 部署目录运行 guardeset_guard.cmd 恢复出厂（数据不丢）。
 * 后端连接失败时不挡门（页面自身会显示连接错误）。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "ok" | "login" | "setup">("checking");

  useEffect(() => {
    let alive = true;
    tokenStatus().then((s) => {
      if (!alive) return;
      if (!s.configured) { setState("setup"); return; }
      getSettings().then(() => {
        if (alive) setState("ok");
      }).catch((e: any) => {
        if (alive) {
          if (String(e?.message || e).includes("401")) setState("login");
          else setState("ok"); // 后端不可达等连接错误：不挡门，页面自身会报连接问题
        }
      });
    }).catch(() => { if (alive) setState("ok"); });
    return () => { alive = false; };
  }, []);

  if (state === "checking") return null;
  if (state === "setup") return <SetupWizard onDone={() => window.location.reload()} />;
  if (state === "login") return <LoginGate onDone={() => window.location.reload()} />;
  return <>{children}</>;
}
