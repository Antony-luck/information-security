# 面向短视频多模态融合的内容安全智能研判系统

这是一个面向全国信息安全竞赛场景的短视频内容安全原型系统。当前主流程已经打通为：

`抖音链接采集 -> 自动下载视频 -> 抽帧 + OCR + 音频提取 + ASR -> 回填采集信息 -> 独立模块分析 -> 综合决策输出`

项目现在适合直接放到 GitHub 公开协作。代码结构已经按独立模块拆开，评论抓取也从“纯文本随机截取”升级为“结构化重要评论筛选”。

## 当前架构

系统按 5 个独立模块组织，全部放在 [app/modules](/c:/Users/admin/Desktop/information-security/app/modules)：

1. `data_collection`
   负责数据清洗、字段标准化、采集完整性评估和元数据可信度检查。
2. `audiovisual_content`
   负责抽帧、OCR、音频事件线索和音画内容分析。
3. `semantic_context`
   负责显性违规、隐性规避、事实断言和上下文语义分析。
4. `comment_analysis`
   负责评论区极化、引流、冲突和评论生态分析。
5. `comprehensive_decision`
   负责整合前四个模块结果，输出总体风险和行动建议。

模块之间不直接互相依赖。它们共享统一输入 `PreprocessedContent`，最终只由综合决策模块负责收口。

## 这版的技术亮点

- 结构化评论采集：评论不再只保留文本，还会保留 `speaker_id`、昵称、点赞数、回复总数、回复预览、IP 属地、是否热门、是否作者发言、关键词标签和重要性分数。
- 重要评论筛选：不是随机拿前 N 条评论，而是先扩大候选集，再按互动强度、回复链、作者参与和风险关键词做排序去重。
- 多模态视频链路：支持视频下载、稳定抽帧、OCR、音频提取、ASR、音频事件识别和页面回填。
- 离线优先 ASR：优先从本地 `faster-whisper` 模型目录加载，适合比赛现场、弱网环境和 GitHub 复现。
- 可演示、可复刻：Web 页面、API、模型下载脚本、测试、`.env.example` 和 README 都已补齐。

## 评论数据规范

当前系统内部推荐的评论结构是：

```json
{
  "comment_id": "7617780217872040753",
  "speaker_id": "1110954566492253",
  "speaker_nickname": "游走的风",
  "text": "第一眼想到泰勒，但是没有具体的想法",
  "like_count": 18,
  "reply_count": 2,
  "reply_preview_count": 1,
  "publish_time": "2026-03-23T12:31:00+08:00",
  "ip_label": "江苏",
  "is_author": false,
  "is_hot": true,
  "is_pinned": false,
  "keyword_tags": ["fact_claim"],
  "importance_score": 3.21,
  "importance_reasons": ["点赞 18", "回复 2"],
  "replies": [
    {
      "reply_id": "7617874983457620751",
      "speaker_id": "2861390065568841",
      "speaker_nickname": "考研数学欧阳蕊",
      "text": "[机智][机智][机智]",
      "like_count": 0,
      "is_author": true
    }
  ]
}
```

这部分字段会进入：

- 抓取接口返回体里的 `input_payload.comment_records`
- 数据处理模块的完整性检查
- 评论区分析模块的高互动评论分析
- 语义模块的 LLM 复判输入

## 快速启动

### 1. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

访问：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 离线 ASR 怎么下载、放到哪里

推荐目录：

- `models/asr/tiny`

这是当前项目最顺手的默认目录。只要模型放在这个目录里，页面和后端都能直接识别。

### 方式 1：用脚本自动下载

默认会把 `Systran/faster-whisper-tiny` 下载到 `models/asr/tiny`：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py
```

下载完成后，可以在页面里把“离线 ASR 模型目录”填成：

```text
models/asr/tiny
```

也可以写进 `.env`：

```env
VIDEO_ASR_MODEL_DIR=models/asr
VIDEO_ASR_MODEL_NAME=tiny
```

如果你必须显式指定绝对路径，也可以：

```env
VIDEO_ASR_MODEL_PATH=C:\path\to\models\asr\tiny
```

### 方式 2：手动放模型目录

如果你已经从别处拿到了 `faster-whisper` 的本地目录，请把包含下面文件的整个目录放进去：

- `config.json`
- `model.bin`
- `tokenizer.json` 或 `tokenizer_config.json`

目录示例：

```text
models/
└─ asr/
   └─ tiny/
      ├─ config.json
      ├─ model.bin
      └─ tokenizer.json
```

### 方式 3：Hugging Face 不通时

如果当前网络不能直连 Hugging Face，可以尝试：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py `
  --provider modelscope `
  --repo-id <你确认可用的 ModelScope 模型 ID> `
  --target-dir models/asr/tiny
```

当前我已经在本机验证过一个可用的 ModelScope 仓库 ID：

```text
gpustack/faster-whisper-tiny
```

## 页面使用流程

1. 输入抖音公开视频链接。
2. 点击“抓取并填充项目栏”。
3. 系统会自动抓取视频详情、重要评论、回复预览、OCR、ASR、音频线索和元数据。
4. 右侧“采集页”会展示结构化评论，不只是纯文本列表。
5. 如有需要，手工修改左侧文本框内容。
6. 点击“启动多模块分析”查看总览页和各模块详情。

## 接口

### 1. 抖音链接采集

```http
POST /api/v1/fetch/url
Content-Type: application/json
```

示例：

```json
{
  "source_url": "https://www.douyin.com/jingxuan?modal_id=7589926461256027430",
  "max_comments": 20,
  "process_video": true,
  "frame_interval_seconds": 4,
  "max_frames": 6,
  "asr_model_path": "models/asr/tiny"
}
```

返回体会同时包含：

- `input_payload.comments`
- `input_payload.comment_records`
- `source.comment_count_scanned`
- `source.comment_selection_strategy`

### 2. 多模块分析

```http
POST /api/v1/analyze
Content-Type: application/json
```

请求体就是左侧分析表单当前内容。

## 测试

单元测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

前端脚本语法检查：

```powershell
node --check app/static/app.js
```

建议每次改完以下部分都跑一遍：

- 抓取器和评论筛选逻辑
- 视频处理链路
- 前端展示层
- LLM 接口层

## 当前已接入的 LLM

项目已经预留统一 provider，并已给 `semantic_context` 接入结构化 JSON 复判。当前推荐通过 `.env` 配置：

```env
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_API_KEY=你的密钥
```

接口不可用时，系统会自动退回本地规则，不会把整条分析链打断。

## 如果你准备继续接 Agent / API / 训练

我当前的建议是：

1. 先继续把 `semantic_context` 和 `comment_analysis` 做成统一 JSON 输出的 LLM 模块。
2. 保持 `audiovisual_content` 先走专用视觉/音频模型，不要急着全部交给通用 LLM。
3. 不要现在就训练。先积累比赛样本、评论结构数据和误报样本，再决定是否做分类器或 LoRA。
4. 训练前先做评测集，至少分为高风险、低风险、争议样本和对抗样本。

更详细的建议见 [docs/agent-integration.md](/c:/Users/admin/Desktop/information-security/docs/agent-integration.md)。

## 当前进度适合 GitHub 展示什么

这个仓库现在已经适合公开展示：

- 一个能跑通的短视频内容安全原型系统
- 一条从抖音链接到多模块研判的完整链路
- 一套结构化重要评论的抓取与分析框架
- 一套离线 ASR 友好的工程化复现方案

## 后续最值得做的事

1. 把真正比赛要用的离线中文 ASR 模型固定下来，并在 `models/asr/` 下留出统一目录规范。
2. 给 `comment_analysis` 接入时间序列和账号画像，继续提升控评/刷评识别能力。
3. 给 `semantic_context` 增加事实核验外部检索和可追溯证据链。
4. 建立比赛样本集和误报样本集，开始做模块级评测。
