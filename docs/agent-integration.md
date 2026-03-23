# Agent 调用与训练建议

这份文档基于当前重构后的新架构来写：系统已经不再是散乱的多个 agent 文件，而是 5 个顶层模块，其中 4 个负责独立分析，1 个负责综合决策。

当前结构：

- `data_collection`
- `audiovisual_content`
- `semantic_context`
- `comment_analysis`
- `comprehensive_decision`

## 总体建议

如果你后面准备自己接 API，我的建议不是“给所有模块都上大模型”，而是：

1. 继续保留 `data_collection` 做规则化输入层。
2. 优先给 `semantic_context` 接 LLM。
3. 第二优先给 `comment_analysis` 接 LLM。
4. `audiovisual_content` 先接视觉模型、音频模型，再考虑是否接 VLM。
5. `comprehensive_decision` 不直接做大模型自由生成，而是吃结构化子模块结果后再整合。

## 为什么这样分

### 1. data_collection 不适合先上 LLM

这个模块的职责是：

- 清洗输入
- 标准化字段
- 评估采集完整性
- 评估元数据可信度

它本质上是一个“结构化预处理模块”，更适合规则和校验逻辑，而不是 LLM。

### 2. semantic_context 最值得优先接 LLM

这个模块负责：

- 显性违规
- 隐性规避表达
- 黑话、缩写、反串
- 事实断言

这一类问题对上下文和语义推理依赖最强，是当前最值得优先使用 LLM 的地方。

### 3. comment_analysis 第二优先

这个模块负责：

- 评论极化
- 情绪对立
- 异常引流
- 重复评论与刷评

如果评论文本量较大，LLM 对识别“群体语气、站队升级、隐性带节奏”会比纯规则更有效。

### 4. audiovisual_content 不建议先上通用 LLM

这个模块更像多模态专用任务：

- 关键帧识别
- 敏感场景识别
- 音频事件分类
- 音画证据对齐

优先级应该是：

1. 视觉模型 / VLM
2. 音频事件分类器
3. 时间戳对齐

而不是直接把原始内容全部丢给通用 LLM。

### 5. comprehensive_decision 只做结构化整合

这个模块不适合直接变成“一个会写长报告的大模型”。

更推荐让它做：

- 风险分数整合
- 证据拼接
- 建议去重
- 下一步动作生成

如果未来要接 LLM，也应该只让它在结构化输入上做“解释增强”，而不是替代全部模块。

## 推荐的 API 集成方式

建议做统一 provider 层，而不是把 API 调用散落到每个模块里。

推荐抽象：

```python
class LLMProvider:
    def complete_json(self, system_prompt: str, user_payload: dict) -> dict:
        ...
```

模块只负责：

1. 组装输入
2. 消费 JSON 输出

不要让模块自己管理：

- `api_key`
- `base_url`
- `timeout`
- `retry`
- `json parsing`

这些都应该统一在 provider 层处理。

## 推荐的模块接入顺序

### 第一阶段

先接一个 `semantic_context` 的 LLM 版本。

目标：

- 判断隐性违规
- 判断规避表达
- 判断事实断言强度
- 输出结构化证据

### 第二阶段

再给 `comment_analysis` 接 LLM。

目标：

- 判断评论区极化
- 判断舆论引导
- 判断隐性带节奏
- 输出高风险评论摘要

### 第三阶段

最后考虑给 `audiovisual_content` 接 VLM 或更强视觉模型。

目标：

- 从关键帧直接抽语义
- 从图像识别高风险对象、动作、场景
- 让音画证据形成更强闭环

## 推荐的输出格式

不管哪个模块接 LLM，都建议输出统一 JSON：

- `risk_score`
- `risk_level`
- `summary`
- `evidence`
- `recommendations`
- `confidence`

其中 `evidence` 最好固定成数组，每一项包含：

- `source`
- `excerpt`
- `reason`

这样可以直接映射到当前项目已经在用的 `ModuleFinding` 结构。

## 训练建议

### 当前阶段

当前阶段不要急着训练大模型。更务实的顺序是：

1. 先接 API
2. 先做样本积累
3. 先做评测
4. 再决定是否训练

### 什么时候值得训练

当你们具备下面条件时，再考虑训练：

- 至少 1000+ 条较高质量标注样本
- 风险标签定义稳定
- 已经有固定评测集
- 已经知道 API 版本的主要误判类型

### 优先训练什么

推荐顺序：

1. `comment_analysis` 小分类器或排序器
2. `semantic_context` 的 LoRA / SFT
3. `audiovisual_content` 的专用视觉或音频模型

## 比赛阶段最现实的路线

如果目标是比赛落地，我建议：

1. 先维持当前 5 模块架构不动。
2. 先给 `semantic_context` 接统一 LLM provider。
3. 再给 `comment_analysis` 接统一 LLM provider。
4. `comprehensive_decision` 继续保留规则整合，不要过早改成黑箱总控。
5. 等样本和评测集稳定后，再考虑训练。
