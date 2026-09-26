'use client';

/**
 * components/chat/useModelSelection.ts —— 输入框模型/思维档/联网开关 hook（原 ChatInterface.tsx 迁出）
 * ------------------------------------------------------------------
 * - 🌐 联网：r32b 起按钮退役恒开（爸爸裁决），无开关无 localStorage 键
 * - 🧠 思维四档：''=默认(随模型出厂)，off/low/medium/high；按对话独立存储（localStorage 'mia.thinking.<tid>'）
 * - 模型选择：R46 按对话记忆 + 全局默认（新对话继承上次选择；切回旧对话自动恢复）
 *   localStorage 键 'mia.model.<tid>' / 'mia.modelProvider.<tid>' / 'mia.model' / 'mia.modelProvider' 原样保留
 * R73：角色卡整体退役（评审一致认定权限裸奔+冲突风险，爸爸拍板取消）——只留米娅工作脑
 */

import { useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { getAllModels } from "@/lib/providerApi";

export function useModelSelection() {
  // r32c #13（CB F10）：webSearchOn/setWebSearchOn 随联网按钮退役（ChatInterface 恒传 true），
  // 死状态与 localStorage 'mia.webSearch' 僵尸键一并清除——联网=默认开，无开关。
  // r25（爸爸：输入框"工具"按钮=只有开关没有下游消费，空壳连根拔；ZCode 式工具本就该由模型自主调用）
  // 思维四档：'' =默认(随模型出厂)，off=关闭，low/medium/high。按对话独立存储，随消息传给引擎
  const [thinking, setThinkingState] = useState("");
  const threadId = useQueryState("threadId");
  const tidNow = threadId[0] ?? "";
  useEffect(() => {
    setThinkingState(localStorage.getItem(`mia.thinking.${tidNow || "default"}`) || "");
  }, [tidNow]);
  const setThinking = (v: string) => {
    setThinkingState(v);
    localStorage.setItem(`mia.thinking.${threadId[0] || "default"}`, v);
  };
  const [models, setModels] = useState<{ model: string; provider: string }[]>([]);
  // R46：模型选择按对话记忆（新对话继承上次选择；切回旧对话自动恢复该对话的模型）
  const [selectedModel, setSelectedModel] = useState<string>(
    typeof window !== "undefined"
      ? localStorage.getItem(`mia.model.${tidNow}`) || localStorage.getItem("mia.model") || ""
      : ""
  );
  const [selectedProvider, setSelectedProvider] = useState<string>(
    typeof window !== "undefined"
      ? localStorage.getItem(`mia.modelProvider.${tidNow}`) || localStorage.getItem("mia.modelProvider") || ""
      : ""
  );
  useEffect(() => {
    // 切换对话时，恢复该对话自己的模型（没有则继承全局上次选择）
    setSelectedModel(localStorage.getItem(`mia.model.${tidNow}`) || localStorage.getItem("mia.model") || "");
    setSelectedProvider(localStorage.getItem(`mia.modelProvider.${tidNow}`) || localStorage.getItem("mia.modelProvider") || "");
  }, [tidNow]);
  useEffect(() => {
    getAllModels().then(setModels);
  }, []);
  const pickModel = (m: string, provider?: string) => {
    setSelectedModel(m);
    if (provider) setSelectedProvider(provider);
    // R46：按对话记忆 + 全局默认（新对话继承）
    localStorage.setItem(`mia.model.${tidNow}`, m);
    localStorage.setItem(`mia.modelProvider.${tidNow}`, provider || "");
    localStorage.setItem("mia.model", m);
    localStorage.setItem("mia.modelProvider", provider || "");
  };
  return {
    thinking,
    setThinking,
    models,
    selectedModel,
    selectedProvider,
    pickModel,
    tidNow,
  };
}
