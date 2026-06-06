# Roadmap Implementation Acceptance Review

日期：2026-06-01

本轮目标：检查 `roadmap.md` 中尚未实现的需求，按顺序做一版可验证实现；每项实现后做验证并记录。当前未提交，等待确认。

## 总览

| 顺序 | Roadmap 需求 | 本轮状态 | 验证状态 |
| --- | --- | --- | --- |
| 1 | 讨论事件稿增强 | 已做一版 | 通过 |
| 2 | Web search 背景补全 | 已做一版 | 通过，当前环境 DNS 不通时会记录失败并继续 |
| 3 | Skill registry 与推荐解释 | 已做一版 | 通过 |
| 4 | 选题生成过程可视化 | 已做一版 | 通过 |
| 5 | 结构化节目脚本 `script.json` | 已做一版 | 通过 |
| 6 | 角色语音原型 | 已做 mock 版 | 通过 |
| 7 | 视频/发布素材包 | 已做草稿包版 | 通过 |
| 8 | 作品数据分析 | 已做一版 | 通过 |

## 1. 讨论事件稿增强

### 实现内容

- `my_agent/input_sources/event_markdown.py` 增强 Markdown 事件稿。
- 新增固定段落：
  - `## 选题判断`
  - `## 背景补全`
- 新增 frontmatter 字段：
  - `topic_angle`
  - `opening_hook`
- 自动生成：
  - 选题角度
  - 开场钩子
  - 核心争议
  - 评论区阵营
- 新增 CLI：
  - `python3 -m my_agent event create ...`
  - `python3 -m my_agent event preview ...`
  - `python3 -m my_agent event edit ...`

### 验证

命令：

```bash
python3 -m my_agent event create "AI最新模型发布会对程序员就业有什么影响？" \
  --event-dir /private/tmp/persona_roundtable_events2 \
  --web-search off

EVENT_PATH=$(ls -1 /private/tmp/persona_roundtable_events2/*.md | tail -n 1)
python3 -m my_agent event edit "$EVENT_PATH" \
  --set topic_angle="从技术变革和就业安全感切入" \
  --task "请围绕这个事件讨论技术变化、职业风险、评论区情绪和普通人的行动选择。"

python3 -m my_agent event preview "$EVENT_PATH"
```

结果摘要：

```text
事件稿：/private/tmp/persona_roundtable_events2/20260601-234034-manual-AI最新模型发布会对程序员就业有什么影响.md
已更新事件稿：...
--- 选题判断 ---
- 选题角度：从技术变革和就业安全感切入
--- 背景补全 ---
无背景补全。
```

结论：通过。

## 2. Web Search 背景补全

### 实现内容

- 新增 `my_agent/input_sources/background.py`。
- `ask` 和 `event create` 新增：

```bash
--web-search auto|on|off
```

- 自动触发规则：
  - 短输入且不是明确个人问题。
  - 包含“最新、最近、今天、热搜、2026、政策、公司、裁员、产品发布”等实时词。
  - 链接提取正文或评论较少。
  - 用户显式要求查背景。
- 背景补全会写入：
  - `NormalizedInput.background`
  - `metadata["background_context"]`
  - 事件稿 `## 背景补全`
- 如果网络失败，不中断讨论，会记录错误。

### 验证

命令：

```bash
python3 -m my_agent event create "AI最新模型发布会对程序员就业有什么影响？" \
  --event-dir /private/tmp/persona_roundtable_events \
  --web-search on
```

结果摘要：

```text
[3/8] 正在补全背景：输入包含近期/实时事件线索。
[3/8] 背景补全失败，已保留失败信息：web search 请求失败：<urlopen error [Errno 8] nodename nor servname provided, or not known>
事件稿：/private/tmp/persona_roundtable_events/...
```

结论：通过。当前运行环境无法解析外网 DNS，但失败信息被写入事件稿并且流程继续，这符合“不能因为背景补全失败中断讨论”的要求。

## 3. Skill Registry 与推荐解释

### 实现内容

- `PersonaSkill` 增加：
  - `voice_style`
  - `visual_style`
  - `metadata`
- `skill_loader` 支持读取 frontmatter 结构化字段：
  - `categories`
  - `suitable_for`
  - `not_suitable_for`
  - `triggers`
  - `voice_style`
  - `visual_style`
- 新增 CLI：

```bash
python3 -m my_agent recommend-agents "问题内容"
```

- 推荐结果展示：
  - 识别分类
  - agent id
  - score
  - 命中理由
  - 分类
- 补充技术就业类关键词，让 AI/程序员/就业/技术变革类问题能命中分类。

### 验证

命令：

```bash
python3 -m my_agent recommend-agents "AI最新模型发布会对程序员就业有什么影响？" \
  --max-agents 3 \
  --web-search off
```

结果摘要：

```text
识别分类：创业产品、社会观察
1. 新青年
   id: mao-zedong-perspective
   score: 23
   reason: 命中 创业产品、社会观察
2. 峰哥亡命天涯视角
   score: 22
   reason: 命中 创业产品、社会观察
3. 童锦程视角
   score: 22
   reason: 命中 创业产品、社会观察
```

结论：通过。

遗留：LLM 二次重排还未接入；当前是一版关键词/metadata 推荐。

## 4. 选题生成过程可视化

### 实现内容

- HTML 增加 `选题生成过程` 区块。
- 展示：
  - 输入来源
  - 事件稿路径
  - 选题判断
  - 背景补全状态
  - 人物入场

### 验证

命令：

```bash
EVENT_PATH=$(ls -1 /private/tmp/persona_roundtable_events2/*.md | tail -n 1)
python3 -m my_agent ask "$EVENT_PATH" \
  --style show \
  --rounds 1 \
  --max-agents 2 \
  --web-search off \
  --quiet

python3 - <<'PY'
from pathlib import Path
run = Path("/Users/miracle778/myproject/my_agent/runs/20260601-234039-042447")
html = (run / "discussion.html").read_text()
print("journey", "选题生成过程" in html)
PY
```

结果摘要：

```text
HTML: /Users/miracle778/myproject/my_agent/runs/20260601-234039-042447/discussion.html
journey True
```

结论：通过。

## 5. 结构化节目脚本 `script.json`

### 实现内容

- `DiscussionRecorder.save()` 现在同时输出：
  - `discussion.json`
  - `discussion.html`
  - `script.json`
- `script.json` 包含：
  - `host_intro`
  - 每条 `dialogue`
  - `host_summary`
  - `reply_to_name`
  - `emotion`
  - `duration_hint`
  - 事件稿路径
  - 来源链接

### 验证

命令：

```bash
python3 - <<'PY'
import json
from pathlib import Path
run = Path("/Users/miracle778/myproject/my_agent/runs/20260601-234039-042447")
script = json.loads((run / "script.json").read_text())
print("scenes", len(script["scenes"]))
print("first", script["scenes"][0]["type"], script["scenes"][0]["duration_hint"])
print("script exists", (run / "script.json").exists())
PY
```

结果摘要：

```text
scenes 4
first host_intro 9
script exists True
```

结论：通过。

## 6. 角色语音原型

### 实现内容

- 新增 `my_agent/core/production.py`。
- 新增 CLI：

```bash
python3 -m my_agent voice render RUN_DIR
```

- 第一版使用 `mock_silence` provider：
  - 根据 `script.json` 为每个 scene 生成一个合法 `.wav` 文件。
  - 输出 `voice_manifest.json`。

说明：这是可验证的本地链路骨架，不是真实 TTS；后续可以替换为真实 provider。

### 验证

命令：

```bash
python3 -m my_agent voice render /Users/miracle778/myproject/my_agent/runs/20260601-234039-042447
```

结果摘要：

```text
语音清单：.../voice_manifest.json
音频目录：.../audio
音频片段：4
```

结论：通过。

## 7. 视频/发布素材包

### 实现内容

- 新增 CLI：

```bash
python3 -m my_agent video package RUN_DIR --platform xiaohongshu
```

- 第一版输出发布草稿包：
  - `publish_metadata.json`
  - `captions.srt`
  - `storyboard.md`

说明：当前环境没有 `ffmpeg`，所以本轮先实现“发布素材包”而不是直接生成 mp4；这符合 roadmap 中“第一版建议只生成发布素材和草稿”的发布策略。

### 验证

命令：

```bash
python3 -m my_agent video package /Users/miracle778/myproject/my_agent/runs/20260601-234039-042447 \
  --platform xiaohongshu
```

结果摘要：

```text
发布素材包：.../publish_package
- .../publish_metadata.json
- .../captions.srt
- .../storyboard.md
```

结论：通过。

遗留：真实 mp4 生成需要后续接入 `ffmpeg` 或视频 provider。

## 8. 作品数据分析

### 实现内容

- 新增 CLI：

```bash
python3 -m my_agent analyze-work metrics.json
```

- 输入作品数据 JSON，输出 Markdown 复盘报告。
- 当前计算：
  - 完播率
  - 点赞率
  - 评论率
  - 转发率
  - 初步建议

### 验证

命令：

```bash
cat > /private/tmp/persona_roundtable_metrics.json <<'JSON'
{
  "platform": "xiaohongshu",
  "work_id": "demo-001",
  "title": "AI会不会让程序员失业",
  "plays": 10000,
  "completions": 4200,
  "likes": 520,
  "comments": 180,
  "shares": 90
}
JSON

python3 -m my_agent analyze-work /private/tmp/persona_roundtable_metrics.json \
  --output /private/tmp/persona_roundtable_analysis.md
```

结果摘要：

```text
播放量：10000
完播率：42.00%
点赞率：5.20%
评论率：1.80%
转发率：0.90%
```

结论：通过。

## 全局验证

命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/my_agent_pycache \
python3 -m compileall my_agent/core my_agent/input_sources my_agent/__main__.py
```

结果：

```text
Listing 'my_agent/core'...
Listing 'my_agent/input_sources'...
Listing 'my_agent/input_sources/platforms'...
```

结论：通过。

## 本轮改动文件

新增：

- `my_agent/input_sources/background.py`
- `my_agent/core/production.py`
- `docs/acceptance_review.md`

修改：

- `my_agent/__main__.py`
- `my_agent/core/models.py`
- `my_agent/core/recorder.py`
- `my_agent/core/skill_loader.py`
- `my_agent/input_sources/event_markdown.py`
- `my_agent/input_sources/resolver.py`

## 尚未提交

按你的要求，本轮没有执行 `git commit`。

## 遗留边界

- Web search 当前环境 DNS 不通，已验证失败可记录并不中断；真实联网环境还需要再跑一次成功路径。
- Agent 推荐目前是一版关键词/metadata 推荐，尚未接入 LLM 二次重排。
- 语音是 mock `.wav`，尚未接入真实 TTS provider。
- 视频当前是发布素材包和字幕/分镜，尚未生成真实 mp4。
- 自动发布仍未接平台 API 或浏览器自动化，只生成草稿素材。
