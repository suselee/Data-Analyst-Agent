import os
import shutil
import pandas as pd
import chainlit as cl
import json
from chainlit.input_widget import Select, TextInput

from config import PROVIDERS, CHART_DIR_ABS, UPLOAD_DIR_ABS
from agent_setup import create_agent


# Get admin credentials from environment or use default
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

@cl.password_auth_callback
def auth(username, password):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return cl.User(identifier=username)
    return None

@cl.on_chat_start
async def on_chat_start():
    # Clean temp_charts/ once per session to avoid showing stale files
    if os.path.exists(CHART_DIR_ABS):
        shutil.rmtree(CHART_DIR_ABS, ignore_errors=True)
    os.makedirs(CHART_DIR_ABS, exist_ok=True)

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR_ABS, exist_ok=True)

    # Setup ChatSettings to replace the Streamlit sidebar
    provider_options = list(PROVIDERS.keys())

    # Check env vars for default keys
    env_keys = {
        name: os.environ.get(prov.env_key_name, "")
        for name, prov in PROVIDERS.items()
    }

    # Load user preferences if available
    user = cl.user_session.get("user")
    user_settings = {}
    if user and os.path.exists("user_settings.json"):
        try:
            with open("user_settings.json", "r", encoding="utf-8") as f:
                all_settings = json.load(f)
                user_settings = all_settings.get(user.identifier, {})
        except Exception as e:
            print(f"Error loading user settings: {e}")

    initial_provider = user_settings.get("provider", "DeepSeek")
    if initial_provider not in provider_options:
        initial_provider = "DeepSeek"

    initial_provider_index = provider_options.index(initial_provider)
    initial_model_id = user_settings.get("model_id", "deepseek-chat")
    initial_api_key = user_settings.get("api_key", env_keys.get(initial_provider, ""))
    initial_base_url = user_settings.get("base_url", "")

    settings = await cl.ChatSettings(
        [
            Select(
                id="provider",
                label="选择供应商 (LLM Provider)",
                values=provider_options,
                initial_index=initial_provider_index,
            ),
            TextInput(
                id="model_id",
                label="模型 ID",
                initial=initial_model_id,
            ),
            TextInput(
                id="api_key",
                label="API Key",
                initial=initial_api_key,
            ),
            TextInput(
                id="base_url",
                label="Base URL (仅用于 OpenAI Like 供应商)",
                initial=initial_base_url,
            ),
        ]
    ).send()

    # Store initial settings
    cl.user_session.set("settings", settings)
    cl.user_session.set("dataframes", {})
    cl.user_session.set("agent", None)

    await cl.Message(
        content="欢迎来到数据分析 Agent！\n请在设置中配置你的 API Key，并点击对话框左侧的 📎 按钮上传 Excel / CSV 数据文件以开始分析。"
    ).send()


@cl.on_settings_update
async def on_settings_update(settings):
    cl.user_session.set("settings", settings)

    # Save user preferences
    user = cl.user_session.get("user")
    if user:
        try:
            all_settings = {}
            if os.path.exists("user_settings.json"):
                with open("user_settings.json", "r", encoding="utf-8") as f:
                    all_settings = json.load(f)

            all_settings[user.identifier] = settings

            with open("user_settings.json", "w", encoding="utf-8") as f:
                json.dump(all_settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving user settings: {e}")

    provider_name = settings["provider"]
    provider = PROVIDERS[provider_name]

    # Auto-update model_id if it's deeply changed or empty
    current_model = settings["model_id"]
    if not current_model or current_model not in provider.models:
         settings["model_id"] = provider.default_model

    # Initialize or recreate the agent if API key is provided and data is available
    api_key = settings["api_key"]
    dataframes = cl.user_session.get("dataframes", {})

    if api_key:
        try:
            agent = create_agent(
                provider_name=provider_name,
                api_key=api_key,
                model_id=settings["model_id"],
                base_url=settings["base_url"],
                dataframes=dataframes,
            )
            cl.user_session.set("agent", agent)
            await cl.Message(content=f"已更新配置，当前供应商为 **{provider_name}**，模型为 **{settings['model_id']}**。").send()
        except Exception as e:
            await cl.Message(content=f"❌ 创建 Agent 失败：{str(e)}").send()
    else:
         cl.user_session.set("agent", None)
         await cl.Message(content="⚠️ 请在设置中配置 API Key。").send()


@cl.on_message
async def on_message(message: cl.Message):
    settings = cl.user_session.get("settings", {})
    api_key = settings.get("api_key", "")
    provider_name = settings.get("provider", "DeepSeek")
    model_id = settings.get("model_id", "deepseek-chat")
    base_url = settings.get("base_url", "")

    dataframes = cl.user_session.get("dataframes", {})
    agent = cl.user_session.get("agent", None)

    # Process file uploads
    if message.elements:
        for element in message.elements:
            if element.mime in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
                "text/csv",
            ]:
                await cl.Message(content=f"⏳ 正在读取文件 {element.name}...").send()
                try:
                    # Copy uploaded file to the fixed upload directory
                    safe_filename = os.path.basename(element.name)
                    save_path = os.path.join(UPLOAD_DIR_ABS, safe_filename)
                    shutil.copy2(element.path, save_path)

                    ext = os.path.splitext(safe_filename)[1].lower()

                    uploaded_dfs = {}
                    if ext in [".xlsx", ".xls"]:
                        sheets = pd.read_excel(save_path, sheet_name=None)
                        for sheet_name, df in sheets.items():
                            df_key = f"{os.path.splitext(safe_filename)[0]}_{sheet_name}"
                            dataframes[df_key] = df
                            uploaded_dfs[df_key] = df
                    elif ext == ".csv":
                        df = pd.read_csv(save_path)
                        df_key = os.path.splitext(safe_filename)[0]
                        dataframes[df_key] = df
                        uploaded_dfs[df_key] = df

                    cl.user_session.set("dataframes", dataframes)
                    await cl.Message(content=f"✅ 成功加载文件 **{safe_filename}** 并保存至上传目录！").send()

                    # Display the first 5 rows of each loaded DataFrame
                    for df_name, df in uploaded_dfs.items():
                        df_preview = df.head(5)
                        elements = [
                            cl.Dataframe(
                                name=f"{df_name} Preview",
                                data=df_preview,
                                display="inline"
                            )
                        ]
                        await cl.Message(
                            content=f"**{df_name}** 概览 (前5行):",
                            elements=elements
                        ).send()
                except Exception as e:
                    await cl.Message(content=f"❌ 读取文件 {element.name} 失败：{str(e)}").send()

        # Re-create agent if new data loaded and API key exists
        if api_key and dataframes:
            try:
                agent = create_agent(
                    provider_name=provider_name,
                    api_key=api_key,
                    model_id=model_id,
                    base_url=base_url,
                    dataframes=dataframes,
                )
                cl.user_session.set("agent", agent)
            except Exception as e:
                await cl.Message(content=f"❌ 创建 Agent 失败：{str(e)}").send()

    # Process prompt
    if not message.content.strip() and message.elements:
        return  # Only files uploaded, no text prompt

    if not agent:
        if not api_key:
            await cl.Message(content="⚠️ 请先在设置中配置 API Key。").send()
        elif not dataframes:
            await cl.Message(content="⚠️ 请先上传 Excel 或 CSV 文件作为分析数据。").send()
        else:
            await cl.Message(content="⚠️ Agent 未就绪，请检查配置和数据文件。").send()
        return

    # Call Agno Agent
    ui_message = cl.Message(content="")
    await ui_message.send()

    try:
        original_cwd = os.getcwd()
        os.makedirs(CHART_DIR_ABS, exist_ok=True)
        os.chdir(CHART_DIR_ABS)

        try:
            # We don't have cl.Step deeply integrated inside Agno callbacks yet,
            # so we use stream_events=True to extract RunOutput and tool calls
            response_stream = agent.run(message.content, stream=True, stream_events=True)

            tool_steps = {} # Track active tool steps

            for event in response_stream:
                event_type = getattr(event, "event", "")

                # Content streaming
                if event_type in ("RunContent", "RunIntermediateContent", "TeamRunContentEvent", "StepOutputEvent"):
                    content = getattr(event, "content", None)
                    if content:
                        await ui_message.stream_token(str(content))

                # Tool Execution
                elif event_type == "ToolCallCompleted":
                    tool_exec = getattr(event, "tool", None)
                    if tool_exec:
                        tool_name = getattr(tool_exec, "tool_name", "unknown")
                        tool_args = str(getattr(tool_exec, "tool_args", ""))
                        tool_result = str(getattr(tool_exec, "result", ""))[:2000]

                        step = cl.Step(name=tool_name, type="tool")
                        step.input = tool_args
                        step.output = tool_result
                        await step.send()

        finally:
            os.chdir(original_cwd)

        await ui_message.update()

        # Scan for generated files
        if os.path.exists(CHART_DIR_ABS):
            elements = []
            for root, _dirs, filenames in os.walk(CHART_DIR_ABS):
                for fname in filenames:
                    file_path = os.path.join(root, fname)
                    ext = os.path.splitext(fname)[1].lower()

                    if fname == "数据分析报告.html":
                        elements.append(cl.File(name=fname, path=file_path, display="inline"))
                    elif ext in [".png", ".jpg", ".jpeg"]:
                        elements.append(cl.Image(name=fname, path=file_path, display="inline"))
                    elif ext in [".html", ".xlsx", ".xls", ".csv"]:
                        elements.append(cl.File(name=fname, path=file_path, display="inline"))

            if elements:
                await cl.Message(
                    content="生成的文件和图表：",
                    elements=elements
                ).send()

    except Exception as e:
        if current_step:
            current_step.status = "FAILED"
            await current_step.update()
        await cl.Message(content=f"❌ 分析时出错: {str(e)}").send()
