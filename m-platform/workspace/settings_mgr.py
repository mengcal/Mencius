"""助手办公室 settings 管理（参考 open-webui PersistentConfig 设计，2026-08-28）v2

参考 open-webui 设计：单一配置文件 + 分节读写 + 敏感键打码 + 明文隔离存储。
- settings.json     ：前端可见版（所有 key 均为打码值）
- .settings_secrets ：明文 key 唯一藏身处（仅后端读，永不回传）

密钥寻址：列表（providers）按其 name 字段寻址，字典按键名寻址。
  external.providers.魔搭.api_key
  search.metasoKey
"""

import json
import os

# R68（评审共识 E2）：嵌入模型默认值全平台单一源——后端各处 import 此常量，前端经配置页注入
DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETTINGS_PATH = BASE / "settings.json"
# R79②（评审C P1 实锤：部门图旧本地 shell `head ../.settings_secrets` 直读出明文=钥匙挂在容器可写墙上）：
# 密钥文件挪出 src 挂载面 → 宿主 D:\m\secrets/（compose 挂 /data/secrets，沙箱不挂、源码 :ro 面不再含它）。
# env 未设时回落 BASE/.settings_secrets（本地裸跑兼容）。
SECRETS_PATH = Path(os.environ.get("MIA_SECRETS_PATH") or (BASE / ".settings_secrets"))

# R73（评审B🟡 补）：邮箱托管带来 password/apiKey/authcode 等新凭据键名，一并入敏感名单——
# 配置页若回传含这些键，明文进 secrets、settings.json 只留打码，绝不明文落盘。
SENSITIVE_KEYS = {"api_key", "metasoKey", "bochaKey", "tavilyKey",
                  "password", "apiKey", "authcode", "appPassword", "auth_code"}
LIST_NAME_KEY = "name"   # 列表元素按此字段寻址（open-webui 的 provider 名寻址同款思路）


def mask_key(k: str) -> str:
    if not k or len(k) <= 10:
        return "****"
    return k[:6] + "****" + k[-4:]


# ── 明文密钥存取 ──────────────────────────────────────────────
def _load_secrets() -> dict:
    if SECRETS_PATH.exists():
        try:
            return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_secrets(sec: dict):
    # R10.5 事故加固（hy4 ②-4 同族）：tmp+replace 原子写——半写崩溃曾可能毒化整个密钥文件
    # （json 损坏→_load_secrets 静默 {}→configured=False+全部服务商密钥"消失"）。
    tmp = SECRETS_PATH.with_name(SECRETS_PATH.name + ".tmp")
    tmp.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(SECRETS_PATH))


def secret_get(path: str) -> str:
    return _load_secrets().get(path, "")


def secret_set(path: str, value: str):
    sec = _load_secrets()
    if value:
        sec[path] = value
    else:
        sec.pop(path, None)
    _save_secrets(sec)


# ── R64/R65 角色模型配置唯一真源 = 设置页 settings.agents（管理员定调：配置页写什么，文件跟着变）──
# agents_config.json 出厂兜底已废（R65）；没配→报空。
# departments/起名/事实抽取等一律经此函数取模型配置，禁止各自硬编码 provider 名。
def load_agents_config() -> dict:
    # 管理员 2026-09-01 铁律：配置页 settings.agents 是唯一真源，彻底废除 agents_config.json 出厂兜底。
    # 删了连接 / 没配 → 就报空，由管理员或助手在设置页补；绝不从任何残留文件"默认"一个服务商/模型。
    merged: dict = {}
    try:
        page = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("agents") or {}
        if isinstance(page, dict):
            # 字段级深度合并：设置页角色只覆盖自己写的字段（如 provider_pid），
            # 不许整个顶掉出厂默认的其他字段（model 等）——2026-09-01 model 丢失教训
            for k, v in page.items():
                if isinstance(v, dict):
                    base = dict(merged.get(k)) if isinstance(merged.get(k), dict) else {}
                    base.update(v)
                    merged[k] = base
                else:
                    merged[k] = v
    except Exception:
        pass
    # R64 终稿（管理员 2026-09-01 定调：我的平台我写什么就是什么）：
    # 按名字查，仅此而已。名字对不上 → 保留原值、启动日志警告，调用时明确报错——
    # 绝不偷偷换别的服务商（那是越权）；回退走管理员在设置页配的回退链（run_config 消费），
    # .env 托底已废（R65：providers 不再借 OPENAI key，配置页=唯一源）。系统没有任何自作主张。
    try:
        ext = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("external", {}).get("providers", []) or []
        names = [p.get("name") for p in ext if isinstance(p, dict) and p.get("name")]
        for role, c in merged.items():
            if isinstance(c, dict) and c.get("provider") and c["provider"] not in names:
                print(f"[agents-config] 警告：角色 {role} 的服务商「{c['provider']}」不在设置页列表，"
                      f"该角色调用时会报错——请在设置页重选，或检查拼写。", flush=True)
    except Exception:
        pass
    return merged


# ── 设置读写 ─────────────────────────────────────────────────
def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {}


def _find_in_list(lst: list, name: str):
    for item in lst:
        if isinstance(item, dict) and item.get(LIST_NAME_KEY) == name:
            return item
    return None


def _merge(old, new, prefix=""):
    """递归合并：敏感键打码+明文入secrets；列表按name对位合并。"""
    out = {}
    if isinstance(new, list):
        old_list = old if isinstance(old, list) else []
        result = []
        for item in new:
            if isinstance(item, dict) and LIST_NAME_KEY in item:
                name = item[LIST_NAME_KEY]
                old_item = _find_in_list(old_list, name) or {}
                result.append(_merge(old_item, item, f"{prefix}{name}."))
            else:
                result.append(item)
        return result
    if not isinstance(new, dict):
        return new
    for k, v in new.items():
        path = f"{prefix}{k}"
        old_v = old.get(k) if isinstance(old, dict) else None
        if isinstance(v, dict) and isinstance(old_v, dict):
            out[k] = _merge(old_v, v, path + ".")
        elif isinstance(v, list):
            out[k] = _merge(old_v if isinstance(old_v, list) else [], v, path + ".")
        elif k in SENSITIVE_KEYS and isinstance(v, str) and "****" in v:
            out[k] = v  # 前端传回打码值=未修改，原样存
        elif k in SENSITIVE_KEYS and isinstance(v, str) and v:
            secret_set(path, v)
            out[k] = mask_key(v)
        elif k in SENSITIVE_KEYS:
            secret_set(path, "")
            out[k] = ""
        else:
            out[k] = v
    # R71 拆大雷（system_prompt 静默蒸发案，git 铁证 9-02 16:07→19:45）：
    # 旧版 _merge 只遍历 new 带的键——前端"保存单行"（如只 POST general.confirmLevel）
    # 会把没带的兄弟键（system_prompt 1042 字人设！）整个丢掉=静默数据销毁。
    # 修正：dict 合并回填未触碰的旧键（new 显式带的键仍以 new 为准，覆盖/删除语义不变；
    # 列表分支在上面已提前 return，删卡仍靠整列表替换，不受本修复影响）。
    if isinstance(old, dict):
        for k in old:
            if k not in out:
                out[k] = old[k]
    return out


def save_section(section: str, data: dict):
    s = load_settings()
    # R74（评审C P1① 侧门·两步绕过补严）：护栏不能依赖"新旧对比"（空→改、改名回填都能短路旧条件）。
    # 改为按【密钥锚定】判定：只要某 name 在 secrets 里有明文 key，且本次请求没带该条目的新明文 key，
    # 则该条目落盘的 base_url 必须 == 当前 settings 里该 name 已存的 base_url，否则拒——
    # 置空、改名回填、孤儿密钥复用，一律逃不过。另：providers:null 直接拒（自残级 DoS）。
    if section == "external":
        provs_in = data.get("providers")
        if provs_in is None and "providers" in data:
            raise ValueError("providers 不允许整体置 null（会清空服务商表）；要删条目请传去掉该项后的完整列表。")
        stored = {p.get("name"): p for p in
                  ((s.get("external", {}) or {}).get("providers") or []) if isinstance(p, dict)}
        pre_had: dict = {}  # R79⑤：锚定快照（本次请求涉及的每个名字"曾有钥匙"否）——secrets 有 key 或 tombstone 在都算
        for p in (provs_in or []):
            if not isinstance(p, dict) or not p.get("name"):
                continue
            name = p.get("name")
            ak = p.get("api_key")
            fresh_key = isinstance(ak, str) and ak and "****" not in ak
            has_secret = bool(get_plain_provider_key(name))
            pre_had[name] = has_secret or _had_key(name)
            if pre_had[name] and not fresh_key:
                new_url = str(p.get("base_url") or "")
                cur_url = str((stored.get(name) or {}).get("base_url") or "")
                if not new_url:
                    raise ValueError(f"服务商「{name}」有已存密钥，base_url 不允许置空（置空是两步绕过换址护栏的前半）。")
                if new_url != cur_url:
                    raise ValueError(
                        f"服务商「{name}」改了 base_url（{cur_url or '∅'} → {new_url}）却没带新的 api_key。"
                        "换地址必须同时重填该地址的新密钥，否则旧明文密钥会被发到新家（外带风险）——已拒绝保存。")
    s[section] = _merge(s.get(section, {}), data, f"{section}.")
    # R79⑤ tombstone 落账：本次保存后"曾有钥匙"的名字若 key 没了（被清）→ 记 tombstone（此后换址仍需新钥）；
    # key 还在（重填了新钥）→ 撤 tombstone（新钥已重新锚定该名字）。
    if section == "external":
        for name, had in pre_had.items():
            flag = f"external.providers.{name}.had_key"
            if get_plain_provider_key(name):
                secret_set(flag, "")
            elif had:
                secret_set(flag, "1")
    # R74（评审C 绕法B·孤儿密钥）：providers 变更后清理已删除服务商遗留在 secrets 里的明文 key，
    # 断掉"删了又用旧名复活→孤儿 key 自动接上"这条绕过零件。
    if section == "external":
        names_now = {p.get("name") for p in (s.get("external", {}).get("providers") or [])
                     if isinstance(p, dict) and p.get("name")}
        for nm in list(_load_secrets().keys()):
            if nm.startswith("external.providers.") and (nm.endswith(".api_key") or nm.endswith(".had_key")):
                suffix = ".api_key" if nm.endswith(".api_key") else ".had_key"
                owner = nm[len("external.providers."):-len(suffix)]
                if owner and owner not in names_now:
                    secret_set(nm, "")
    # R61 防弹衣升级：不管前端传什么形状，落盘前强制把 external.providers 规范成
    # list[dict(name=..., base_url=..., ...)]。字典形式（"0": {...}）= 按 key 排序转列表。
    if section == "external":
        provs = s.get("external", {}).get("providers")
        if isinstance(provs, dict):
            # 字典 → 按 key 排序转列表（历史脏数据的兼容修复）
            s["external"]["providers"] = [
                v for _, v in sorted(provs.items(), key=lambda x: x[0])
                if isinstance(v, dict) and v.get("name")
            ]
        elif isinstance(provs, list):
            s["external"]["providers"] = [
                p for p in provs if isinstance(p, dict) and p.get("name")
            ]
        else:
            s["external"]["providers"] = []
        # R69 拆雷（评审B🟡9 预警今日成真）：删掉"按 base_url 猜改名"的联动。
        # 旧逻辑在管理员"新加一个同地址服务商"（如书生6号与书生2~5号同 base_url）时，
        # 会把新地址误判成"旧服务商改名"，连带把 agents 里 coder/researcher/... 的
        # provider 全部静默改写成新名——加号≠改名！
        # 改名联动现在只认显式 /providers/rename 端点（office.api_provider_rename，那里
        # 精确按 old→new 处理，且是用户主动改名）。按名字查、宁报错不猜，符合零硬编码铁律。
    SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s[section]


def get_plain_provider_key(name: str) -> str:
    return secret_get(f"external.providers.{name}.api_key")


# R79⑤（评审B 第三报·锚定两步绕）：第一步 POST api_key="" 合法清掉明文 key，第二步再改 base_url
# 时 has_secret 已=False、锚定检查整个跳过——"清 key→改址"两步绕过换址护栏（埋桩等管理员补 key）。
# 修法=记"曾有钥匙"：key 被清时在 secrets 留 tombstone（<name>.had_key），此后该名字换址仍必须带
# 新明文 key；重填新钥=新钥锚定生效、tombstone 撤销。改名随 rename 端点迁移、删条目随孤儿清理清账。
def _had_key(name: str) -> bool:
    return bool(secret_get(f"external.providers.{name}.had_key"))


def get_plain_search_key(which: str) -> str:
    return secret_get(f"search.{which}")


def get_plain_key(path: str) -> str:
    """通用：按完整路径取明文。"""
    return secret_get(path)


# ── R75 统一 token（管理员密钥）：只存 .settings_secrets，源码/设置页明文都不落 ──
# R10.6（管理员拍板"一次做成 外置式守卫外置"）：M_GUARD_URL 配置时，密钥真源=m-guard 守卫服务
# （宿主 SYSTEM 常驻进程，DPAPI 加密存储，只答"验证通过/不通过"永不外发明文——ssh-agent 模式）。
# 本进程不再持有明文钥匙：助手终态有宿主全权也改不了判定、偷不到钥匙。
# env 未配 M_GUARD_URL=本地裸跑兼容（旧文件逻辑）。
TOKEN_SECRET_PATH = "general.apiToken"
M_GUARD_URL = os.environ.get("M_GUARD_URL", "").strip().rstrip("/")


def _guard_post(path: str, payload: dict, timeout: float = 5.0) -> dict:
    import json as _j
    import urllib.request as _u
    import os as _os
    req = _u.Request(f"{M_GUARD_URL}{path}", data=_j.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json",
                              "X-Guard-Key": _os.environ.get("M_GUARD_KEY", "")}, method="POST")
    with _u.urlopen(req, timeout=timeout) as r:
        return _j.loads(r.read())


def get_api_token() -> str:
    if M_GUARD_URL:
        return ""  # guard 模式：本进程不持有明文（比较一律走 token_ok→guard）
    return secret_get(TOKEN_SECRET_PATH)


def api_token_configured() -> bool:
    if M_GUARD_URL:
        try:
            import json as _j
            import urllib.request as _u
            with _u.urlopen(f"{M_GUARD_URL}/status", timeout=5.0) as r:
                return bool(_j.loads(r.read()).get("configured"))
        except Exception:
            return False  # guard 不可达=fail-closed（宁拒勿裸）
    return bool(secret_get(TOKEN_SECRET_PATH))


def set_api_token(value: str) -> None:
    if M_GUARD_URL:
        return  # guard 模式：设置走 office /settings/token → guard /set（带激活码/当前密钥证明），不走此处
    # 凭据只入 secrets（不进 settings.json、不进源码）；空串=清除（回到未配置=放行，供管理员重置）
    secret_set(TOKEN_SECRET_PATH, value)


_VERIFY_CACHE: dict = {}  # R10.8h（评审B P2⑤）：token_ok 结果 30s TTL 缓存——三处扇出每请求
_VERIFY_TTL = 30.0        # 一跳 guard，高负载会自我 DoS。单管理员场景缓存单条即可。
                          # rotate/clear 使旧钥匙失效后，最迟 30s 自然过期（窗口可接受，注明）。
                          # R10.11（评审C P3）：rotate/clear 成功路径改为主动调 clear_verify_cache()，窗口压到 0。


def clear_verify_cache() -> None:
    """R10.11（评审C P3）：rotate/clear 成功后由调用方主动清验证缓存——撤销即时生效。"""
    _VERIFY_CACHE.clear()


def token_ok(presented: str) -> bool:
    """常数时间比对，防时序侧信道。未配置 token 时不在此处判定（由调用方决定放行策略）。
    R10.2（hy4 ③-10）：先 encode 成 bytes 再比，非 ASCII 头不再炸 500。
    R10.6：guard 模式下判定在守卫进程内——本函数变成"问守卫"，明文不进本进程。"""
    if M_GUARD_URL:
        import time as _t
        c = _VERIFY_CACHE
        if (c.get("tok") == str(presented or "") and c.get("t")
                and _t.time() - c["t"] < _VERIFY_TTL):
            return c["ok"]
        try:
            ok = bool(_guard_post("/verify", {"token": str(presented or "")}).get("ok"))
        except Exception:
            return False  # guard 不可达=fail-closed
        c.clear()
        c["tok"] = str(presented or "")
        c["ok"] = ok
        c["t"] = _t.time()
        return ok
    import hmac
    cur = secret_get(TOKEN_SECRET_PATH)
    if not cur:
        return False
    try:
        return hmac.compare_digest(str(cur).encode("utf-8"), str(presented or "").encode("utf-8"))
    except Exception:
        return False
