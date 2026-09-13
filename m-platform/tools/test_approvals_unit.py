"""R10.3/R10.4/r27 approvals 单元语义测试（终版-工具 随包交付；容器内跑：
docker exec -i m-workplatform-1 python3 - < test_approvals_unit.py）
覆盖：fp 不匹配拒/匹配过/无 fp 必填拒/连点不覆盖/r27 重试窗（窗内同 fp≤3 放行、用满拒、
窗后一次性）/revoke/空登记拒/裁剪 ≤400。
"""
import approvals as ap

FAILS = []


def check(label, got, want):
    ok = got == want
    print(('✓' if ok else '✗'), label, '->', got)
    if not ok:
        FAILS.append(label)


tid, tool = "unit-t1", "execute"

ap.set_blocked(tid, tool, "aaaa1111aaaa1111")
check("1 fp不匹配=拒", ap.approve(tid, tool, "bbbb2222bbbb2222")[0], False)
check("2 fp匹配=过", ap.approve(tid, tool, "aaaa1111aaaa1111")[0], True)
check("3 无fp=拒(必填)", ap.approve(tid, tool, "")[0], False)
check("4 首次消费=过", ap.consume(tid, tool, "aaaa1111aaaa1111"), True)
# r27 重试竞争窗：批准后 90 秒内同 fp 最多放行 3 次（覆盖双唤醒打断 run 的场景）
check("5a 窗内第2次=仍过", ap.consume(tid, tool, "aaaa1111aaaa1111"), True)
check("5b 窗内第3次=仍过", ap.consume(tid, tool, "aaaa1111aaaa1111"), True)
check("5c 窗内用满第4次=拒", ap.consume(tid, tool, "aaaa1111aaaa1111"), False)
# 窗后（模拟批准时刻过期但仍在 24h TTL 内）：未消费过的批准=一次性
ap.set_blocked(tid, tool, "eeee5555eeee5555")
ap.approve(tid, tool, "eeee5555eeee5555")
k = (tid, tool, "eeee5555eeee5555")
ts, used = ap._approved[k]
ap._approved[k] = (ts - 91, used)  # 拨出 90 秒重试窗
check("5d 窗后首次=过", ap.consume(tid, tool, "eeee5555eeee5555"), True)
check("5e 窗后复用=焚", ap.consume(tid, tool, "eeee5555eeee5555"), False)
ap.set_blocked(tid, tool, "cccc3333cccc3333")
check("6 revoke", (ap.revoke(tid, tool), ap.revoke(tid, tool)), (True, False))
check("7 空登记=拒", ap.approve(tid, tool, "dddd4444dddd4444")[0], False)
for i in range(500):
    ap.set_blocked(f"tid{i}", tool, f"fp{i:04d}")
check("8 裁剪≤400", len(ap._blocked_fp) <= 400, True)

print('ALL GREEN' if not FAILS else f'FAILURES: {FAILS}')
raise SystemExit(0 if not FAILS else 1)
