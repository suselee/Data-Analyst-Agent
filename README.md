# 数据分析 Agent (Data-Analyst-Agent)

基于 Chainlit 和 Agno 构建的智能数据分析智能体（Agent）。它能够理解自然语言指令，通过调用大语言模型（LLM）配合强大的 Pandas 和 Python 工具，自动完成数据处理、探索性分析、可视化图表生成和专业分析报告的编写。

## ✨ 主要特性

- **多模型支持**：无缝对接主流大模型，目前支持：
  - DeepSeek (deepseek-chat, deepseek-reasoner)
  - Kimi (moonshot 系列)
  - MiniMax (MiniMax-M2.5)
- **智能数据处理**：通过 `PandasTools` 和 `PythonTools` 对上传的 CSV 或 Excel 结构化数据进行筛选、聚合、统计等复杂操作。
- **高级可视化**：基于 Plotly 生成交互式图表，**自动内嵌**显示在对话页面中。
- **文件导出**：支持将分析结果导出为 Excel/CSV 文件，生成的文件自动附带下载按钮。
- **自动化报告生成**：将分析结论、数据表格和可视化图表整合，生成自包含的 HTML 格式数据分析报告。
- **稳定的长时间分析**：Agent 在后台线程中运行，防止长时间数据处理导致 WebSocket 超时断连。
- **浏览器兼容性**：内置 Firefox IME 输入修复和 Chrome 109 (Win7) API polyfill。
- **友好的 Web 交互**：基于 Chainlit 构建的响应式界面，支持文件上传、一键分析和设置面板。

## 📦 项目结构

```text
├── app.py                  # Chainlit 应用主入口（含线程化 Agent 执行）
├── agent_setup.py          # Agent 核心逻辑：提示词配置、工具挂载及实例化
├── config.py               # 配置文件：模型服务商参数与路径设定
├── requirements.txt        # Python 依赖清单
├── chainlit.md             # Chainlit 欢迎页内容
├── .env.example            # 环境变量配置参考
├── public/
│   ├── styles.css          # 自定义 UI 样式
│   └── compat.js           # 浏览器兼容性修复（Firefox IME / Chrome 109）
├── .chainlit/
│   └── config.toml         # Chainlit 框架配置
└── temp_charts/            # 运行时产生的临时图表及报告存放目录（已 gitignore）
```

## 🛠️ 安装与运行

### 1. 环境准备

确保您的本地环境已安装 **Python 3.10+**。

克隆本仓库到本地：

```bash
git clone https://github.com/suselee/Data-Analyst-Agent.git
cd Data-Analyst-Agent
```

### 2. 安装依赖

推荐使用虚拟环境进行依赖安装：

```bash
python -m venv venv
source venv/bin/activate  # Windows 下请使用 venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 文件并重命名为 `.env`：

```bash
cp .env.example .env
```

在 `.env` 文件中填入配置（API Key 也可在页面上直接输入）：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
MOONSHOT_API_KEY=your_kimi_api_key
MINIMAX_API_KEY=your_minimax_api_key
CHAINLIT_AUTH_SECRET=your_auth_secret
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

### 4. 启动应用

```bash
chainlit run app.py -w
```

服务启动后，浏览器打开 `http://localhost:8000`，使用配置的管理员账号登录后即可开始使用。

## 💡 使用指南

1. **选择模型与配置**：在页面设置面板中选择 LLM 提供商和模型，填入 API Key。
2. **上传数据**：点击对话框左侧 📎 按钮上传 Excel 或 CSV 文件。
3. **自然语言对话**：在聊天框中直接提问，例如：
   - "帮我查看一下这份数据的基本描述性统计信息"
   - "绘制柱状图展示各类别的销量总和"
   - "将筛选后的数据导出为 Excel 文件"
   - "基于当前数据生成一份完整的数据分析报告"
4. **查看结果**：图表自动内嵌在对话中，导出文件自动显示下载按钮。

## 📝 依赖说明

主要依赖包括但不限于：
- `chainlit` (>=1.1.0): 响应式 Web UI 框架
- `agno` (>=1.2.0): Agent 开发框架
- `pandas` (>=2.0.0), `numpy`: 数据处理基础库
- `plotly` (>=5.18.0): 交互式可视化库
- `openpyxl`: Excel 文件读取支持
