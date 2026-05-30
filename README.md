# MultiProviderAIBatchTool 使用说明

项目地址：

https://github.com/3571949306/multi-provider-ai-batch-tool

## 中文说明

### 可执行文件

双击运行：

`MultiProviderAIBatchTool.exe`

### 支持模式

1. `xAI Grok Batch 官方`
   - 默认使用 xAI 官方 Batch API 的 JSONL 文件上传方式。
   - Batch 文档写明文件上传上限为 200 MB、最多 50,000 条请求。
   - 注意：xAI 通用 Files API 文档同时写了单文件 50 MB 上限；如果超过 50 MB 上传失败，请拆分任务。

2. `OpenAI 官方 Batch（JSONL 文件上传）`
   - 使用 OpenAI 官方 `/v1/files` + `/v1/batches` 流程。
   - 官方上限为 200 MB、最多 50,000 条请求。

3. `OpenAI-compatible`
   - 使用 `/chat/completions` 兼容接口做并发批量处理。
   - 适合阿里百炼、SiliconFlow、Kimi、DeepSeek，以及国内第三方中转/聚合商。
   - Claude/Gemini 如果通过 OpenAI 兼容网关提供，也可以用这个模式。

### 常用填写方式

- OpenAI: `https://api.openai.com/v1`
- xAI: `https://api.x.ai/v1`
- 阿里百炼 DashScope: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- SiliconFlow: `https://api.siliconflow.cn/v1`
- Kimi / Moonshot: `https://api.moonshot.ai/v1`
- DeepSeek: `https://api.deepseek.com/v1`
- 国内第三方中转: 填对方给你的 `https://.../v1`

模型名需要按对应平台实际可用模型填写。第三方中转通常会在控制台或文档里列出可用模型。

### 输入格式

- 直接在输入框中输入：每行一条任务。
- 也可以加载 `.txt`、`.csv`、`.tsv`。
- CSV/TSV 有表头时，工具优先读取 `text`、`content`、`prompt`、`input` 列；没有表头时读取第一列。

### 结果查看

- 处理完成并导出后，会自动加载结果。
- 可以点击 `打开最近结果` 查看最近一次导出的结果。
- 可以点击 `打开结果文件` 手动打开 `.json` 或 `.csv`。
- 左侧选择任务编号，右侧查看输出正文和原始 JSON。
- `复制选中结果` 会复制当前选中任务的输出正文。

### 使用说明

- 初次进入会自动显示内置说明。
- 可以在 `设置` 里再次打开。
- 说明窗口分为 `简单版` 和 `超详细版`，可以切换查看。
- 可以在说明窗口里复制项目地址。

### 省钱建议

- 大量、不急着立刻拿结果的任务：优先使用官方 Batch。
- 少量、需要马上看结果的任务：使用兼容批量调用。
- 第一次测试先提交 1 到 3 条，确认 Key、模型和结果格式都正常后再扩大规模。
- 相同任务共用一个 System Prompt，每行只放不同输入，减少重复 token。

## English Guide

### Executable

Run:

`MultiProviderAIBatchTool.exe`

### Supported Modes

1. `xAI Grok Official Batch`
   - Uses xAI's official Batch API.
   - The Batch documentation states a JSONL upload limit of 200 MB and up to 50,000 requests.
   - Note: xAI's general Files API documentation also mentions a 50 MB file limit. If a large upload fails, split the task file.

2. `OpenAI Official Batch`
   - Uses the official `/v1/files` + `/v1/batches` workflow.
   - Official limit: 200 MB and up to 50,000 requests.

3. `OpenAI-compatible concurrent mode`
   - Calls `/chat/completions` concurrently.
   - Useful for DashScope, SiliconFlow, Kimi, DeepSeek, and third-party API gateways.
   - This is not a real Batch API unless your provider explicitly supports `/v1/batches`.

### Common Base URLs

- OpenAI: `https://api.openai.com/v1`
- xAI: `https://api.x.ai/v1`
- DashScope: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- SiliconFlow: `https://api.siliconflow.cn/v1`
- Kimi / Moonshot: `https://api.moonshot.ai/v1`
- DeepSeek: `https://api.deepseek.com/v1`
- Third-party gateways: use the `/v1` URL provided by the provider.

### Input Format

- Type one task per line.
- You can also load `.txt`, `.csv`, or `.tsv` files.
- For CSV/TSV files with headers, the tool prefers `text`, `content`, `prompt`, or `input` columns.
- Without headers, it reads the first column.

### Result Viewer

- Results are loaded automatically after export.
- Click `Open Latest Result` to inspect the latest output.
- Click `Open Result File` to open a `.json` or `.csv` result file manually.
- Select an item on the left to view extracted text and raw JSON on the right.
- `Copy Selected Result` copies the extracted output text.

### How To Save Cost

- Use official Batch mode for large jobs that do not need immediate responses.
- Use concurrent compatible mode for small jobs or quick checks.
- Start with 1 to 3 tasks first, then scale up after confirming the API key, model, and result format.
- Put shared instructions in the System Prompt and keep each input line focused to reduce repeated tokens.

### Safety Notes

- API keys are saved only in your local user configuration if you enable saving.
- API keys, tokens, configs, result folders, and build caches are ignored by Git.
- Do not upload local configuration files or tokens manually.
