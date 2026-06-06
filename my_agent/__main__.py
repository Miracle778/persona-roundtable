from __future__ import annotations

import argparse
import sys
from pathlib import Path

from my_agent.core.discussion import DiscussionEngine
from my_agent.core.llm import (
    as_error_message,
    build_llm,
    load_dotenv_files,
    llm_models_from_environment_or_opencode,
    load_opencode_llm_config,
    render_env_exports_from_opencode,
)
from my_agent.core.matcher import select_agents
from my_agent.core.production import analyze_work_data, build_publish_package, render_mock_voice
from my_agent.core.progress import noop_progress, stderr_progress
from my_agent.core.recorder import DiscussionRecorder
from my_agent.core.skill_loader import load_skills
from my_agent.input_sources.event_markdown import (
    edit_discussion_event_markdown,
    load_discussion_event_markdown,
    save_discussion_event_markdown,
    with_event_markdown_path,
)
from my_agent.input_sources.media_crawler import MediaCrawlerError, extract_social_url
from my_agent.input_sources.resolver import normalize_user_input
from my_agent.web.server import run_server


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_SKILL_DIRS = [PACKAGE_ROOT / "demo_skills", PACKAGE_ROOT / "skills"]
DEFAULT_RUN_DIR = PACKAGE_ROOT / "runs"
DEFAULT_EVENT_DIR = PACKAGE_ROOT / "events"
DEFAULT_ENV_FILES = [Path.cwd() / ".env", PACKAGE_ROOT / ".env"]


def main() -> None:
    try:
        load_dotenv_files(DEFAULT_ENV_FILES)
    except Exception as exc:
        print(as_error_message(exc), file=sys.stderr)
        raise SystemExit(1)

    parser = argparse.ArgumentParser(description="Run a multi-persona discussion.")
    subparsers = parser.add_subparsers(dest="command")

    ask = subparsers.add_parser("ask", help="Start a discussion from text or a URL.")
    ask.add_argument("question", nargs="*", help="Question text or URL. If omitted, read from stdin.")
    ask.add_argument("--rounds", type=int, default=2, help="Discussion rounds. Default: 2.")
    ask.add_argument("--agents", nargs="*", help="Skill ids/names to force-select.")
    ask.add_argument("--max-agents", type=int, default=4, help="Maximum auto-selected agents.")
    ask.add_argument("--llm", choices=["mock", "openai"], default="mock", help="LLM backend. Default: mock.")
    ask.add_argument("--model", help="Override MY_AGENT_MODEL for this run.")
    ask.add_argument("--choose-model", action="store_true", help="Choose a model from MY_AGENT_AVAILABLE_MODELS.")
    ask.add_argument("--style", choices=["analysis", "show"], default="analysis", help="Discussion style. Default: analysis.")
    ask.add_argument("--web-search", choices=["auto", "on", "off"], default="auto", help="Background web search mode. Default: auto.")
    ask.add_argument("--serial", action="store_true", help="Generate agent utterances one by one instead of per-round parallel generation.")
    ask.add_argument("--max-concurrency", type=int, help="Maximum parallel LLM calls per round. Default: selected agent count.")
    ask.add_argument("--quiet", action="store_true", help="Do not print progress messages.")

    env_from_opencode = subparsers.add_parser(
        "llm-env-from-opencode",
        help="Print MY_AGENT_* exports from ~/.config/opencode/opencode.json.",
    )
    env_from_opencode.add_argument(
        "--path",
        type=Path,
        help="Path to opencode.json. Default: ~/.config/opencode/opencode.json.",
    )
    env_from_opencode.add_argument(
        "--show-secret",
        action="store_true",
        help="Print the real API key instead of ***.",
    )

    subparsers.add_parser("list-skills", help="List loaded persona skills.")
    subparsers.add_parser("list-categories", help="List categories inferred from loaded skills.")
    subparsers.add_parser("list-llm-models", help="List MY_AGENT_AVAILABLE_MODELS or opencode models.")
    recommend = subparsers.add_parser("recommend-agents", help="Recommend agents for a question and show reasons.")
    recommend.add_argument("question", nargs="*", help="Question text or event markdown path.")
    recommend.add_argument("--max-agents", type=int, default=4, help="Maximum recommended agents.")
    recommend.add_argument("--web-search", choices=["auto", "on", "off"], default="off", help="Background web search mode for recommendation. Default: off.")

    event = subparsers.add_parser("event", help="Create or preview discussion event markdown.")
    event_subparsers = event.add_subparsers(dest="event_command")
    event_create = event_subparsers.add_parser("create", help="Create a discussion event markdown from text or URL.")
    event_create.add_argument("input", nargs="*", help="Text, URL, or markdown path. If omitted, read from stdin.")
    event_create.add_argument("--event-dir", type=Path, default=DEFAULT_EVENT_DIR, help="Directory to save event markdown.")
    event_create.add_argument("--web-search", choices=["auto", "on", "off"], default="auto", help="Background web search mode. Default: auto.")
    event_create.add_argument("--quiet", action="store_true", help="Do not print progress messages.")
    event_preview = event_subparsers.add_parser("preview", help="Preview a discussion event markdown.")
    event_preview.add_argument("path", type=Path, help="Discussion event markdown path.")
    event_edit = event_subparsers.add_parser("edit", help="Edit discussion event metadata or task.")
    event_edit.add_argument("path", type=Path, help="Discussion event markdown path.")
    event_edit.add_argument("--set", dest="sets", action="append", default=[], help="Set frontmatter field, e.g. topic_angle=...")
    event_edit.add_argument("--task", help="Replace the discussion task section.")
    extract_url = subparsers.add_parser("extract-url", help="Extract social-media URL content without running agents.")
    extract_url.add_argument("url", help="Zhihu or Weibo URL to extract.")
    extract_url.add_argument("--event-dir", type=Path, default=DEFAULT_EVENT_DIR, help="Directory to save discussion event markdown.")
    extract_url.add_argument("--quiet", action="store_true", help="Do not print progress messages.")

    voice = subparsers.add_parser("voice", help="Render voice assets for a discussion run.")
    voice_subparsers = voice.add_subparsers(dest="voice_command")
    voice_render = voice_subparsers.add_parser("render", help="Render mock voice wav files from script.json.")
    voice_render.add_argument("run_dir", type=Path, help="Discussion run directory containing script.json.")

    video = subparsers.add_parser("video", help="Build video publishing assets.")
    video_subparsers = video.add_subparsers(dest="video_command")
    video_package = video_subparsers.add_parser("package", help="Build a draft publish package from script.json.")
    video_package.add_argument("run_dir", type=Path, help="Discussion run directory containing script.json.")
    video_package.add_argument("--platform", default="douyin", help="Target platform name. Default: douyin.")

    analyze = subparsers.add_parser("analyze-work", help="Analyze imported work metrics JSON.")
    analyze.add_argument("metrics_json", type=Path, help="Metrics JSON path.")
    analyze.add_argument("--output", type=Path, help="Output markdown report path.")
    web = subparsers.add_parser("web", help="Start the local web workspace.")
    web.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1.")
    web.add_argument("--port", type=int, default=3004, help="Port to bind. Default: 3004.")
    web.add_argument("--config-path", type=Path, help="Local provider config JSON path.")
    web.add_argument("--db-path", type=Path, help="Local SQLite database path.")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "llm-env-from-opencode":
        try:
            config = load_opencode_llm_config(args.path)
            print(render_env_exports_from_opencode(config, show_secret=args.show_secret))
            if not args.show_secret:
                print("# API key 已脱敏。需要真实 export 时加 --show-secret。", file=sys.stderr)
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        return
    if args.command == "list-llm-models":
        try:
            current_model, models, source = llm_models_from_environment_or_opencode()
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        list_llm_models(current_model, models, source)
        return
    if args.command == "extract-url":
        progress = noop_progress if args.quiet else stderr_progress
        try:
            extracted = extract_social_url(args.url, progress=progress)
            event_path = save_discussion_event_markdown(extracted, args.event_dir, progress=progress)
            extracted = with_event_markdown_path(extracted, event_path)
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        print_extracted_input(extracted, event_path=event_path)
        return
    if args.command == "voice":
        if args.voice_command == "render":
            try:
                result = render_mock_voice(args.run_dir)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
            print(f"语音清单：{result.manifest_path}")
            print(f"音频目录：{result.audio_dir}")
            print(f"音频片段：{result.segment_count}")
            return
        voice.print_help()
        return
    if args.command == "video":
        if args.video_command == "package":
            try:
                result = build_publish_package(args.run_dir, platform=args.platform)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
            print(f"发布素材包：{result.package_dir}")
            for path in result.files:
                print(f"- {path}")
            return
        video.print_help()
        return
    if args.command == "analyze-work":
        try:
            output = analyze_work_data(args.metrics_json, output_path=args.output)
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        print(f"数据复盘报告：{output}")
        return
    if args.command == "web":
        run_server(
            host=args.host,
            port=args.port,
            config_path=args.config_path,
            db_path=args.db_path,
        )
        return

    progress = noop_progress
    if args.command in {"ask", "recommend-agents"}:
        progress = noop_progress if getattr(args, "quiet", False) else stderr_progress
        progress("[1/8] 正在加载 skills...")
    skills = load_skills(DEFAULT_SKILL_DIRS)
    if args.command == "list-skills":
        list_skills(skills)
        return
    if args.command == "list-categories":
        list_categories(skills)
        return
    if args.command == "recommend-agents":
        raw_question = " ".join(args.question).strip()
        if not raw_question:
            raw_question = input("请输入问题或事件稿路径：").strip()
        try:
            question = normalize_user_input(raw_question, progress=progress, event_dir=None, web_search=args.web_search)
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        detected, selections = select_agents(question.content, skills, max_agents=max(1, args.max_agents))
        print_recommended_agents(detected, selections)
        return
    if args.command == "event":
        if args.event_command == "create":
            progress = noop_progress if args.quiet else stderr_progress
            raw_input = " ".join(args.input).strip()
            if not raw_input:
                raw_input = sys.stdin.read().strip()
            if not raw_input:
                print("缺少事件输入。", file=sys.stderr)
                raise SystemExit(1)
            try:
                normalized = normalize_user_input(raw_input, progress=progress, event_dir=None, web_search=args.web_search)
                event_path = save_discussion_event_markdown(normalized, args.event_dir, progress=progress)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
            print(f"事件稿：{event_path}")
            return
        if args.event_command == "preview":
            try:
                event_input = load_discussion_event_markdown(args.path)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
            print_event_preview(event_input)
            return
        if args.event_command == "edit":
            try:
                updates = parse_set_arguments(args.sets)
                path = edit_discussion_event_markdown(args.path, updates=updates, task=args.task)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
            print(f"已更新事件稿：{path}")
            return
        event.print_help()
        return
    if args.command == "ask":
        raw_question = " ".join(args.question).strip()
        if not raw_question:
            raw_question = input("请输入问题或链接：").strip()
        try:
            question = normalize_user_input(
                raw_question,
                progress=progress,
                event_dir=DEFAULT_EVENT_DIR,
                web_search=args.web_search,
            )
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        model = args.model
        if args.choose_model:
            try:
                model = choose_llm_model(default_model=model)
            except Exception as exc:
                print(as_error_message(exc), file=sys.stderr)
                raise SystemExit(1)
        try:
            llm = build_llm(args.llm, model_override=model)
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        engine = DiscussionEngine(skills=skills, llm=llm, output_root=DEFAULT_RUN_DIR)
        try:
            run = engine.run(
                question,
                rounds=max(1, args.rounds),
                agent_ids=args.agents,
                max_agents=max(1, args.max_agents),
                progress=progress,
                parallel=not args.serial,
                max_concurrency=max(1, args.max_concurrency) if args.max_concurrency else None,
                style=args.style,
            )
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        progress("[8/8] 正在保存 JSON / HTML...")
        json_path, html_path, script_path = DiscussionRecorder().save(run)
        progress("[8/8] 讨论完成。")
        print(f"讨论完成：{run.run_id}")
        print(f"识别分类：{'、'.join(run.detected_categories)}")
        print("参与人物：" + "、".join(selection.skill.display_name for selection in run.selected_agents))
        print(f"JSON: {json_path}")
        print(f"HTML: {html_path}")
        print(f"Script: {script_path}")


def list_skills(skills) -> None:
    if not skills:
        print("未发现 skill。")
        return
    for skill in skills:
        categories = "、".join(skill.categories) or "未分类"
        print(f"{skill.id}\t{skill.display_name}\t{categories}")


def list_categories(skills) -> None:
    categories = sorted({category for skill in skills for category in skill.categories})
    if not categories:
        print("未发现分类。")
        return
    for category in categories:
        owners = [skill.display_name for skill in skills if category in skill.categories]
        print(f"{category}: {'、'.join(owners)}")


def list_llm_models(current_model: str | None, models: list[str], source: str) -> None:
    if not models:
        print("未发现可选模型。请设置 MY_AGENT_AVAILABLE_MODELS，或运行 llm-env-from-opencode。")
        return
    print(f"模型来源：{source}")
    if current_model:
        print(f"默认模型：{current_model}")
    for model in models:
        prefix = "*" if model == current_model else " "
        print(f"{prefix} {model}")


def print_recommended_agents(detected_categories, selections) -> None:
    print("识别分类：" + "、".join(detected_categories))
    for index, selection in enumerate(selections, start=1):
        matched = "、".join(selection.matched_terms) or "默认入选"
        print(
            f"{index}. {selection.skill.display_name}\n"
            f"   id: {selection.skill.id}\n"
            f"   score: {selection.score}\n"
            f"   reason: 命中 {matched}\n"
            f"   categories: {'、'.join(selection.skill.categories) or '未分类'}"
        )


def print_event_preview(event_input) -> None:
    print(f"标题：{event_input.title or '未命名事件'}")
    print(f"平台：{event_input.platform or '未知'}")
    print(f"链接：{event_input.source_url or '无'}")
    print(f"作者：{event_input.author or '未知'}")
    print(f"评论数量：{len(event_input.comments)}")
    if event_input.metadata.get("topic_brief"):
        print("\n--- 选题判断 ---")
        print(event_input.metadata["topic_brief"])
    if event_input.metadata.get("background_markdown"):
        print("\n--- 背景补全 ---")
        print(event_input.metadata["background_markdown"][:1200])
    print("\n--- 讨论输入预览 ---")
    print(event_input.content[:1600])


def parse_set_arguments(items: list[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--set 需要 key=value 格式，当前值：{item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--set 的 key 不能为空：{item}")
        updates[key] = value.strip()
    return updates


def print_extracted_input(extracted, event_path: Path | None = None) -> None:
    print(f"平台：{extracted.platform}")
    print(f"标题：{extracted.title or '未提取到标题'}")
    print(f"作者：{extracted.author or '未提取到作者'}")
    print(f"链接：{extracted.source_url}")
    if event_path:
        print(f"事件稿：{event_path}")
    print(f"正文长度：{len(extracted.content)}")
    print(f"评论数量：{len(extracted.comments)}")
    print("\n--- 内容预览 ---")
    print(extracted.content[:1200])


def choose_llm_model(default_model: str | None = None) -> str:
    current_model, models, source = llm_models_from_environment_or_opencode()
    if default_model and default_model not in models:
        models.insert(0, default_model)
    if not models:
        raise RuntimeError("没有可选模型。请先设置 MY_AGENT_AVAILABLE_MODELS。")

    print(f"可选模型来源：{source}")
    for index, model in enumerate(models, start=1):
        marker = " 默认" if model == (default_model or current_model) else ""
        print(f"{index}. {model}{marker}")
    raw_choice = input("请选择模型编号，直接回车使用默认：").strip()
    if not raw_choice:
        return default_model or current_model or models[0]
    try:
        choice = int(raw_choice)
    except ValueError as exc:
        raise RuntimeError(f"模型编号必须是数字，当前输入：{raw_choice}") from exc
    if choice < 1 or choice > len(models):
        raise RuntimeError(f"模型编号超出范围：{choice}")
    return models[choice - 1]


if __name__ == "__main__":
    main()
