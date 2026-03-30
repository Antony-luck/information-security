# 基于多智能体协作的短视频社区有害内容检测与告警系统

> 技术汇报（截至 2026-03-30）  
> 面向全国信息安全大赛的工程化原型，强调“可跑通、可解释、可复现、可扩展”。

## 1. 项目目标与问题定义

本项目聚焦短视频社区场景，输入为抖音视频链接，输出为结构化风险研判结论。  
目标不是单点模型识别，而是构建一条完整、可追踪的研判流水线：

`链接采集 -> 视频处理 -> 数据标准化 -> 多模块独立研判 -> 综合决策 -> 前端证据链展示`

系统采用“多智能体协作”思想落地为 5 个职责清晰的模块：

1. 数据处理与采集模块（输入质量与可信度）
2. 音画内容分析模块（视觉/音频风险）
3. 语义与上下文分析模块（显性违规、隐性规避、事实核查）
4. 评论区分析模块（极化、冲突、引流、异常传播）
5. 综合决策模块（风险汇总、动作建议、流程追踪）

---

## 2. 当前实现范围与状态

当前代码已形成可运行闭环，核心能力如下：

- 抖音链接解析与信息抓取（含 `modal_id`、`/video/`、重定向场景）
- 视频下载（可选）+ 自动抽帧 + OCR + ASR + 音频事件线索
- 评论结构化采集与重要评论筛选（非随机抽样）
- 四个独立分析模块并行执行
- 综合决策融合输出总体风险分数和处置动作
- 前端展示全链路流程、模块证据、指标、建议
- 调试页展示“原始字段 -> 预处理字段 -> 模块去向”的完整映射

---

## 3. 架构总览

### 3.1 逻辑架构

1. API 层（`app/main.py`）负责接收请求、编排抓取和分析。
2. 采集层（`app/services/douyin.py`）负责抖音详情/评论抓取与结构化。
3. 视频处理层（`app/services/video_processing.py`）负责抽帧、OCR、ASR、音频事件。
4. 预处理层（`app/modules/data_collection/preprocessor.py`）统一标准化分段与元数据。
5. 分析层（`app/modules/*/module.py`）四模块并行判定。
6. 决策层（`app/modules/comprehensive_decision/coordinator.py`）融合输出。
7. 展示层（`app/static/*`）负责总览、流程、模块详情和数据流核查。

### 3.2 关键目录

```text
app/
  main.py                          # FastAPI 入口与路由
  pipeline/orchestrator.py         # 任务编排与并行执行
  models/schemas.py                # 全部输入输出数据结构
  services/
    douyin.py                      # 抖音采集与评论结构化
    video_processing.py            # 抽帧/OCR/ASR/音频线索
    llm_provider.py                # OpenAI-compatible LLM 封装
    fact_check_search.py           # 事实核查检索
    data_flow_trace.py             # 调试页数据流追踪
  modules/
    data_collection/               # 数据质量与可信度
    audiovisual_content/           # 音画风险
    semantic_context/              # 语义与事实核查
    comment_analysis/              # 评论生态
    comprehensive_decision/        # 综合决策
  static/                          # 前端页面与脚本
tests/                             # 单元测试与接口测试
scripts/download_asr_model.py      # 离线 ASR 模型下载脚本
```

---

## 4. 端到端流程（一次任务的执行过程）

### 步骤 A：输入链接并抓取（`POST /api/v1/fetch/url`）

系统执行：

1. 解析 `aweme_id`，优先读取 `modal_id`，否则尝试 `video/note` 路径，再回退重定向解析。
2. 请求抖音详情接口和评论接口。
3. 扫描评论候选集（通常高于最终保留数），再按策略筛选重要评论。
4. 可选下载视频并进入视频处理链路。
5. 返回：
   - `source`：采集摘要（平台、作者、发布时间、评论统计、视频路径等）
   - `input_payload`：后续分析统一输入结构

### 步骤 B：视频处理（抓取阶段内联执行）

如果 `process_video=true`，执行：

1. 抽帧：分桶采样 + 中心窗口清晰度优选 + 直方图去重。
2. OCR：基于 RapidOCR 提取帧内文字并生成抽帧摘要。
3. 音频：ffmpeg 抽取单声道 16k wav 后做启发式事件识别。
4. ASR：优先离线 faster-whisper，本地不可用时可回退在线模型。
5. 写回 `input_payload` 的 `speech_text / visual_descriptions / audio_cues / ocr_text`。

### 步骤 C：多模块分析（`POST /api/v1/analyze`）

`AnalysisOrchestrator` 执行顺序：

1. 预处理：清洗文本、生成标准化分段、补齐标准元数据。
2. 并行分析：数据采集模块 + 音画模块 + 语义模块 + 评论模块。
3. 综合决策：按权重融合模块分数，输出总风险等级与动作建议。
4. 输出可解释字段：`module_findings / pipeline_flow / execution_trace`。

---

## 5. 核心实现细节

### 5.1 数据采集与评论筛选（`app/services/douyin.py`）

#### 评论结构化字段

每条评论会构造成 `CommentRecord`，包含：

- `speaker_id / speaker_nickname / speaker_unique_id / speaker_region`
- `text / like_count / reply_count / reply_preview_count`
- `publish_time / ip_label / is_hot / is_pinned / is_author / is_verified`
- `replies[]`（回复链结构）
- `keyword_tags / importance_score / importance_reasons`

#### 评论筛选模式（`comment_selection_mode`）

1. `comprehensive`：综合重要性（互动强度+作者参与+关键词+去重）
2. `engagement`：点赞/回复/热评优先
3. `recent`：最近时间优先并带互动补偿
4. `risk`：风险关键词优先（引流、冲突、事实断言等）

说明：系统会先“扩大扫描”，再“筛选保留”，避免随机评论导致样本偏差。

### 5.2 视频处理链路（`app/services/video_processing.py`）

#### 抽帧策略

- 帧时间点生成：按视频时长分桶，限制最大帧数。
- 每个目标时点在窗口内多候选偏移采样。
- 用拉普拉斯方差评估清晰度，选清晰帧。
- 用 HSV 直方图相关性做去重，减少重复场景。

#### OCR

- 引擎：`rapidocr-onnxruntime`（`RapidOCR`）。
- 输出：
  - `ocr_text[]`：纯文本
  - `visual_descriptions[]`：带时间戳的抽帧摘要描述
  - `frames[]`：关键帧路径与资源 URL

#### ASR（在线/离线）

- 引擎：`faster-whisper`
- 离线优先：
  - 若给定 `asr_model_path` 或本地命中 `VIDEO_ASR_MODEL_DIR`，走离线目录。
  - 若开启 `VIDEO_ASR_OFFLINE_ONLY=1` 且无本地模型，则不回退在线。
- 在线回退：
  - 仅在离线未命中且未强制离线时，按模型名在线加载。
- 转写参数：
  - `beam_size=3`, `language=zh`, `vad_filter=True`, `condition_on_previous_text=False`
- 产物：
  - `speech_text`
  - 带时间戳的语音片段线索（写入 `audio_cues`）

#### 音频事件线索

使用信号处理启发式特征进行事件分类（RMS、ZCR、谱质心、频段能量等）：

- 疑似爆炸/冲击高能音
- 疑似警报/蜂鸣
- 疑似尖叫/高频喊叫

### 5.3 预处理标准化（`app/modules/data_collection/preprocessor.py`）

预处理会统一生成：

- `normalized_segments`：标题、描述、语音、评论、回复、标签、OCR、音频线索等分段
- `combined_text`：主文本拼接语料
- `comment_corpus`：评论及回复语料
- `standardized_metadata`：补齐默认值并计算衍生统计

### 5.4 四个独立模块实现

#### 数据处理与采集模块（`data_collection`）

关注输入质量与可信度：

- 模态覆盖检查（标题/描述/语音/评论/OCR/音画线索）
- 结构化评论覆盖率、回复链覆盖率
- 扫描评论数与入选评论数关系
- 来源认证、作者认证、账号年龄、地域一致性

输出风险标签如：`模态覆盖不足`、`评论结构化偏弱`、`来源未认证` 等。

#### 音画内容分析模块（`audiovisual_content`）

规则层 + LLM 复核：

- 规则层关键词扫描视觉线索与音频线索
- 音画协同加权（例如暴力画面 + 暴力音频共现）
- 可调用 LLM 输出 `risk_score/summary/tags/evidence/recommendations`

#### 语义与上下文分析模块（`semantic_context`）

重点实现了“规则+检索+LLM”三段式：

1. 显性违规和隐性规避关键词扫描
2. 候选事实断言提取与外部检索核查
3. LLM 语义复判与事实核查补充

最后将规则结果和 LLM 结果融合，避免只看字面文本。

#### 评论区分析模块（`comment_analysis`）

关注评论生态与传播风险：

- 极端正/负表达并存（极化）
- 冲突对喷、导流引流
- 重复评论比例、突发评论比例
- 回复链活跃度、账号集中度
- 可调用 LLM 做评论生态复核

### 5.5 综合决策模块（`comprehensive_decision`）

#### 加权聚合

默认权重：

- `data_collection`: 0.55
- `audiovisual_content`: 1.15
- `semantic_context`: 1.20
- `comment_analysis`: 0.95

并加入跨模块协同增益（例如语义高风险 + 评论高风险同时出现）。

#### 输出内容

- `overall_risk_level / overall_risk_score`
- 统一摘要
- 去重后的建议动作
- `next_actions`（例如人工复核、证据导出、二次核查）

---

## 6. 事实核查与大模型接入

### 6.1 事实核查检索（`app/services/fact_check_search.py`）

- 首选 DuckDuckGo Instant Answer
- 回退中文维基开放搜索
- 对检索结果做轻量规则判定：支持 / 反证 / 未核实 / 不确定
- 将结果写入证据链并影响语义模块风险增量

### 6.2 大模型统一接入（`app/services/llm_provider.py`）

采用 OpenAI-compatible 接口：

- 支持 `qwen/openai/openai_compatible/custom/deepseek`
- 统一请求格式：`/chat/completions`
- 强制 JSON 输出解析，失败抛出 `LLMProviderError`
- 模块侧只关心结构化结果，不耦合 API 细节

---

## 7. 前端与可解释展示

主页面：`/`  
调试页：`/debug/flow`  
接口文档：`/docs`

主页面能力：

- 顶部模块导航（总览、流程、采集、各分析模块）
- 链接输入与采集限制配置
- 一键抓取 + 一键多模块分析
- 模块详情页展示：风险等级、摘要、证据、指标、建议
- 长文本折叠与完整文本下载，保持页面可读性

调试页能力：

- 展示原始输入字段预览（field trace）
- 展示预处理分段与数量（segment trace）
- 展示元数据字段被哪些模块消费（metadata trace）
- 展示模块路由映射（module routes）

---

## 8. 关键数据结构

核心模型定义在 `app/models/schemas.py`：

- `AnalysisInput`：统一分析输入
- `CommentRecord / CommentReply`：结构化评论与回复
- `PreprocessedContent`：预处理后的标准内容容器
- `ModuleFinding`：模块输出（含指标、证据、步骤）
- `AnalysisOutput`：最终输出（含流程与执行轨迹）
- `VideoProcessingSummary`：视频处理过程摘要

可解释性关键字段：

- `module_findings[*].workflow_steps`
- `module_findings[*].metrics`
- `pipeline_flow`
- `execution_trace`

---

## 9. API 一览

1. `GET /health`：运行状态与关键配置摘要
2. `GET /api/v1/modules`：模块注册清单
3. `POST /api/v1/fetch/url`：链接采集并返回结构化输入
4. `POST /api/v1/debug/flow`：采集 + 预处理数据流核查
5. `POST /api/v1/analyze`：执行完整多模块分析

`POST /api/v1/fetch/url` 请求示例：

```json
{
  "source_url": "https://www.douyin.com/jingxuan?modal_id=7589926461256027430",
  "max_comments": 20,
  "comment_selection_mode": "comprehensive",
  "process_video": true,
  "frame_interval_seconds": 4,
  "max_frames": 6,
  "asr_model_path": "models/asr/tiny"
}
```

---

## 10. 环境准备与快速启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

启动后访问：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/debug/flow`
- `http://127.0.0.1:8000/docs`

---

## 11. 配置说明（`.env`）

参考 `.env.example`，建议至少配置：

```env
APP_NAME=基于多智能体协作的短视频社区有害内容检测与告警系统

LLM_PROVIDER=qwen
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=你的API密钥
LLM_MODEL=qwen-plus
LLM_API_PATH=/chat/completions
LLM_TIMEOUT_SECONDS=60

FACT_CHECK_SEARCH_ENABLED=1
FACT_CHECK_MAX_QUERIES=3
FACT_CHECK_TIMEOUT_SECONDS=10

VIDEO_ASR_MODEL_DIR=models/asr
VIDEO_ASR_MODEL_NAME=tiny
VIDEO_ASR_OFFLINE_ONLY=1
```

注意：

- 不要把真实 API Key 提交到 GitHub。
- 线上环境建议通过系统环境变量注入密钥。

---

## 12. 离线 ASR 模型准备

推荐目录：`models/asr/tiny`

默认下载（Hugging Face）：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py
```

网络受限时可使用 ModelScope：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py `
  --provider modelscope `
  --repo-id gpustack/faster-whisper-tiny `
  --target-dir models/asr/tiny
```

脚本会自动校验目录是否为可用 `faster-whisper` 模型格式。

---

## 13. 测试与当前结果

在虚拟环境中执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前结果（2026-03-30）：

- 共 20 项测试，全部通过（`OK`）
- 覆盖接口、采集、评论筛选、语义事实核查、视频处理、编排流程等关键路径

前端脚本语法检查：

```powershell
node --check app/static/app.js
node --check app/static/trace.js
```

---

## 14. 技术亮点（可用于比赛答辩）

1. 多模块并行 + 综合决策收敛的工程化架构。
2. 评论数据结构化采集，支持发言人、互动量、回复链、重要性评分。
3. 抽帧/OCR/ASR/音频线索的可复现视频处理链路。
4. 语义模块采用“规则 + 外部检索 + LLM”复合事实核查机制。
5. 全流程可解释输出（证据、指标、步骤、执行轨迹）并可前端对照展示。
6. 提供数据流核查页，支持答辩场景下字段去向追踪。

---

## 15. 已知限制

1. 音频事件识别当前为启发式规则，尚未接入专用深度模型。
2. 事实核查检索源仍是轻量公网源，稳定性和覆盖度可继续提升。
3. 当前以单机同步 API 流程为主，尚未引入异步任务队列。
4. 数据持久化与历史任务管理（数据库）未完成。

---

## 16. 下一步建议

1. 接入稳定国内检索 API，增强事实核查证据可信度。
2. 音频事件改造为模型化分类器，降低启发式误差。
3. 引入数据库保存任务、证据与分析版本，支持可审计回溯。
4. 建设标注集与评测看板，量化误报漏报与模块贡献。
5. 按竞赛规则补充告警分级处置策略与证据导出模板。
