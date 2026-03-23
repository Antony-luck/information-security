# 面向短视频多模态融合的内容安全智能研判系统

这是一个面向比赛答辩和后续 GitHub 开源复刻的短视频内容安全原型系统。当前主流程已经固定为：

`抖音链接采集 -> 自动下载视频 -> 抽帧 + OCR + 音频提取 + ASR -> 自动回填表单 -> 独立模块分析 -> 综合决策输出`

这次重构后的重点，不是继续堆功能，而是把工程结构改成“模块独立、职责清晰、便于别人复刻和继续改进”。

## 当前架构

系统现在按 5 个顶层模块组织，全部放在 [app/modules](/c:/Users/admin/Desktop/information-security/app/modules)：

1. `data_collection`
   负责数据清洗、字段标准化、采集完整性评估、元数据可信度检查。
2. `audiovisual_content`
   负责画面风险、音频异常、音画协同线索分析。
3. `semantic_context`
   负责显性违规、隐性规避表达、事实断言和上下文语义分析。
4. `comment_analysis`
   负责评论区极化、异常引流、刷评和评论生态分析。
5. `comprehensive_decision`
   负责整合前四个独立模块的结果，输出总风险、行动建议和综合证据。

模块之间不直接相互调用。它们都只依赖统一的输入结构 `PreprocessedContent`，由综合决策模块在最后汇总。这样做的好处是：

- 每个模块都可以单独调试和替换
- 后续接入 LLM 或训练模型时，不会把整个系统绑死在一处
- GitHub 上别人可以只改某一个模块，而不用先理解整套逻辑

## 目录结构

```text
app/
├─ core/
├─ models/
├─ modules/
│  ├─ data_collection/
│  ├─ audiovisual_content/
│  ├─ semantic_context/
│  ├─ comment_analysis/
│  └─ comprehensive_decision/
├─ pipeline/
├─ services/
└─ static/
```

关键入口：

- 后端入口：[app/main.py](/c:/Users/admin/Desktop/information-security/app/main.py)
- 模块注册：[app/core/registry.py](/c:/Users/admin/Desktop/information-security/app/core/registry.py)
- 调度编排：[app/pipeline/orchestrator.py](/c:/Users/admin/Desktop/information-security/app/pipeline/orchestrator.py)
- 数据预处理：[app/modules/data_collection/preprocessor.py](/c:/Users/admin/Desktop/information-security/app/modules/data_collection/preprocessor.py)
- 综合决策：[app/modules/comprehensive_decision/coordinator.py](/c:/Users/admin/Desktop/information-security/app/modules/comprehensive_decision/coordinator.py)

## 模块说明

### 1. 数据处理与采集模块

目录：[app/modules/data_collection](/c:/Users/admin/Desktop/information-security/app/modules/data_collection)

负责：

- 输入字段清洗
- 多模态字段标准化
- 元数据默认值归一化
- 采集完整性和可信度评估

这一层不判断“内容是否违规”，只负责判断“当前样本是否足够可靠、是否足够完整，能否支撑后面的模块分析”。

### 2. 音画内容分析模块

目录：[app/modules/audiovisual_content](/c:/Users/admin/Desktop/information-security/app/modules/audiovisual_content)

负责：

- 关键帧 OCR 结果解释
- 视觉风险代理词识别
- 音频异常线索识别
- 音画协同加权

当前仍以规则和代理文本为主，但已经把真实视频处理链路接进来了，后续最适合继续接视觉模型和音频分类器。

### 3. 语义与上下文分析模块

目录：[app/modules/semantic_context](/c:/Users/admin/Desktop/information-security/app/modules/semantic_context)

负责：

- 显性违规文本识别
- 黑话、缩写、规避式表达识别
- 待核验事实断言识别
- 结合上下文做风险放大判断

这一块是后续最适合优先接 LLM 的模块。

### 4. 评论区分析模块

目录：[app/modules/comment_analysis](/c:/Users/admin/Desktop/information-security/app/modules/comment_analysis)

负责：

- 评论极化
- 冲突升级
- 异常引流
- 重复评论与刷评

这一块已经具备单独模块化能力，后续可以继续补评论时间序列和账号画像。

### 5. 综合决策模块

目录：[app/modules/comprehensive_decision](/c:/Users/admin/Desktop/information-security/app/modules/comprehensive_decision)

负责：

- 汇总独立模块结论
- 加权计算总体风险
- 生成统一总结
- 输出行动建议和下一步动作

这也是系统里唯一允许“整合其他模块结果”的模块。

## 技术亮点

- `模块彻底分层`：从原来的分散 agent，重构成 5 个可独立替换的大模块。
- `模块互不干扰`：每个模块只吃统一预处理结果，不直接依赖其他模块内部逻辑。
- `真实视频链路已接入`：支持视频下载、抽帧、OCR、音频提取、ASR、音频线索补强。
- `离线优先 ASR`：优先找本地 `faster-whisper` 模型目录，适合比赛现场或弱网环境。
- `可开源复刻`：环境变量模板、样例请求、模型下载脚本、启动脚本、README 已齐备。

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

访问：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 离线 ASR 模型

推荐把 `faster-whisper` 模型放到：

- `models/asr/tiny`
- `models/asr/small`

或在页面直接填绝对路径。

如果要用脚本下载：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py
```

如果当前环境无法直连 Hugging Face，可以尝试：

```powershell
.\.venv\Scripts\python.exe .\scripts\download_asr_model.py `
  --provider modelscope `
  --repo-id <你们确认可用的模型 ID>
```

环境变量模板见 [.env.example](/c:/Users/admin/Desktop/information-security/.env.example)。

## 页面使用

1. 输入抖音公开视频链接。
2. 点击“抓取并填充项目栏”。
3. 系统自动回填 `视频编号`、`标题`、`描述`、`ASR`、`评论`、`OCR`、`音频线索`、`元数据`。
4. 右侧可查看采集页、模块页和总览页。
5. 点击“启动多模块分析”。
6. 查看 5 个模块的独立结论和综合决策结果。

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
  "whisper_model": "tiny",
  "asr_model_path": "models/asr/tiny"
}
```

### 2. 多模块分析

```http
POST /api/v1/analyze
Content-Type: application/json
```

请求体就是页面左侧分析表单。

## 测试

单元测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

当前覆盖：

- 5 个顶层模块注册
- 抖音链接采集接口
- 多模块综合分析主流程
- 离线 ASR 模型目录识别
- 音频事件识别基础逻辑
- 视频处理回填逻辑

## 如果你准备继续接 API

如果你后面要自己接大模型 API，我的建议是：

- 优先给 `semantic_context` 接 LLM
- 第二优先给 `comment_analysis` 接 LLM
- `audiovisual_content` 更适合先接专用视觉/音频模型，不要急着交给通用 LLM
- LLM 输出一律做结构化 JSON，不要返回长自然语言
- 统一做 provider 层，不要把 API 逻辑写进每个模块里

更详细的建议在 [docs/agent-integration.md](/c:/Users/admin/Desktop/information-security/docs/agent-integration.md)。

## 当前进度适合 GitHub 展示什么

现在这个仓库已经适合公开展示以下进度：

- 一个能跑通的短视频内容安全原型系统
- 一个从抖音链接到多模块研判的完整链路
- 一个可被别人拆分和替换的模块化工程结构
- 一个已经考虑离线模型、弱网环境和后续 API 接入的开源基础版本

## 后续最值得做的事

1. 给 `semantic_context` 接统一的 LLM provider。
2. 给 `audiovisual_content` 接更强的视觉理解和音频分类模型。
3. 给 `comment_analysis` 补评论时间序列和账号画像。
4. 建立比赛样本集和评测集。
5. 把综合决策模块里的权重从人工规则升级为数据驱动。
