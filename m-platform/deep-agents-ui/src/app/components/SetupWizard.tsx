"use client";

/**
 * SetupWizard — 管理员注册向导（R10.7，管理员："发布到 GitHub，没基础的用户
 * 怎么取得管理员权限？需要一个管理员注册页面，这个一定要有"）。
 * 未配置管理员密钥时全屏展示：粘贴激活码 + 设置管理员密码 → 完成注册。
 * 激活码 = 部署目录 secrets 文件夹里的 .token_bootstrap 文件内容
 * （带外证明：能打开那个文件夹的才是主人——Jupyter token / Portainer setup token 同款模式）。
 * 密码 = 找回通道（PBKDF2 哈希存守卫；忘记 Cookie 时凭密码自助找回）。
 */
import { useEffect, useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders, clearAdminToken, getSettings, tokenStatus } from "@/lib/providerApi";
import { Button } from "@/components/ui/button";

export function SetupWizard({ onDone }: { onDone: () => void }) {
  const [boot, setBoot] = useState("");
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [done, setDone] = useState(false);

  const submit = async () => {
    if (!boot.trim()) return setMsg("请先粘贴激活码");
    if (pwd.length < 8) return setMsg("密码至少 8 位");
    if (pwd !== pwd2) return setMsg("两次输入的密码不一致");
    setBusy(true);
    setMsg("");
    try {
      // R10.7b（hy4 P1-1 死锁修复）：注册=单请求原子化——激活码验证、写密钥、写密码、
      // 兑现激活码在守卫同一持锁段一次完成，不存在"码已废、密码未落"的中间态。
      const r1 = await apiFetch(`${API}/settings/token`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json", "X-Bootstrap": boot.trim() }),
        body: JSON.stringify({ token: "", password: pwd }),
      });
      const j1 = await r1.json();
      if (!j1?.ok || !j1?.token) {
        setMsg(j1?.error || "注册失败（检查激活码与后端状态）");
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
          首次使用需要注册管理员。整个过程只需一分钟。
        </p>

        <div className="mb-5 rounded-xl border border-amber-400/50 bg-amber-50 p-4 text-xs leading-relaxed dark:bg-amber-950">
          <div className="mb-1 font-semibold text-amber-900 dark:text-amber-200">第 1 步 · 取出激活码</div>
          <div className="text-amber-900/90 dark:text-amber-200/90">
            用记事本打开部署目录下的  <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900">guard\.token_bootstrap</code> 文件，
            全选复制里面的 32 位码。只有能打开这个文件夹的人才能注册管理员——
            平台进程和外部访问都拿不到它。
          </div>
        </div>

        <label className="mb-1 block text-xs font-medium text-muted-foreground">第 2 步 · 粘贴激活码</label>
        <input
          type="password"
          value={boot}
          onChange={(e) => setBoot(e.target.value)}
          placeholder="粘贴 .token_bootstrap 文件的内容"
          className="mb-4 w-full rounded-xl border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400 shadow-inner font-mono text-sm"
        />

        <label className="mb-1 block text-xs font-medium text-muted-foreground">第 3 步 · 设置管理员密码（用于找回，至少 8 位）</label>
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
 * LoginGate — R10.8e（管理员："401 死锁，找回入口在进不去的设置页里"）：
 * 已配置密钥、但本浏览器没有有效凭证时（换电脑/清数据/密钥被轮换），
 * 主界面所有请求 401 → 显示密码登录层，验证通过自动进入。
 * 忘记密码 → 部署目录运行 guard\reset_guard.cmd 恢复出厂（数据不丢）。
 */
export function LoginGate({ onDone }: { onDone: () => void }) {
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const submit = async () => {
    if (!pwd) return setMsg("请输入管理员密码");
    setBusy(true);
    setMsg("");
    try {
      const r = await apiFetch(`${API}/auth/login`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ password: pwd }),
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
        <p className="mb-6 text-sm text-muted-foreground">请输入管理员密码登录本机平台。</p>
        <input
          type="password"
          autoFocus
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
          忘记密码？在部署目录运行 <code className="rounded bg-muted px-1">guard\reset_guard.cmd</code>{" "}
          恢复出厂（对话与配置数据不会丢失），然后按注册向导重新设置。
        </div>
      </div>
    </div>
  );
}


/**
 * AuthGate — R10.8e（管理员："401 死锁，找回入口在进不去的设置页里"）：
 * 全局登录闸门（layout 层挂载，覆盖所有页面，含 /settings）。
 * - checking：检测中（短暂空白）
 * - setup：未配置密钥 → 全屏 SetupWizard 注册向导
 * - login：已配置但本浏览器无有效凭证（换电脑/清数据/密钥被轮换）→ LoginGate 密码登录
 * - ok：凭证有效 → 渲染平台
 * 忘记密码 → 部署目录运行 guard
eset_guard.cmd 恢复出厂（数据不丢）。
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
