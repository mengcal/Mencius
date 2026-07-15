"""
圆桌会议 Pipe for Open WebUI
多模型圆桌讨论：2轮 + 主持人总结
直连各家模型API，不走OWUI中转，避免死锁
"""

import requests
import concurrent.futures
from pydantic import BaseModel, Field
from typing import Generator

TITLE = "圆桌会议"


class Pipe:
    class Valves(BaseModel):
        # 百炼云（阿里DashScope）
        BAILIAN_API_KEY: str = Field(default="", description="百炼云API Key")
        BAILIAN_BASE_URL: str = Field(
            default="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        # 智谱
        ZHIPU_API_KEY: str = Field(default="", description="智谱API Key")
        ZHIPU_BASE_URL: str = Field(default="https://open.bigmodel.cn/api/paas/v4")
        # 腾讯云
        TENCENT_API_KEY: str = Field(default="", description="腾讯云API Key")
        TENCENT_BASE_URL: str = Field(
            default="https://api.hunyuan.cloud.tencent.com/v1"
        )
        # DeepSeek
        DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API Key")
        DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1")
        # 书生InternLM
        INTERNLM_API_KEY: str = Field(default="", description="书生InternLM API Key")
        INTERNLM_BASE_URL: str = Field(
            default="https://internlm-chat.intern-ai.org.cn/puyu/api/v1"
        )
        # Ollama本地
        OLLAMA_BASE_URL: str = Field(
            default="http://host.docker.internal:11434",
            description="Ollama地址",
        )
        TEMPERATURE: float = Field(default=0.8, description="温度")
        MAX_TOKENS: int = Field(default=2000, description="每次发言最大token")

    def __init__(self):
        self.valves = self.Valves()

    def _resolve_provider(self, model_id: str):
        """根据模型ID判断用哪个API。返回 (base_url, api_key) 或 None。
        百炼云聚合了DS、智谱、Kimi等，默认走百炼云。"""
        v = self.valves

        # 明确走专属API的（独立Key优先）
        # 智谱直连
        if model_id.startswith("glm-") and v.ZHIPU_API_KEY:
            return v.ZHIPU_BASE_URL, v.ZHIPU_API_KEY

        # DeepSeek直连
        if model_id.startswith("deepseek-") and v.DEEPSEEK_API_KEY:
            return v.DEEPSEEK_BASE_URL, v.DEEPSEEK_API_KEY

        # 腾讯混元直连
        if "hunyuan" in model_id and v.TENCENT_API_KEY:
            return v.TENCENT_BASE_URL, v.TENCENT_API_KEY

        # 书生直连
        if "intern" in model_id and v.INTERNLM_API_KEY:
            return v.INTERNLM_BASE_URL, v.INTERNLM_API_KEY

        # 本地Ollama（模型名含冒号）
        if ":" in model_id:
            return f"{v.OLLAMA_BASE_URL}/v1", "ollama"

        # 百炼云作为默认（聚合了qwen、deepseek、glm、kimi、minimax等133+模型）
        if v.BAILIAN_API_KEY:
            return v.BAILIAN_BASE_URL, v.BAILIAN_API_KEY

        return None

    def pipe(self, body: dict, __user__: dict) -> Generator[str, None, None]:
        messages = body.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        if not user_msg:
            yield "请输入议题。"
            return

        # 解析消息
        topic = user_msg
        moderator = ""
        prev_minutes = ""

        mod_marker = "【主持人】"
        models_marker = "【参会模型】"
        minutes_marker = "【上次纪要】"

        # 提取主持人
        if mod_marker in topic:
            parts = topic.split(mod_marker, 1)
            topic = parts[0]
            rest = parts[1]
            if minutes_marker in rest:
                m_parts = rest.split(minutes_marker, 1)
                moderator = m_parts[0].strip()
                prev_minutes = m_parts[1].strip()
            else:
                moderator = rest.strip()
        elif minutes_marker in topic:
            parts = topic.split(minutes_marker, 1)
            topic = parts[0].strip()
            prev_minutes = parts[1].strip()

        # 提取参会模型
        participants = []
        if models_marker in topic:
            parts = topic.split(models_marker, 1)
            topic = parts[0].strip()
            rest = parts[1]
            if mod_marker in rest:
                rest = rest.split(mod_marker)[0]
            if minutes_marker in rest:
                rest = rest.split(minutes_marker)[0]
            for line in rest.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if "@" in line:
                    model_id, label = line.rsplit("@", 1)
                    participants.append({"label": label, "model": model_id.strip()})
                else:
                    participants.append({"label": line, "model": line})
        else:
            yield (
                "请用以下格式发消息：\n\n"
                "你的议题\n"
                "【参会模型】\n"
                "qwen-plus@千问\n"
                "glm-4-plus@智谱\n"
                "【主持人】glm-4-plus\n"
            )
            return

        topic = topic.strip()
        if not topic:
            yield "请输入议题。"
            return
        if not participants:
            yield "请至少指定一个参会模型。"
            return
        if not moderator:
            moderator = participants[0]["model"]
            yield f"⚠️ 未指定主持人，默认使用 {moderator}\n\n"

        # 验证API配置
        errors = []
        all_models = [p["model"] for p in participants] + [moderator]
        for m in all_models:
            provider = self._resolve_provider(m)
            if provider is None:
                errors.append(f"❌ 模型 `{m}` 无法匹配API提供商，请检查模型名或配置Key\n")
        if errors:
            for e in errors:
                yield e
            yield "\n所有模型默认走百炼云。如需直连智谱/DS/腾讯/书生，在Valves中填对应Key即可。\n"
            return

        # === 会议头 ===
        yield f"# 圆桌会议\n\n"
        yield f"**议题：** {topic}\n"
        yield f"**参与者：** {', '.join(p['label'] for p in participants)}\n"
        yield f"**主持人：** {moderator}\n"
        if prev_minutes:
            yield f"**参考：** 上次会议纪要\n"
        yield f"---\n\n"

        R1_PROMPT = (
            f"议题：{topic}\n\n"
            "请直接发表你的观点，简洁有力，不要重复议题。"
        )
        if prev_minutes:
            R1_PROMPT = (
                f"议题：{topic}\n\n"
                f"上次纪要：\n{prev_minutes}\n\n"
                "请在上次讨论基础上发表你的观点。"
            )

        R1_SYS = (
            "你是一场圆桌会议的参与者。请直接发表观点，用中文回答，控制在300字以内。"
        )

        # === 第一轮 ===
        yield f"## 第一轮：各自观点\n\n"

        r1_results = self._parallel_call(participants, R1_PROMPT, R1_SYS)
        for label, model, text in r1_results:
            yield f"### {label}（{model}）\n\n{text}\n\n"

        # 构建第一轮记录
        r1_transcript = "\n\n".join(
            f"【{p['label']}（{p['model']}）】\n{text}"
            for p, (_, _, text) in zip(participants, r1_results)
        )

        # === 第二轮 ===
        yield f"## 第二轮：点评与表态\n\n"

        R2_PROMPT = (
            f"议题：{topic}\n\n"
            f"第一轮发言记录：\n{r1_transcript}\n\n"
            "请点评其他参与者的观点，明确表态：\n"
            "1. 你同意谁的观点？为什么？\n"
            "2. 你反对谁的观点？为什么？\n"
            "3. 你要补充或修改自己的观点吗？\n"
            "用中文，控制在400字以内。"
        )
        R2_SYS = (
            "你是圆桌会议参与者，现在进入第二轮。"
            "请认真点评他人观点并表态，用中文。"
        )

        r2_results = self._parallel_call(participants, R2_PROMPT, R2_SYS)
        for label, model, text in r2_results:
            yield f"### {label}（{model}）\n\n{text}\n\n"

        # 构建完整记录
        r2_transcript = "\n\n".join(
            f"【{p['label']}（{p['model']}）】\n{text}"
            for p, (_, _, text) in zip(participants, r2_results)
        )

        full_transcript = f"第一轮：\n{r1_transcript}\n\n第二轮：\n{r2_transcript}"

        # === 主持人总结 ===
        yield f"## 主持人总结\n\n"

        MOD_PROMPT = (
            f"议题：{topic}\n\n"
            f"讨论记录：\n{full_transcript}\n\n"
            "你是会议主持人，请归纳总结：\n"
            "1. 找出观点一致的阵营（≥2人观点趋同合并为一个方案）\n"
            "2. 坚持独立观点的人单独成方案\n"
            "3. 每个方案标注：支持者、核心观点、风险点、备选路径\n"
            "4. 至少给出2个方案，如果只有1个共识也要给出2条执行路径\n"
            "5. 末尾输出【纪要】标签，包含简明纪要供下次会议参考\n"
            "用中文。"
        )
        MOD_SYS = (
            "你是圆桌会议主持人/参谋。你负责归纳多方观点，"
            "整理方案矩阵，不替用户做决定。用中文。"
        )

        try:
            mod_text = self._call_model(moderator, MOD_PROMPT, MOD_SYS)
            yield mod_text
        except Exception as e:
            yield f"[主持人调用失败: {e}]"

    def _parallel_call(self, participants, prompt, system_prompt):
        """并发调用多个模型，按完成顺序返回结果。"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(participants)
        ) as executor:
            futures = {}
            for p in participants:
                future = executor.submit(
                    self._call_model, p["model"], prompt, system_prompt
                )
                futures[future] = p

            for future in concurrent.futures.as_completed(futures):
                p = futures[future]
                try:
                    text = future.result()
                except Exception as e:
                    text = f"[调用失败: {e}]"
                results.append((p["label"], p["model"], text))
        return results

    def _call_model(self, model, prompt, system_prompt="") -> str:
        """直连模型API调用。"""
        provider = self._resolve_provider(model)
        if provider is None:
            raise ValueError(f"无法匹配API提供商: {model}")

        base_url, api_key = provider
        url = f"{base_url}/chat/completions"

        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})

        headers = {"Content-Type": "application/json"}
        if api_key and api_key != "ollama":
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(
            url,
            json={
                "model": model,
                "messages": msgs,
                "stream": False,
                "temperature": self.valves.TEMPERATURE,
                "max_tokens": self.valves.MAX_TOKENS,
            },
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
