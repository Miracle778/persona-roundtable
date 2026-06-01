# my_agent

一个从 `demo_skills` 加载人物 Skill 的多 Agent 视角讨论 Demo。

## 现在支持

- 默认读取 `my_agent/demo_skills/*/SKILL.md`
- 根据问题关键词和 Skill 标签自动选择人物
- 支持手输文本，也预留 URL 输入结构
- 多轮顺序讨论
- 输出 `discussion.json` 和 `discussion.html`
- 默认 `mock` 模式，不需要 API key

## 使用

```bash
python3 -m my_agent list-skills
python3 -m my_agent list-categories
python3 -m my_agent ask "我和对象总是因为边界感吵架，该怎么办？"
python3 -m my_agent ask "我要不要做一个面向小红书内容分析的产品？" --rounds 2
python3 -m my_agent ask "问题内容" --agents tong-jincheng-perspective feng-ge-perspective
```

运行后会生成：

```text
my_agent/runs/<timestamp>/discussion.json
my_agent/runs/<timestamp>/discussion.html
```

## 真实模型

支持 OpenAI-compatible 接口。程序启动时会自动读取：

```text
my_agent/.env
当前运行目录/.env
```

`.env` 示例：

```bash
MY_AGENT_API_KEY="..."
MY_AGENT_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
MY_AGENT_MODEL="minimax-m2.7"
MY_AGENT_AVAILABLE_MODELS="minimax-m2.7,deepseek-v3.2,glm-5.1"
```

也可以从已有 opencode 配置导出环境变量：

```bash
python3 -m my_agent llm-env-from-opencode
```

默认会脱敏 API key。需要复制真实 export 命令时使用：

```bash
python3 -m my_agent llm-env-from-opencode --show-secret
```

把输出的 `export ...` 复制到当前 shell 后，可以列出可用模型：
如果已经写入 `.env`，不需要复制 export，直接运行即可。

```bash
python3 -m my_agent list-llm-models
```

使用默认模型：

```bash
python3 -m my_agent ask "问题内容" --llm openai
```

临时指定模型：

```bash
python3 -m my_agent ask "问题内容" --llm openai --model deepseek-v3.2
```

交互选择模型：

```bash
python3 -m my_agent ask "问题内容" --llm openai --choose-model
```

也可以手动设置：

```bash
export MY_AGENT_API_KEY="..."
export MY_AGENT_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
export MY_AGENT_MODEL="minimax-m2.7"
export MY_AGENT_AVAILABLE_MODELS="minimax-m2.7,deepseek-v3.2,glm-5.1"
```

## 后续扩展

## 社交媒体链接输入

第一版社交媒体链接解析通过外部 MediaCrawler 适配器完成，不复制 MediaCrawler 源码。支持：

- 知乎
- 微博

`.env` 里增加：

```bash
MEDIA_CRAWLER_HOME="/path/to/MediaCrawler"
MEDIA_CRAWLER_OUTPUT_DIR="/path/to/MediaCrawler/data"
MEDIA_CRAWLER_UV_BIN="uv"
MEDIA_CRAWLER_COMMENTS_LIMIT="5"
MEDIA_CRAWLER_SUB_COMMENTS_LIMIT="3"
MEDIA_CRAWLER_TIMEOUT="180"
```

调试提取：

```bash
python3 -m my_agent extract-url "https://www.zhihu.com/question/..."
python3 -m my_agent extract-url "https://m.weibo.cn/detail/..."
```

提取成功后会在 `my_agent/events/` 下保存一份 Markdown 讨论事件稿，结构固定为：

```markdown
---
my_agent_event_version: "1"
event_type: "social_post"
platform: "zhihu"
source_url: "..."
title: "..."
author: "..."
extracted_at: "..."
---

# 讨论事件：标题

## 事件来源
## 原帖正文
## 评论区摘录
## 讨论任务
```

进入讨论：

```bash
python3 -m my_agent ask "https://www.zhihu.com/question/..." --llm openai --rounds 1 --max-agents 2
```

也可以直接加载已经保存好的事件稿：

```bash
python3 -m my_agent ask my_agent/events/20260601-230000-zhihu-example.md --llm openai --style show
```

要求：

- 本机已安装 `uv`
- `MEDIA_CRAWLER_HOME` 指向可运行的 MediaCrawler 仓库
- Chrome/Edge 已按 MediaCrawler CDP 方式配置并登录目标平台
- MediaCrawler 保存格式为 JSONL

暂不支持的平台会直接报错停止，不会拿空内容继续讨论。

URL 输入已有统一结构，后面可以继续接入：

- 小红书
- 抖音

解析完成后，只要填充标准化 `content`，后面的分类、选人、讨论、可视化流程不用改。
