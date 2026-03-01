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
from agno.team import Team
from agno.workflow import Workflow

from config import CHART_DIR, CHART_DIR_ABS, PROVIDERS


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

    # Configure PandasTools
    pandas_tools = PandasTools()
    pandas_tools.dataframes = dict(dataframes)

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
    }
    for sheet_name, df in dataframes.items():
        var_name = f"df_{sheet_name}".replace(" ", "_").replace("-", "_")
        safe_locals[var_name] = df
    # Also provide a simple "df" alias when there's only one sheet
    if len(dataframes) == 1:
        safe_locals["df"] = list(dataframes.values())[0]

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
        "你有两类工具可以使用：",
        "1. **PandasTools**: 用于数据探索和分析操作（如查看数据形状、描述统计、筛选、分组聚合等）。",
        "2. **PythonTools**: 用于执行 Python 代码，尤其是用 Plotly 生成可视化图表。",
        "",
        "当前可用的数据：",
        df_info,
        "",
        "可视化规范：",
        "- 使用 plotly.express (px) 或 plotly.graph_objects (go) 创建图表",
        "- 图表保存方式: `fig.write_html(os.path.join(CHART_DIR, '描述性名称.html'))`，或 `fig.write_image(os.path.join(CHART_DIR, '描述性名称.png'))`",
        "- CHART_DIR 变量已预定义，直接使用即可，不要自己定义路径",
        "- 绝对不要调用 `fig.show()`",
        "- 确保图表有中文标题和轴标签",
        "",
        "文件导出规范：",
        "- 当用户需要导出数据时，使用 `df.to_excel(os.path.join(CHART_DIR, '描述性名称.xlsx'), index=False)` 或 `df.to_csv(os.path.join(CHART_DIR, '描述性名称.csv'), index=False)` 保存文件",
        "- 始终使用 os.path.join(CHART_DIR, '文件名') 构建保存路径",
        "- 文件保存后页面上会自动出现下载按钮供用户下载",
        "",
        "报告生成规范：",
        "- 当用户要求生成报告时，创建一个自包含的 HTML 报告文件",
        "- 报告中使用内嵌的 Plotly 图表（通过 fig.to_html(full_html=False, include_plotlyjs='cdn') 获取图表 HTML 片段）",
        "- 报告应包含：标题、数据概述、图表可视化、数据表格、文字分析和结论",
        "- 报告保存方式: 将完整 HTML 字符串写入 `os.path.join(CHART_DIR, '报告名称.html')`",
        "- 使用 `with open(os.path.join(CHART_DIR, '报告名称.html'), 'w', encoding='utf-8') as f: f.write(html_content)`",
        "",
        "回答规范：",
        "- 先分析数据，再给出结论",
        "- 如果需要可视化，先说明你要创建什么图表，然后生成",
        "- 数值结果请给出具体数字",
        "",
        "错误处理规范：",
        "- 当工具调用返回错误时，你必须分析错误信息，修正参数或换一种方法重试，绝对不要停下来",
        "- 如果 PandasTools 报错，改用 PythonTools 直接写 pandas 代码实现同样的操作",
        "- 如果某个方法不可用，尝试等价的替代方法",
        "- 最多重试 3 次不同的方案，如果仍然失败，向用户说明原因并给出建议",
    ]

    if len(dataframes) > 1:
        data_agent = Agent(
            name="数据分析专员",
            role="负责使用 Pandas 处理、分析和统计数据",
            model=model,
            tools=[pandas_tools],
            instructions=["请使用 PandasTools 对数据进行深入分析，提取有价值的结论。不要自己尝试画图。"],
            markdown=True,
            db=InMemoryDb(),
            session_id="app_session",
            add_history_to_context=True,
            num_history_runs=5,
        )
        vis_agent = Agent(
            name="数据可视化专员",
            role="负责使用 Python 代码生成 Plotly 可视化图表",
            model=model,
            tools=[python_tools],
            instructions=["请使用 PythonTools 和 Plotly 生成美观的可视化图表，严格遵守图表保存和导出的规范。"],
            markdown=True,
            db=InMemoryDb(),
            session_id="app_session",
            add_history_to_context=True,
            num_history_runs=5,
        )

        team_instructions = instructions.copy()
        team_instructions.append("- 这是一个多数据表分析任务，你需要协调数据分析专员和数据可视化专员共同完成任务。")

        agent = Team(
            name="数据分析团队",
            members=[data_agent, vis_agent],
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions=team_instructions,
            markdown=True,
            db=InMemoryDb(),
            session_id="app_session",
            add_history_to_context=True,
            num_history_runs=5,
            retries=3,
        )
        return agent
    else:
        single_agent = Agent(
            model=model,
            tools=[pandas_tools, python_tools, ReasoningTools(add_instructions=True)],
            instructions=instructions,
            markdown=True,
            db=InMemoryDb(),
            session_id="app_session",
            add_history_to_context=True,
            num_history_runs=5,
            retries=3,
        )
        workflow = Workflow(steps=[single_agent])
        return workflow
