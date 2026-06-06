from __future__ import annotations

import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VoiceRenderResult:
    manifest_path: Path
    audio_dir: Path
    segment_count: int


@dataclass(frozen=True)
class PublishPackageResult:
    package_dir: Path
    files: list[Path]


def render_mock_voice(run_dir: Path) -> VoiceRenderResult:
    script = load_script(run_dir)
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    segments: list[dict[str, Any]] = []
    for index, scene in enumerate(script.get("scenes", []), start=1):
        duration = max(1, min(10, int(scene.get("duration_hint") or 4)))
        path = audio_dir / f"{index:03d}-{safe_name(scene.get('speaker') or 'speaker')}.wav"
        write_silence_wav(path, duration_seconds=duration)
        segments.append(
            {
                "scene_index": index,
                "type": scene.get("type"),
                "speaker": scene.get("speaker"),
                "text": scene.get("text"),
                "duration_hint": duration,
                "audio_path": str(path),
                "provider": "mock_silence",
            }
        )
    manifest = {
        "run_id": script.get("run_id"),
        "provider": "mock_silence",
        "segments": segments,
    }
    manifest_path = run_dir / "voice_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return VoiceRenderResult(manifest_path=manifest_path, audio_dir=audio_dir, segment_count=len(segments))


def build_publish_package(run_dir: Path, platform: str = "douyin") -> PublishPackageResult:
    script = load_script(run_dir)
    package_dir = run_dir / "publish_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    title = build_title(script)
    description = build_description(script)
    captions = build_srt(script)
    metadata = {
        "run_id": script.get("run_id"),
        "platform": platform,
        "title": title,
        "description": description,
        "tags": infer_tags(script),
        "source_url": script.get("source_url"),
        "video_ratio": "9:16",
        "status": "draft",
        "note": "第一版发布包只生成素材草稿；正式 mp4 生成和自动发布留给后续 provider。",
    }
    files = [
        package_dir / "publish_metadata.json",
        package_dir / "captions.srt",
        package_dir / "storyboard.md",
    ]
    files[0].write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    files[1].write_text(captions, encoding="utf-8")
    files[2].write_text(build_storyboard(script, metadata), encoding="utf-8")
    return PublishPackageResult(package_dir=package_dir, files=files)


def analyze_work_data(metrics_path: Path, output_path: Path | None = None) -> Path:
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    plays = safe_number(data.get("plays"))
    likes = safe_number(data.get("likes"))
    comments = safe_number(data.get("comments"))
    shares = safe_number(data.get("shares"))
    completions = safe_number(data.get("completions"))
    completion_rate = completions / plays if plays else 0
    like_rate = likes / plays if plays else 0
    comment_rate = comments / plays if plays else 0
    share_rate = shares / plays if plays else 0
    lines = [
        "# 作品数据复盘",
        "",
        f"- 平台：{data.get('platform') or '未知'}",
        f"- 作品：{data.get('title') or data.get('work_id') or '未命名'}",
        f"- 播放量：{plays:.0f}",
        f"- 完播率：{completion_rate:.2%}",
        f"- 点赞率：{like_rate:.2%}",
        f"- 评论率：{comment_rate:.2%}",
        f"- 转发率：{share_rate:.2%}",
        "",
        "## 初步判断",
        "",
        f"- {judge_metric('完播', completion_rate, 0.35, 0.55)}",
        f"- {judge_metric('点赞', like_rate, 0.02, 0.06)}",
        f"- {judge_metric('评论', comment_rate, 0.005, 0.02)}",
        "",
        "## 下一步建议",
        "",
        "- 如果完播偏低，优先缩短开场，把事件钩子放到前 3 秒。",
        "- 如果评论率高但点赞率低，说明争议足够，可以强化角色冲突但要收束观点。",
        "- 如果转发率低，补一个更清晰的结论卡片或可复用金句。",
    ]
    output = output_path or metrics_path.with_name("analysis_report.md")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def load_script(run_dir: Path) -> dict[str, Any]:
    script_path = run_dir / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"找不到 script.json：{script_path}")
    return json.loads(script_path.read_text(encoding="utf-8"))


def write_silence_wav(path: Path, duration_seconds: int, sample_rate: int = 8000) -> None:
    frame_count = duration_seconds * sample_rate
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def build_title(script: dict[str, Any]) -> str:
    title = str(script.get("title") or "多人物圆桌讨论").strip()
    if len(title) > 42:
        title = title[:41] + "..."
    return title


def build_description(script: dict[str, Any]) -> str:
    agents = "、".join(script.get("agents") or [])
    return f"本期由 {agents} 一起讨论：{script.get('title') or '一个值得拆开看的问题'}。"


def infer_tags(script: dict[str, Any]) -> list[str]:
    tags = ["多人物圆桌", "AI讨论"]
    tags.extend(str(item) for item in script.get("detected_categories") or [])
    if script.get("style") == "show":
        tags.append("节目化对话")
    return list(dict.fromkeys(tags))[:8]


def build_srt(script: dict[str, Any]) -> str:
    cursor = 0
    blocks: list[str] = []
    for index, scene in enumerate(script.get("scenes", []), start=1):
        duration = max(2, int(scene.get("duration_hint") or 4))
        start = cursor
        end = cursor + duration
        cursor = end
        text = f"{scene.get('speaker', '说话人')}：{scene.get('text', '')}"
        blocks.append(f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
    return "\n".join(blocks)


def build_storyboard(script: dict[str, Any], metadata: dict[str, Any]) -> str:
    lines = [
        f"# {metadata['title']}",
        "",
        f"- 平台：{metadata['platform']}",
        f"- 画幅：{metadata['video_ratio']}",
        f"- 状态：{metadata['status']}",
        "",
        "## 镜头脚本",
        "",
    ]
    for index, scene in enumerate(script.get("scenes", []), start=1):
        lines.append(f"{index}. **{scene.get('speaker')}** ({scene.get('type')})")
        lines.append(f"   - 情绪：{scene.get('emotion')}")
        lines.append(f"   - 字幕：{scene.get('text')}")
    return "\n".join(lines) + "\n"


def format_srt_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")[:24] or "speaker"


def safe_number(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if math.isnan(number) or math.isinf(number):
        return 0
    return number


def judge_metric(name: str, value: float, low: float, high: float) -> str:
    if value >= high:
        return f"{name}表现较强，可以复用当前选题和开场结构。"
    if value >= low:
        return f"{name}表现中等，建议做 A/B 标题或缩短前半段。"
    return f"{name}表现偏弱，需要优化前 3 秒钩子和角色冲突密度。"
