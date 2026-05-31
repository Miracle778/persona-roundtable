from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from my_agent.core.agent import PersonaAgent
from my_agent.core.llm import LLMClient, MockLLMClient, as_error_message
from my_agent.core.matcher import select_agents
from my_agent.core.models import DiscussionRun, NormalizedInput, PersonaSkill, Utterance, now_iso
from my_agent.core.progress import ProgressCallback, noop_progress
from my_agent.core.recorder import build_run_id


class DiscussionEngine:
    def __init__(self, skills: list[PersonaSkill], llm: LLMClient, output_root: Path):
        self.skills = skills
        self.llm = llm
        self.output_root = output_root

    def run(
        self,
        question: NormalizedInput,
        rounds: int = 2,
        agent_ids: list[str] | None = None,
        max_agents: int = 4,
        progress: ProgressCallback = noop_progress,
        parallel: bool = True,
        max_concurrency: int | None = None,
    ) -> DiscussionRun:
        progress("[4/8] 正在匹配讨论人物...")
        detected_categories, selections = select_agents(
            question.content,
            self.skills,
            agent_ids=agent_ids,
            max_agents=max_agents,
        )
        progress(
            "[5/8] 匹配到人物："
            + "、".join(selection.skill.display_name for selection in selections)
        )
        agents = [PersonaAgent(selection.skill, self.llm) for selection in selections]
        utterances: list[Utterance] = []
        round_summaries: list[str] = []
        for round_index in range(1, rounds + 1):
            round_context = "\n\n".join(round_summaries)
            if parallel and len(agents) > 1:
                worker_count = max(1, min(max_concurrency or len(agents), len(agents)))
                progress(
                    f"[6/8] 第 {round_index} 轮：{len(agents)} 位人物并发发言中 "
                    f"(并发 {worker_count})..."
                )
                round_utterances = speak_round_parallel(
                    agents=agents,
                    question=question,
                    transcript=utterances,
                    round_index=round_index,
                    round_context=round_context,
                    max_workers=worker_count,
                    progress=progress,
                )
                utterances.extend(round_utterances)
            else:
                for agent in agents:
                    progress(f"[6/8] 第 {round_index} 轮：{agent.skill.display_name} 发言中...")
                    utterances.append(agent.speak(question, utterances, round_index, round_context))

            if round_index < rounds:
                progress(f"[6/8] 第 {round_index} 轮临时总结中...")
                round_summaries.append(
                    synthesize_round_summary(
                        question=question,
                        utterances=[item for item in utterances if item.round_index == round_index],
                        previous_summaries=round_summaries,
                        llm=self.llm,
                    )
                )

        progress("[7/8] 主持人总结中...")
        summary = synthesize_summary(
            question=question,
            utterances=utterances,
            categories=detected_categories,
            llm=self.llm,
            round_summaries=round_summaries,
        )
        run_id = build_run_id()
        output_dir = self.output_root / run_id
        return DiscussionRun(
            run_id=run_id,
            created_at=now_iso(),
            input=question,
            detected_categories=detected_categories,
            selected_agents=selections,
            utterances=utterances,
            summary=summary,
            output_dir=output_dir,
        )


def speak_round_parallel(
    agents: list[PersonaAgent],
    question: NormalizedInput,
    transcript: list[Utterance],
    round_index: int,
    round_context: str,
    max_workers: int,
    progress: ProgressCallback,
) -> list[Utterance]:
    transcript_snapshot = list(transcript)
    results: dict[str, Utterance] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_agent = {
            executor.submit(
                agent.speak,
                question,
                transcript_snapshot,
                round_index,
                round_context,
            ): agent
            for agent in agents
        }
        for future in as_completed(future_to_agent):
            agent = future_to_agent[future]
            results[agent.skill.id] = future.result()
            progress(f"[6/8] 第 {round_index} 轮：{agent.skill.display_name} 已完成。")
    return [results[agent.skill.id] for agent in agents]


def synthesize_summary(
    question: NormalizedInput,
    utterances: list[Utterance],
    categories: list[str],
    llm: LLMClient,
    round_summaries: list[str] | None = None,
) -> str:
    if isinstance(llm, MockLLMClient):
        return synthesize_rule_summary(question, utterances, categories)

    prompt = build_moderator_prompt(question, utterances, categories, round_summaries or [])
    try:
        return llm.complete(prompt).strip()
    except Exception as exc:
        fallback = synthesize_rule_summary(question, utterances, categories)
        return f"LLM 主持总结失败，已使用规则兜底。错误：{as_error_message(exc)}\n\n{fallback}"


def build_moderator_prompt(
    question: NormalizedInput,
    utterances: list[Utterance],
    categories: list[str],
    round_summaries: list[str] | None = None,
) -> str:
    transcript = "\n\n".join(
        f"[第{item.round_index}轮][{item.agent_name}]\n{item.content}"
        for item in utterances
    )
    participant_names = "、".join(dict.fromkeys(item.agent_name for item in utterances))
    round_summary_text = "\n\n".join(round_summaries or []) or "无。"
    return f"""
你是一个多人物讨论系统的中立主持人。请只基于公开讨论记录做总结，不新增事实，不伪装成任何人物，不替用户做高风险决定。

原始问题：
{question.content}

识别分类：
{"、".join(categories)}

参与人物：
{participant_names}

公开讨论记录：
{transcript}

每轮临时总结：
{round_summary_text}

请输出中文主持总结，300-600字，必须包含以下三个小标题：
1. 共识
2. 分歧
3. 行动建议

要求：
- 总结每个视角真正说了什么，不要机械罗列。
- 保留关键分歧和风险提醒。
- 行动建议要具体、低成本、可验证。
- 只输出总结正文，不要输出解释性前言。
""".strip()


def synthesize_round_summary(
    question: NormalizedInput,
    utterances: list[Utterance],
    previous_summaries: list[str],
    llm: LLMClient,
) -> str:
    if isinstance(llm, MockLLMClient):
        points = "\n".join(
            f"- {item.agent_name}：核心观点是「{compact_sentence(item.content, max_chars=90)}」；下一轮可被点名回应。"
            for item in utterances
        )
        return (
            f"第 {utterances[0].round_index if utterances else 0} 轮战场摘要：\n"
            f"本轮主要分歧已经出现。下一轮不要泛泛说“大家”，请围绕以下人物逐一点名接话：\n{points}"
        )

    transcript = "\n\n".join(
        f"[{item.agent_name}]\n{item.content}"
        for item in utterances
    )
    previous_text = "\n\n".join(previous_summaries) or "无。"
    prompt = f"""
你是多人物讨论的临时主持人。请把本轮公开发言压缩成下一轮可参考的“战场摘要 + 点名接话索引”。

原始问题：
{question.content}

此前轮次摘要：
{previous_text}

本轮发言：
{transcript}

请输出中文，180-320字，必须包含：
1. 本轮战场：一句话概括本轮真正争的是什么。
2. 点名接话索引：逐个列出每位人物的核心观点，以及下一轮最值得被其他人回应/反驳/补充的一点。
3. 下一轮追问：给出1-2个具体追问，必须能引导人物互相点名接话。

要求：
- 不要只写“大家认为”“前面几位认为”。
- 要保留人物名，例如“峰哥把问题落到生存成本，童锦程可以回应其关系判断是否过度现实”。
- 只输出摘要正文，不要新增事实，不要伪装成任何人物。
""".strip()
    try:
        return llm.complete(prompt).strip()
    except Exception as exc:
        points = "；".join(
            f"{item.agent_name}：{compact_sentence(item.content, max_chars=90)}"
            for item in utterances
        )
        return f"LLM 临时总结失败，使用规则摘要。错误：{as_error_message(exc)}\n{points}"


def synthesize_rule_summary(
    question: NormalizedInput,
    utterances: list[Utterance],
    categories: list[str],
) -> str:
    names = "、".join(dict.fromkeys(item.agent_name for item in utterances))
    category_text = "、".join(categories)
    key_points = "\n".join(
        f"- {item.agent_name}：{compact_sentence(item.content)}"
        for item in utterances
    )
    return (
        f"1. 共识\n"
        f"本次问题「{question.content}」被归入「{category_text}」。参与讨论的人物视角包括：{names}。"
        f"各方共同指向的是：先把事实、情绪和真实约束分开，再判断主要矛盾，不要用单一情绪替代决策。\n\n"
        f"2. 分歧\n"
        f"不同视角的侧重点如下：\n{key_points}\n\n"
        f"3. 行动建议\n"
        f"先做一次低成本复盘：写下争执发生的场景、各自真正担心的损失、可以接受和不能接受的边界。"
        f"再设计一个一周内可验证的小行动，用结果判断是否继续投入，而不是在抽象争论里反复消耗。"
    )


def compact_sentence(content: str, max_chars: int = 220) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_chars:
        return normalized
    cut = normalized[:max_chars]
    punctuation_positions = [cut.rfind(mark) for mark in ["。", "！", "？", ".", "!", "?"]]
    best = max(punctuation_positions)
    if best >= 80:
        return cut[: best + 1]
    return cut.rstrip("，,；;：:、") + "..."
