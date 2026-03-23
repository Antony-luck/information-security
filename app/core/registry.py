from __future__ import annotations

from app.models.schemas import ModuleProfile


MODULE_REGISTRY = [
    ModuleProfile(
        module_id="data_collection",
        module_name="数据处理与采集模块",
        module_group="基础采集与预处理",
        detection_goal="负责输入清洗、字段标准化、采集完整性评估和元数据可信度检查。",
    ),
    ModuleProfile(
        module_id="audiovisual_content",
        module_name="音画内容分析模块",
        module_group="音画内容分析",
        detection_goal="负责画面风险、音频异常和音画协同线索的独立判断。",
    ),
    ModuleProfile(
        module_id="semantic_context",
        module_name="语义与上下文分析模块",
        module_group="文本语义分析",
        detection_goal="负责显性违规、隐性规避表达和事实断言风险的独立判断。",
    ),
    ModuleProfile(
        module_id="comment_analysis",
        module_name="评论区分析模块",
        module_group="评论生态分析",
        detection_goal="负责群体极化、异常引流、刷评和评论区传播生态的独立判断。",
    ),
    ModuleProfile(
        module_id="comprehensive_decision",
        module_name="综合决策模块",
        module_group="协调与决策",
        detection_goal="负责整合前四个独立模块的结论，输出总体风险、处置建议和下一步动作。",
    ),
]
