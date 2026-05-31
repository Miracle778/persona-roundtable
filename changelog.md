# Changelog

- 你希望先参考 ai-hedge-fund 设计一个多人物视角讨论系统，我给出了基于 `my_agent` 的 PersonaAgent、skill 加载、分类匹配、讨论记录和 HTML 可视化方案。
- 你希望确认 PersonaAgent 之间是否隔离，我说明了每个 agent 只读取自己的 skill、共享的只有公开发言 transcript。
- 你希望确认 agent 技术栈，我选择了轻量 Python CLI、Markdown skill、OpenAI-compatible LLM、JSON/HTML recorder 的第一版技术路线。
- 你希望先开发第一版，我实现了 `my_agent` 的文本输入、多人物选择、多轮讨论、mock LLM、JSON/HTML 输出。
- 你发现讨论内容像固定模板，我说明当前是 mock 规则生成，并准备接入真实 LLM。
- 你希望接入已有 opencode LLM 配置，我实现了从 `.env` 读取 `MY_AGENT_*` 配置并调用 OpenAI-compatible `/chat/completions`。
- 你希望直接把 key 放进 env 文件，我调整为程序启动时读取 `my_agent/.env`。
- 你发现主持总结像被截断，我去掉了规则总结中的硬截断，并在真实 LLM 模式下增加了主持人总结调用。
- 你发现 HTML 不支持 Markdown 渲染，我给发言和主持总结区域增加了基础 Markdown 渲染。
- 你想了解当前 CLI 参数，我解释了 `ask`、`extract-url`、`--llm`、`--model`、`--rounds`、`--agents`、`--max-agents` 等参数。
- 你想讨论社交媒体链接输入，我设计了 URL 识别、正文/评论提取、结构化 NormalizedInput 和后续 agent 讨论流程。
- 你问嵌套评论怎么处理，我设计了一级评论加二级回复的评论线程结构。
- 你问知乎、微博是否需要账号登录，我说明第一版使用本机 Chrome CDP 登录态，不保存账号密码或 cookie。
- 你希望参考 MediaCrawler 实现社媒爬取，我接入了外部 MediaCrawler 适配层，支持知乎/微博 URL 提取和 JSONL 读取。
- 你不知道怎么运行社媒提取，我给出了启动 Chrome CDP、登录平台、运行 `extract-url` 和 `ask` 的命令。
- 你让我帮你运行知乎链接，我用 Chrome CDP 跑通了知乎正文和评论提取。
- 你发现 MediaCrawler 会新开 Chrome，我调整配置和说明为连接已开启远程调试端口的本机 Chrome。
- 你问现在能不能提取评论，我验证并修复了知乎评论提取，最终可提取 5 条可见评论。
- 你觉得问题分析太正式，希望参考 WeirdoTV 重新设计，我给出了新增 `show` 节目化对话模式的方案。
- 你觉得运行过程没有进度输出，我实现了 `progress` 回调、默认阶段日志和 `--quiet` 静默模式。
- 你问怎么运行新版进度，我给出了文本讨论、真实 LLM、知乎链接和只提取链接内容的命令。
- 你遇到无法连接 Chrome CDP 9222，我说明了如何用 `--remote-debugging-port=9222` 启动 Chrome 并检测端口。
- 你怀疑 CDP 明明开着为什么我连不上，我确认是 Codex 沙箱限制本机 TCP，非沙箱权限下 CDP 可访问。
- 你让我帮你跑知乎链接，我用非沙箱权限跑通 `extract-url` 和完整 `ask --llm openai --rounds 3`。
- 你问为什么 MediaCrawler 本体失败、CDP 如何兜底，我解释了 MediaCrawler HTTP/API 请求被知乎 Forbidden，而 CDP 兜底通过已登录 Chrome DOM 抓取。
- 你希望真正跑通 MediaCrawler 本体，我修复了 MediaCrawler 的知乎 `--specified_id` 未生效和 CDP WebSocket 地址写死的问题。
- 你问大模型怎么调用以及为什么慢，我解释了原来是每个 agent 串行调用 `/chat/completions`，4 人 3 轮需要 13 次请求。
- 你建议第一轮并发、每轮用临时总结衔接下一轮，我实现了按轮并发生成、轮次临时总结、`--serial` 和 `--max-concurrency` 参数。
- 你发现并发后后续轮次缺少点对点接话，我把临时总结改成“战场摘要 + 点名接话索引”，并要求 agent 下一轮必须点名回应具体人物。
- 你问并发用什么实现、异步协程是否更好，我说明当前使用 `ThreadPoolExecutor` 适配阻塞式 `urllib`，后续要真正异步需替换为 async HTTP 客户端。
- 你希望把毛选 agent 名称改成“新青年”，我把 maoxuan skill 的显示标题改为 `新青年`。
- 你希望新青年人物定位改成“深入学习、理解毛选的湖南新青年”，我更新了 maoxuan skill 的 description、角色规则和身份卡，避免再扮演毛泽东本人。
- 你希望记录新的产品想法并和之前计划合并，我把输入增强、角色视听化、skill 分类、视频生成发布和作品数据分析整理成后续路线。
- 你希望 roadmap 单独成文并详细展开，我新增了 `roadmap.md`，把产品愿景、阶段规划、风险、里程碑和开放问题拆出来。
- 你追问“让对话变得诙谐幽默”的需求是否重要，我把它提升为 roadmap 的核心阶段，明确为 `--style show` 节目化对话能力。

详细路线见：[roadmap.md](./roadmap.md)。
