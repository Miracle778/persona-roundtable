# IndexTTS 自部署与声音素材指南

日期：2026-06-02

目标：租 GPU 算力自部署 IndexTTS，把 `persona-roundtable` 后续生成的 `script.json` 转成角色语音，并为视频化链路做准备。

## 1. 先说结论

推荐路线：

1. 租一台 Linux GPU 云主机。
2. 安装 `git`、`git-lfs`、`uv`、CUDA 12.8+ 相关环境。
3. 克隆官方仓库 `https://github.com/index-tts/index-tts`。
4. 用 `uv sync --all-extras` 安装依赖。
5. 下载 `IndexTeam/IndexTTS-2` 模型到 `checkpoints/`。
6. 先跑官方 WebUI 验证。
7. 再封装一个 HTTP API，供 `my_agent` 调用。
8. 声音素材优先用自己录制或明确授权的素材，不建议直接拿别人的抖音视频克隆。

官方仓库 README 提到：IndexTTS2 支持 zero-shot voice cloning，安装推荐使用 `uv`，模型可从 HuggingFace 或 ModelScope 下载，WebUI 用 `uv run webui.py` 启动，Python 推理使用 `IndexTTS2(...).infer(...)`。

## 2. 合规边界

### 可以用的声音素材

优先级从高到低：

1. **你自己录的声音**  
   最安全，最好用。

2. **你请配音演员录制并获得书面授权的声音**  
   建议授权里明确包含：
   - 可用于 AI 语音合成。
   - 可用于你的视频内容。
   - 是否可商用。
   - 是否可长期保存声音样本。
   - 是否允许生成相似音色而非逐条录制。

3. **项目成员、朋友提供并明确授权的声音**  
   也建议保留文字授权记录。

4. **公开版权/开放许可的语音素材**  
   要确认许可证允许“声音克隆 / 生成式使用 / 商业使用”。

### 不建议或不要用的素材

不要直接拿这些做声音克隆：

- 未经授权的抖音、快手、B站、小红书、微博视频里的真人声音。
- 公众人物、主播、演员、网红、UP 主的声音。
- 明显带有隐私内容的聊天录音、会议录音。
- 未成年人声音。
- 任何你无法证明授权来源的声音。

IndexTTS 官方免责声明明确限制：不得合成政治人物、公众人物或任何未经授权的个人声音，不得用于欺诈、身份盗用、侵权、违法等用途。

## 3. 抖音视频可以吗？

分情况：

### 可以考虑

只有在这些条件同时满足时才建议用：

- 视频是你自己发布的，里面是你自己的声音；或者
- 声音本人明确授权你使用这段声音做 AI 合成；并且
- 视频/音频没有第三方版权音乐、影视片段、他人声音；并且
- 使用方式符合平台规则和当地法律。

### 不建议

如果是“看到某个角色/主播/网红说话很有风格，想拿来克隆”，不建议这么做。即使视频公开可见，也不等于你拥有克隆其声音、生成新内容、商业发布的权利。

### 对你的项目更合适的做法

你的 agent 大多是“蒸馏人物风格”或“节目化代理角色”，建议用：

- 风格化原创音色，而不是真人声音克隆。
- 比如“湖南青年感”“冷静法理感”“抽象弹幕感”“科技创业感”。
- 可以请配音演员录 5-10 个基础音色，然后映射到不同 agent。

这样既有角色区分，又不会暗示真实人物参与。

## 4. 声音素材规格建议

IndexTTS 可以用单个参考音频做 zero-shot voice cloning。实际效果取决于素材质量。

建议准备：

- 时长：10-30 秒起步，最好准备 3-5 条不同语气样本。
- 格式：WAV 优先。
- 声道：单声道或干净的双声道都可以，后处理建议转单声道。
- 采样率：24kHz / 44.1kHz / 48kHz 都可以，最终可统一转 24kHz 或 16kHz。
- 内容：普通自然说话，不要唱歌，不要多人对话。
- 环境：无背景音乐、无混响、无强噪声。
- 情绪：每个角色可准备不同风格，例如冷静、吐槽、激动、沉稳。

素材命名建议：

```text
voices/
  xin_qingnian/
    neutral_01.wav
    firm_01.wav
  abstract_barrage/
    playful_01.wav
    roast_01.wav
  tech_founder/
    calm_01.wav
    excited_01.wav
```

## 5. 素材清洗流程

如果是你自己录制：

```bash
ffmpeg -i input.m4a -ac 1 -ar 24000 voices/xin_qingnian/neutral_01.wav
```

如果有背景噪声：

```bash
ffmpeg -i input.mp4 -vn -ac 1 -ar 24000 raw.wav
```

再用音频工具做降噪，例如：

- Adobe Podcast Enhance
- Audacity
- iZotope RX
- UVR / Demucs 做人声分离

清洗后检查：

- 是否只剩一个人声。
- 是否没有明显 BGM。
- 是否没有爆音、断裂、强电流声。
- 是否没有其他人插话。

## 6. 租算力建议

### 最低建议

- 系统：Ubuntu 22.04
- GPU：NVIDIA RTX 3090 / 4090 / A10 / A100 这类
- 显存：建议 16GB+，更稳是 24GB+
- 磁盘：至少 80GB，建议 100GB+
- Python：按仓库 `uv` 环境来，不要自己手动乱配 conda
- CUDA：官方 README 提醒 Linux/Windows 如果遇到 CUDA 报错，需要 CUDA Toolkit 12.8 或更新版本

### 端口

- WebUI 默认：`7860`
- 如果你后续封 API，可以用：`8000`

云服务商安全组要放行对应端口，或者更安全地用 SSH 隧道。

## 7. 云主机初始化

登录机器：

```bash
ssh root@YOUR_SERVER_IP
```

安装基础工具：

```bash
apt update
apt install -y git git-lfs ffmpeg curl build-essential
git lfs install
```

安装 `uv`：

```bash
pip install -U uv
```

检查 GPU：

```bash
nvidia-smi
```

## 8. 安装 IndexTTS

克隆官方仓库：

```bash
git clone https://github.com/index-tts/index-tts.git
cd index-tts
git lfs pull
```

安装依赖：

```bash
uv sync --all-extras
```

如果国内下载慢，可以试镜像：

```bash
uv sync --all-extras --default-index "https://mirrors.aliyun.com/pypi/simple"
```

或：

```bash
uv sync --all-extras --default-index "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
```

## 9. 下载模型

HuggingFace：

```bash
uv tool install "huggingface-hub[cli,hf_xet]"
hf download IndexTeam/IndexTTS-2 --local-dir=checkpoints
```

如果访问 HuggingFace 慢：

```bash
export HF_ENDPOINT="https://hf-mirror.com"
hf download IndexTeam/IndexTTS-2 --local-dir=checkpoints
```

ModelScope：

```bash
uv tool install "modelscope"
modelscope download --model IndexTeam/IndexTTS-2 --local_dir checkpoints
```

## 10. 检查 GPU 与启动 WebUI

官方仓库提供 GPU 检查：

```bash
uv run tools/gpu_check.py
```

启动 WebUI：

```bash
uv run webui.py
```

打开：

```text
http://YOUR_SERVER_IP:7860
```

如果不想公网暴露 WebUI，建议本地 SSH 隧道：

```bash
ssh -L 7860:127.0.0.1:7860 root@YOUR_SERVER_IP
```

然后本地打开：

```text
http://127.0.0.1:7860
```

## 11. Python 推理测试

新建 `test_tts.py`：

```python
from indextts.infer_v2 import IndexTTS2

tts = IndexTTS2(
    cfg_path="checkpoints/config.yaml",
    model_dir="checkpoints",
    use_fp16=True,
    use_cuda_kernel=False,
    use_deepspeed=False,
)

tts.infer(
    spk_audio_prompt="examples/voice_01.wav",
    text="大家好，今天我们来聊一个有意思的问题。",
    output_path="gen.wav",
    verbose=True,
)
```

运行：

```bash
PYTHONPATH="$PYTHONPATH:." uv run test_tts.py
```

听一下：

```bash
ffplay gen.wav
```

如果服务器没音频输出，可以下载到本地：

```bash
scp root@YOUR_SERVER_IP:/path/to/index-tts/gen.wav .
```

## 12. 给 my_agent 封装 HTTP API

后续 `my_agent` 最适合通过 HTTP 调 TTS 服务，不要每条发言都新启动一次 Python。

可以在 IndexTTS 目录新建 `api_server.py`：

```python
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from indextts.infer_v2 import IndexTTS2

app = FastAPI()

tts = IndexTTS2(
    cfg_path="checkpoints/config.yaml",
    model_dir="checkpoints",
    use_fp16=True,
    use_cuda_kernel=False,
    use_deepspeed=False,
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


class TTSRequest(BaseModel):
    text: str
    voice_path: str
    emotion_voice_path: str | None = None
    emo_alpha: float = 0.6


@app.post("/tts")
def synthesize(req: TTSRequest):
    output = OUTPUT_DIR / f"{uuid4().hex}.wav"
    kwargs = {
        "spk_audio_prompt": req.voice_path,
        "text": req.text,
        "output_path": str(output),
        "verbose": True,
    }
    if req.emotion_voice_path:
        kwargs["emo_audio_prompt"] = req.emotion_voice_path
        kwargs["emo_alpha"] = req.emo_alpha
    tts.infer(**kwargs)
    return {"audio_path": str(output)}


@app.get("/audio")
def get_audio(path: str):
    return FileResponse(path, media_type="audio/wav")
```

安装 FastAPI 相关依赖：

```bash
uv add fastapi uvicorn
```

启动：

```bash
PYTHONPATH="$PYTHONPATH:." uv run uvicorn api_server:app --host 0.0.0.0 --port 8000
```

测试：

```bash
curl -X POST http://127.0.0.1:8000/tts \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "老马这个点我接一下，创业不是热血上头，先看现金流。",
    "voice_path": "voices/tech_founder/calm_01.wav"
  }'
```

## 13. my_agent 后续对接方式

建议在 `my_agent/.env` 增加：

```bash
MY_AGENT_TTS_PROVIDER="indextts"
MY_AGENT_TTS_BASE_URL="http://YOUR_SERVER_IP:8000"
MY_AGENT_TTS_TIMEOUT="120"
MY_AGENT_VOICE_DIR="/path/to/voices"
```

每个 skill 可以加：

```yaml
voice_style:
  voice_id: xin_qingnian
  voice_file: voices/xin_qingnian/neutral_01.wav
  tone: 直爽、辩证、有湖南青年气质
```

然后让 `my_agent voice render RUN_DIR --provider indextts`：

1. 读取 `script.json`。
2. 按 speaker 找 voice 文件。
3. 调 `/tts`。
4. 保存每条发言 wav。
5. 写入 `voice_manifest.json`。

## 14. 角色声音设计建议

不要做“某某真实人物声音克隆”，而是做原创角色音色：

| Agent 类型 | 建议音色 |
| --- | --- |
| 新青年 | 年轻男声，湖南口音轻微，坚定但不端着 |
| 峰哥亡命天涯视角 | 中青年男声，现实、粗粝、语速略快 |
| 童锦程视角 | 年轻男声，松弛、社交感强 |
| 李大霄视角 | 中年男声，金融节目感，乐观但克制 |
| 抽象弹幕王 | 年轻男声，碎嘴、吐槽、弹幕感 |
| 法理观察员 | 中青年男声，冷静、逻辑感 |
| 第一性原理玩家 | 干练男声，科技创业感 |

这样能体现角色风味，又不直接侵犯真实人物声音权益。

## 15. 质量验收 checklist

### 环境

- `nvidia-smi` 正常。
- `uv run tools/gpu_check.py` 能识别 GPU。
- `uv run webui.py` 可启动。
- `test_tts.py` 能生成 `gen.wav`。

### 声音

- 参考音频无 BGM。
- 参考音频只有一个人。
- 生成语音没有明显破音、吞字、机械感。
- 同一个 voice 在多条句子中音色稳定。
- 不同角色之间有明显区分。

### 合规

- 每个 voice 都有来源记录。
- 每个 voice 都有授权说明。
- 没有未经授权的公众人物/主播/网红声音。
- 生成内容没有暗示“真人本人参与”。

## 16. 推荐落地顺序

1. 先用你自己的声音或授权朋友声音跑通。
2. 给 3 个 agent 配 3 个原创音色。
3. 把 `script.json` 里 5-10 条发言转成 wav。
4. 检查音色一致性和可听性。
5. 再把 TTS HTTP API 接进 `my_agent voice render`。
6. 最后再做字幕、音频和 HTML/视频时间轴对齐。

## 参考来源

- IndexTTS 官方仓库：https://github.com/index-tts/index-tts
- IndexTTS 官方 README：安装、模型下载、WebUI、Python 推理示例。
- IndexTTS 官方免责声明：限制未经授权的个人声音、公众人物声音、欺诈、侵权等用途。
- IndexTTS 模型许可证：使用者需自行承担合规、授权、输出内容责任。
