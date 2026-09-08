"""R10.3 skills_lock（评审A/评审B 方案落地）：技能清单哈希锁——挂载回归保险的"下一层失守兜底"。

威胁模型（两家信中对齐）：当前写面已死（沙箱 EROFS、助手进程 EROFS+自锁、n8n 不沾 mia_home），
本锁不堵现洞，防的是：未来新容器忘叠 :ro、部署改版漏挂、宿主侧误操作把 D:\\m\\skills 改回可写。

机制（原地校验版——deepagents SkillsMiddleware 经 backend(root=mia_home) 读路径，
绝对路径副本喂不进 backend，故不做副本；启动时校验恰好覆盖回归场景：改挂载=必重启=必再校验）：
- 基线 {相对路径: sha256} 落宿主 secrets 卷 skills_manifest.json（被校验方改不到）；
- 基线缺失=首次部署自动信任首扫（落审计日志，之后转入严格模式）；
- 校验不符 → 图构建时 skills=[]（宁可不带技能不裸奔）+ 容器日志 + 审计出声；
- settings.skills_lock.enabled=false 时跳过（管理员在设置页明确知情地关）；
- /skills/rehash（管理员门）：管理员改完 D:\\m\\skills 后重扫重建基线。

残留（诚实清单）：平台运行中宿主直接改技能文件，到下次重启/重登记前不被捕获——
宿主写=下战场威胁模型，与 ②-2 同判断。
"""
import hashlib
import json
from pathlib import Path

import settings_mgr


def _manifest_path() -> Path:
    return settings_mgr.SECRETS_PATH.parent / "skills_manifest.json"


def _lock_cfg() -> dict:
    try:
        cfg = settings_mgr.load_settings().get("skills_lock") or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def enabled() -> bool:
    """默认开（fail-closed 方向）；settings.skills_lock.enabled=false 才关（管理员显式知情）。"""
    return bool(_lock_cfg().get("enabled", True))


def _iter_skill_files(base: Path):
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if p.is_file():
            yield p


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(base: Path) -> dict:
    """全量扫描 → {相对路径: sha256}。"""
    return {str(p.relative_to(base)).replace("\\", "/"): _sha256(p) for p in _iter_skill_files(base)}


def audit(action: str, detail: str) -> None:
    """落 secrets 卷审计（被审方摸不到）；写失败只出声不影响主流程。"""
    try:
        log = _manifest_path().parent / "skills_lock_audit.jsonl"
        import datetime as _dt
        rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "action": action, "detail": detail[:200]}
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ensure_baseline(base: Path) -> dict:
    """基线缺失=首扫落账（评审B：首次部署自动信任首扫）；已有基线原样返回。"""
    mp = _manifest_path()
    if mp.exists():
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    manifest = scan(base)
    try:
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        audit("baseline_first_scan", f"{len(manifest)} files")
    except Exception as e:
        audit("baseline_write_failed", str(e))
    return manifest


def verify(base: Path, manifest: dict, audit_on: bool = True) -> dict:
    """逐文件校验 → {"missing": [...], "mismatch": [...], "extra": [...]}（空 dict=全部干净）。
    audit_on=False 供只读的 /skills/list 用（查状态不刷审计）。"""
    out = {"missing": [], "mismatch": [], "extra": []}
    for rel, want in manifest.items():
        p = base / rel
        if not p.is_file():
            out["missing"].append(rel)
        elif _sha256(p) != want:
            out["mismatch"].append(rel)
    for p in _iter_skill_files(base):
        rel = str(p.relative_to(base)).replace("\\", "/")
        if rel not in manifest:
            out["extra"].append(rel)
    if audit_on and any(out.values()):
        audit("mismatch", json.dumps({k: v[:8] for k, v in out.items() if v}, ensure_ascii=False))
    return out


def rehash(base: Path) -> dict:
    """管理员在宿主改完技能后重扫重建基线（管理员门内的端点调这里）。"""
    manifest = scan(base)
    _manifest_path().write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    audit("rehash", f"{len(manifest)} files")
    return manifest
