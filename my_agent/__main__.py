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
from my_agent.core.progress import noop_progress, stderr_progress
from my_agent.core.recorder import DiscussionRecorder
from my_agent.core.skill_loader import load_skills
from my_agent.input_sources.media_crawler import MediaCrawlerError, extract_social_url
from my_agent.input_sources.resolver import normalize_user_input


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_SKILL_DIRS = [PACKAGE_ROOT / "demo_skills", PACKAGE_ROOT / "skills"]
DEFAULT_RUN_DIR = PACKAGE_ROOT / "runs"
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
    extract_url = subparsers.add_parser("extract-url", help="Extract social-media URL content without running agents.")
    extract_url.add_argument("url", help="Zhihu or Weibo URL to extract.")
    extract_url.add_argument("--quiet", action="store_true", help="Do not print progress messages.")

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
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        print_extracted_input(extracted)
        return

    progress = noop_progress
    if args.command == "ask":
        progress = noop_progress if args.quiet else stderr_progress
        progress("[1/8] 正在加载 skills...")
    skills = load_skills(DEFAULT_SKILL_DIRS)
    if args.command == "list-skills":
        list_skills(skills)
        return
    if args.command == "list-categories":
        list_categories(skills)
        return
    if args.command == "ask":
        raw_question = " ".join(args.question).strip()
        if not raw_question:
            raw_question = input("请输入问题或链接：").strip()
        try:
            question = normalize_user_input(raw_question, progress=progress)
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
            )
        except Exception as exc:
            print(as_error_message(exc), file=sys.stderr)
            raise SystemExit(1)
        progress("[8/8] 正在保存 JSON / HTML...")
        json_path, html_path = DiscussionRecorder().save(run)
        progress("[8/8] 讨论完成。")
        print(f"讨论完成：{run.run_id}")
        print(f"识别分类：{'、'.join(run.detected_categories)}")
        print("参与人物：" + "、".join(selection.skill.display_name for selection in run.selected_agents))
        print(f"JSON: {json_path}")
        print(f"HTML: {html_path}")


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


def print_extracted_input(extracted) -> None:
    print(f"平台：{extracted.platform}")
    print(f"标题：{extracted.title or '未提取到标题'}")
    print(f"作者：{extracted.author or '未提取到作者'}")
    print(f"链接：{extracted.source_url}")
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
