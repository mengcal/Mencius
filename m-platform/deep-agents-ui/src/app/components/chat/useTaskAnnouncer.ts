'use client';

/**
 * components/chat/useTaskAnnouncer.ts —— 后台任务完成自动播报（原 ChatInterface.tsx R3/R64 段迁出）
 * ------------------------------------------------------------------
 * 轮询 /background_tasks（15s），完成且未播报的任务 → 自动让助手读结果汇报给管理员。
 * R64 修复：① 只播报 !reported 的任务（webhook 已汇报过的老任务永不重复播，
 *     bk_001/bk_002 这类历史任务从此闭嘴）；② announced 集合持久化到 localStorage
 *     'mia.announcedTasks'，刷新页面不再清空重播（原 useRef 内存集刷新即失忆 = R56 反复出现的元凶）
 */

import { useEffect, useRef } from "react";
import { getBackgroundTasks } from "@/lib/providerApi";

type SendMessage = (
  content: string,
  runOpts?: { model?: string; provider?: string; webSearch?: boolean; thinking?: string }
) => void;

export function useTaskAnnouncer(isLoading: boolean, sendMessage: SendMessage) {
  const announcedRef = useRef<Set<string>>(
    typeof window !== "undefined"
      ? new Set(JSON.parse(localStorage.getItem("mia.announcedTasks") || "[]"))
      : new Set()
  );
  useEffect(() => {
    const timer = setInterval(async () => {
      if (isLoading) return; // 正在流式输出时不插话
      try {
        const { tasks } = await getBackgroundTasks();
        const done = tasks.filter(
          (t: any) =>
            t.status === "done" && !t.reported && !announcedRef.current.has(t.id)
        );
        for (const t of done) {
          announcedRef.current.add(t.id);
          localStorage.setItem(
            "mia.announcedTasks",
            JSON.stringify([...announcedRef.current])
          );
          sendMessage(
            `后台任务《${t.task}》已完成，结果如下：\n${t.result}\n请把结果整理后汇报给管理员。`
          );
        }
      } catch {
        /* 后端不在也无所谓 */
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [isLoading, sendMessage]);
}
