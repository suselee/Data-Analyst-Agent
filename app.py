import os
import shutil
import pandas as pd
import chainlit as cl

from config import PROVIDERS, CHART_DIR_ABS
from agent_setup import create_agent

@cl.on_chat_start
async def on_chat_start():
    # Configure the chat settings (Provider, Model, API Key)
    settings = cl.ChatSettings(
        [
            cl.input_widget.Select(
                id="provider",
                label="选择供应商",
                values=list(PROVIDERS.keys()),
                initial_index=0,
            ),
            cl.input_widget.TextInput(
                id="model_id",
                label="模型 ID (可选，留空则使用默认模型)",
                initial="",
            ),
            cl.input_widget.TextInput(
                id="api_key",
                label="API Key (如果已在环境变量中配置，此处可留空)",
                initial="",
            ),
            cl.input_widget.TextInput(
                id="base_url",
                label="Base URL (如果是自定义的 OpenAI 兼容接口需填写)",
                initial="",
            ),
        ]
    )
    await settings.send()

    # Build initial settings dictionary manually
    initial_settings = {
        "provider": list(PROVIDERS.keys())[0],
        "model_id": "",
        "api_key": "",
        "base_url": ""
    }

    # Store settings in session
    await setup_agent_from_settings(initial_settings)

    # Send a welcome message asking for data upload
    await request_data_upload()


@cl.on_settings_update
async def setup_agent_from_settings(settings):
    provider_name = settings["provider"]
    provider = PROVIDERS[provider_name]

    model_id = settings.get("model_id") or provider.default_model

    # Check API key: user input or environment variable
    api_key = settings.get("api_key")
    if not api_key:
        api_key = os.environ.get(provider.env_key_name, "")

    base_url = settings.get("base_url")
    if not base_url and provider.provider_type == "openai_like":
        base_url = provider.base_url

    cl.user_session.set("provider", provider_name)
    cl.user_session.set("model_id", model_id)
    cl.user_session.set("api_key", api_key)
    cl.user_session.set("base_url", base_url)

    # Also recreate agent if dataframes exist
    dataframes = cl.user_session.get("dataframes", {})
    if dataframes and api_key:
        agent = create_agent(
            provider_name=provider_name,
            api_key=api_key,
            model_id=model_id,
            base_url=base_url,
            dataframes=dataframes
        )
        cl.user_session.set("agent", agent)


async def request_data_upload():
    # Clean up temp charts dir
    if os.path.exists(CHART_DIR_ABS):
        shutil.rmtree(CHART_DIR_ABS, ignore_errors=True)
    os.makedirs(CHART_DIR_ABS, exist_ok=True)

    res = await cl.AskFileMessage(
        content="欢迎使用数据分析 Agent！请上传要分析的 Excel 或 CSV 数据文件 (仅支持 .xlsx, .xls, .csv)。或者您可以随时点击输入框左侧的回形针图标发送文件以覆盖当前数据。",
        accept={"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
                "application/vnd.ms-excel": [".xls"],
                "text/csv": [".csv"]},
        max_size_mb=50,
        timeout=3600
    ).send()

    if res:
        uploaded_file = res[0]
        await process_uploaded_file(uploaded_file)


async def process_uploaded_file(uploaded_file):
    msg = cl.Message(content=f"正在读取文件 `{uploaded_file.name}`...")
    await msg.send()

    try:
        dataframes = {}
        ext = os.path.splitext(uploaded_file.name)[1].lower()

        if ext in [".xlsx", ".xls"]:
            sheets = pd.read_excel(uploaded_file.path, sheet_name=None)
            fname = os.path.splitext(uploaded_file.name)[0]
            for sheet_name, df in sheets.items():
                dataframes[f"{fname}_{sheet_name}"] = df
        elif ext == ".csv":
            df = pd.read_csv(uploaded_file.path)
            fname = os.path.splitext(uploaded_file.name)[0]
            dataframes[fname] = df

        cl.user_session.set("dataframes", dataframes)

        # Build agent
        api_key = cl.user_session.get("api_key")
        if not api_key:
            msg.content = "⚠️ 数据读取成功，但未配置 API Key。请在侧边栏设置配置中填写 API Key。"
            await msg.update()
            return

        agent = create_agent(
            provider_name=cl.user_session.get("provider"),
            api_key=api_key,
            model_id=cl.user_session.get("model_id"),
            base_url=cl.user_session.get("base_url"),
            dataframes=dataframes
        )
        cl.user_session.set("agent", agent)

        # Display summary and details
        summary = f"成功加载了 **{len(dataframes)}** 个数据表：\n"
        for sheet_name, df in dataframes.items():
            summary += f"\n### 表格: {sheet_name}\n"
            summary += f"**行数:** {len(df)}　**列数:** {len(df.columns)}\n"

            # Preview head
            display_df = df.head().copy()
            for col in display_df.columns:
                if display_df[col].dtype == 'object' or str(display_df[col].dtype).startswith('period') or str(display_df[col].dtype).startswith('datetime'):
                    display_df[col] = display_df[col].astype(str)

            summary += "\n**数据前 5 行预览:**\n"
            summary += display_df.to_markdown(index=False)
            summary += "\n\n**字段类型:**\n"

            dtypes_df = df.dtypes.reset_index().rename(columns={"index": "列名", 0: "类型"})
            dtypes_df['类型'] = dtypes_df['类型'].astype(str)
            summary += dtypes_df.to_markdown(index=False)

            summary += "\n\n**统计摘要:**\n"
            summary += df.describe().to_markdown()
            summary += "\n---\n"

        summary += "\n您可以开始向我提出分析需求了，例如：\n- 分析这份数据的基本情况\n- 绘制图表展示某些数据的趋势\n- 指令我使用专门的报告模版生成数据分析报告"

        msg.content = summary
        await msg.update()

    except Exception as e:
        msg.content = f"❌ 读取文件时出错: {str(e)}"
        await msg.update()


@cl.on_message
async def main(message: cl.Message):
    # Process new uploaded files from the message elements
    uploaded_files = [el for el in message.elements if isinstance(el, cl.File)]
    if uploaded_files:
        # Just use the first uploaded file for simplicity if multiple are provided
        await process_uploaded_file(uploaded_files[0])
        # If no explicit message content other than the file, return
        if not message.content.strip():
            return

    agent = cl.user_session.get("agent")
    if not agent:
        await cl.Message(content="⚠️ 请先上传数据并确保配置了 API Key。").send()
        return

    # User intention to generate a report, explicitly ask model to follow report format
    # Better heuristic: prompt user for reports or just let LLM handle it, but we can augment the prompt
    # to enforce HTML output if report keywords are matched
    report_keywords = ["生成报告", "数据分析报告", "分析报告"]
    prompt = message.content

    if any(kw in message.content for kw in report_keywords):
        prompt = (
            f"请根据以下需求生成一份完整的数据分析报告：\n\n{message.content}\n\n"
            "要求：\n"
            "1. 生成一个自包含的 HTML 报告文件，文件名为 '数据分析报告.html'\n"
            "2. 报告中内嵌 Plotly 图表（使用 fig.to_html(full_html=False, include_plotlyjs='cdn') 获取图表片段）\n"
            "3. 报告应包含：标题、数据概述、可视化图表、数据表格、文字分析和结论\n"
            "4. 使用美观的 HTML/CSS 样式排版\n"
            "5. 将报告保存到 os.path.join(CHART_DIR, '数据分析报告.html')\n"
            "6. 报告中所有结论和分析必须严格基于数据，不得包含任何没有数据支撑的推测性内容\n"
            "7. 每个结论必须引用具体的数据指标（数值、百分比、排名等），禁止使用没有量化依据的模糊描述\n"
        )

    response_msg = cl.Message(content="")
    await response_msg.send()

    os.makedirs(CHART_DIR_ABS, exist_ok=True)

    # Track current step if tools are called
    current_step = None

    try:
        # Before run, get existing files to detect newly created ones
        before_files = set(os.listdir(CHART_DIR_ABS))

        response_stream = agent.run(prompt, stream=True, stream_events=True)

        for event in response_stream:
            event_type = getattr(event, "event", "")

            if event_type in ("RunContent", "RunIntermediateContent", "TeamRunContentEvent", "StepOutputEvent"):
                content = getattr(event, "content", None)
                if content:
                    await response_msg.stream_token(str(content))

            elif event_type == "ToolCallStarted":
                tool_call = getattr(event, "tool_call", None)
                if tool_call:
                    func = tool_call.get("function", {}) if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
                    tool_name = func.get("name", "unknown") if isinstance(func, dict) else getattr(func, "name", "unknown")
                    tool_args = func.get("arguments", "") if isinstance(func, dict) else getattr(func, "arguments", "")

                    current_step = cl.Step(name=tool_name, type="tool")
                    current_step.input = tool_args
                    await current_step.send()

            elif event_type == "ToolCallCompleted":
                tool_exec = getattr(event, "tool", None)
                if tool_exec and current_step:
                    result = str(getattr(tool_exec, "result", ""))
                    current_step.output = result
                    current_step.status = "COMPLETED"
                    await current_step.update()
                    current_step = None

        await response_msg.update()

        # Detect new generated files
        after_files = set(os.listdir(CHART_DIR_ABS))
        new_files = after_files - before_files

        if new_files:
            elements = []
            for file_name in sorted(new_files):
                file_path = os.path.join(CHART_DIR_ABS, file_name)
                ext = os.path.splitext(file_name)[1].lower()

                if ext in [".png", ".jpg", ".jpeg"]:
                    elements.append(cl.Image(path=file_path, name=file_name, display="inline"))
                elif ext in [".html", ".csv", ".xlsx", ".xls"]:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    elements.append(cl.File(name=file_name, content=file_content, display="inline"))

            if elements:
                await cl.Message(
                    content="以下是为您生成的图表或文件：",
                    elements=elements
                ).send()

    except Exception as e:
        if current_step:
            current_step.status = "FAILED"
            await current_step.update()
        await cl.Message(content=f"❌ 分析时出错: {str(e)}").send()
