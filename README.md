# 数据分析 Agent (Data-Analyst-Agent)

基于 Streamlit 和 Agno 构建的智能数据分析智能体（Agent）。它能够理解自然语言指令，通过调用大语言模型（LLM）配合强大的 Pandas 和 Python 工具，自动完成数据处理、探索性分析、可视化图表生成和专业分析报告的编写。

## ✨ 主要特性

- **多模型支持**：无缝对接主流大模型，目前支持：
  - DeepSeek (deepseek-chat, deepseek-reasoner)
  - Kimi (moonshot 系列)
  - MiniMax (MiniMax-M2.5)
- **智能数据处理**：通过底层的 `PandasTools` 直接对上传的 CSV 或 Excel 结构化数据进行筛选、聚合、统计等复杂操作。
- **高级可视化**：基于 `Plotly` (`plotly.express`, `plotly.graph_objects`) 生成交互式图表（支持自定义保存为 HTML 供在线预览和下载）。
- **自动化报告生成**：能够将分析结论、数据表格和可视化图表整合，生成自包含的 HTML 格式数据分析报告。
- **友好的 Web 交互**：基于 Streamlit 构建的响应式界面，支持多对话历史和图表、报告等文件的直接下载。

## 📦 项目结构

```text
├── app.py                  # Streamlit 应用主入口
├── agent_setup.py          # Agent 核心逻辑：提示词配置、工具挂载及实例化
├── config.py               # 配置文件：模型服务商参数与路径设定
├── requirements.txt        # Python 依赖清单
├── .env.example            # 环境变量配置参考
├── ui/                     # UI 组件模块（侧边栏、主区域渲染逻辑）
├── utils/                  # 辅助工具模块（如 session 状态管理）
└── temp_charts/            # 运行时产生的临时图表及报告存放目录
```

## 🛠️ 安装与运行

### 1. 环境准备

确保您的本地环境已安装 **Python 3.8+**。

克隆本仓库到本地：

```bash
git clone <your-repo-url>
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

在 `.env` 文件中填入您拥有的 API 密钥（如果在页面上直接输入则可省略此步）：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
MOONSHOT_API_KEY=your_kimi_api_key
MINIMAX_API_KEY=your_minimax_api_key
```

### 4. 启动应用

在终端中运行以下命令启动 Streamlit 服务：

```bash
streamlit run app.py
```

服务启动后，通常会自动在浏览器中打开 `http://localhost:8501`。在侧边栏配置您的 API Key（如果未在 `.env` 中设置），上传数据文件后即可开始与数据分析 Agent 对话。

## 💡 使用指南

1. **上传数据**：支持多工作表的 Excel 或是单张 CSV 文件。
2. **选择模型**：在左侧边栏根据需要选择要调用的 LLM 提供商及具体模型。
3. **自然语言对话**：在聊天框中直接向 Agent 提问，例如：
   - "帮我查看一下这份数据的基本描述性统计信息"
   - "绘制柱状图展示各个类别的销量总和，并生成一张交互式图表"
   - "基于当前数据生成一份完整的数据分析报告"
4. **下载结果**：Agent 生成的图表（`.html`）或导出数据可直接在界面上点击下载。

## 📝 依赖说明

主要依赖包括但不限于：
- `streamlit` (>=1.38.0): Web UI 框架
- `agno` (>=1.2.0): 强大的 Agent 开发框架
- `pandas` (>=2.0.0), `numpy`: 数据处理基础库
- `plotly` (>=5.18.0): 交互式可视化库
- `openpyxl`: Excel 文件读取支持
