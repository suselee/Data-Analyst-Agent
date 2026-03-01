import os
import glob
import streamlit as st
import streamlit.components.v1 as components

from config import CHART_DIR_ABS


def _scan_chart_files() -> list:
    if not os.path.exists(CHART_DIR_ABS):
        return []
    files = glob.glob(os.path.join(CHART_DIR_ABS, "*.html"))
    files.sort(key=os.path.getmtime)
    return files


def _scan_data_files() -> list:
    if not os.path.exists(CHART_DIR_ABS):
        return []
    files = []
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        files.extend(glob.glob(os.path.join(CHART_DIR_ABS, ext)))
    files.sort(key=os.path.getmtime)
    return files


def _render_data_overview():
    dataframes = st.session_state.get("dataframes", {})
    if not dataframes:
        st.info("请在侧边栏上传 Excel 文件以开始分析")
        return

    st.subheader("数据概览")
    for sheet_name, df in dataframes.items():
        with st.expander(f"Sheet: {sheet_name}", expanded=len(dataframes) == 1):
            st.write(f"**行数:** {len(df)}　**列数:** {len(df.columns)}")
            st.dataframe(df.head(), use_container_width=True)
            col1, col2 = st.columns(2)
            with col1:
                st.write("**字段类型**")
                st.dataframe(
                    df.dtypes.reset_index().rename(
                        columns={"index": "列名", 0: "类型"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            with col2:
                st.write("**统计摘要**")
                st.dataframe(df.describe(), use_container_width=True)


def _render_charts():
    chart_files = _scan_chart_files()
    if not chart_files:
        return

    st.subheader("图表与报告展示")
    for chart_path in reversed(chart_files):
        chart_name = os.path.splitext(os.path.basename(chart_path))[0]
        with st.expander(chart_name, expanded=True):
            with open(chart_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            components.html(html_content, height=500, scrolling=True)
            st.download_button(
                label=f"下载 {chart_name}.html",
                data=html_content,
                file_name=f"{chart_name}.html",
                mime="text/html",
                key=f"dl_chart_{chart_name}",
            )


def _render_process_log():
    logs = st.session_state.get("process_log", [])
    if not logs:
        return

    with st.expander("分析过程", expanded=False):
        for entry in logs:
            tool_name = entry.get("tool", "unknown")
            args_str = entry.get("args", "")
            result_str = entry.get("result", "")
            st.markdown(f"**{tool_name}**")
            if args_str:
                st.code(args_str, language="python")
            if result_str:
                display = (
                    result_str if len(result_str) < 2000 else result_str[:2000] + "..."
                )
                st.text(display)
            st.divider()


def _render_chat():
    st.subheader("对话")

    # Render message history
    for msg in st.session_state.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("请输入你的分析需求..."):
        agent = st.session_state.get("agent")
        if not agent:
            st.error("请先配置 API Key 并上传数据文件")
            return

        # Display user message
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Agent response with streaming
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""
            tool_logs = []

            try:
                original_cwd = os.getcwd()
                os.makedirs(CHART_DIR_ABS, exist_ok=True)
                os.chdir(CHART_DIR_ABS)
                try:
                    response_stream = agent.run(prompt, stream=True, stream_events=True)
                    last_run_output = None

                    for event in response_stream:
                        event_type = getattr(event, "event", "")

                        # Content streaming events
                        if event_type in ("RunContent", "RunIntermediateContent"):
                            content = getattr(event, "content", None)
                            if content:
                                full_response += str(content)
                                placeholder.markdown(full_response + "▌")

                        # Tool call completed events - capture for process log
                        elif event_type == "ToolCallCompleted":
                            tool_exec = getattr(event, "tool", None)
                            if tool_exec:
                                log_entry = {
                                    "tool": getattr(tool_exec, "tool_name", "unknown"),
                                    "args": str(
                                        getattr(tool_exec, "tool_args", "")
                                    ),
                                    "result": str(
                                        getattr(tool_exec, "result", "")
                                    )[:2000],
                                }
                                tool_logs.append(log_entry)

                        # Final RunOutput - capture the complete content
                        if hasattr(event, "content") and hasattr(event, "messages"):
                            last_run_output = event
                finally:
                    os.chdir(original_cwd)

                # If streaming didn't produce content, get it from final output
                if not full_response and last_run_output:
                    content = getattr(last_run_output, "content", "")
                    if content:
                        full_response = str(content)

                placeholder.markdown(full_response or "（无输出）")

                # If no tool logs from events, try extracting from RunOutput
                if not tool_logs and last_run_output:
                    messages = getattr(last_run_output, "messages", [])
                    if messages:
                        for msg in messages:
                            tool_calls = getattr(msg, "tool_calls", None)
                            if tool_calls:
                                for tc in tool_calls:
                                    func = (
                                        tc.get("function", {})
                                        if isinstance(tc, dict)
                                        else getattr(tc, "function", None)
                                    )
                                    if func:
                                        name = (
                                            func.get("name", "")
                                            if isinstance(func, dict)
                                            else getattr(func, "name", "")
                                        )
                                        arguments = (
                                            func.get("arguments", "")
                                            if isinstance(func, dict)
                                            else getattr(func, "arguments", "")
                                        )
                                        tool_logs.append(
                                            {"tool": name, "args": str(arguments)}
                                        )
                            role = getattr(msg, "role", "")
                            if role == "tool" and tool_logs:
                                content = getattr(msg, "content", "")
                                tool_logs[-1]["result"] = (
                                    str(content)[:2000] if content else ""
                                )

                st.session_state["process_log"].extend(tool_logs)

            except Exception as e:
                full_response = f"出错了: {str(e)}"
                placeholder.markdown(full_response)

        st.session_state["messages"].append(
            {"role": "assistant", "content": full_response}
        )

        # Scan for new charts
        st.session_state["chart_files"] = _scan_chart_files()

        # Rerun to show new charts and process log
        st.rerun()


def _handle_report_generation():
    if not st.session_state.get("report_generating"):
        return

    agent = st.session_state.get("agent")
    report_request = st.session_state.get("report_request", "")
    if not agent or not report_request:
        st.session_state["report_generating"] = False
        return

    st.subheader("报告生成中...")
    prompt = (
        f"请根据以下需求生成一份完整的数据分析报告：\n\n{report_request}\n\n"
        "要求：\n"
        "1. 生成一个自包含的 HTML 报告文件，文件名为 '数据分析报告.html'\n"
        "2. 报告中内嵌 Plotly 图表（使用 fig.to_html(full_html=False, include_plotlyjs='cdn') 获取图表片段）\n"
        "3. 报告应包含：标题、数据概述、可视化图表、数据表格、文字分析和结论\n"
        "4. 使用美观的 HTML/CSS 样式排版\n"
        "5. 将报告保存到 os.path.join(CHART_DIR, '数据分析报告.html')\n"
        "6. 报告中所有结论和分析必须严格基于数据，不得包含任何没有数据支撑的推测性内容\n"
        "7. 每个结论必须引用具体的数据指标（数值、百分比、排名等），禁止使用没有量化依据的模糊描述\n"
    )

    with st.spinner("正在生成报告，请稍候..."):
        try:
            original_cwd = os.getcwd()
            os.makedirs(CHART_DIR_ABS, exist_ok=True)
            os.chdir(CHART_DIR_ABS)
            try:
                agent.run(prompt)
            finally:
                os.chdir(original_cwd)

            report_path = os.path.join(CHART_DIR_ABS, "数据分析报告.html")
            if not os.path.exists(report_path):
                st.warning("报告生成未成功：未找到报告文件，请重试。")
            else:
                st.session_state["messages"].append(
                    {"role": "user", "content": f"[报告生成请求] {report_request}"}
                )
                st.session_state["messages"].append(
                    {"role": "assistant", "content": "报告已生成，请在页面上方查看和下载。"}
                )
        except Exception as e:
            st.error(f"报告生成出错: {str(e)}")

    st.session_state["report_generating"] = False
    st.session_state["report_request"] = ""
    st.rerun()


def _render_generated_files():
    data_files = _scan_data_files()
    if not data_files:
        return

    st.subheader("生成文件")
    for file_path in reversed(data_files):
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        ext = os.path.splitext(file_name)[1].lower()
        mime = {
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".csv": "text/csv",
        }.get(ext, "application/octet-stream")
        st.download_button(
            label=f"下载 {file_name}",
            data=file_bytes,
            file_name=file_name,
            mime=mime,
            key=f"dl_file_{file_name}",
        )


def render_main_area():
    _render_data_overview()
    _handle_report_generation()
    _render_charts()
    _render_generated_files()
    _render_process_log()
    _render_chat()
