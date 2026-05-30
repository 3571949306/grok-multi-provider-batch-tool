# GrokMultiProviderBatchTool 使用说明

项目地址：

https://github.com/3571949306/grok-multi-provider-batch-tool

## 可执行文件

双击运行：

`GrokMultiProviderBatchTool.exe`

## 支持模式

1. `xAI Grok Batch 官方`
   - 默认使用 xAI 官方 Batch API 的 JSONL 文件上传方式。
   - Batch 文档写明文件上传上限为 200 MB、最多 50,000 条请求。
   - 注意：xAI 通用 Files API 文档同时写了单文件 50 MB 上限；如果超过 50 MB 上传失败，请拆分任务。

2. `OpenAI 官方 Batch（JSONL 文件上传）`
   - 使用 OpenAI 官方 `/v1/files` + `/v1/batches` 流程。
   - 官方上限为 200 MB、最多 50,000 条请求。

3. `OpenAI-compatible`
   - 使用 `/chat/completions` 兼容接口做并发批量处理。
   - 适合 OpenAI、阿里百炼、SiliconFlow、Kimi、DeepSeek，以及国内第三方中转/聚合商。
   - Claude/Gemini 如果通过 OpenAI 兼容网关提供，也可以用这个模式。

## 常用填写方式

- OpenAI: `https://api.openai.com/v1`
- 阿里百炼 DashScope: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- SiliconFlow: `https://api.siliconflow.cn/v1`
- Kimi / Moonshot: `https://api.moonshot.ai/v1`
- DeepSeek: `https://api.deepseek.com/v1`
- 国内第三方中转: 填对方给你的 `https://.../v1`

模型名需要按对应平台实际可用模型填写。第三方中转通常会在控制台或文档里列出可用模型。

## 输入格式

- 直接在输入框中输入：每行一条任务。
- 也可以加载 `.txt`、`.csv`、`.tsv`。
- CSV/TSV 有表头时，工具优先读取 `text`、`content`、`prompt`、`input` 列；没有表头时读取第一列。

## 输出

处理结果会导出到当前目录下的 `outputs` 文件夹：

- `.json`：完整原始结果。
- `.csv`：便于 Excel 查看，包含任务编号、输入、输出文本、错误信息和原始 JSON。

新版程序还内置结果查看器：

- 处理完成并导出后，会自动加载结果。
- 可以点击 `打开最近结果` 查看最近一次导出的结果。
- 可以点击 `打开结果文件` 手动打开 `.json` 或 `.csv`。
- 左侧选择任务编号，右侧查看输出正文和原始 JSON。
- `复制选中结果` 会复制当前选中任务的输出正文。

程序内置“使用说明与省钱建议”窗口：

- 初次进入会自动显示。
- 可以在 `设置` 里再次打开。
- 可以在说明窗口里复制项目地址。

## 注意

- API Key 只在本地程序内使用，不会写入文件。
- xAI Batch 是异步的，提交后需要稍后查询进度，再获取结果。
- OpenAI-compatible 模式是同步并发调用，供应商可能有速率限制；如果报 429 或限流，请降低并发数。
