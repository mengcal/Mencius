"""
世界杯团队赛 Pipe for Open WebUI (v1 框架)
多团队对抗式讨论——团队内讨论达成共识，团队间对抗辩论

作者: EVE (智谱 AgentMore 全栈开发)

⚠️ 这是一个框架，未经过充分测试。
   适合有充足 API 额度和算力的社区用户完善和运行。
   作者配置有限(8G显存/免费额度)，无法跑大规模团队赛。
   欢迎在 GitHub/Gitee 上提交 PR 完善。

GitHub: https://github.com/Mencius/mengcal
Gitee:  https://gitee.com/MengCal

赛制设计:
  第一阶段: 小组赛 — 每个团队内部多模型讨论，达成共识
  第二阶段: 对抗赛 — 各团队代表交叉辩论
  第三阶段: 决赛 — 最终方案对决
  主持人总结: 归纳所有团队的观点，划分阵营

通道配置:
  复用圆桌会议 v5.1 的 8 通道设计。
  每个通道4个字段: PREFIX(前缀)、NAME(显示名)、API_KEY、BASE_URL
  详见圆桌会议 v5.1 的文档。

团队定义(在消息中指定):

  议题
  【团队A】
  BL:qwen-plus
  ZP:glm-4.5-air
  【团队B】
  DS:deepseek-chat
  BL:kimi-k2.6
  【主持人】BL:qwen-plus

  也可以用其他格式:
  (团队A) [团队A] {团队A} 团队A: 等都能识别

设计思路:
  - 团队内讨论: 每个团队的模型先内部讨论，互相补充，形成团队共识
  - 团队间对抗: 每个团队选出代表(或所有成员)参与跨团队辩论
  - 主持人总结: 归纳所有团队观点，找出共识和分歧
  - 目标: 集思广益，通过竞争产生更优方案

与圆桌会议的区别:
  - 圆桌会议: 所有模型平等讨论，不分组
  - 团队赛: 模型分组，先组内讨论，再组间对抗
  - 圆桌会议适合 2-5 个模型快速讨论
  - 团队赛适合 6-16 个模型深度对抗

未实现/待完善(欢迎社区贡献):
  - 流式输出优化(当前非流式)
  - 团队代表选举机制
  - 多轮淘汰赛制
  - 评分系统
  - 并发调用优化
  - 错误重试机制
"""

import requests
import concurrent.futures
import re
import time
from pydantic import BaseModel, Field
from typing import Generator, List, Dict

TITLE = "世界杯团队赛"

# ============================================================
# 标记列表(与圆桌会议 v5.1 保持一致)
# ============================================================
_TEAM_MARKERS = [
    "【团队", "(团队", "[团队", "{团队",
]

_PARTICIPANT_MARKERS = [
    "【参会模型】", "(参会模型)", "[参会模型]", "{参会模型}",
    "【模型】", "(模型)", "[模型]", "{模型}",
]

_MODERATOR_MARKERS = [
    "【主持人】", "(主持人)", "[主持人]", "{主持人}",
    "【主持】", "(主持)", "[主持]",
    "主持人：", "主持人:", "主持：", "主持:",
]


class Pipe:
    class Valves(BaseModel):
        # ============================================================
        # 8个通道(与圆桌会议 v5.1 一致)
        # ============================================================
        CH1_PREFIX: str = Field(default="BL/百炼", description="通道1前缀")
        CH1_NAME: str = Field(default="百炼云", description="通道1显示名")
        CH1_API_KEY: str = Field(default=" ", description="通道1 API Key", json_schema_extra={"format": "password"})
        CH1_BASE_URL: str = Field(default="", description="通道1 Base URL")

        CH2_PREFIX: str = Field(default="TX/腾讯", description="通道2前缀")
        CH2_NAME: str = Field(default="腾讯云", description="通道2显示名")
        CH2_API_KEY: str = Field(default=" ", description="通道2 API Key", json_schema_extra={"format": "password"})
        CH2_BASE_URL: str = Field(default="", description="通道2 Base URL")

        CH3_PREFIX: str = Field(default="SS/书生", description="通道3前缀")
        CH3_NAME: str = Field(default="书生", description="通道3显示名")
        CH3_API_KEY: str = Field(default=" ", description="通道3 API Key", json_schema_extra={"format": "password"})
        CH3_BASE_URL: str = Field(default="", description="通道3 Base URL")

        CH4_PREFIX: str = Field(default="ZP/智谱", description="通道4前缀")
        CH4_NAME: str = Field(default="智谱", description="通道4显示名")
        CH4_API_KEY: str = Field(default=" ", description="通道4 API Key", json_schema_extra={"format": "password"})
        CH4_BASE_URL: str = Field(default="", description="通道4 Base URL")

        CH5_PREFIX: str = Field(default="DS/深度求索", description="通道5前缀")
        CH5_NAME: str = Field(default="DeepSeek", description="通道5显示名")
        CH5_API_KEY: str = Field(default=" ", description="通道5 API Key", json_schema_extra={"format": "password"})
        CH5_BASE_URL: str = Field(default="", description="通道5 Base URL")

        CH6_PREFIX: str = Field(default="", description="通道6前缀(空=未启用)")
        CH6_NAME: str = Field(default="通道6", description="通道6显示名")
        CH6_API_KEY: str = Field(default=" ", description="通道6 API Key", json_schema_extra={"format": "password"})
        CH6_BASE_URL: str = Field(default="", description="通道6 Base URL")

        CH7_PREFIX: str = Field(default="", description="通道7前缀(空=未启用)")
        CH7_NAME: str = Field(default="通道7", description="通道7显示名")
        CH7_API_KEY: str = Field(default=" ", description="通道7 API Key", json_schema_extra={"format": "password"})
        CH7_BASE_URL: str = Field(default="", description="通道7 Base URL")

        CH8_PREFIX: str = Field(default="", description="通道8前缀(空=未启用)")
        CH8_NAME: str = Field(default="通道8", description="通道8显示名")
        CH8_API_KEY: str = Field(default=" ", description="通道8 API Key", json_schema_extra={"format": "password"})
        CH8_BASE_URL: str = Field(default="", description="通道8 Base URL")

        # ============================================================
        # 赛制参数
        # ============================================================
        TEMPERATURE: float = Field(default=0.8, description="温度")
        MAX_TOKENS: int = Field(default=2000, description="每次发言最大token")
        MODERATOR_MAX_TOKENS: int = Field(default=4000, description="主持人总结最大token")
        TEAM_DISCUSSION_ROUNDS: int = Field(default=1, description="团队内讨论轮数")
        DEBATE_ROUNDS: int = Field(default=1, description="团队间对抗轮数")
        API_TIMEOUT: int = Field(default=180, description="API请求超时(秒)")
        HEARTBEAT_INTERVAL: int = Field(default=5, description="心跳间隔(秒)")

    def __init__(self):
        self.valves = self.Valves()

    # ============================================================
    # 通道解析(与圆桌会议 v5.1 一致)
    # ============================================================
    def _build_prefix_map(self):
        pm = {}
        for i in range(1, 9):
            prefix_str = getattr(self.valves, f"CH{i}_PREFIX", "").strip()
            if not prefix_str:
                continue
            parts = [p.strip() for p in prefix_str.split("/") if p.strip()]
            for p in parts:
                pm[p.lower()] = i
                pm[p] = i
        return pm

    def _get_channel_info(self, ch_num):
        v = self.valves
        return {
            "name": getattr(v, f"CH{ch_num}_NAME", f"通道{ch_num}"),
            "api_key": getattr(v, f"CH{ch_num}_API_KEY", "").strip(),
            "base_url": getattr(v, f"CH{ch_num}_BASE_URL", "").strip(),
        }

    def _resolve_provider(self, model_id):
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
            return None
        info = self._get_channel_info(ch)
        return {
            "base_url": info["base_url"],
            "api_key": info["api_key"],
            "actual_model": actual_model,
            "channel": ch,
            "channel_name": info["name"],
        }

    def _parse_participant(self, line):
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

    def _call_model(self, p, prompt, system_prompt="", max_tokens=None):
        if max_tokens is None:
            max_tokens = self.valves.MAX_TOKENS
        base_url = p["base_url"].strip()
        url = f"{base_url.rstrip('/')}/chat/completions"
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})
        headers = {"Content-Type": "application/json"}
        if p["api_key"]:
            headers["Authorization"] = f"Bearer {p['api_key'].strip()}"
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
        return resp.json()["choices"][0]["message"]["content"]

    def _parallel_call(self, participants, prompts, system_prompts, max_tokens=None):
        """并发调用多个模型。prompts 和 system_prompts 是列表(每个模型独立)。"""
        results = [None] * len(participants)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(participants)) as executor:
            futures = {}
            for i, p in enumerate(participants):
                s_prompt = system_prompts[i] if isinstance(system_prompts, list) else system_prompts
                futures[executor.submit(self._call_model, p, prompts[i], s_prompt, max_tokens)] = i
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = f"[调用失败: {e}]"
        return results

    # ============================================================
    # 团队解析
    # ============================================================
    def _parse_teams(self, text):
        """从用户消息中解析团队定义。

        格式:
          议题
          【团队A】
          BL:qwen-plus
          ZP:glm-4.5-air
          【团队B】
          DS:deepseek-chat
          BL:kimi-k2.6
          【主持人】BL:qwen-plus

        返回: (topic, teams, moderator_str)
          teams = [{"name": "团队A", "members": [participant, ...]}, ...]
        """
        lines = text.strip().split("\n")

        # 找主持人
        moderator_str = ""
        topic_lines = []
        team_lines = []
        current_team = None
        in_team = False

        for line in lines:
            line_stripped = line.strip()

            # 检查是否是主持人标记
            is_moderator = False
            for marker in _MODERATOR_MARKERS:
                if marker in line_stripped:
                    moderator_str = line_stripped.split(marker, 1)[1].strip()
                    is_moderator = True
                    break

            if is_moderator:
                continue

            # 检查是否是团队标记
            is_team = False
            for marker in _TEAM_MARKERS:
                if marker in line_stripped:
                    # 提取团队名(如"团队A")
                    after = line_stripped.split(marker, 1)[1]
                    # 去掉结束符号
                    team_name = after.rstrip("】)}]")
                    if not team_name:
                        team_name = after.strip()
                    current_team = {"name": team_name, "lines": []}
                    team_lines.append(current_team)
                    in_team = True
                    is_team = True
                    break

            if is_team:
                continue

            if in_team and current_team:
                current_team["lines"].append(line_stripped)
            else:
                topic_lines.append(line_stripped)

        topic = "\n".join(t for t in topic_lines if t).strip()

        # 解析团队成员
        teams = []
        for t in team_lines:
            members = []
            for line in t["lines"]:
                if not line:
                    continue
                p = self._parse_participant(line)
                if p:
                    members.append(p)
            if members:
                teams.append({"name": t["name"], "members": members})

        return topic, teams, moderator_str

    # ============================================================
    # 主流程
    # ============================================================
    def pipe(self, body: dict, __user__: dict) -> Generator[str, None, None]:
        messages = body.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        if not user_msg:
            yield "请输入议题和团队定义。"
            return

        # 解析团队
        topic, teams, moderator_str = self._parse_teams(user_msg)

        if not topic:
            yield "请输入议题。"
            return

        if not teams or len(teams) < 2:
            yield (
                "请至少定义2个团队。格式:\n\n"
                "议题\n"
                "【团队A】\n"
                "BL:qwen-plus\n"
                "ZP:glm-4.5-air\n"
                "【团队B】\n"
                "DS:deepseek-chat\n"
                "BL:kimi-k2.6\n"
                "【主持人】BL:qwen-plus\n"
            )
            return

        # 解析主持人
        moderator = None
        if moderator_str:
            moderator = self._parse_participant(moderator_str)
        if not moderator:
            # 默认用第一个团队的第一个成员
            moderator = teams[0]["members"][0]
            yield f"⚠️ 未指定主持人，默认使用 {moderator['label']}\n\n"

        # 统计
        total_models = sum(len(t["members"]) for t in teams)
        yield f"# 世界杯团队赛\n\n"
        yield f"**议题:** {topic}\n"
        yield f"**团队数:** {len(teams)}\n"
        yield f"**总模型数:** {total_models}\n"
        for t in teams:
            yield f"- {t['name']}: {', '.join(m['label'] for m in t['members'])}\n"
        yield f"**主持人:** {moderator['model']}\n"
        yield f"---\n\n"

        # ============================================================
        # 第一阶段:小组赛(团队内讨论)
        # ============================================================
        yield f"## 第一阶段:小组赛（团队内讨论）\n\n"

        team_consensuses = []
        for team in teams:
            yield f"### {team['name']} 内部讨论\n\n"
            members = team["members"]

            # 每个成员发表观点
            prompts = []
            systems = []
            for m in members:
                prompts.append(
                    f"议题:{topic}\n\n"
                    f"你是团队{team['name']}的成员。请发表你的观点，用中文，控制在300字以内。"
                )
                systems.append(
                    f"你是{team['name']}的成员({m['label']})。"
                    "请认真思考议题，发表独立观点。用中文。"
                )

            results = self._parallel_call(members, prompts, systems)

            for m, text in zip(members, results):
                yield f"**{m['label']}({m['model']})**\n\n{text}\n\n"

            # 团队共识(让第一个成员总结)
            discussion = "\n\n".join(
                f"【{m['label']}】\n{text}"
                for m, text in zip(members, results)
            )

            consensus_prompt = (
                f"议题:{topic}\n\n"
                f"你们团队({team['name']})的讨论记录:\n{discussion}\n\n"
                "请总结你们团队的共识观点，找出分歧点，形成团队立场。用中文，控制在400字以内。"
            )
            consensus_system = (
                f"你是{team['name']}的共识总结者。"
                "请归纳团队讨论，形成统一立场。用中文。"
            )

            try:
                consensus = self._call_model(members[0], consensus_prompt, consensus_system)
            except Exception as e:
                consensus = f"[共识总结失败: {e}]"

            yield f"**{team['name']} 共识:**\n{consensus}\n\n"
            yield "---\n\n"

            team_consensuses.append({
                "team": team,
                "discussion": discussion,
                "consensus": consensus,
            })

        # ============================================================
        # 第二阶段:对抗赛(团队间辩论)
        # ============================================================
        yield f"## 第二阶段:对抗赛（团队间辩论）\n\n"

        # 每个团队看到其他团队的共识，进行辩论
        debate_prompts = []
        debate_systems = []
        debate_participants = []

        for i, tc in enumerate(team_consensuses):
            team = tc["team"]
            others_text = "\n\n".join(
                f"【{team_consensuses[j]['team']['name']}】\n{team_consensuses[j]['consensus']}"
                for j in range(len(team_consensuses))
                if j != i
            )
            # 每个团队派第一个成员参加辩论
            rep = team["members"][0]
            debate_participants.append(rep)

            debate_prompts.append(
                f"议题:{topic}\n\n"
                f"你方({team['name']})的立场:\n{tc['consensus']}\n\n"
                f"其他团队的立场:\n{others_text}\n\n"
                "请为你的团队立场辩护，反驳其他团队的观点。用中文，控制在400字以内。"
            )
            debate_systems.append(
                f"你是{team['name']}的辩论代表({rep['label']})。"
                "请坚定地为你的团队立场辩护，同时客观回应其他团队的质疑。用中文。"
            )

        debate_results = self._parallel_call(debate_participants, debate_prompts, debate_systems)

        for rep, text in zip(debate_participants, debate_results):
            yield f"**{rep['label']}({rep['model']})**\n\n{text}\n\n"

        yield "---\n\n"

        # ============================================================
        # 第三阶段:主持人总结
        # ============================================================
        yield f"## 主持人总结\n\n"

        all_debate = "\n\n".join(
            f"【{debate_participants[i]['label']}({team_consensuses[i]['team']['name']})】\n{debate_results[i]}"
            for i in range(len(debate_participants))
        )

        all_consensuses = "\n\n".join(
            f"【{tc['team']['name']}】\n{tc['consensus']}"
            for tc in team_consensuses
        )

        MOD_PROMPT = (
            f"议题:{topic}\n\n"
            f"各团队共识:\n{all_consensuses}\n\n"
            f"对抗辩论记录:\n{all_debate}\n\n"
            "你是主持人，请归纳总结:\n"
            "1. 找出各团队的共识和分歧\n"
            "2. 哪个团队的方案更具可行性?\n"
            "3. 是否能融合各团队的优势形成更优方案?\n"
            "4. 末尾输出【纪要】标签\n"
            "用中文。"
        )
        MOD_SYS = (
            "你是世界杯团队赛的主持人/裁判。你负责归纳各团队观点，"
            "评判方案优劣，不偏袒任何团队。用中文。"
        )

        try:
            mod_text = self._call_model(
                moderator, MOD_PROMPT, MOD_SYS,
                max_tokens=self.valves.MODERATOR_MAX_TOKENS,
            )
            yield mod_text
        except Exception as e:
            yield f"[主持人调用失败: {e}]"


# ============================================================
# 框架说明(给社区贡献者)
# ============================================================
"""
待完善清单(欢迎PR):

1. 流式输出
   - 当前 _parallel_call 是非流式的，等所有模型完成才返回
   - 应该改成流式，每个模型完成就输出(参考圆桌会议 v5.1 的实现)

2. 团队代表选举
   - 当前默认用每个团队的第一个成员当辩论代表
   - 可以加一轮"团队内部投票选代表"的机制

3. 多轮淘汰赛
   - 当前只有一轮对抗
   - 可以支持多轮淘汰:小组赛→半决赛→决赛

4. 评分系统
   - 当前主持人主观评判
   - 可以加评分维度(创新性/可行性/风险控制等)

5. 错误重试
   - 当前模型调用失败直接显示错误
   - 可以加自动重试机制

6. 并发优化
   - 团队内讨论是串行的(一个团队完了才下一个)
   - 可以改成所有团队同时讨论

7. 历史记录
   - 当前不保留跨轮次历史
   - 可以加续赛功能(参考圆桌会议的续议机制)

作者备注:
  这个框架的核心思路是"竞争产生更优方案"——
  不是让所有模型在一起和稀泥，而是让不同团队形成独立立场，
  再通过对抗辩论暴露弱点，最终由主持人融合最优方案。

  大模型不应该是概率生成的万金油，而应该是有效信息的组织者。
  先搜索(团队内讨论)→再对抗(团队间辩论)→最后检验(主持人总结)，
  这个流程比单纯的概率生成更接近人类的智囊团决策模式。

  —— EVE (智谱 AgentMore 全栈开发) 2026-08-01
"""
