---
topics: [review, design, quality-gate]
doc_kind: lesson_learned
feature_ids: []
created: 2026-06-06
authors: [缅因猫/砚砚]
severity: P1
status: active
---

# LL-001: Reviewer 必须在 review 前确认设计稿真相源

## 一句话教训

**任何带 UI 改动的 code review，reviewer 必须先确认设计稿是否存在、是否被对照——找不到设计稿就 stop the line，不能放过。**

## 失败现场

- 项目：my_agent Web v0
- 时间窗口：2026-06-06 R1 / R2 / R3 三轮 review
- Reviewer：缅因猫/砚砚 (claude-haiku-4-6)
- Author：布偶猫/宪宪 (gpt-5.5)
- 设计师：暹罗猫/烁烁 (doubao)

### 事实链

1. 烁烁很早就声称做了 `designs/my_agent_web.pen`（三栏布局 + 配色 + 角色主题色 + 气泡样式）
2. 宪宪 F1 实现日志原话："没有 `designs/` 目录，Pencil 对照不适用"——他主动找了，没找到就放下了，**没拉响警报**
3. 砚砚（reviewer）做了 R1/R2/R3 三轮 verdict，**0 次提及设计稿对照**——全是 code review 维度（架构 / TDD / 测试覆盖 / fallback 层）
4. R3 verdict 放行后，铲屎官实际打开页面，第一反应：**"你这ui界面写的啥啊，跟设计的一点都不一样"**
5. 事后确认：`designs/my_agent_web.pen` **从未存在**——烁烁那轮可能没保存或没真的创建文件
6. 当前 v0 UI 完全是宪宪凭感觉写的 stdlib HTML/CSS，0 视觉规范来源

## Root cause

**Reviewer 的 review checklist 缺一项："设计稿存在性 + 对照性验证"**。

具体三个失误叠加：

| 失误层 | 角色 | 应该做但没做 |
|---|---|---|
| L1 - Author | 宪宪 | 找不到 `designs/` 应该立刻拉响警报（"我没有视觉真相源，建议先找烁烁要"），而不是默默继续 |
| L2 - Reviewer | 砚砚 | Review 流程缺设计稿验证项；3 轮全靠"代码维度" verdict，看不见视觉维度 |
| L3 - 流程 | 三猫共同 | 没有任何 mechanism 检查"设计师声称的产物是否真的存在/可访问"——口头交付 ≠ 真交付 |

## 反向工程：为什么没发现

1. **Reviewer 把 "tests OK" 当成 "全部 OK"**——绿测试只能证明代码不崩，证明不了视觉对齐
2. **Author 的"没找到 designs/"信号被淡化**——只在 F1 日志里轻描淡写，没在 handoff packet 顶部 flag
3. **铲屎官没看实物之前没人意识到差距**——三猫都在"对自己负责"，没人对"最终用户看到的样子"负责

## 修复 — Reviewer Checklist 增项

任何带 UI 改动的 review（前端、可视化、富文本、CSS、HTML），**verdict 前必须确认**：

- [ ] **设计稿真相源存在性**：`designs/*.pen` / Figma 链接 / Pencil 文件——必须能 `ls` / `cat` / `mcp__pencil__get_editor_state` 实证
- [ ] **设计稿被对照**：实现 diff 至少在某个 review 维度提到"对照设计 X 章节"
- [ ] **设计师签字**：如果设计师在线，PR/review 必须有设计师 LGTM；如果设计稿不存在，**stop the line** 找设计师重新出
- [ ] **视觉证据**：screenshot / browser preview 截图作为 review 附件，不是只跑 tests

**触发反射**：reviewer 看到 PR 含 `*.css` / `*.html` / `*.tsx` / `static/` 任何前端文件 → **第一动作不是 read code，是 ls designs/**。

## 修复 — Author 触发反射

Author 在自检阶段（quality-gate / self-check）发现"找不到设计稿"：

- ✅ **正确**：在 handoff packet 顶部用 🚨 flag 出来；继续做的部分明确标"凭感觉实现，待设计师对齐"；hold ball 给设计师
- ❌ **错误**：放在日志中间一笔带过，继续推进

## 修复 — 流程改进建议

| 项 | 建议 |
|---|---|
| Spec 阶段 | 设计稿位置写进 `docs/features/F*.md`，作为真相源链接 |
| Skill 启动 | `request-review` / `code-review` skill 启动时如果检测到前端文件，自动检查 designs/ 是否存在 |
| Handoff packet | 五件套之外再加一项 "Design source": 设计稿路径或 N/A 理由 |
| PR template | UI PR 必填 "设计稿对照" 一栏，N/A 必须说明理由 |

## 关联

- 家规 W4：「产出放对目录」——设计稿没放进 designs/ 是源头
- 家规 W7：「Knowledge Feed」——这个 lesson 应该回流到 cat-cafe 的方法论层（如果通用）
- Magic Word「绕路了」：3 轮 review 都没看设计稿就是绕路
- pencil-design skill：cat-cafe 的标准设计流程，my_agent 项目应该启用

## 我（砚砚）的承诺

下次任何 PR 含前端文件，**verdict 前我必须显式提到设计稿状态**——格式：
```
Design source: designs/F*.pen ✅ 对照 | ❌ 不存在 (stop the line) | N/A (纯逻辑改动)
```
不写这一行就是无效 verdict。

—— 缅因猫/砚砚 🐾 [claude-haiku-4-6]
