from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from my_agent.core.models import NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress


SUPPORTED_PLATFORMS = {"zhihu", "weibo"}
PLATFORM_TO_MEDIA_CRAWLER = {"zhihu": "zhihu", "weibo": "wb"}


class MediaCrawlerError(RuntimeError):
    """Raised when social-media extraction cannot produce usable content."""


@dataclass(frozen=True)
class CommentThread:
    author: str
    content: str
    likes: str | int | None = None
    published_at: str | None = None
    replies: list["CommentThread"] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedSocialContent:
    platform: str
    source_url: str
    title: str | None
    author: str | None
    body: str
    comments: list[str]
    comment_threads: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_normalized_input(self, raw_input: str) -> NormalizedInput:
        content = build_discussion_content(self)
        return NormalizedInput(
            type="url",
            raw_input=raw_input,
            content=content,
            title=self.title,
            source_url=self.source_url,
            platform=self.platform,
            author=self.author,
            comments=self.comments,
            metadata={
                **self.metadata,
                "comment_threads": self.comment_threads,
                "extracted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
        )


def extract_social_url(
    raw_url: str,
    progress: ProgressCallback = noop_progress,
) -> NormalizedInput:
    progress("[extract-url] 正在识别平台...")
    normalized_url = normalize_social_url(raw_url)
    platform = detect_platform(normalized_url)
    if platform not in SUPPORTED_PLATFORMS:
        raise MediaCrawlerError(
            f"暂不支持该平台的链接解析：{platform or raw_url}。第一版只支持知乎和微博。"
        )
    progress(f"[extract-url] 已识别平台：{platform}。")
    config = MediaCrawlerConfig.from_env()
    extracted = MediaCrawlerAdapter(config, progress=progress).extract(normalized_url, platform)
    progress(
        f"[extract-url] 结构化完成：正文 {len(extracted.body)} 字，评论 {len(extracted.comments)} 条。"
    )
    return extracted.to_normalized_input(raw_url)


def normalize_social_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if not parsed.scheme or not parsed.netloc:
        return raw_url.strip()
    host = parsed.netloc.lower()
    scheme = "https" if parsed.scheme == "http" else parsed.scheme
    if host == "zhihu.com":
        host = "www.zhihu.com"
    return urlunparse((scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))


def detect_platform(raw_url: str) -> str | None:
    host = urlparse(raw_url).netloc.lower()
    if "zhihu" in host:
        return "zhihu"
    if "weibo" in host:
        return "weibo"
    if "xiaohongshu" in host or "xhslink" in host:
        return "xiaohongshu"
    if "douyin" in host:
        return "douyin"
    return None


@dataclass(frozen=True)
class MediaCrawlerConfig:
    home: Path
    output_dir: Path
    uv_bin: str
    login_type: str
    comments_limit: int
    sub_comments_limit: int
    timeout: int
    cdp_port: int

    @classmethod
    def from_env(cls) -> "MediaCrawlerConfig":
        home_raw = os.environ.get("MEDIA_CRAWLER_HOME", "").strip()
        if not home_raw:
            raise MediaCrawlerError(
                "缺少 MEDIA_CRAWLER_HOME。请在 my_agent/.env 中配置本机 MediaCrawler 目录。"
            )
        home = Path(home_raw).expanduser()
        if not home.exists():
            raise MediaCrawlerError(f"MEDIA_CRAWLER_HOME 不存在：{home}")
        if not (home / "main.py").exists():
            raise MediaCrawlerError(f"MEDIA_CRAWLER_HOME 下找不到 main.py：{home}")

        output_raw = os.environ.get("MEDIA_CRAWLER_OUTPUT_DIR", "").strip()
        output_dir = Path(output_raw).expanduser() if output_raw else home / "data"
        return cls(
            home=home,
            output_dir=output_dir,
            uv_bin=os.environ.get("MEDIA_CRAWLER_UV_BIN", "uv"),
            login_type=os.environ.get("MEDIA_CRAWLER_LOGIN_TYPE", "qrcode"),
            comments_limit=read_int("MEDIA_CRAWLER_COMMENTS_LIMIT", 5),
            sub_comments_limit=read_int("MEDIA_CRAWLER_SUB_COMMENTS_LIMIT", 3),
            timeout=read_int("MEDIA_CRAWLER_TIMEOUT", 180),
            cdp_port=read_int("MEDIA_CRAWLER_CDP_PORT", 9222),
        )


class MediaCrawlerAdapter:
    def __init__(
        self,
        config: MediaCrawlerConfig,
        progress: ProgressCallback = noop_progress,
    ):
        self.config = config
        self.progress = progress

    def extract(self, raw_url: str, platform: str) -> ExtractedSocialContent:
        self.progress(f"[extract-url] 检查 Chrome CDP 端口 {self.config.cdp_port}...")
        ensure_cdp_browser_available(self.config.cdp_port)
        media_platform = PLATFORM_TO_MEDIA_CRAWLER[platform]
        specified_id = normalize_specified_id(raw_url, platform)
        started_at = datetime.now().timestamp()
        before_files = snapshot_jsonl_files(self.config.output_dir)
        self.progress("[extract-url] 调用 MediaCrawler 提取正文和评论...")
        command = [
            self.config.uv_bin,
            "run",
            "main.py",
            "--platform",
            media_platform,
            "--lt",
            self.config.login_type,
            "--type",
            "detail",
            "--specified_id",
            specified_id,
            "--get_comment",
            "true",
            "--get_sub_comment",
            "true" if self.config.sub_comments_limit > 0 else "false",
            "--save_data_option",
            "jsonl",
            "--save_data_path",
            str(self.config.output_dir),
            "--max_comments_count_singlenotes",
            str(self.config.comments_limit),
        ]
        env = {
            **os.environ,
            "ENABLE_CDP_MODE": "True",
            "CDP_CONNECT_EXISTING": "True",
            "CDP_DEBUG_PORT": str(self.config.cdp_port),
            "AUTO_CLOSE_BROWSER": "False",
        }
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.home,
                env=env,
                text=True,
                capture_output=True,
                timeout=self.config.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MediaCrawlerError(
                f"找不到 uv 命令：{self.config.uv_bin}。请安装 uv，或设置 MEDIA_CRAWLER_UV_BIN。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaCrawlerError(f"MediaCrawler 运行超时：超过 {self.config.timeout} 秒。") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            if platform == "zhihu":
                self.progress("[extract-url] MediaCrawler 失败，正在尝试 CDP 兜底提取...")
                return extract_zhihu_from_cdp_fallback(
                    raw_url=raw_url,
                    specified_id=specified_id,
                    config=self.config,
                    error=stderr[-1200:],
                    progress=self.progress,
                )
            raise MediaCrawlerError(
                f"MediaCrawler 运行失败，退出码 {completed.returncode}。输出：{stderr[-1200:]}"
            )

        new_files = find_changed_jsonl_files(self.config.output_dir, before_files, started_at)
        if not new_files:
            if platform == "zhihu":
                self.progress("[extract-url] MediaCrawler 未产出 JSONL，正在尝试 CDP 兜底提取...")
                return extract_zhihu_from_cdp_fallback(
                    raw_url=raw_url,
                    specified_id=specified_id,
                    config=self.config,
                    error="MediaCrawler 正常退出但没有产出 JSONL。",
                    progress=self.progress,
                )
            raise MediaCrawlerError(
                f"MediaCrawler 没有产出 JSONL。请确认保存格式为 jsonl、登录态有效、链接可访问。输出目录：{self.config.output_dir}"
            )
        records = read_jsonl_records(new_files)
        self.progress(
            f"[extract-url] MediaCrawler 产出 {len(new_files)} 个 JSONL，正在解析正文和评论..."
        )
        extracted = build_extracted_content(
            platform=platform,
            raw_url=raw_url,
            specified_id=specified_id,
            records=records,
            comments_limit=self.config.comments_limit,
            sub_comments_limit=self.config.sub_comments_limit,
            files=new_files,
        )
        self.progress(
            f"[extract-url] 已提取正文 {len(extracted.body)} 字，评论 {len(extracted.comments)} 条。"
        )
        return extracted


def normalize_specified_id(raw_url: str, platform: str) -> str:
    if platform == "zhihu":
        return raw_url
    if platform == "weibo":
        parsed = urlparse(raw_url)
        candidates = [
            re.search(r"/detail/(\d+)", parsed.path),
            re.search(r"/status/(\d+)", parsed.path),
            re.search(r"/(\d{6,})/?$", parsed.path),
        ]
        for match in candidates:
            if match:
                return match.group(1)
        raise MediaCrawlerError(f"无法从微博链接中提取微博 ID：{raw_url}")
    raise MediaCrawlerError(f"不支持的平台：{platform}")


def build_extracted_content(
    platform: str,
    raw_url: str,
    specified_id: str,
    records: list[dict[str, Any]],
    comments_limit: int,
    sub_comments_limit: int,
    files: list[Path],
) -> ExtractedSocialContent:
    content_records = [record for record in records if is_content_record(record)]
    comment_records = [record for record in records if is_comment_record(record)]
    target_content = choose_content_record(content_records, raw_url, specified_id)
    if not target_content:
        raise MediaCrawlerError("MediaCrawler 产出了 JSONL，但没有找到正文内容记录。")

    body = first_text(
        target_content,
        ["content_text", "content", "desc", "text", "title"],
    )
    if not body:
        raise MediaCrawlerError("正文为空，可能是登录失败、反爬页面或该链接不可访问。")

    title = first_text(target_content, ["title"]) or default_title(platform, body)
    author = first_text(target_content, ["user_nickname", "nickname", "author", "screen_name"])
    source_url = first_text(target_content, ["content_url", "note_url", "url"]) or raw_url
    content_id = first_text(target_content, ["content_id", "note_id", "id"]) or specified_id
    threads = build_comment_threads(comment_records, content_id, comments_limit, sub_comments_limit)
    comments = [format_comment_thread(thread) for thread in threads]

    return ExtractedSocialContent(
        platform=platform,
        source_url=source_url,
        title=title,
        author=author,
        body=body,
        comments=comments,
        comment_threads=[comment_thread_to_dict(thread) for thread in threads],
        metadata={
            "content_id": content_id,
            "specified_id": specified_id,
            "media_crawler_files": [str(path) for path in files],
            "comments_count": len(comments),
            "records_count": len(records),
        },
    )


def is_content_record(record: dict[str, Any]) -> bool:
    return bool(
        record.get("content_id")
        or record.get("note_id")
        or record.get("content_url")
        or record.get("note_url")
    ) and not is_comment_record(record)


def is_comment_record(record: dict[str, Any]) -> bool:
    return bool(record.get("comment_id") or record.get("parent_comment_id"))


def choose_content_record(
    records: list[dict[str, Any]],
    raw_url: str,
    specified_id: str,
) -> dict[str, Any] | None:
    if not records:
        return None
    for record in records:
        values = [str(value) for value in record.values() if isinstance(value, (str, int))]
        if any(specified_id and specified_id in value for value in values):
            return record
        if any(raw_url and raw_url in value for value in values):
            return record
    return records[-1]


def build_comment_threads(
    comments: list[dict[str, Any]],
    content_id: str,
    comments_limit: int,
    sub_comments_limit: int,
) -> list[CommentThread]:
    related = [
        item for item in comments
        if not content_id or str(item.get("content_id") or item.get("note_id") or "") in {"", str(content_id)}
    ]
    by_id = {str(item.get("comment_id")): item for item in related if item.get("comment_id")}
    children: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    for item in related:
        parent_id = str(item.get("parent_comment_id") or "")
        if parent_id and parent_id not in {"0", str(item.get("comment_id") or "")} and parent_id in by_id:
            children.setdefault(parent_id, []).append(item)
        else:
            roots.append(item)

    threads: list[CommentThread] = []
    for root in roots[:comments_limit]:
        root_id = str(root.get("comment_id") or "")
        replies = [
            record_to_comment_thread(child, [])
            for child in children.get(root_id, [])[:sub_comments_limit]
        ]
        threads.append(record_to_comment_thread(root, replies))
    return threads


def record_to_comment_thread(record: dict[str, Any], replies: list[CommentThread]) -> CommentThread:
    return CommentThread(
        author=first_text(record, ["user_nickname", "nickname", "author", "screen_name"]) or "匿名用户",
        content=first_text(record, ["content", "comment_text", "text"]) or "",
        likes=record.get("like_count") or record.get("comment_like_count"),
        published_at=first_text(record, ["create_date_time", "publish_time", "created_time"]),
        replies=replies,
    )


def build_discussion_content(extracted: ExtractedSocialContent) -> str:
    comments_text = "\n".join(
        f"{index}. {comment}"
        for index, comment in enumerate(extracted.comments, start=1)
    ) or "未提取到可见评论。"
    return f"""【内容来源】
平台：{extracted.platform}
链接：{extracted.source_url}
标题：{extracted.title or "未提取到标题"}
作者：{extracted.author or "未提取到作者"}
提取时间：{datetime.now().astimezone().isoformat(timespec="seconds")}

【正文】
{extracted.body}

【可见评论】
{comments_text}

【讨论任务】
请围绕以上社交媒体内容进行多人物视角讨论：
- 判断这条内容的核心问题是什么。
- 分析作者和评论区体现出的情绪、动机、主要矛盾和分歧。
- 区分事实、立场、猜测和价值判断。
- 给出不同人物视角下的理解、风险提醒和可行动建议。"""


def format_comment_thread(thread: CommentThread) -> str:
    text = f"{thread.author}：{thread.content}"
    if thread.replies:
        replies = "\n".join(f"  - {reply.author} 回复：{reply.content}" for reply in thread.replies)
        text = f"{text}\n  回复：\n{replies}"
    return text


def comment_thread_to_dict(thread: CommentThread) -> dict[str, Any]:
    return {
        "author": thread.author,
        "content": thread.content,
        "likes": thread.likes,
        "published_at": thread.published_at,
        "replies": [comment_thread_to_dict(reply) for reply in thread.replies],
    }


def snapshot_jsonl_files(output_dir: Path) -> dict[Path, float]:
    if not output_dir.exists():
        return {}
    return {path: path.stat().st_mtime for path in output_dir.rglob("*.jsonl")}


def find_changed_jsonl_files(output_dir: Path, before: dict[Path, float], started_at: float) -> list[Path]:
    if not output_dir.exists():
        return []
    result = []
    for path in output_dir.rglob("*.jsonl"):
        mtime = path.stat().st_mtime
        if path not in before or mtime > before[path] or mtime >= started_at:
            result.append(path)
    return sorted(result, key=lambda item: item.stat().st_mtime)


def read_jsonl_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def first_text(record: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def default_title(platform: str, body: str) -> str:
    prefix = "知乎内容" if platform == "zhihu" else "微博内容"
    return f"{prefix}：{body[:30]}"


def read_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise MediaCrawlerError(f"{name} 必须是整数，当前值：{value}") from exc


def extract_zhihu_from_cdp_fallback(
    raw_url: str,
    specified_id: str,
    config: MediaCrawlerConfig,
    error: str,
    progress: ProgressCallback = noop_progress,
) -> ExtractedSocialContent:
    script = r'''
import asyncio
import json
import re
import sys
from urllib.parse import urlparse
import urllib.request
import websockets

target = sys.argv[1]
port = sys.argv[2]
target_path = urlparse(target).path.rstrip("/")
target_answer = ""
answer_match = re.search(r"/answer/(\d+)", target_path)
if answer_match:
    target_answer = answer_match.group(1)


class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.seq = 0
        self.ws = None

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=20 * 1024 * 1024)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.ws.close()

    async def call(self, method, params=None):
        self.seq += 1
        message_id = self.seq
        await self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method} failed: {message['error']}")
                return message.get("result", {})


def cdp_http(path):
    return urllib.request.urlopen(f"http://127.0.0.1:{port}/{path}", timeout=3).read().decode()


def is_target_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return target in url or url in target or path == target_path or (target_answer and target_answer in url)


async def create_target_in_browser():
    version = json.loads(cdp_http("json/version"))
    async with CDPClient(version["webSocketDebuggerUrl"]) as browser_cdp:
        await browser_cdp.call("Target.createTarget", {"url": target})
    await asyncio.sleep(1)


async def get_target_ws_url():
    tabs = json.loads(cdp_http("json/list"))
    for tab in tabs:
        url = tab.get("url", "")
        if is_target_url(url):
            return tab["webSocketDebuggerUrl"]
    await create_target_in_browser()
    tabs = json.loads(cdp_http("json/list"))
    for tab in tabs:
        url = tab.get("url", "")
        if is_target_url(url):
            return tab["webSocketDebuggerUrl"]
    raise RuntimeError("target page not found after Target.createTarget")

async def main():
    async with CDPClient(await get_target_ws_url()) as cdp:
        await cdp.call("Runtime.enable")
        await cdp.call("Page.enable")
        await asyncio.sleep(1)
        click_expr = """(() => {
          const buttons = Array.from(document.querySelectorAll('button'));
          const targetButton = buttons.find(button => /评论/.test(button.innerText || ''));
          if (targetButton) {
            targetButton.click();
            return true;
          }
          return false;
        })()"""
        comments_opened = (await cdp.call("Runtime.evaluate", {"expression": click_expr, "returnByValue": True})).get("result", {}).get("value", False)
        await asyncio.sleep(3 if comments_opened else 1)
        extract_expr = """(() => {
          const pick = (root, selectors) => {
            for (const selector of selectors) {
              const el = root.querySelector(selector);
              if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
            }
            return "";
          };
          const answer = document.querySelector(".AnswerItem") || document.querySelector("[data-zop]") || document.body;
          const commentNodes = Array.from(document.querySelectorAll(".CommentItem, .NestComment, [class*=CommentItem], [class*=CommentContent]")).slice(0, 20);
          return {
            title: pick(document, [".QuestionHeader-title", "h1"]) || document.title,
            author: pick(answer, [".AuthorInfo-name", ".UserLink-link", ".AuthorInfo-content a"]),
            body: pick(answer, [".RichContent-inner", ".RichText", ".ContentItem-content"]) || answer.innerText,
            comments: commentNodes.map(node => node.innerText.trim()).filter(Boolean),
            source_url: location.href,
            comments_opened: __COMMENTS_OPENED__
          };
        })()""".replace("__COMMENTS_OPENED__", "true" if comments_opened else "false")
        result = await cdp.call("Runtime.evaluate", {"expression": extract_expr, "returnByValue": True})
        data = result.get("result", {}).get("value")
        print(json.dumps(data, ensure_ascii=False))

asyncio.run(main())
'''
    command = [
        config.uv_bin,
        "run",
        "python",
        "-c",
        script,
        raw_url,
        str(config.cdp_port),
    ]
    try:
        progress("[extract-url] CDP 兜底：连接已登录的 Chrome 页面...")
        completed = subprocess.run(
            command,
            cwd=config.home,
            text=True,
            capture_output=True,
            timeout=min(config.timeout, 60),
            check=False,
        )
    except Exception as exc:
        raise MediaCrawlerError(
            f"MediaCrawler 失败，CDP 兜底也失败。MediaCrawler 输出：{error}"
        ) from exc
    if completed.returncode != 0:
        raise MediaCrawlerError(
            f"MediaCrawler 失败，CDP 兜底也失败。MediaCrawler 输出：{error}；"
            f"CDP 输出：{(completed.stderr or completed.stdout)[-800:]}"
        )
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise MediaCrawlerError(
            f"CDP 兜底返回内容不是合法 JSON：{completed.stdout[-800:]}"
        ) from exc
    body = str(data.get("body") or "").strip()
    if not body:
        raise MediaCrawlerError(
            f"MediaCrawler 失败，CDP 兜底也没有提取到正文。MediaCrawler 输出：{error}"
        )
    comments = [clean_comment_text(comment) for comment in data.get("comments") or []]
    comments = [comment for comment in comments if comment][: config.comments_limit]
    progress(f"[extract-url] CDP 兜底成功：正文 {len(body)} 字，评论 {len(comments)} 条。")
    comment_threads = [
        comment_thread_to_dict(CommentThread(author="可见评论", content=comment))
        for comment in comments
    ]
    return ExtractedSocialContent(
        platform="zhihu",
        source_url=str(data.get("source_url") or raw_url),
        title=str(data.get("title") or "知乎内容").strip(),
        author=str(data.get("author") or "").strip() or None,
        body=body,
        comments=[f"可见评论：{comment}" for comment in comments],
        comment_threads=comment_threads,
        metadata={
            "content_id": specified_id,
            "specified_id": specified_id,
            "extractor": "cdp_fallback",
            "media_crawler_error": error,
            "comments_count": len(comments),
        },
    )


def clean_comment_text(text: str) -> str:
    return " ".join(text.split())


def ensure_cdp_browser_available(port: int) -> None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MediaCrawlerError(
            f"无法连接到 Chrome CDP 端口 {port}。请先用 --remote-debugging-port={port} 启动 Chrome 并登录平台。"
        ) from exc
    if not data.get("webSocketDebuggerUrl"):
        raise MediaCrawlerError(f"Chrome CDP 端口 {port} 未返回 webSocketDebuggerUrl。")
