"""
圆桌会议 Pipe for Open WebUI (v5)
多模型圆桌讨论:2轮 + 主持人总结
直连各家模型API,不走OWUI中转,避免死锁

v5 改动(2026-08-01):
  1. 8个统一通道(CH1-CH8),格式完全一致,不分永久/临时
  2. 前缀从Valves动态读取,改通道不用改代码
  3. 新增DS通道(DeepSeek官方API)
  4. 多格式标记:【】、()、[]、{}、冒号 都能识别
  5. base_url加.strip()防止复制粘贴空格导致404
  6. 错误信息增强:显示模型名、URL、通道名
  7. 去掉DEFAULT通道,所有模型必须带前缀

8个通道配置方法:
  每个通道4个字段: PREFIX(前缀)、NAME(显示名)、API_KEY、BASE_URL
  - 前缀格式: "BL/百炼"(英文/中文,用/分隔,大小写不敏感)
  - 前缀留空 = 通道未启用
  - 想换平台:直接改对应通道的4个字段,代码不动
  - 想加平台:找空通道(CH6-CH8)填上,或复制一组格式增加

如何添加更多通道(超过8个):
  复制以下4行,改数字即可:
    CH9_PREFIX: str = Field(default="", description="通道9前缀")
    CH9_NAME: str = Field(default="通道9", description="通道9显示名")
    CH9_API_KEY: str = Field(default=" ", description="通道9 API Key", json_schema_extra={"format": "password"})
    CH9_BASE_URL: str = Field(default="", description="通道9 Base URL")
  然后把 _build_prefix_map 和 _get_channel_info 里的 range(1, 9) 改成 range(1, 10)

模型写法:
  BL:kimi-k2.6           → 走通道1(百炼)
  百炼:kimi-k2.6          → 走通道1(百炼,中文前缀)
  DS:deepseek-chat       → 走通道5(DeepSeek)
  BL:kimi-k2.6@Kimi      → 走通道1,显示名"Kimi"

标记格式(支持多种写法):
  参会模型: 【参会模型】 (参会模型) [参会模型] {参会模型} 参会模型： 参会： 模型：
  主持人:   【主持人】 (主持人) [主持人] {主持人} 主持人： 主持：
  续议:     【续议】 (续议) [续议] 续议：
  上次纪要: 【上次纪要】 (上次纪要) [上次纪要]

用法示例:

  第一次讨论:
    为什么docker可以有-d参数而酒馆没有?
    【参会模型】
    BL:kimi-k2.6
    DS:deepseek-chat
    ZP:glm-4.5-air
    【主持人】BL:qwen-plus

  自然语言继续讨论(不用写标记,自动继承上一轮):
    接着聊,从安全角度重新审视一下

  续议(新议题,自动带上次纪要):
    如何把方案落地实施?
    【参会模型】
    BL:kimi-k2.6
    DS:deepseek-chat
    【主持人】BL:qwen-plus
    【续议】
"""

import requests
import concurrent.futures
import re
import time
from pydantic import BaseModel, Field
from typing import Generator

TITLE = "圆桌会议"

# ============================================================
# 标记列表(支持多种格式写法)
# 顺序:长标记在前,避免短标记误匹配
# ============================================================
_PARTICIPANT_MARKERS = [
    "【参会模型】", "(参会模型)", "[参会模型]", "{参会模型}",
    "参会模型：", "参会模型:",
    "【模型】", "(模型)", "[模型]", "{模型}",
    "参会：", "参会:",
    "模型：", "模型:",
]

_MODERATOR_MARKERS = [
    "【主持人】", "(主持人)", "[主持人]", "{主持人}",
    "【主持】", "(主持)", "[主持]", "{主持}",
    "【支持人】", "(支持人)", "[支持人]",  # 错别字容错
    "主持人：", "主持人:",
    "主持：", "主持:",
]

_RESUME_MARKERS = [
    "【续议】", "(续议)", "[续议]", "{续议}",
    "续议：", "续议:",
]

_MINUTES_MARKERS = [
    "【上次纪要】", "(上次纪要)", "[上次纪要]", "{上次纪要}",
    "上次纪要：", "上次纪要:",
]

# 续议触发词(自然语言,不需要完整标记)
_RESUME_KEYWORDS = [
    "续议", "带上次纪要", "带上次结论", "带上次结果",
    "参考上次", "上次纪要", "结合上次",
]


class Pipe:
    class Valves(BaseModel):
        # ============================================================
        # 8个通道(CH1-CH8),格式完全统一
        # 填了前缀和Key就能用,前缀留空=未启用
        # 想换平台:直接改对应通道的4个字段
        # 想加平台:找空通道填上,或复制格式增加CH9/CH10...
        # ============================================================

        # 通道1: 百炼云(阿里DashScope)
        CH1_PREFIX: str = Field(default="BL/百炼", description="通道1前缀(中英文用/分隔,如 BL/百炼)")
        CH1_NAME: str = Field(default="百炼云", description="通道1显示名")
        CH1_API_KEY: str = Field(default=" ", description="通道1 API Key", json_schema_extra={"format": "password"})
        CH1_BASE_URL: str = Field(default="", description="通道1 Base URL")

        # 通道2: 腾讯云
        CH2_PREFIX: str = Field(default="TX/腾讯", description="通道2前缀")
        CH2_NAME: str = Field(default="腾讯云", description="通道2显示名")
        CH2_API_KEY: str = Field(default=" ", description="通道2 API Key", json_schema_extra={"format": "password"})
        CH2_BASE_URL: str = Field(default="", description="通道2 Base URL")

        # 通道3: 书生InternLM
        CH3_PREFIX: str = Field(default="SS/书生", description="通道3前缀")
        CH3_NAME: str = Field(default="书生", description="通道3显示名")
        CH3_API_KEY: str = Field(default=" ", description="通道3 API Key", json_schema_extra={"format": "password"})
        CH3_BASE_URL: str = Field(default="", description="通道3 Base URL")

        # 通道4: 智谱
        CH4_PREFIX: str = Field(default="ZP/智谱", description="通道4前缀")
        CH4_NAME: str = Field(default="智谱", description="通道4显示名")
        CH4_API_KEY: str = Field(default=" ", description="通道4 API Key", json_schema_extra={"format": "password"})
        CH4_BASE_URL: str = Field(default="", description="通道4 Base URL")

        # 通道5: DeepSeek
        CH5_PREFIX: str = Field(default="DS/深度求索", description="通道5前缀")
        CH5_NAME: str = Field(default="DeepSeek", description="通道5显示名")
        CH5_API_KEY: str = Field(default=" ", description="通道5 API Key", json_schema_extra={"format": "password"})
        CH5_BASE_URL: str = Field(default="", description="通道5 Base URL")

        # 通道6: 空(待填)
        CH6_PREFIX: str = Field(default="", description="通道6前缀(留空=未启用)")
        CH6_NAME: str = Field(default="通道6", description="通道6显示名")
        CH6_API_KEY: str = Field(default=" ", description="通道6 API Key", json_schema_extra={"format": "password"})
        CH6_BASE_URL: str = Field(default="", description="通道6 Base URL")

        # 通道7: 空(待填)
        CH7_PREFIX: str = Field(default="", description="通道7前缀(留空=未启用)")
        CH7_NAME: str = Field(default="通道7", description="通道7显示名")
        CH7_API_KEY: str = Field(default=" ", description="通道7 API Key", json_schema_extra={"format": "password"})
        CH7_BASE_URL: str = Field(default="", description="通道7 Base URL")

        # 通道8: 空(待填)
        CH8_PREFIX: str = Field(default="", description="通道8前缀(留空=未启用)")
        CH8_NAME: str = Field(default="通道8", description="通道8显示名")
        CH8_API_KEY: str = Field(default=" ", description="通道8 API Key", json_schema_extra={"format": "password"})
        CH8_BASE_URL: str = Field(default="", description="通道8 Base URL")

        # ============================================================
        # 通用设置
        # ============================================================
        TEMPERATURE: float = Field(default=0.8, description="温度")
        MAX_TOKENS: int = Field(default=2000, description="每次发言最大token")
        MODERATOR_MAX_TOKENS: int = Field(default=4000, description="主持人总结最大token(需要更大)")
        HEARTBEAT_INTERVAL: int = Field(default=5, description="心跳间隔(秒),每N秒无输出时发送等待中保持连接")
        API_TIMEOUT: int = Field(default=180, description="API请求超时(秒),单个模型最大等待时间")

    def __init__(self):
        self.valves = self.Valves()

    # ============================================================
    # 通道解析:前缀->通道号 (从Valves动态读取)
    # ============================================================
    def _build_prefix_map(self):
        """从Valves构建前缀到通道号的映射。"""
        pm = {}
        for i in range(1, 9):
            prefix_str = getattr(self.valves, f"CH{i}_PREFIX", "").strip()
            if not prefix_str:
                continue
            # 支持 "BL/百炼" 格式,用/分割出多个前缀
            parts = [p.strip() for p in prefix_str.split("/") if p.strip()]
            for p in parts:
                pm[p.lower()] = i
                pm[p] = i  # 原样也存一份(中文)
        return pm

    def _get_channel_info(self, ch_num):
        """获取通道的Key和URL(都加了strip)。"""
        v = self.valves
        return {
            "name": getattr(v, f"CH{ch_num}_NAME", f"通道{ch_num}"),
            "api_key": getattr(v, f"CH{ch_num}_API_KEY", "").strip(),
            "base_url": getattr(v, f"CH{ch_num}_BASE_URL", "").strip(),
        }

    def _list_available_prefixes(self):
        """列出所有已配置的通道,用于错误提示。"""
        result = []
        for i in range(1, 9):
            prefix_str = getattr(self.valves, f"CH{i}_PREFIX", "").strip()
            if prefix_str:
                name = getattr(self.valves, f"CH{i}_NAME", f"通道{i}")
                result.append(f"{prefix_str}({name})")
        return result

    def _resolve_provider(self, model_id):
        """解析模型ID到API通道。
        返回 dict 或 None(未知前缀/无前缀)。
        """
        pm = self._build_prefix_map()

        if ":" in model_id:
            prefix, actual_model = model_id.split(":", 1)
            prefix_clean = prefix.strip()
            prefix_lower = prefix_clean.lower()
            actual_model = actual_model.strip()

            ch = pm.get(prefix_clean) or pm.get(prefix_lower)
            if ch is None:
                return None
        else:
            return None  # 无前缀

        info = self._get_channel_info(ch)
        return {
            "base_url": info["base_url"],
            "api_key": info["api_key"],
            "actual_model": actual_model,
            "channel": ch,
            "channel_name": info["name"],
        }

    def _parse_participant(self, line):
        """解析一行参会模型。
        格式:
          前缀:模型ID        → 走对应通道
          前缀:模型ID@显示名  → 走对应通道,自定义显示名
        返回 dict 或 None(空行/解析失败)。
        """
        line = line.strip()
        if not line:
            return None

        label = ""
        if "@" in line:
            model_part, label = line.rsplit("@", 1)
            label = label.strip()
            model_id = model_part.strip()
        else:
            model_id = line

        info = self._resolve_provider(model_id)
        if info is None:
            return None

        if not label:
            label = info["actual_model"]

        return {
            "label": label,
            "model": model_id,
            "actual_model": info["actual_model"],
            "base_url": info["base_url"],
            "api_key": info["api_key"],
            "channel": info["channel"],
            "channel_name": info["channel_name"],
        }

    def _strip_thinking(self, text):
        """剥离推理模型的思维链输出。"""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        # 剥离开头的思维链(在正式回答前的大段英文推理)
        lines = text.strip().split("\n")
        if lines:
            reasoning_keywords = [
                "i should", "i need", "let me", "given that",
                "i will", "so the", "this means", "however",
                "therefore", "on the other hand", "but the user",
                "the instruction",
            ]
            first_chinese = 0
            for i, line in enumerate(lines[:20]):
                line_lower = line.strip().lower()
                if (
                    line_lower
                    and not any(line_lower.startswith(k) for k in reasoning_keywords)
                    and not line_lower.startswith("#")
                ):
                    if re.search(r"[\u4e00-\u9fff]", line):
                        first_chinese = i
                        break
            else:
                first_chinese = 0
            reasoning_count = sum(
                1
                for line in lines[:10]
                if any(line.strip().lower().startswith(k) for k in reasoning_keywords)
            )
            if reasoning_count >= 3 and first_chinese > 0:
                text = "\n".join(lines[first_chinese:])
        return text.strip()

    def _call_model(self, p, prompt, system_prompt="", max_tokens=None):
        """直连模型API调用。p 是 participant dict。"""
        if max_tokens is None:
            max_tokens = self.valves.MAX_TOKENS
        # .strip() 防止复制粘贴时带入不可见空格导致404
        base_url = p["base_url"].strip()
        url = f"{base_url.rstrip('/')}/chat/completions"
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})

        headers = {"Content-Type": "application/json"}
        if p["api_key"]:
            headers["Authorization"] = f"Bearer {p['api_key'].strip()}"

        try:
            resp = requests.post(
                url,
                json={
                    "model": p["actual_model"],
                    "messages": msgs,
                    "stream": False,
                    "temperature": self.valves.TEMPERATURE,
                    "max_tokens": max_tokens,
                },
                headers=headers,
                timeout=self.valves.API_TIMEOUT,
            )
            resp.raise_for_status()
            return self._strip_thinking(resp.json()["choices"][0]["message"]["content"])
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            raise requests.exceptions.HTTPError(
                f"{status} Error | 模型:{p['actual_model']} | URL:{url} | 通道:{p.get('channel_name','?')}"
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"连接失败 | 模型:{p['actual_model']} | URL:{url} | 通道:{p.get('channel_name','?')}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"超时({self.valves.API_TIMEOUT}s) | 模型:{p['actual_model']} | 通道:{p.get('channel_name','?')}")
        except Exception as e:
            raise Exception(f"{e} | 模型:{p['actual_model']} | URL:{url} | 通道:{p.get('channel_name','?')}")

    def _parallel_call_stream_with_heartbeat(self, participants, prompt, system_prompt, max_tokens=None):
        """并发调用,按完成顺序逐个 yield 结果,并加入心跳机制。
        prompt/system_prompt 可以是字符串(所有模型共用)或列表(每个模型独立)。
        """
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(participants)
        ) as executor:
            futures = {}
            for idx, p in enumerate(participants):
                p_prompt = prompt[idx] if isinstance(prompt, list) else prompt
                p_sys = system_prompt[idx] if isinstance(system_prompt, list) else system_prompt
                futures[executor.submit(self._call_model, p, p_prompt, p_sys, max_tokens)] = p
            last_heartbeat = time.time()
            heartbeat_interval = self.valves.HEARTBEAT_INTERVAL

            while futures:
                done, _ = concurrent.futures.wait(
                    futures, timeout=heartbeat_interval,
                    return_when=concurrent.futures.FIRST_COMPLETED
                )
                if not done:
                    yield ("__heartbeat__", "", "")
                    last_heartbeat = time.time()
                    continue

                for future in done:
                    p = futures.pop(future)
                    try:
                        text = future.result()
                    except Exception as e:
                        text = f"[调用失败: {e}]"
                    yield (p["label"], p["model"], text)
                    last_heartbeat = time.time()

    def _split_by_markers(self, text, markers):
        """尝试用多个标记分割文本。
        返回 (before, after) 或 None。
        markers 列表顺序:长标记在前,避免短标记误匹配。
        """
        for marker in markers:
            if marker in text:
                parts = text.split(marker, 1)
                return parts[0], parts[1]
        return None

    def _extract_prev_round(self, messages):
        """从对话历史中提取上一轮圆桌会议的信息。
        返回 {"participants": [...], "moderator": {...}, "transcript": "...", "minutes": "..."} 或 None。
        """
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if "圆桌会议" not in content:
                continue

            # 解析参与者:从 ### {label}({model}) 提取,兼容全角和半角括号
            participants = []
            seen_models = set()
            for match in re.finditer(r"###\s+(.+?)[\uff08(](.+?)[\uff09)]", content):
                label = match.group(1).strip()
                model_id = match.group(2).strip()
                if model_id in seen_models:
                    continue
                seen_models.add(model_id)
                p = self._parse_participant(model_id)
                if p:
                    participants.append(p)

            if not participants:
                continue

            # 解析主持人:从 **主持人:** xxx 提取
            moderator = None
            mod_match = re.search(r"\*\*主持人[\uff1a:]\*\*\s*(.+)", content)
            if mod_match:
                mod_str = mod_match.group(1).strip()
                moderator = self._parse_participant(mod_str)
            if not moderator:
                moderator = participants[0]

            # 提取纪要
            minutes = ""
            if "【纪要】" in content:
                minutes = content.split("【纪要】", 1)[1].strip()
            elif "## 主持人总结" in content:
                minutes = content.split("## 主持人总结", 1)[1].strip()

            return {
                "participants": participants,
                "moderator": moderator,
                "transcript": content,
                "minutes": minutes,
            }
        return None

    def pipe(self, body: dict, __user__: dict) -> Generator[str, None, None]:
        messages = body.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        if not user_msg:
            yield "请输入议题。"
            return

        user_stripped = user_msg.strip()

        # ============================================================
        # 核心路由:判断是"开新局"还是"接着聊"
        # ============================================================
        has_models = any(m in user_stripped for m in _PARTICIPANT_MARKERS)

        has_resume_tag = any(m in user_stripped for m in _RESUME_MARKERS)
        if not has_resume_tag:
            for kw in _RESUME_KEYWORDS:
                if kw in user_stripped:
                    has_resume_tag = True
                    break

        # ===== 模式一:没有参会模型标记 -> 继续讨论或提示格式 =====
        if not has_models:
            prev = self._extract_prev_round(messages)
            if prev is None:
                yield (
                    "请用以下格式发消息:\n\n"
                    "你的议题\n"
                    "【参会模型】\n"
                    "BL:kimi-k2.6\n"
                    "DS:deepseek-chat\n"
                    "ZP:glm-4.5-air\n"
                    "【主持人】BL:qwen-plus\n"
                )
                return

            participants = prev["participants"]
            moderator = prev["moderator"]
            prev_transcript = prev["transcript"]
            prev_minutes = prev["minutes"]

            yield f"# 圆桌会议(继续讨论)\n\n"
            yield f"**参与者:** {', '.join(p['label'] for p in participants)}\n"
            yield f"**主持人:** {moderator['model']}\n"
            yield f"**用户指示:** {user_stripped}\n"
            yield f"---\n\n"

            R1_PROMPT = f"【上一轮完整讨论记录】:\n{prev_transcript}\n\n"
            if prev_minutes:
                R1_PROMPT += f"【上一轮核心纪要】:\n{prev_minutes}\n\n"
            R1_PROMPT += (
                f"【用户的最新自然语言指示】:\n{user_stripped}\n\n"
                "请根据用户的最新指示,结合上一轮的背景继续讨论。\n"
                "注意:如果用户是在追问或要求深入某个细节,请针对性补充;\n"
                "如果用户提出了全新的议题,请结合上一轮的经验和纪要,给出新的方案。\n"
                "用中文,控制在400字以内。"
            )
            R1_SYS = "你是一场圆桌会议的参与者。请认真理解用户的自然语言意图,结合历史背景发表观点。用中文。"

            yield f"## 继续讨论\n\n"
            r1_results = []
            for label, model, text in self._parallel_call_stream_with_heartbeat(participants, R1_PROMPT, R1_SYS):
                if label == "__heartbeat__":
                    yield "⏳ 等待模型响应中...\n\n"
                    continue
                r1_results.append((label, model, text))
                yield f"### {label}({model})\n\n{text}\n\n"

            r1_transcript = "\n\n".join(
                f"【{p['label']}({p['model']})】\n{text}"
                for p, (_, _, text) in zip(participants, r1_results)
            )

            yield f"## 点评与表态\n\n"
            # 每个模型独立prompt,区分自己vs别人的发言
            r2_prompts = []
            r2_systems = []
            for i, p in enumerate(participants):
                own_text = r1_results[i][2]
                others_text = "\n\n".join(
                    f"【{participants[j]['label']}({participants[j]['model']})】\n{r1_results[j][2]}"
                    for j in range(len(participants))
                    if j != i
                )
                r2_prompts.append(
                    f"上一轮讨论记录:\n{prev_transcript}\n\n"
                    f"你在本轮的发言:\n{own_text}\n\n"
                    f"其他参与者在本轮的发言:\n{others_text}\n\n"
                    "请结合两轮讨论,点评其他参与者的观点,明确表态:\n"
                    "1. 你同意谁的观点?为什么?\n"
                    "2. 你反对谁的观点?为什么?\n"
                    "3. 你要补充或修改自己的观点吗?\n"
                    "用中文,控制在400字以内。"
                )
                r2_systems.append(
                    f"你是圆桌会议参与者,你的名字是{p['label']}。"
                    "现在进入点评环节。请点评其他人的观点并表态,用中文。"
                    "重要:上面「你在本轮的发言」是你自己说的,不要把自己的观点当作别人的来点评。"
                )

            r2_results = []
            for label, model, text in self._parallel_call_stream_with_heartbeat(participants, r2_prompts, r2_systems):
                if label == "__heartbeat__":
                    yield "⏳ 等待模型点评中...\n\n"
                    continue
                r2_results.append((label, model, text))
                yield f"### {label}({model})\n\n{text}\n\n"

            r2_transcript = "\n\n".join(
                f"【{p['label']}({p['model']})】\n{text}"
                for p, (_, _, text) in zip(participants, r2_results)
            )

            full_transcript = (
                f"上轮讨论:\n{prev_transcript}\n\n"
                f"本轮第一轮:\n{r1_transcript}\n\n"
                f"本轮点评:\n{r2_transcript}"
            )

            yield f"## 主持人总结\n\n"
            MOD_PROMPT = (
                f"议题方向:{user_stripped or '继续深入讨论'}\n\n"
                f"完整讨论记录:\n{full_transcript}\n\n"
                "你是会议主持人,请归纳总结:\n"
                "1. 找出观点一致的阵营(>=2人观点趋同合并为一个方案)\n"
                "2. 坚持独立观点的人单独成方案\n"
                "3. 每个方案标注:支持者、核心观点、风险点、备选路径\n"
                "4. 至少给出2个方案,如果只有1个共识也要给出2条执行路径\n"
                "5. 末尾输出【纪要】标签,包含简明纪要供下次会议参考\n"
                "用中文。"
            )
            MOD_SYS = "你是圆桌会议主持人/参谋。你负责归纳多方观点,整理方案矩阵,不替用户做决定。用中文。"

            try:
                mod_text = self._call_model(moderator, MOD_PROMPT, MOD_SYS)
                yield mod_text
            except Exception as e:
                yield f"[主持人调用失败: {e}]"
            return

        # ===== 模式二/三:开新局 / 续议 =====
        is_resume = has_resume_tag

        topic_raw = user_msg
        if is_resume:
            # 剥离所有续议触发词,保持议题干净
            for marker in _RESUME_MARKERS + _RESUME_KEYWORDS:
                topic_raw = topic_raw.replace(marker, "")
            topic_raw = re.sub(r'^[\uff0c,\s\uff1a:]+|[\uff0c,\s\uff1a:]+$', '', topic_raw.strip())

        topic = topic_raw
        moderator_str = ""
        prev_minutes = ""

        # 提取主持人(多格式)
        mod_result = self._split_by_markers(topic, _MODERATOR_MARKERS)
        if mod_result:
            topic = mod_result[0]
            rest = mod_result[1]
            # 检查是否有上次纪要标记
            min_result = self._split_by_markers(rest, _MINUTES_MARKERS)
            if min_result:
                moderator_str = min_result[0].strip()
                prev_minutes = min_result[1].strip()
            else:
                moderator_str = rest.strip()
        else:
            # 没有主持人标记,检查是否有上次纪要标记
            min_result = self._split_by_markers(topic, _MINUTES_MARKERS)
            if min_result:
                topic = min_result[0].strip()
                prev_minutes = min_result[1].strip()

        # 续议模式:从对话历史自动提取上次纪要
        if is_resume and not prev_minutes:
            prev = self._extract_prev_round(messages)
            if prev:
                prev_minutes = prev["minutes"] or prev["transcript"]

        # 提取参会模型(多格式)
        participants = []
        parse_errors = []
        models_result = self._split_by_markers(topic, _PARTICIPANT_MARKERS)
        if models_result:
            topic = models_result[0].strip()
            rest = models_result[1]
            # 从rest中去掉主持人和纪要标记后面的内容
            for markers in [_MODERATOR_MARKERS, _MINUTES_MARKERS]:
                split = self._split_by_markers(rest, markers)
                if split:
                    rest = split[0]
            for line in rest.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                p = self._parse_participant(line)
                if p:
                    participants.append(p)
                else:
                    # 区分错误类型
                    if ":" in line:
                        prefix = line.split(":")[0].strip()
                        parse_errors.append(f"❌ 未知前缀 `{prefix}` | 行: {line}\n")
                    else:
                        parse_errors.append(f"❌ 缺少前缀 | 行: {line} (需要 前缀:模型ID 格式)\n")
        else:
            yield (
                "请用以下格式发消息:\n\n"
                "你的议题\n"
                "【参会模型】\n"
                "BL:kimi-k2.6\n"
                "DS:deepseek-chat\n"
                "ZP:glm-4.5-air\n"
                "【主持人】BL:qwen-plus\n"
            )
            return

        if parse_errors:
            for e in parse_errors:
                yield e
            available = self._list_available_prefixes()
            yield f"\n当前已配置的通道: {', '.join(available)}\n"
            yield "模型写法: 前缀:模型ID (如 BL:kimi-k2.6)\n"
            yield "未配置的通道请在 Pipe 设置中填写前缀和API Key。\n"
            return

        topic = topic.strip()
        if not topic:
            yield "请输入议题。"
            return
        if not participants:
            yield "请至少指定一个参会模型。"
            return

        # 解析主持人
        moderator = None
        if moderator_str:
            moderator = self._parse_participant(moderator_str)
        if not moderator:
            moderator = participants[0]
            yield f"⚠️ 未指定主持人,默认使用 {moderator['label']}\n\n"

        # 验证 API Key 和 Base URL
        errors = []
        seen_channels = set()
        for p in participants:
            if p["channel"] in seen_channels:
                continue
            seen_channels.add(p["channel"])
            if not p["api_key"] or p["api_key"].strip() == "":
                errors.append(f"❌ {p['channel_name']} API Key 未配置\n")
            if not p["base_url"] or p["base_url"].strip() == "":
                errors.append(f"❌ {p['channel_name']} Base URL 未配置\n")
        if moderator["channel"] not in seen_channels:
            if not moderator["api_key"]:
                errors.append(f"❌ 主持人({moderator['channel_name']})API Key 未配置\n")
            if not moderator["base_url"]:
                errors.append(f"❌ 主持人({moderator['channel_name']})Base URL 未配置\n")
        if errors:
            for e in errors:
                yield e
            yield "\n请在 Pipe 设置中配置对应通道的 API Key 和 Base URL。\n"
            return

        # === 会议头 ===
        yield f"# 圆桌会议\n\n"
        yield f"**议题:** {topic}\n"
        yield f"**参与者:** {', '.join(p['label'] for p in participants)}\n"
        yield f"**主持人:** {moderator['model']}\n"
        if prev_minutes:
            yield f"**参考:** 上次会议纪要\n"
        yield f"---\n\n"

        R1_PROMPT = f"议题:{topic}\n\n请直接发表你的观点,简洁有力,不要重复议题。"
        if prev_minutes:
            R1_PROMPT = (
                f"议题:{topic}\n\n"
                f"上次纪要:\n{prev_minutes}\n\n"
                "请在上次讨论基础上发表你的观点。"
            )

        R1_SYS = [
            f"你是一场圆桌会议的参与者,你的名字是{p['label']}。请直接发表观点,用中文回答,控制在300字以内。"
            for p in participants
        ]

        # === 动态计算 max_tokens ===
        n = len(participants)
        r1_max_tokens = self.valves.MAX_TOKENS
        r2_max_tokens = min(1500 + (n - 1) * 500, 6000)
        mod_max_tokens = min(3000 + n * 800, 8000)

        # === 第一轮:流式输出 + 心跳 ===
        yield f"## 第一轮:各自观点\n\n"
        r1_results = []
        for label, model, text in self._parallel_call_stream_with_heartbeat(
            participants, R1_PROMPT, R1_SYS, max_tokens=r1_max_tokens
        ):
            if label == "__heartbeat__":
                yield "⏳ 等待模型响应中...\n\n"
                continue
            r1_results.append((label, model, text))
            yield f"### {label}({model})\n\n{text}\n\n"

        r1_transcript = "\n\n".join(
            f"【{p['label']}({p['model']})】\n{text}"
            for p, (_, _, text) in zip(participants, r1_results)
        )

        # === 第二轮:流式输出 + 心跳 ===
        yield f"## 第二轮:点评与表态\n\n"
        # 每个模型收到独立prompt,明确区分"你的发言"和"别人的发言"
        r2_prompts = []
        r2_systems = []
        for i, p in enumerate(participants):
            own_text = r1_results[i][2]
            others_text = "\n\n".join(
                f"【{participants[j]['label']}({participants[j]['model']})】\n{r1_results[j][2]}"
                for j in range(len(participants))
                if j != i
            )
            r2_prompts.append(
                f"议题:{topic}\n\n"
                f"你在第一轮的发言:\n{own_text}\n\n"
                f"其他参与者的发言:\n{others_text}\n\n"
                "请点评其他参与者的观点,明确表态:\n"
                "1. 你同意谁的观点?为什么?\n"
                "2. 你反对谁的观点?为什么?\n"
                "3. 你要补充或修改自己的观点吗?\n"
                f"用中文,控制在{300 + (n-1)*100}字以内。"
            )
            r2_systems.append(
                f"你是圆桌会议参与者,你的名字是{p['label']}。"
                "现在进入第二轮点评。请点评其他人的观点并表态,用中文。"
                "重要:上面「你在第一轮的发言」是你自己说的,不要把自己的观点当作别人的来点评。"
            )

        r2_results = []
        for label, model, text in self._parallel_call_stream_with_heartbeat(
            participants, r2_prompts, r2_systems, max_tokens=r2_max_tokens
        ):
            if label == "__heartbeat__":
                yield "⏳ 等待模型点评中...\n\n"
                continue
            r2_results.append((label, model, text))
            yield f"### {label}({model})\n\n{text}\n\n"

        r2_transcript = "\n\n".join(
            f"【{p['label']}({p['model']})】\n{text}"
            for p, (_, _, text) in zip(participants, r2_results)
        )

        full_transcript = f"第一轮:\n{r1_transcript}\n\n第二轮:\n{r2_transcript}"

        # === 主持人总结 ===
        yield f"## 主持人总结\n\n"
        MOD_PROMPT = (
            f"议题:{topic}\n\n"
            f"讨论记录:\n{full_transcript}\n\n"
            "你是会议主持人,请归纳总结:\n"
            "1. 找出观点一致的阵营(>=2人观点趋同合并为一个方案)\n"
            "2. 坚持独立观点的人单独成方案\n"
            "3. 每个方案标注:支持者、核心观点、风险点、备选路径\n"
            "4. 至少给出2个方案,如果只有1个共识也要给出2条执行路径\n"
            "5. 末尾输出【纪要】标签,包含简明纪要供下次会议参考\n"
            "用中文。\n\n"
            "重要:直接输出方案矩阵,不要输出思考过程、推理步骤、内心独白、"
            "对指令的分析。第一行就应该是「方案一」。"
        )
        MOD_SYS = (
            "你是圆桌会议主持人/参谋。你负责归纳多方观点,整理方案矩阵,"
            "不替用户做决定。用中文。"
            "直接输出结果,不要展示任何思考过程。"
        )

        try:
            mod_text = self._call_model(
                moderator,
                MOD_PROMPT,
                MOD_SYS,
                max_tokens=mod_max_tokens,
            )
            yield mod_text
        except Exception as e:
            yield f"[主持人调用失败: {e}]"
