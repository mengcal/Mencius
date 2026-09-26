"""米娅办公室 settings 管理（OWUI PersistentConfig 同构，2026-08-28）v2

架构照抄 OWUI：单一配置文件 + 分节读写 + 敏感键打码 + 明文隔离存储。
- settings.json     ：前端可见版（所有 key 均为打码值）
- .settings_secrets ：明文 key 唯一藏身处（仅后端读，永不回传）

密钥寻址：列表（providers）按其 name 字段寻址，字典按键名寻址。
  external.providers.魔搭.api_key
  search.metasoKey
"""

import json
import os
import shutil

# R68（评审共识 E2）：嵌入模型默认值全平台单一源——后端各处 import 此常量，前端经配置页注入
# 09-17 深夜 schema 收口：默认值单一来源=settings_schema.py（hy4 挑刺②：模块常量=第二真源，堵掉）
from settings_schema import default_of as _dof
DEFAULT_EMBED_MODEL = _dof("rag.embeddingModel")
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETTINGS_PATH = BASE / "settings.json"


def settings_rev() -> int:
    """_rev 单一源（r32 CB F13）：settings.json 修改时间的微秒整数。
    秒级粒度下同秒内两次保存互不可见=防撞车失明；微秒值 ~1.77e15 < 2^53，JS Number 精度安全。
    providers.py（GET/POST）与 token_admin.py（confirm-level）一律 import 本函数，禁止再各自 stat。"""
    return int(SETTINGS_PATH.stat().st_mtime * 1_000_000)
# R79②（Eve P1 实锤：部门图旧本地 shell `head ../.settings_secrets` 直读出明文=钥匙挂在容器可写墙上）：
# 密钥文件挪出 src 挂载面 → 宿主 D:\m\secrets/（compose 挂 /data/secrets，沙箱不挂、源码 :ro 面不再含它）。
# env 未设时回落 BASE/.settings_secrets（本地裸跑兼容）。
SECRETS_PATH = Path(os.environ.get("MIA_SECRETS_PATH") or (BASE / ".settings_secrets"))

# R73（NOVA🟡 补）：邮箱托管带来 password/apiKey/authcode 等新凭据键名，一并入敏感名单——
# 配置页若回传含这些键，明文进 secrets、settings.json 只留打码，绝不明文落盘。
SENSITIVE_KEYS = {"api_key", "metasoKey", "bochaKey", "tavilyKey",
                  "password", "apiKey", "authcode", "appPassword", "auth_code"}
LIST_NAME_KEY = "name"   # 列表元素按此字段寻址（OWUI 的 provider 名寻址同款思路）


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


# ── R64/R65 角色模型配置唯一真源 = 设置页 settings.agents（爸爸定调：配置页写什么，文件跟着变）──
# agents_config.json 出厂兜底已废（R65）；没配→报空。
# departments/起名/事实抽取等一律经此函数取模型配置，禁止各自硬编码 provider 名。
def load_agents_config() -> dict:
    # 爸爸 2026-09-01 铁律：配置页 settings.agents 是唯一真源，彻底废除 agents_config.json 出厂兜底。
    # 删了连接 / 没配 → 就报空，由爸爸或米娅在设置页补；绝不从任何残留文件"默认"一个服务商/模型。
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
    # R64 终稿（爸爸 2026-09-01 定调：我的平台我写什么就是什么）：
    # 按名字查，仅此而已。名字对不上 → 保留原值、启动日志警告，调用时明确报错——
    # 绝不偷偷换别的服务商（那是越权）；回退走爸爸在设置页配的回退链（run_config 消费），
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
# r32（Cora P1/NOVA 中危/CB F1 五路合流）：直写时代（r31 回退）读侧必须有兜底——
# 半写毒化此前 = 登录/设置面/保存修复通道全 500 且 UI 无法自救（死锁态）。
# 三防：短睡重试吃半写窗口 → 回落 .bak 自愈 → 无 .bak 才炸（fail-loud）。
# 铁律：绝不静默 {} 兜底——admin_name 回落 "admin"=爸爸被自己的名字挡在门外（Cora：比炸更阴险）。
def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        import time as _t
        _t.sleep(0.2)  # 半写窗口：并发写者可能正在落盘，短睡后重读一次
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        bak = SECRETS_PATH.with_name("settings.json.bak")  # 与写侧同处：secrets rw 卷（workspace 目录容器内只读）
        if bak.exists():
            try:
                data = json.loads(bak.read_text(encoding="utf-8"))
                try:  # 毒化原件留证；容器 ro 目录里写不进 .poisoned 也不影响自愈
                    SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".poisoned").write_text(
                        SETTINGS_PATH.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                except Exception:
                    pass
                SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print("[settings] 警告：settings.json 解析失败（%s），已从 .bak 自动恢复，原件留证 .poisoned"
                      % type(e).__name__, flush=True)
                return data
            except Exception as e2:
                print("[settings] .bak 恢复也失败（%s）——请手工检查 settings.json" % type(e2).__name__, flush=True)
        print("[settings] settings.json 解析失败且无可用备份（%s）——fail-loud，请手工修复该文件"
              % type(e).__name__, flush=True)
        raise


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
    # R74（Eve P1① 侧门·两步绕过补严）：护栏不能依赖"新旧对比"（空→改、改名回填都能短路旧条件）。
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
    # R74（Eve 绕法B·孤儿密钥）：providers 变更后清理已删除服务商遗留在 secrets 里的明文 key，
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
        # R69 拆雷（NOVA🟡9 预警今日成真）：删掉"按 base_url 猜改名"的联动。
        # 旧逻辑在爸爸"新加一个同地址服务商"（如两个书生号同 base_url）时，
        # 会把新地址误判成"旧服务商改名"，连带把 agents 里 coder/researcher/... 的
        # provider 全部静默改写成新名——加号≠改名！
        # 改名联动现在只认显式 /providers/rename 端点（office.api_provider_rename，那里
        # 精确按 old→new 处理，且是用户主动改名）。按名字查、宁报错不猜，符合零硬编码铁律。
    # r30 CB#8 原子写→r31 09-26 回退：tmp 文件落在 ro 挂载目录内写不进去（容器内
    # workspace 根 :ro，settings.json 单文件 rw 不覆盖同目录其他文件），注册/保存全炸
    # （"用户名保存失败"实证）。settings.json 本身是单文件 rw 挂载=直写安全，回退直写。
    # r32 更正（Qoder Max EXDEV 指谬）：旧注释建议"tmp 写 rw 卷后 os.replace 跨卷"——
    # os.replace 跨设备必 EXDEV 失败（Windows MoveFileEx 同样），该路线根本不成立。
    # 直写时代的兜底=写前 .bak（落 secrets rw 卷——workspace 同目录在容器里只读，
    # 新建 .bak 必失败）+ load_settings 三防自愈（毒化→短睡重试→回落 .bak→fail-loud）。
    _bak = SECRETS_PATH.with_name("settings.json.bak")
    try:
        if SETTINGS_PATH.exists():
            shutil.copyfile(SETTINGS_PATH, _bak)
    except Exception:
        pass  # 备份失败不阻断保存；缺 .bak 时 load_settings 走 fail-loud 而非静默
    SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s[section]


def get_plain_provider_key(name: str) -> str:
    return secret_get(f"external.providers.{name}.api_key")


# R79⑤（NOVA 第三报·锚定两步绕）：第一步 POST api_key="" 合法清掉明文 key，第二步再改 base_url
# 时 has_secret 已=False、锚定检查整个跳过——"清 key→改址"两步绕过换址护栏（埋桩等爸爸补 key）。
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
# R10.6（爸爸拍板"一次做成 ZCode 式守卫外置"）：M_GUARD_URL 配置时，密钥真源=m-guard 守卫服务
# （宿主 SYSTEM 常驻进程，DPAPI 加密存储，只答"验证通过/不通过"永不外发明文——ssh-agent 模式）。
# 本进程不再持有明文钥匙：米娅终态有宿主全权也改不了判定、偷不到钥匙。
# env 未配 M_GUARD_URL=本地裸跑兼容（旧文件逻辑）。
TOKEN_SECRET_PATH = "general.apiToken"
M_GUARD_URL = os.environ.get("M_GUARD_URL", "").strip().rstrip("/")
# r27 评审 P1（Cora/Eve 独立同锤，修法采 NOVA fail-closed 版）：守卫地址白名单【唯一真源】
# 在此——token_admin 不再自带一份（两处实现分叉=NOVA P1-② 假成功链的根）。
# 场景：.env/compose 的 M_GUARD_URL 被改成外域（配置劫持）→ 扇出点会把管理员
# 密钥明文 POST 给假守卫。空=本地裸跑（放行旧语义）；设了但白名单外=非法，
# 保持非空+标记短路全部扇出 fail-closed——绝不置空降级本地（Cora 368 推演：
# 置空=注册窗口误开+双源分裂抢注，比原洞更糟）。
_GUARD_HOSTS_ALLOWED = {"127.0.0.1", "localhost", "host.docker.internal"}


def _guard_url_ok(raw: str) -> bool:
    from urllib.parse import urlparse
    p = urlparse(raw)
    # r27 Veda P2：端口也锁——白名单内主机配成非守卫端口（如平台自身 2024）同样拒，
    # 防 X-Guard-Key 打向非守卫服务。期望端口=M_GUARD_PORT env（默认 9101，与守卫监听同源）。
    want_port = int(os.environ.get("M_GUARD_PORT", "9101") or 9101)
    return (p.scheme == "http" and (p.hostname or "") in _GUARD_HOSTS_ALLOWED
            and (p.port or 80) == want_port)


GUARD_URL_ILLEGAL = bool(M_GUARD_URL) and not _guard_url_ok(M_GUARD_URL)
if GUARD_URL_ILLEGAL:
    print("[settings_mgr] FATAL: M_GUARD_URL 指向白名单外（疑似配置劫持）——守卫扇出全部 fail-closed，立即核对 .env/compose", flush=True)


def _guard_post(path: str, payload: dict, timeout: float = 5.0) -> dict:
    if GUARD_URL_ILLEGAL:
        raise RuntimeError("guard 地址被白名单拒绝（fail-closed，疑配置劫持）——拒绝外发任何凭据")
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
        if GUARD_URL_ILLEGAL:
            # r27 NOVA/Cora fail-closed 知夏定夺：非法态保守当"已配置"——
            # 代价=新部署配置手误时登录页挡住注册页（loud log 可查）；
            # 反面（误判未配置→重开注册窗口）=抢注竞态，不可接受。
            return True
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
        # r27 NOVA P1-②：guard 模式的本函数曾被 token_admin 本地分支误调=no-op 假成功。
        # 改抛异常：任何"guard 模式下还想本地写 token"的路径都是 bug，必须炸出来。
        raise RuntimeError("guard 模式禁止本地写 token（fail-closed）——检查调用方分支")
    # 凭据只入 secrets（不进 settings.json、不进源码）；空串=清除（回到未配置=放行，供爸爸重置）
    secret_set(TOKEN_SECRET_PATH, value)


_VERIFY_CACHE: dict = {}  # R10.8h（NOVA P2⑤）：token_ok 结果 30s TTL 缓存——三处扇出每请求
_VERIFY_TTL = 30.0        # 一跳 guard，高负载会自我 DoS。单管理员场景缓存单条即可。
                          # rotate/clear 使旧钥匙失效后，最迟 30s 自然过期（窗口可接受，注明）。
                          # R10.11（Eve P3）：rotate/clear 成功路径改为主动调 clear_verify_cache()，窗口压到 0。


def clear_verify_cache() -> None:
    """R10.11（Eve P3）：rotate/clear 成功后由调用方主动清验证缓存——撤销即时生效。"""
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
