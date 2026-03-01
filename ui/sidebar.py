import os
import glob
import pandas as pd
import streamlit as st

from config import PROVIDERS, CHART_DIR_ABS
from agent_setup import create_agent
from utils.session import config_changed, update_config_hash


def _render_sidebar_downloads():
    """Render download buttons for generated files in the sidebar."""
    if not os.path.exists(CHART_DIR_ABS):
        return

    # Scan data files
    data_files = []
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        data_files.extend(glob.glob(os.path.join(CHART_DIR_ABS, ext)))
    data_files.sort(key=os.path.getmtime)

    # Check for report
    report_path = os.path.join(CHART_DIR_ABS, "数据分析报告.html")
    has_report = os.path.exists(report_path)

    if not data_files and not has_report:
        return

    st.divider()
    st.header("文件下载")

    # Report download (primary, prominent)
    if has_report:
        with open(report_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        st.download_button(
            label="下载数据分析报告",
            data=html_content,
            file_name="数据分析报告.html",
            mime="text/html",
            key="dl_sidebar_report",
            type="primary",
        )

    # Data file downloads
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
            key=f"dl_sidebar_{file_name}",
        )


def render_sidebar():
    with st.sidebar:
        st.header("LLM 配置")

        # Provider selection
        provider_name = st.selectbox(
            "选择供应商",
            options=list(PROVIDERS.keys()),
            index=list(PROVIDERS.keys()).index(st.session_state["provider"]),
            key="provider_select",
        )
        st.session_state["provider"] = provider_name
        provider = PROVIDERS[provider_name]

        # Model selection
        model_id = st.text_input(
            "模型 ID",
            value=st.session_state.get("model_id") or provider.default_model,
            key="model_input",
        )
        st.session_state["model_id"] = model_id

        # API Key
        env_key = os.environ.get(provider.env_key_name, "")
        api_key = st.text_input(
            "API Key",
            value=st.session_state.get("api_key") or env_key,
            type="password",
            key="api_key_input",
        )
        st.session_state["api_key"] = api_key

        # Base URL (only for OpenAILike providers)
        if provider.provider_type == "openai_like":
            base_url = st.text_input(
                "Base URL",
                value=st.session_state.get("base_url") or provider.base_url,
                key="base_url_input",
            )
            st.session_state["base_url"] = base_url
        else:
            st.session_state["base_url"] = ""

        # Rebuild agent if config changed
        if config_changed() and st.session_state["api_key"]:
            st.session_state["agent"] = create_agent(
                provider_name=st.session_state["provider"],
                api_key=st.session_state["api_key"],
                model_id=st.session_state["model_id"],
                base_url=st.session_state["base_url"],
                dataframes=st.session_state.get("dataframes", {}),
            )
            update_config_hash()

        st.divider()

        # Data upload
        st.header("数据上传")
        uploaded_files = st.file_uploader(
            "上传 Excel 文件", type=["xlsx", "xls"], accept_multiple_files=True
        )

        if uploaded_files:
            current_names = {f.name for f in uploaded_files}
            prev_names = st.session_state.get("uploaded_file_names", set())

            if current_names != prev_names:
                with st.spinner("读取 Excel 文件..."):
                    all_sheets = {}
                    for f in uploaded_files:
                        sheets = pd.read_excel(f, sheet_name=None)
                        fname = os.path.splitext(f.name)[0]
                        for sheet_name, df in sheets.items():
                            all_sheets[f"{fname}_{sheet_name}"] = df
                    st.session_state["all_sheets"] = all_sheets
                    st.session_state["uploaded_file_names"] = current_names

            all_sheets = st.session_state.get("all_sheets", {})
            if all_sheets:
                sheet_names = list(all_sheets.keys())
                selected_sheets = st.multiselect(
                    "选择要分析的 Sheet",
                    options=sheet_names,
                    default=sheet_names,
                    key="sheet_select",
                )

                new_dataframes = {
                    name: all_sheets[name] for name in selected_sheets
                }

                # Update dataframes and rebuild agent if data changed
                if set(new_dataframes.keys()) != set(
                    st.session_state["dataframes"].keys()
                ):
                    st.session_state["dataframes"] = new_dataframes
                    if st.session_state["api_key"]:
                        st.session_state["agent"] = create_agent(
                            provider_name=st.session_state["provider"],
                            api_key=st.session_state["api_key"],
                            model_id=st.session_state["model_id"],
                            base_url=st.session_state["base_url"],
                            dataframes=new_dataframes,
                        )
                        update_config_hash()
                elif not st.session_state["dataframes"] and new_dataframes:
                    st.session_state["dataframes"] = new_dataframes

        # Clear data button
        if st.session_state.get("dataframes"):
            if st.button("清除数据", type="secondary"):
                st.session_state["dataframes"] = {}
                st.session_state["uploaded_file_names"] = set()
                st.session_state["all_sheets"] = {}
                st.session_state["chart_files"] = []
                st.session_state["messages"] = []
                st.session_state["process_log"] = []
                st.session_state["agent"] = None
                st.session_state["report_generating"] = False
                st.session_state["report_request"] = ""
                import shutil
                if os.path.exists(CHART_DIR_ABS):
                    shutil.rmtree(CHART_DIR_ABS, ignore_errors=True)
                st.rerun()

        # Report generation
        if st.session_state.get("agent") and st.session_state.get("dataframes"):
            st.divider()
            st.header("报告生成")
            report_request = st.text_area(
                "报告需求",
                placeholder="例如：生成各医院汇款金额对比条形图、占比饼图和汇总表格",
                key="report_request_input",
            )
            if st.button("生成报告", type="primary"):
                if report_request.strip():
                    st.session_state["report_generating"] = True
                    st.session_state["report_request"] = report_request.strip()
                    st.rerun()
                else:
                    st.warning("请输入报告需求")

        # Sidebar downloads
        _render_sidebar_downloads()

        # Status indicator
        st.divider()
        if st.session_state.get("agent"):
            st.success("Agent 就绪")
        elif not st.session_state.get("api_key"):
            st.warning("请输入 API Key")
        elif not st.session_state.get("dataframes"):
            st.info("请上传数据文件")
