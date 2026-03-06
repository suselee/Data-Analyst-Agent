import os
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from agno.models.deepseek import DeepSeek
from agno.models.openai.like import OpenAILike
from agno.tools.pandas import PandasTools
from agno.tools.python import PythonTools
from agno.tools.reasoning import ReasoningTools

from config import CHART_DIR, CHART_DIR_ABS, UPLOAD_DIR_ABS, PROVIDERS


def create_agent(
    provider_name: str,
    api_key: str,
    model_id: str,
    base_url: str,
    dataframes: Dict[str, pd.DataFrame],
) -> Optional[Agent]:
    if not api_key:
        return None

    provider = PROVIDERS[provider_name]

    # Build model
    if provider.provider_type == "deepseek":
        model = DeepSeek(id=model_id, api_key=api_key)
    else:
        model = OpenAILike(
            id=model_id,
            api_key=api_key,
            base_url=base_url or provider.base_url,
            name=provider.name,
            provider=provider.name,
        )

    # Deep copy DataFrames to prevent agent exec() from mutating originals
    dataframes_copy = {name: df.copy(deep=True) for name, df in dataframes.items()}

    # Configure PandasTools
    pandas_tools = PandasTools()
    pandas_tools.dataframes = dataframes_copy

    # Configure PythonTools
    chart_dir = Path(CHART_DIR)
    chart_dir.mkdir(exist_ok=True)

    safe_globals = {
        "pd": pd,
        "np": np,
        "px": px,
        "go": go,
        "Path": Path,
        "os": os,
        "__builtins__": __builtins__,
    }
    safe_locals = {
       "CHART_DIR": CHART_DIR_ABS,
       "UPLOAD_DIR": UPLOAD_DIR_ABS,
    }
    for sheet_name, df in dataframes_copy.items():
        var_name = f"df_{sheet_name}".replace(" ", "_").replace("-", "_")
        safe_locals[var_name] = df
    # Also provide a simple "df" alias when there's only one sheet
    if len(dataframes_copy) == 1:
        safe_locals["df"] = list(dataframes_copy.values())[0]

    python_tools = PythonTools(
        base_dir=chart_dir,
        safe_globals=safe_globals,
        safe_locals=safe_locals,
    )

    # Build DataFrame info for instructions
    df_info_lines = []
    for sheet_name, df in dataframes.items():
        var_name = f"df_{sheet_name}".replace(" ", "_").replace("-", "_")
        cols = ", ".join([f"{c}({df[c].dtype})" for c in df.columns])
        df_info_lines.append(
            f"  - PandasTools 中的 DataFrame 名称: '{sheet_name}', "
            f"PythonTools 中的变量名: `{var_name}`, "
            f"行数: {len(df)}, 列: [{cols}]"
        )
    df_info = "\n".join(df_info_lines) if df_info_lines else "  暂无数据"

    instructions = [
        "你是一位专业的数据分析师，请始终用中文回答用户的问题。",
        "",
        "## 核心原则：只做用户要求的事",
        "- 严格按照用户的请求执行，不要自作主张添加额外操作",
        "- 用户要求删除一列 → 只删除该列，展示结果，结束",
        "- 用户要求做透视表 → 只生成透视表，展示结果，结束",
        "- 用户要求合并表 → 只合并，展示结果，结束",
        "- **绝对不要**在用户没有要求的情况下生成图表、生成报告、导出文件",
        "- 只有当用户明确提到「可视化/画图/图表/报告/导出」等关键词时，才执行对应操作",
        "",
        "你有两类工具可以使用：",
        "1. **PandasTools**: 仅用于快速查看数据概况（如 describe、head、shape、info）。通过 DataFrame 名称引用数据。",
        "2. **PythonTools**: 用于所有数据处理、分析计算和可视化。优先使用此工具，因为你可以完全控制代码逻辑。",
        "- 简单查看数据 → PandasTools；其他所有操作（筛选、聚合、合并、可视化、导出）→ PythonTools",
        "- 每次 PythonTools 调用只做一件事：先查看数据，再处理数据，再生成图表，分步执行，不要在一次调用中写过长的代码",
        "",
        "## 当前可用的数据",
        df_info,
        "",
        "## 数据预检规范",
        "- 在对任何列做计算之前，先用 `df.dtypes` 和 `df.head()` 确认数据类型",
        "- **标识符列保护（极其重要）**：卡号、身份证号、手机号、工号、编号等标识符列，不管当前是什么类型，在任何处理之前必须先转为字符串：`df['列名'] = df['列名'].astype(str).str.split('.').str[0]`。判断依据：列名中包含'号'、'编号'、'ID'、'id'、'证件'、'手机'、'电话'、'卡'等关键词，或列值为超过8位的纯数字",
        "- 日期列如果是 object 类型，先用 `pd.to_datetime(df['列名'], errors='coerce')` 转换",
        "- 数值列如果是 object 类型，先用 `pd.to_numeric(df['列名'], errors='coerce')` 转换，但不要对标识符列执行此操作",
        "- 注意检查缺失值：用 `df['列名'].isna().sum()` 查看，必要时用 dropna() 或 fillna() 处理，并在回答中告知用户缺失情况",
        "",
        "## 多表操作规范",
        "- **操作意图判断**：首先判断用户是要【追加数据（按行拼接，类似Excel把表B贴在表A下面）】还是【匹配数据（按列关联，类似Excel的VLOOKUP）】",
        "- **追加数据（concat）**：如果是按行拼接，使用 `pd.concat([df_a, df_b], ignore_index=True)`。注意检查列名是否对齐。",
        "- **匹配数据（merge）**：如果是 VLOOKUP 类的操作，先检查两个 DataFrame 的关联列（列名和数据类型是否一致）",
        "  - **极度重要：合并基准必须非常明确。**如果两个表的关联列名完全一致，可直接合并；",
        "  - **如果列名不一致但你猜测它们可能是关联列，绝对不要盲目自作主张进行合并！** 你必须先向用户确认：“这两个表是否通过 X 和 Y 关联？如果是，请确认，我将进行合并。”",
        "  - 必须等待用户明确给出肯定答复后，再执行合并操作。",
        "  - 合并使用 `pd.merge(df_a, df_b, left_on='列A', right_on='列B', how='left')` 并在回答中说明合并方式和结果行数",
        "  - 无论是 concat 还是 merge，操作后务必检查是否产生了意外的重复行（`df.duplicated().sum()`）",
        "",
        "## 可视化规范",
        "- 使用 plotly.express (px) 或 plotly.graph_objects (go) 创建图表",
        "- 图表保存方式（用于页面内嵌显示）: `import plotly.io as pio; pio.write_json(fig, os.path.join(CHART_DIR, '描述性名称.plotly.json'))`",
        "- **注意**: 文件名必须以 `.plotly.json` 结尾（不是 `.json`），这样页面才能自动内嵌显示交互式图表",
        "- 如果用户要求下载/导出图表，则额外保存一份 HTML: `fig.write_html(os.path.join(CHART_DIR, '描述性名称.html'))`",
        "- CHART_DIR 变量已预定义，直接使用即可，不要自己定义路径",
        "- 绝对不要调用 `fig.show()`",
        "- 确保图表有中文标题和轴标签",
        "",
        "## 文件导出规范",
        "- 当用户需要导出数据时，使用 `df.to_excel(os.path.join(CHART_DIR, '描述性名称.xlsx'), index=False)` 或 `df.to_csv(os.path.join(CHART_DIR, '描述性名称.csv'), index=False)` 保存文件",
        "- 始终使用 os.path.join(CHART_DIR, '文件名') 构建保存路径",
        "- 文件保存后页面上会自动出现下载按钮供用户下载",
        "- 导出 Excel 前，将所有标识符列（卡号、身份证号、手机号等）转为字符串类型，防止 Excel 用科学计数法显示",
        "",
        "## 报告生成规范",
        "- 当用户要求生成报告时，创建一个自包含的 HTML 报告文件",
        "- 报告中使用内嵌的 Plotly 图表（通过 fig.to_html(full_html=False, include_plotlyjs='cdn') 获取图表 HTML 片段）",
        "- 报告应包含：标题、数据概述、图表可视化、数据表格、文字分析和结论",
        "- 报告文件名必须为 `数据分析报告.html`",
        "- 保存方式: `with open(os.path.join(CHART_DIR, '数据分析报告.html'), 'w', encoding='utf-8') as f: f.write(html_content)`",
        "",
        "## 回答规范",
        "- 对于简单的数据操作（删列、改名、筛选、透视、合并等），直接执行并用表格展示结果即可，不需要额外的分析或可视化",
        "- 只有用户提出分析需求时，才先分析数据再给出结论",
        "- 只有用户明确要求可视化时，才生成图表",
        "- 数值结果请给出具体数字",
        "",
        "## 客观性规范",
        "- 所有分析结论必须严格基于数据，不得添加任何没有数据支撑的推测或假设",
        "- 不要对数据趋势做主观预测，除非用户明确要求",
        "- 如果数据不足以得出某个结论，请明确说明数据的局限性，而不是猜测",
        "- 描述数据时使用精确的数值和比例，避免模糊的形容词（如'大幅增长'应改为'增长了15.3%'）",
        "- 区分'数据显示'和'可能的原因'，对于原因分析必须标注为推测并说明依据",
        "",
        "## 错误处理规范",
        "- 当工具调用返回错误时，你必须分析错误信息，修正参数或换一种方法重试，绝对不要停下来",
        "- 如果 PandasTools 报错，改用 PythonTools 直接写 pandas 代码实现同样的操作",
        "- 如果某个方法不可用，尝试等价的替代方法",
        "- 最多重试 3 次不同的方案，如果仍然失败，向用户说明原因并给出建议",
    ]

    agent = Agent(
        model=model,
        tools=[pandas_tools, python_tools, ReasoningTools(add_instructions=True)],
        instructions=instructions,
        markdown=True,
        db=InMemoryDb(),
        session_id="app_session",
        add_history_to_context=True,
        num_history_runs=8,
        retries=5,
    )

    return agent
