from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


InputType = Literal["text", "url", "event_markdown"]


@dataclass(frozen=True)
class BackgroundContext:
    mode: str
    triggered: bool
    reason: str
    query: str
    summary: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class NormalizedInput:
    type: InputType
    raw_input: str
    content: str
    title: str | None = None
    source_url: str | None = None
    platform: str | None = None
    author: str | None = None
    comments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    background: BackgroundContext | None = None


@dataclass(frozen=True)
class PersonaSkill:
    id: str
    name: str
    display_name: str
    description: str
    source_path: Path
    raw_content: str
    categories: list[str] = field(default_factory=list)
    suitable_for: list[str] = field(default_factory=list)
    not_suitable_for: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    role_rules: str = ""
    voice_style: dict[str, Any] = field(default_factory=dict)
    visual_style: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSelection:
    skill: PersonaSkill
    score: int
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Utterance:
    round_index: int
    agent_id: str
    agent_name: str
    categories: list[str]
    content: str
    created_at: str
    reply_to: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscussionRun:
    run_id: str
    created_at: str
    input: NormalizedInput
    detected_categories: list[str]
    selected_agents: list[AgentSelection]
    utterances: list[Utterance]
    summary: str
    output_dir: Path
    style: str = "analysis"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        for item in data["selected_agents"]:
            item["skill"]["source_path"] = str(item["skill"]["source_path"])
        return data


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
