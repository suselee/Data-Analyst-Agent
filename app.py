import asyncio
import os
import shutil
import pandas as pd
import chainlit as cl
import json
import plotly.io as pio
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


async def _run_agent_query(query: str):
    """Reusable helper: run agent query with streaming, nested tool steps, and file scanning.

    Agent 在后台线程中以同步模式运行，防止 PythonTools exec() 阻塞事件循环
    导致 WebSocket 超时断连。文件扫描在 finally 中始终执行。
    """
    agent = cl.user_session.get("agent", None)
    if not agent:
        await cl.Message(content="⚠️ Agent 未就绪，请检查配置和数据文件。").send()
        return

    ui_message = cl.Message(content="")
    await ui_message.send()

    os.makedirs(CHART_DIR_ABS, exist_ok=True)
    event_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _agent_worker():
        """在独立线程中同步运行 Agent，通过队列传递流式事件。"""
        saved_cwd = os.getcwd()
        try:
            os.chdir(CHART_DIR_ABS)
            print(f"[Agent] 开始执行, CWD={os.getcwd()}, CHART_DIR={CHART_DIR_ABS}")
            for ev in agent.run(query, stream=True, stream_events=True):
                loop.call_soon_threadsafe(event_queue.put_nowait, ("event", ev))
        except Exception as exc:
            print(f"[Agent] 执行出错: {exc}")
            loop.call_soon_threadsafe(event_queue.put_nowait, ("error", exc))
        finally:
            os.chdir(saved_cwd)
            loop.call_soon_threadsafe(event_queue.put_nowait, ("done", None))

    # 在后台线程启动 Agent
    thread_future = loop.run_in_executor(None, _agent_worker)

    # 在主事件循环中消费事件（WebSocket 保持活跃）
    agent_error = None
    try:
        while True:
            msg_type, data = await event_queue.get()

            if msg_type == "done":
                break
            elif msg_type == "error":
                agent_error = data
                # 不要 raise —— 继续等 "done" 信号以确保线程结束
                continue
            elif msg_type == "event":
                event_type = getattr(data, "event", "")

                # Content streaming
                if event_type in ("RunContent", "RunIntermediateContent", "TeamRunContentEvent", "StepOutputEvent"):
                    content = getattr(data, "content", None)
                    if content:
                        await ui_message.stream_token(str(content))

                # Tool Execution — nested under response message, collapsed
                elif event_type == "ToolCallCompleted":
                    tool_exec = getattr(data, "tool", None)
                    if tool_exec:
                        tool_name = getattr(tool_exec, "tool_name", "unknown")
                        tool_args = str(getattr(tool_exec, "tool_args", ""))
                        tool_result = str(getattr(tool_exec, "result", ""))[:2000]

                        step = cl.Step(
                            name=tool_name,
                            type="tool",
                            show_input=False,
                        )
                        step.input = tool_args
                        step.output = tool_result
                        await step.send()
    except Exception as e:
        agent_error = e

    finally:
        # 等待后台线程彻底完成（确保所有文件已写入磁盘）
        try:
            await thread_future
        except Exception:
            pass

        try:
            await ui_message.update()
        except Exception:
            pass

        if agent_error:
            await cl.Message(content=f"❌ 分析时出错: {str(agent_error)}").send()

        # 文件扫描始终执行（无论 Agent 是否出错）
        await _scan_and_send_files()


async def _scan_and_send_files():
    """扫描 CHART_DIR_ABS 中生成的文件，发送为 Chainlit 元素。"""
    if not os.path.exists(CHART_DIR_ABS):
        return

    elements = []
    try:
        all_files = []
        for root, _dirs, filenames in os.walk(CHART_DIR_ABS):
            for fname in filenames:
                all_files.append(os.path.join(root, fname))

        print(f"[文件扫描] CHART_DIR: {CHART_DIR_ABS}, 找到 {len(all_files)} 个文件: {all_files}")

        for file_path in all_files:
            fname = os.path.basename(file_path)
            ext = os.path.splitext(fname)[1].lower()

            if fname.endswith(".plotly.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        fig = pio.from_json(f.read())
                    display_name = fname.replace(".plotly.json", "")
                    elements.append(cl.Plotly(name=display_name, figure=fig, display="inline"))
                    print(f"[文件扫描] Plotly 图表: {fname}")
                except Exception as e:
                    print(f"[文件扫描] Plotly 解析失败 {fname}: {e}, 改为文件下载")
                    elements.append(cl.File(name=fname, path=file_path, display="inline"))
            elif ext in [".png", ".jpg", ".jpeg"]:
                elements.append(cl.Image(name=fname, path=file_path, display="inline"))
                print(f"[文件扫描] 图片: {fname}")
            elif ext == ".html":
                elements.append(cl.File(name=fname, path=file_path, display="inline"))
                print(f"[文件扫描] HTML 文件: {fname}")
            elif ext in [".xlsx", ".xls", ".csv"]:
                elements.append(cl.File(name=fname, path=file_path, display="inline"))
                print(f"[文件扫描] 数据文件: {fname}")
            elif ext == ".py":
                pass  # 跳过 PythonTools 生成的 .py 脚本文件
            else:
                print(f"[文件扫描] 跳过未知文件: {fname}")

    except Exception as e:
        print(f"[文件扫描] 扫描出错: {e}")

    if elements:
        print(f"[文件扫描] 发送 {len(elements)} 个元素")
        await cl.Message(
            content="📊 生成的文件和图表：",
            elements=elements
        ).send()
    else:
        print("[文件扫描] 没有找到可显示的文件")



@cl.on_chat_start
async def on_chat_start():
    # 仅在真正的新会话时清空临时目录（非重连）
    # 重连时 user_session 可能已有数据，此时不应清空
    existing_dataframes = cl.user_session.get("dataframes", None)
    if existing_dataframes is None:
        # 全新会话，安全清空临时目录
        for d in (CHART_DIR_ABS, UPLOAD_DIR_ABS):
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
    else:
        # 重连场景，仅确保目录存在
        for d in (CHART_DIR_ABS, UPLOAD_DIR_ABS):
            os.makedirs(d, exist_ok=True)

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

    # Store settings
    cl.user_session.set("settings", settings)
    cl.user_session.set("dataframes", {})
    cl.user_session.set("agent", None)

    # 根据 API Key 状态显示不同的欢迎信息
    api_key = settings.get("api_key", "")
    provider_name = settings.get("provider", "DeepSeek")
    if api_key:
        await cl.Message(
            content=f"当前供应商：**{provider_name}**，API Key 已配置。\n"
                    f"请点击对话框左侧的 📎 按钮上传 Excel / CSV 数据文件以开始分析。"
        ).send()
    else:
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


# --- Action callbacks ---

@cl.action_callback("one_click_analyze")
async def on_one_click_analyze(action: cl.Action):
    dataframes = cl.user_session.get("dataframes", {})
    df_names = ", ".join(dataframes.keys())
    query = f"请对以下数据进行全面分析，包括数据概览、描述统计、异常值检测，并生成可视化图表：{df_names}"
    await _run_agent_query(query)


@cl.action_callback("export_results")
async def on_export_results(action: cl.Action):
    dataframes = cl.user_session.get("dataframes", {})
    df_names = ", ".join(dataframes.keys())
    query = f"请将以下数据导出为 Excel 文件：{df_names}"
    await _run_agent_query(query)


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

                    # Merged upload message: single message with all sheet summaries
                    summary_lines = [f"**{safe_filename}** 加载成功\n"]
                    preview_elements = []
                    for df_name, df_data in uploaded_dfs.items():
                        rows, cols = df_data.shape
                        summary_lines.append(f"> **{df_name}** — {rows:,} 行 x {cols} 列")
                        preview_elements.append(
                            cl.Dataframe(
                                name=f"{df_name} Preview",
                                data=df_data.head(5),
                                display="inline"
                            )
                        )

                    # Action buttons for quick operations
                    actions = [
                        cl.Action(
                            name="one_click_analyze",
                            payload={"action": "analyze"},
                            label="一键分析",
                            tooltip="对上传的数据进行全面分析并生成可视化图表",
                        ),
                        cl.Action(
                            name="export_results",
                            payload={"action": "export"},
                            label="导出结果",
                            tooltip="将数据导出为 Excel 文件",
                        ),
                    ]

                    await cl.Message(
                        content="\n".join(summary_lines),
                        elements=preview_elements,
                        actions=actions,
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

    await _run_agent_query(message.content)
