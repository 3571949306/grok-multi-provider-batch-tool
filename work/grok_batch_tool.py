import csv
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Button, Canvas, Checkbutton, Entry, Frame, Label, LabelFrame, StringVar, BooleanVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


API_BASE = "https://api.x.ai/v1"
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "GrokMultiProviderBatchTool"
CONFIG_PATH = APP_DIR / "config.json"
PROJECT_URL = "https://github.com/3571949306/grok-multi-provider-batch-tool"
MODE_LABELS = {
    "xAI 异步 Batch（逐条提交）": "xai_batch",
    "xAI 异步 Batch（JSONL 文件上传）": "xai_batch_file",
    "OpenAI 官方 Batch（JSONL 文件上传）": "openai_batch_file",
    "兼容批量调用（OpenAI 格式）": "openai_chat",
}
MODE_VALUES = {value: label for label, value in MODE_LABELS.items()}
PROVIDERS = {
    "xAI Grok Batch 官方": {"mode": "xai_batch_file", "base_url": "https://api.x.ai/v1", "model": "grok-4.3"},
    "OpenAI Compatible 自定义": {"mode": "openai_chat", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
    "OpenAI": {"mode": "openai_batch_file", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
    "阿里百炼 DashScope": {"mode": "openai_chat", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "SiliconFlow 硅基流动": {"mode": "openai_chat", "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen3-8B"},
    "Kimi / Moonshot": {"mode": "openai_chat", "base_url": "https://api.moonshot.ai/v1", "model": "moonshot-v1-8k"},
    "DeepSeek": {"mode": "openai_chat", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "国内第三方中转 / 聚合商": {"mode": "openai_chat", "base_url": "https://your-provider.example/v1", "model": "your-model"},
    "Claude/Gemini via OpenAI 兼容网关": {"mode": "openai_chat", "base_url": "https://your-gateway.example/v1", "model": "claude-or-gemini-model"},
}


class XAIError(Exception):
    pass


def normalize_api_key(value):
    return "".join((value or "").strip().split())


def friendly_error(exc):
    text = str(exc)
    if "Incorrect API key provided" in text or "invalid_api_key" in text or "invalid_api_key" in text.lower():
        return "API Key 无效。请确认使用的是该平台控制台创建的 API Key，不是网页登录凭证；也请检查是否复制了多余空格、换行，或当前供应商选错。"
    if "401" in text or "Unauthorized" in text:
        return "认证失败。请检查 API Key、供应商和 Base URL 是否匹配。"
    if "403" in text:
        return "权限不足。请确认该 API Key 已开通对应模型或 Batch/Files 权限。"
    if "404" in text and "/models" in text:
        return "当前 Base URL 不支持 /models 模型列表接口。可以手动填写模型名，或换用供应商给出的模型列表地址。"
    return text


@dataclass
class SavedConfig:
    provider: str = "xAI Grok Batch 官方"
    mode: str = "xai_batch_file"
    base_url: str = API_BASE
    model: str = "grok-4.3"
    api_key: str = ""
    batch_name: str = ""
    concurrency: str = "3"
    system_prompt: str = "你是一个专业、高效的批量文本处理助手。"
    providers: dict = field(default_factory=dict)
    output_folder: str = ""
    auto_save_on_switch: bool = True
    auto_save_keys: bool = True
    show_guide_on_start: bool = True


GUIDE_TEXT = f"""多供应商 AI 批量处理工具使用说明

项目地址：
{PROJECT_URL}

一、先选供应商
1. xAI Grok Batch 官方：适合使用 Grok 官方 Batch。
2. OpenAI：适合使用 OpenAI 官方 Batch。
3. 阿里百炼、SiliconFlow、Kimi、DeepSeek、国内第三方中转：通常走 OpenAI 兼容并发调用。
4. 如果第三方明确支持 /v1/batches，可以手动改 Base URL 和处理方式再测试。

二、配置 API Key 和模型
1. 填写 API Key。
2. 点击“测试 Key”确认 Key 和 Base URL 匹配。
3. 点击“获取模型列表”自动读取 /models；如果供应商不支持 /models，可以手动填写模型名。
4. 勾选“保存 Key 到本机配置”后，每个供应商会独立保存自己的 Key、Base URL、模型和并发数。

三、处理方式怎么选
1. xAI 异步 Batch（JSONL 文件上传）：推荐给 Grok 批量任务，真正走 Batch。
2. xAI 异步 Batch（逐条提交）：兼容旧流程，也是真正走 Batch。
3. OpenAI 官方 Batch（JSONL 文件上传）：推荐给 OpenAI 批量任务，真正走 Batch。
4. 兼容批量调用（OpenAI 格式）：不是 Batch，是逐条请求 /chat/completions，只是工具帮你并发处理。

四、怎么判断有没有真的走 Batch
1. 点击“判断执行方式”。
2. 如果日志显示“已走 Batch”并有 Batch ID，说明走了 /batches。
3. 如果显示“非 Batch：OpenAI 兼容并发调用”，说明只是逐条调用 /chat/completions。

五、怎么最划算
1. 大量、不急着立刻拿结果的任务：优先用官方 Batch。通常比实时接口更适合批量处理。
2. 少量、需要马上看结果的任务：用兼容批量调用或普通实时接口更方便。
3. 第一次测试不要提交太多：先用 1 到 3 条验证 Key、模型、结果格式，再扩大到几十条或更多。
4. 任务很多时，把相似任务放在同一个 System Prompt 下，每行一个输入，避免重复写长提示词。
5. 如果文件上传 Batch 接近 50 MB 或 200 MB，请拆分，减少失败后重跑的成本。

六、结果在哪里看
1. 处理完成会自动导出 JSON 和 CSV，并加载到“结果查看器”。
2. 也可以点击“打开最近结果”或“打开结果文件”。
3. 左侧选任务编号，右侧查看输出正文和原始 JSON。
4. 点击“复制选中结果”可复制当前结果正文。
"""


def request_json(method, path, api_key, payload=None):
    data = None
    headers = {"Authorization": f"Bearer {normalize_api_key(api_key)}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise XAIError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise XAIError(f"网络错误: {exc.reason}") from exc


def request_json_url(method, url, api_key, payload=None, extra_headers=None):
    data = None
    headers = {"Authorization": f"Bearer {normalize_api_key(api_key)}"}
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise XAIError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise XAIError(f"网络错误: {exc.reason}") from exc


def request_raw_url(method, url, api_key):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {normalize_api_key(api_key)}"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise XAIError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise XAIError(f"网络错误: {exc.reason}") from exc


def multipart_upload(url, api_key, file_path, extra_fields=None):
    boundary = f"----CodexBatchBoundary{int(time.time() * 1000)}"
    parts = []
    for name, value in (extra_fields or {}).items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    p = Path(file_path)
    file_head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{p.name}"\r\n'
        "Content-Type: application/jsonl\r\n\r\n"
    ).encode("utf-8")
    body = b"".join(parts) + file_head + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {
        "Authorization": f"Bearer {normalize_api_key(api_key)}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise XAIError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise XAIError(f"网络错误: {exc.reason}") from exc


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def extract_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        if "output_text" in value and isinstance(value["output_text"], str):
            return value["output_text"]
        if isinstance(value.get("raw_json"), str) and value["raw_json"].strip():
            try:
                found = extract_text(json.loads(value["raw_json"]))
                if found:
                    return found
            except json.JSONDecodeError:
                pass
        if isinstance(value.get("message"), dict):
            found = extract_text(value["message"])
            if found:
                return found
        parts = []
        for key in ("batch_result", "result", "response", "chat_get_completion", "output", "content", "choices", "body"):
            if key in value:
                found = extract_text(value[key])
                if found:
                    parts.append(found)
        return "\n".join(parts)
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := extract_text(item)))
    return ""


def make_chat_jsonl(path, rows, system, model):
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        for idx, text in enumerate(rows, start=1):
            item = {
                "custom_id": f"item_{idx:05d}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                },
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def default_output_dir():
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    folder = base / "batch_results"
    folder.mkdir(exist_ok=True)
    return folder


class GrokBatchTool:
    def __init__(self, root):
        self.root = root
        self.root.title("多供应商 AI 批量处理工具")
        self.root.geometry("1180x820")
        self.last_results = []
        self.viewer_results = []
        self.last_run_mode = ""
        self.last_batch_verified = False
        self.saved = self.load_config_file()
        self.provider_configs = self.saved.providers if isinstance(self.saved.providers, dict) else {}
        if self.saved.provider and self.saved.provider not in self.provider_configs:
            self.provider_configs[self.saved.provider] = {
                "mode": self.saved.mode,
                "base_url": self.saved.base_url,
                "model": self.saved.model,
                "api_key": self.saved.api_key,
                "concurrency": self.saved.concurrency,
            }
        self.previous_provider = self.saved.provider

        self.api_key = StringVar(value=self.saved.api_key or os.environ.get("XAI_API_KEY", ""))
        self.save_key = BooleanVar(value=self.saved.auto_save_keys if self.saved.auto_save_keys is not None else bool(self.saved.api_key))
        self.provider = StringVar(value=self.saved.provider)
        self.mode_label = StringVar(value=MODE_VALUES.get(self.saved.mode, "xAI 异步 Batch（JSONL 文件上传）"))
        self.base_url = StringVar(value=self.saved.base_url)
        self.batch_id = StringVar()
        self.batch_name = StringVar(value=self.saved.batch_name or f"batch_{time.strftime('%Y%m%d_%H%M%S')}")
        self.model = StringVar(value=self.saved.model)
        self.concurrency = StringVar(value=self.saved.concurrency)
        self.status = StringVar(value="就绪")
        self.output_folder = StringVar(value=self.saved.output_folder)
        self.auto_save_on_switch = BooleanVar(value=bool(self.saved.auto_save_on_switch))
        self.auto_save_keys = BooleanVar(value=bool(self.saved.auto_save_keys))
        self.show_guide_on_start = BooleanVar(value=bool(self.saved.show_guide_on_start))

        self.build_ui()
        if self.show_guide_on_start.get():
            self.root.after(300, self.open_guide)

    def build_ui(self):
        self.canvas = Canvas(self.root, highlightthickness=0)
        self.main_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.main_frame = Frame(self.canvas)
        self.main_window = self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.main_scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.main_scrollbar.pack(side=RIGHT, fill="y")

        def sync_scroll_region(_event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def sync_window_width(event):
            self.canvas.itemconfigure(self.main_window, width=event.width)

        def mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.main_frame.bind("<Configure>", sync_scroll_region)
        self.canvas.bind("<Configure>", sync_window_width)
        self.canvas.bind_all("<MouseWheel>", mousewheel)

        config_frame = LabelFrame(self.main_frame, text="1. 接口配置", padx=10, pady=8)
        config_frame.pack(fill=X, padx=10, pady=(10, 6))

        top = Frame(config_frame)
        top.pack(fill=X)
        Label(top, text="供应商").pack(side=LEFT)
        provider_box = ttk.Combobox(top, textvariable=self.provider, values=list(PROVIDERS.keys()), width=24, state="readonly")
        provider_box.pack(side=LEFT, padx=6)
        provider_box.bind("<<ComboboxSelected>>", self.apply_provider)
        Label(top, text="API Key").pack(side=LEFT)
        Entry(top, textvariable=self.api_key, show="*", width=42).pack(side=LEFT, padx=6)
        Checkbutton(top, text="保存 Key 到本机配置", variable=self.save_key).pack(side=LEFT, padx=4)
        Button(top, text="保存配置", command=self.save_config).pack(side=LEFT, padx=4)
        Button(top, text="测试 Key", command=self.test_key).pack(side=LEFT, padx=4)
        Button(top, text="清除保存", command=self.clear_saved_config).pack(side=LEFT, padx=4)
        Button(top, text="获取模型列表", command=self.fetch_models).pack(side=LEFT, padx=4)
        Button(top, text="设置", command=self.open_settings).pack(side=LEFT, padx=4)

        conn = Frame(config_frame)
        conn.pack(fill=X, pady=(8, 0))
        Label(conn, text="处理方式").pack(side=LEFT)
        ttk.Combobox(conn, textvariable=self.mode_label, values=list(MODE_LABELS.keys()), width=28, state="readonly").pack(side=LEFT, padx=6)
        Label(conn, text="Base URL").pack(side=LEFT)
        Entry(conn, textvariable=self.base_url, width=58).pack(side=LEFT, padx=6)
        Label(conn, text="模型").pack(side=LEFT)
        self.model_box = ttk.Combobox(conn, textvariable=self.model, values=[], width=34)
        self.model_box.pack(side=LEFT, padx=6)

        run_opts = Frame(config_frame)
        run_opts.pack(fill=X, pady=(8, 0))
        Label(run_opts, text="Batch 名称（xAI 异步模式使用）").pack(side=LEFT)
        Entry(run_opts, textvariable=self.batch_name, width=44).pack(side=LEFT, padx=6)
        Label(run_opts, text="并发").pack(side=LEFT)
        Entry(run_opts, textvariable=self.concurrency, width=6).pack(side=LEFT, padx=6)
        Label(run_opts, text="说明：文件上传 Batch 上限通常是 200 MB/50,000 条；兼容批量调用适合不支持 Batch 的中转商。").pack(side=LEFT, padx=12)

        task_frame = LabelFrame(self.main_frame, text="2. 任务内容", padx=10, pady=8)
        task_frame.pack(fill=BOTH, expand=True, padx=10, pady=6)
        Label(task_frame, text="System Prompt").pack(anchor="w")
        self.system_prompt = ScrolledText(task_frame, height=4, wrap="word")
        self.system_prompt.pack(fill=X)
        self.system_prompt.insert(END, self.saved.system_prompt)

        task_tools = Frame(task_frame)
        task_tools.pack(fill=X, pady=(8, 4))
        Button(task_tools, text="加载并替换", command=lambda: self.load_inputs(append=False)).pack(side=LEFT, padx=3)
        Button(task_tools, text="追加加载", command=lambda: self.load_inputs(append=True)).pack(side=LEFT, padx=3)
        Button(task_tools, text="从剪贴板追加", command=self.append_clipboard).pack(side=LEFT, padx=3)
        Button(task_tools, text="清空任务", command=self.clear_tasks).pack(side=LEFT, padx=3)
        Button(task_tools, text="保存任务文本", command=self.save_tasks).pack(side=LEFT, padx=3)

        input_frame = Frame(task_frame)
        input_frame.pack(fill=BOTH, expand=True)
        Label(input_frame, text="输入任务：每行一条。也可以加载 .txt/.csv 文件，CSV 默认读取第一列或名为 text/content/prompt/input 的列。").pack(anchor="w")
        self.input_text = ScrolledText(input_frame, height=10, wrap="word")
        self.input_text.pack(fill=BOTH, expand=True)

        run_frame = LabelFrame(self.main_frame, text="3. 运行与结果", padx=10, pady=8)
        run_frame.pack(fill=X, padx=10, pady=6)
        btns = Frame(run_frame)
        btns.pack(fill=X)
        Button(btns, text="开始处理", command=self.submit_batch).pack(side=LEFT, padx=3)
        Label(btns, text="Batch ID").pack(side=LEFT, padx=(20, 3))
        Entry(btns, textvariable=self.batch_id, width=42).pack(side=LEFT, padx=3)
        Button(btns, text="查询进度", command=self.check_status).pack(side=LEFT, padx=3)
        Button(btns, text="获取并导出结果", command=self.fetch_results).pack(side=LEFT, padx=3)
        Button(btns, text="判断执行方式", command=self.check_execution_mode).pack(side=LEFT, padx=3)

        state_frame = Frame(run_frame)
        state_frame.pack(fill=X)
        Label(state_frame, textvariable=self.status).pack(side=LEFT)

        result_frame = Frame(self.main_frame, padx=10, pady=4)
        result_frame.pack(fill=BOTH, expand=True)
        Label(result_frame, text="日志 / 返回内容").pack(anchor="w")
        self.output = ScrolledText(result_frame, height=7, wrap="word")
        self.output.pack(fill=BOTH, expand=True)

        viewer_frame = LabelFrame(self.main_frame, text="4. 结果查看器", padx=10, pady=8)
        viewer_frame.pack(fill=BOTH, expand=True, padx=10, pady=6)
        viewer_tools = Frame(viewer_frame)
        viewer_tools.pack(fill=X, pady=(0, 6))
        Button(viewer_tools, text="打开结果文件", command=self.open_result_file).pack(side=LEFT, padx=3)
        Button(viewer_tools, text="打开最近结果", command=self.open_latest_result).pack(side=LEFT, padx=3)
        Button(viewer_tools, text="复制选中结果", command=self.copy_selected_result).pack(side=LEFT, padx=3)
        Button(viewer_tools, text="清空查看器", command=self.clear_viewer).pack(side=LEFT, padx=3)

        viewer_body = ttk.PanedWindow(viewer_frame, orient="horizontal")
        viewer_body.pack(fill=BOTH, expand=True)
        list_frame = Frame(viewer_body)
        detail_frame = Frame(viewer_body)
        viewer_body.add(list_frame, weight=1)
        viewer_body.add(detail_frame, weight=2)

        self.result_tree = ttk.Treeview(list_frame, columns=("request_id", "status", "preview"), show="headings", height=8)
        self.result_tree.heading("request_id", text="任务编号")
        self.result_tree.heading("status", text="状态")
        self.result_tree.heading("preview", text="结果预览")
        self.result_tree.column("request_id", width=130, anchor="w")
        self.result_tree.column("status", width=70, anchor="w")
        self.result_tree.column("preview", width=360, anchor="w")
        self.result_tree.pack(fill=BOTH, expand=True)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_selected_result)

        Label(detail_frame, text="选中结果正文 / 原始 JSON").pack(anchor="w")
        self.result_detail = ScrolledText(detail_frame, height=8, wrap="word")
        self.result_detail.pack(fill=BOTH, expand=True)

        bottom = Frame(self.main_frame, padx=10, pady=6)
        bottom.pack(fill=X)
        Button(bottom, text="保存日志", command=self.save_log).pack(side=RIGHT, padx=3)

    def current_mode(self):
        return MODE_LABELS.get(self.mode_label.get(), "xai_batch")

    def load_config_file(self):
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return SavedConfig(**{k: v for k, v in data.items() if k in SavedConfig.__annotations__})
        except Exception:
            pass
        return SavedConfig()

    def capture_provider_config(self, provider_name=None):
        provider_name = provider_name or self.provider.get()
        self.provider_configs[provider_name] = {
            "mode": self.current_mode(),
            "base_url": self.base_url.get().strip(),
            "model": self.model.get().strip(),
            "api_key": normalize_api_key(self.api_key.get()) if self.save_key.get() else "",
            "concurrency": self.concurrency.get().strip(),
        }

    def save_config(self, quiet=False):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            provider_name = self.provider.get()
            self.capture_provider_config(provider_name)
            self.write_config_file(provider_name)
            if not quiet:
                self.log(f"配置已保存: {CONFIG_PATH}")
        except Exception as exc:
            if quiet:
                self.log(f"自动保存配置失败: {exc}")
            else:
                messagebox.showerror("保存失败", str(exc))

    def write_config_file(self, provider_name):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        current = self.provider_configs.get(provider_name, {})
        data = {
            "provider": provider_name,
            "mode": current.get("mode", self.current_mode()),
            "base_url": current.get("base_url", self.base_url.get().strip()),
            "model": current.get("model", self.model.get().strip()),
            "api_key": current.get("api_key", ""),
            "batch_name": self.batch_name.get().strip(),
            "concurrency": current.get("concurrency", self.concurrency.get().strip()),
            "system_prompt": self.system_prompt.get("1.0", END).strip(),
            "providers": self.provider_configs,
            "output_folder": self.output_folder.get().strip(),
                "auto_save_on_switch": self.auto_save_on_switch.get(),
                "auto_save_keys": self.auto_save_keys.get(),
                "show_guide_on_start": self.show_guide_on_start.get(),
            }
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_saved_config(self):
        if not messagebox.askyesno("确认清除", "确定要清除本机保存的 API 配置吗？当前界面内容也会清空 Key。"):
            return
        try:
            if CONFIG_PATH.exists():
                CONFIG_PATH.unlink()
            self.provider_configs = {}
            self.api_key.set("")
            self.save_key.set(False)
            self.log("已清除本机保存的配置。")
        except Exception as exc:
            messagebox.showerror("清除失败", str(exc))

    def open_settings(self):
        win = Toplevel(self.root)
        win.title("设置")
        win.geometry("620x260")
        win.transient(self.root)
        win.grab_set()

        box = LabelFrame(win, text="基础设置", padx=10, pady=10)
        box.pack(fill=BOTH, expand=True, padx=12, pady=12)

        row1 = Frame(box)
        row1.pack(fill=X, pady=6)
        Label(row1, text="结果输出目录", width=14, anchor="w").pack(side=LEFT)
        Entry(row1, textvariable=self.output_folder, width=56).pack(side=LEFT, padx=6)

        def choose_folder():
            folder = filedialog.askdirectory(initialdir=self.output_folder.get().strip() or str(default_output_dir()))
            if folder:
                self.output_folder.set(folder)

        Button(row1, text="选择", command=choose_folder).pack(side=LEFT, padx=4)

        row2 = Frame(box)
        row2.pack(fill=X, pady=6)
        Checkbutton(row2, text="切换供应商时自动保存当前供应商配置", variable=self.auto_save_on_switch).pack(side=LEFT)

        row3 = Frame(box)
        row3.pack(fill=X, pady=6)
        Checkbutton(row3, text="默认允许保存 API Key 到本机配置", variable=self.auto_save_keys).pack(side=LEFT)

        row_guide = Frame(box)
        row_guide.pack(fill=X, pady=6)
        Checkbutton(row_guide, text="启动时显示使用说明", variable=self.show_guide_on_start).pack(side=LEFT)
        Button(row_guide, text="打开使用说明", command=self.open_guide).pack(side=LEFT, padx=12)

        row4 = Frame(box)
        row4.pack(fill=X, pady=6)
        Label(row4, text=f"配置文件: {CONFIG_PATH}").pack(side=LEFT)

        buttons = Frame(win, padx=12, pady=8)
        buttons.pack(fill=X)

        def save_and_close():
            self.save_key.set(self.auto_save_keys.get())
            self.save_config()
            win.destroy()

        Button(buttons, text="保存设置", command=save_and_close).pack(side=RIGHT, padx=4)
        Button(buttons, text="取消", command=win.destroy).pack(side=RIGHT, padx=4)

    def open_guide(self):
        win = Toplevel(self.root)
        win.title("使用说明与省钱建议")
        win.geometry("820x680")
        win.transient(self.root)

        body = Frame(win, padx=10, pady=10)
        body.pack(fill=BOTH, expand=True)
        text = ScrolledText(body, wrap="word")
        text.pack(fill=BOTH, expand=True)
        text.insert(END, GUIDE_TEXT)
        text.configure(state="disabled")

        footer = Frame(win, padx=10, pady=8)
        footer.pack(fill=X)

        def copy_project_url():
            self.root.clipboard_clear()
            self.root.clipboard_append(PROJECT_URL)
            self.log("已复制项目地址。")

        def close_and_save():
            self.show_guide_on_start.set(False)
            self.save_config(quiet=True)
            win.destroy()

        Button(footer, text="复制项目地址", command=copy_project_url).pack(side=LEFT, padx=4)
        Checkbutton(footer, text="下次启动继续显示", variable=self.show_guide_on_start).pack(side=LEFT, padx=12)
        Button(footer, text="关闭", command=win.destroy).pack(side=RIGHT, padx=4)
        Button(footer, text="关闭并下次不再自动显示", command=close_and_save).pack(side=RIGHT, padx=4)

    def test_key(self):
        def work():
            try:
                api_key = self.require_key()
                base = self.base_url.get().strip().rstrip("/")
                if not base:
                    raise XAIError("请填写 Base URL。")
                request_json_url("GET", f"{base}/models", api_key)
                self.log("Key 测试通过：可以访问模型列表接口。")
                messagebox.showinfo("测试成功", "API Key 可用，已成功访问 /models。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"Key 测试失败: {msg}")
                messagebox.showerror("Key 测试失败", msg)

        self.run_async(work)

    def apply_provider(self, _event=None):
        if self.previous_provider and self.previous_provider != self.provider.get() and self.auto_save_on_switch.get():
            self.capture_provider_config(self.previous_provider)
            try:
                self.write_config_file(self.provider.get())
            except Exception as exc:
                self.log(f"自动保存配置失败: {exc}")
        preset = PROVIDERS.get(self.provider.get())
        if not preset:
            return
        saved = self.provider_configs.get(self.provider.get(), {})
        mode = saved.get("mode", preset["mode"])
        self.mode_label.set(MODE_VALUES.get(mode, self.mode_label.get()))
        self.base_url.set(saved.get("base_url", preset["base_url"]))
        self.model.set(saved.get("model", preset["model"]))
        self.concurrency.set(saved.get("concurrency", self.concurrency.get()))
        if "api_key" in saved:
            self.api_key.set(saved.get("api_key", ""))
            self.save_key.set(bool(saved.get("api_key", "")))
        else:
            self.api_key.set("")
            self.save_key.set(self.auto_save_keys.get())
        self.model_box["values"] = []
        self.previous_provider = self.provider.get()

    def fetch_models(self):
        def work():
            try:
                api_key = self.require_key()
                base = self.base_url.get().strip().rstrip("/")
                if not base:
                    raise XAIError("请填写 Base URL。")
                data = request_json_url("GET", f"{base}/models", api_key)
                models = []
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    for item in data["data"]:
                        if isinstance(item, dict) and item.get("id"):
                            models.append(item["id"])
                        elif isinstance(item, str):
                            models.append(item)
                elif isinstance(data, list):
                    models = [item.get("id", item) if isinstance(item, dict) else item for item in data]
                models = sorted({str(m) for m in models if m})
                if not models:
                    raise XAIError(f"接口返回了模型数据，但没有识别到模型 id: {json.dumps(data, ensure_ascii=False)[:500]}")
                self.model_box["values"] = models
                if self.model.get() not in models:
                    self.model.set(models[0])
                self.log(f"已获取 {len(models)} 个模型。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"获取模型失败: {msg}")
                messagebox.showerror("获取模型失败", msg)

        self.run_async(work)

    def log(self, message):
        self.output.insert(END, f"{time.strftime('%H:%M:%S')}  {message}\n")
        self.output.see(END)
        self.status.set(message)

    def describe_current_execution_mode(self):
        mode = self.current_mode()
        if mode == "xai_batch":
            return "xAI 官方 Batch（逐条提交到 /batches/{id}/requests）"
        if mode == "xai_batch_file":
            return "xAI 官方 Batch（JSONL 文件上传到 /files 后创建 /batches）"
        if mode == "openai_batch_file":
            return "OpenAI 官方 Batch（JSONL 文件上传到 /files 后创建 /batches）"
        return "非 Batch：OpenAI 兼容并发调用（逐条请求 /chat/completions）"

    def mark_batch_verified(self, label, batch_id):
        self.last_run_mode = label
        self.last_batch_verified = True
        self.log(f"执行方式确认：已走 Batch。方式：{label}；Batch ID：{batch_id}")

    def mark_non_batch(self):
        self.last_run_mode = "非 Batch：OpenAI 兼容并发调用（/chat/completions）"
        self.last_batch_verified = False
        self.log("执行方式确认：未走 Batch。方式：OpenAI 兼容并发调用；接口：/chat/completions。")

    def run_async(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def require_key(self):
        key = normalize_api_key(self.api_key.get())
        if key != self.api_key.get():
            self.api_key.set(key)
        if not key:
            raise XAIError("请填写 API Key。")
        return key

    def load_inputs(self, append=False):
        path = filedialog.askopenfilename(filetypes=[("Text/CSV", "*.txt *.csv *.tsv"), ("All files", "*.*")])
        if not path:
            return
        p = Path(path)
        rows = []
        try:
            if p.suffix.lower() in {".csv", ".tsv"}:
                delimiter = "\t" if p.suffix.lower() == ".tsv" else ","
                with p.open("r", encoding="utf-8-sig", newline="") as f:
                    sample = f.read(4096)
                    f.seek(0)
                    has_header = csv.Sniffer().has_header(sample)
                    if has_header:
                        reader = csv.DictReader(f, delimiter=delimiter)
                        for row in reader:
                            rows.append(next((row.get(k, "").strip() for k in ("text", "content", "prompt", "input") if row.get(k, "").strip()), ""))
                    else:
                        reader = csv.reader(f, delimiter=delimiter)
                        rows.extend(row[0].strip() for row in reader if row)
            else:
                rows = p.read_text(encoding="utf-8-sig").splitlines()
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))
            return

        rows = [row for row in rows if row.strip()]
        if not append:
            self.input_text.delete("1.0", END)
        elif self.input_text.get("1.0", END).strip():
            self.input_text.insert(END, "\n")
        self.input_text.insert(END, "\n".join(rows))
        self.log(f"已加载 {len(rows)} 条任务。")

    def append_clipboard(self):
        try:
            text = self.root.clipboard_get().strip()
            if not text:
                return
            if self.input_text.get("1.0", END).strip():
                self.input_text.insert(END, "\n")
            self.input_text.insert(END, text)
            self.log("已从剪贴板追加任务。")
        except Exception as exc:
            messagebox.showerror("读取剪贴板失败", str(exc))

    def clear_tasks(self):
        if messagebox.askyesno("确认清空", "确定要清空当前任务吗？"):
            self.input_text.delete("1.0", END)
            self.log("任务已清空。")

    def save_tasks(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt"), ("CSV", "*.csv")])
        if path:
            Path(path).write_text(self.input_text.get("1.0", END).strip(), encoding="utf-8")
            self.log(f"任务已保存: {path}")

    def get_input_rows(self):
        rows = [line.strip() for line in self.input_text.get("1.0", END).splitlines() if line.strip()]
        if not rows:
            raise XAIError("请先输入至少一条任务。")
        return rows

    def submit_batch(self):
        mode = self.current_mode()
        if mode == "openai_chat":
            self.process_openai_compatible()
            return
        if mode in {"xai_batch_file", "openai_batch_file"}:
            self.submit_file_batch(mode)
            return

        def work():
            try:
                api_key = self.require_key()
                rows = self.get_input_rows()
                system = self.system_prompt.get("1.0", END).strip()
                model = self.model.get().strip() or "grok-4.3"
                name = self.batch_name.get().strip() or f"batch_{int(time.time())}"

                self.log("正在创建 Batch...")
                batch = request_json("POST", "/batches", api_key, {"name": name})
                bid = batch.get("batch_id") or batch.get("id")
                if not bid:
                    raise XAIError(f"创建成功但没有返回 batch_id: {json.dumps(batch, ensure_ascii=False)}")
                self.batch_id.set(bid)
                self.log(f"Batch 已创建: {bid}")
                self.mark_batch_verified("xAI 官方 Batch（逐条提交）", bid)

                for idx, part in enumerate(chunked(rows, 100), start=1):
                    batch_requests = []
                    offset = (idx - 1) * 100
                    for pos, text in enumerate(part, start=1):
                        request_id = f"item_{offset + pos:05d}"
                        batch_requests.append(
                            {
                                "batch_request_id": request_id,
                                "batch_request": {
                                    "responses": {
                                        "model": model,
                                        "input": [
                                            {"role": "system", "content": system},
                                            {"role": "user", "content": text},
                                        ],
                                    }
                                },
                            }
                        )
                    request_json("POST", f"/batches/{urllib.parse.quote(bid)}/requests", api_key, {"batch_requests": batch_requests})
                    self.log(f"已提交第 {idx} 批，共 {len(batch_requests)} 条。")
                self.log(f"提交完成，共 {len(rows)} 条。可稍后查询进度并导出结果。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"失败: {msg}")
                messagebox.showerror("提交失败", msg)

        self.run_async(work)

    def submit_file_batch(self, mode):
        def work():
            try:
                api_key = self.require_key()
                rows = self.get_input_rows()
                if len(rows) > 50000:
                    raise XAIError("文件上传 Batch 最多 50,000 条请求，请拆分任务。")
                system = self.system_prompt.get("1.0", END).strip()
                model = self.model.get().strip()
                base = self.base_url.get().strip().rstrip("/")
                name = self.batch_name.get().strip() or f"batch_{int(time.time())}"
                if not base:
                    raise XAIError("请填写 Base URL。")
                if not model:
                    raise XAIError("请填写模型名。")

                work_dir = Path.cwd() / "work"
                work_dir.mkdir(exist_ok=True)
                jsonl_path = work_dir / f"{name}_{int(time.time())}.jsonl"
                make_chat_jsonl(jsonl_path, rows, system, model)
                size = jsonl_path.stat().st_size
                max_size = 200 * 1024 * 1024
                if size > max_size:
                    raise XAIError(f"JSONL 文件 {size / 1024 / 1024:.1f} MB，超过 Batch 文档上限 200 MB。")
                if mode == "xai_batch_file" and size > 50 * 1024 * 1024:
                    self.log("提示：xAI Batch 文档写 200 MB，但通用 Files 文档写 50 MB；当前文件超过 50 MB，若上传失败请拆分。")

                self.log(f"已生成 JSONL：{jsonl_path}，{len(rows)} 条，{size / 1024 / 1024:.2f} MB。")
                upload_fields = {"purpose": "batch"} if mode == "openai_batch_file" else None
                file_obj = multipart_upload(f"{base}/files", api_key, jsonl_path, upload_fields)
                file_id = file_obj.get("id") or file_obj.get("file_id")
                if not file_id:
                    raise XAIError(f"文件上传成功但没有返回 file id: {json.dumps(file_obj, ensure_ascii=False)}")
                self.log(f"文件已上传: {file_id}")

                payload = {"input_file_id": file_id}
                if mode == "xai_batch_file":
                    payload["name"] = name
                else:
                    payload.update({"endpoint": "/v1/chat/completions", "completion_window": "24h", "metadata": {"name": name}})
                batch = request_json_url("POST", f"{base}/batches", api_key, payload)
                bid = batch.get("id") or batch.get("batch_id")
                if not bid:
                    raise XAIError(f"Batch 创建成功但没有返回 id: {json.dumps(batch, ensure_ascii=False)}")
                self.batch_id.set(bid)
                self.log(f"文件上传 Batch 已创建: {bid}")
                label = "xAI 官方 Batch（JSONL 文件上传）" if mode == "xai_batch_file" else "OpenAI 官方 Batch（JSONL 文件上传）"
                self.mark_batch_verified(label, bid)
                self.log("稍后可点击“查询进度”；完成后点击“获取并导出结果”。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"失败: {msg}")
                messagebox.showerror("提交失败", msg)

        self.run_async(work)

    def process_openai_compatible(self):
        def work():
            try:
                api_key = self.require_key()
                rows = self.get_input_rows()
                system = self.system_prompt.get("1.0", END).strip()
                model = self.model.get().strip()
                base = self.base_url.get().strip().rstrip("/")
                if not base:
                    raise XAIError("请填写 OpenAI-compatible Base URL。")
                if not model:
                    raise XAIError("请填写模型名。")
                try:
                    max_workers = max(1, min(20, int(self.concurrency.get().strip())))
                except ValueError:
                    max_workers = 3

                url = f"{base}/chat/completions"
                self.log(f"开始 OpenAI-compatible 批量处理：{len(rows)} 条，并发 {max_workers}。")
                self.mark_non_batch()

                def call_one(index, text):
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": text},
                        ],
                    }
                    raw = request_json_url("POST", url, api_key, payload)
                    content = ""
                    try:
                        content = raw["choices"][0]["message"]["content"]
                    except Exception:
                        content = extract_text(raw)
                    return {"batch_request_id": f"item_{index:05d}", "input": text, "text": content, "raw": raw}

                results = []
                done = 0
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    future_map = {pool.submit(call_one, idx, text): (idx, text) for idx, text in enumerate(rows, start=1)}
                    for future in as_completed(future_map):
                        idx, text = future_map[future]
                        try:
                            results.append(future.result())
                        except Exception as exc:
                            results.append({"batch_request_id": f"item_{idx:05d}", "input": text, "text": "", "error": str(exc)})
                        done += 1
                        if done == len(rows) or done % 5 == 0:
                            self.log(f"已完成 {done}/{len(rows)} 条。")

                results.sort(key=lambda x: x.get("batch_request_id", ""))
                self.export_results(results, "openai_compatible")
                self.log("OpenAI-compatible 批量处理完成。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"失败: {msg}")
                messagebox.showerror("处理失败", msg)

        self.run_async(work)

    def export_results(self, results, name):
        self.last_results = results
        out_dir = self.get_output_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:80]
        json_path = out_dir / f"grok_batch_results_{safe_name}_{stamp}.json"
        csv_path = out_dir / f"grok_batch_results_{safe_name}_{stamp}.csv"
        meta = {
            "execution_mode": self.last_run_mode or self.describe_current_execution_mode(),
            "is_batch": bool(self.last_batch_verified),
            "batch_id": self.batch_id.get().strip(),
            "provider": self.provider.get(),
            "model": self.model.get().strip(),
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": results,
        }
        json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["execution_mode", "is_batch", "batch_request_id", "input", "text", "error", "raw_json"])
            for item in results:
                if isinstance(item, dict):
                    request_id = item.get("batch_request_id") or item.get("custom_id") or ""
                    writer.writerow(
                        [
                            meta["execution_mode"],
                            meta["is_batch"],
                            request_id,
                            item.get("input", ""),
                            item.get("text") or extract_text(item),
                            item.get("error", ""),
                            json.dumps(item, ensure_ascii=False),
                        ]
                    )
                else:
                    writer.writerow([meta["execution_mode"], meta["is_batch"], "", "", extract_text(item), "", json.dumps(item, ensure_ascii=False)])
        self.log(f"已导出 {len(results)} 条结果:")
        self.log(str(json_path))
        self.log(str(csv_path))
        self.show_results_in_viewer(results)

    def check_execution_mode(self):
        def work():
            try:
                mode = self.current_mode()
                bid = self.batch_id.get().strip()
                if mode == "openai_chat":
                    self.mark_non_batch()
                    messagebox.showinfo("执行方式", "当前模式不是 Batch。\n实际会逐条调用 /chat/completions，并发处理。")
                    return
                if not bid:
                    label = self.describe_current_execution_mode()
                    self.log(f"当前选择的是 Batch 模式：{label}，但还没有 Batch ID。请先开始处理。")
                    messagebox.showinfo("执行方式", f"当前选择的是 Batch 模式：{label}\n但还没有 Batch ID。")
                    return
                api_key = self.require_key()
                base = self.base_url.get().strip().rstrip("/")
                if mode == "xai_batch":
                    data = request_json("GET", f"/batches/{urllib.parse.quote(bid)}", api_key)
                else:
                    data = request_json_url("GET", f"{base}/batches/{urllib.parse.quote(bid)}", api_key)
                returned_id = data.get("id") or data.get("batch_id") if isinstance(data, dict) else ""
                state = data.get("state", {}) if isinstance(data, dict) else {}
                is_batch = bool(returned_id or state)
                if is_batch:
                    self.mark_batch_verified(self.describe_current_execution_mode(), returned_id or bid)
                    self.log(f"Batch 状态：{json.dumps(state or data, ensure_ascii=False, indent=2)}")
                    messagebox.showinfo("执行方式", f"确认已走 Batch。\nBatch ID: {returned_id or bid}")
                else:
                    self.log(f"没有从 /batches 查询到有效 Batch 结构：{json.dumps(data, ensure_ascii=False)[:600]}")
                    messagebox.showwarning("执行方式", "没有确认到 Batch 结构，请检查 Batch ID 和模式。")
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"判断执行方式失败: {msg}")
                messagebox.showerror("判断失败", msg)

        self.run_async(work)

    def result_id(self, item, index):
        if isinstance(item, dict):
            return str(item.get("batch_request_id") or item.get("custom_id") or item.get("id") or f"item_{index:05d}")
        return f"item_{index:05d}"

    def result_error(self, item):
        if isinstance(item, dict):
            return str(item.get("error") or item.get("error_message") or "")
        return ""

    def show_results_in_viewer(self, results):
        self.viewer_results = list(results or [])
        self.result_tree.delete(*self.result_tree.get_children())
        for index, item in enumerate(self.viewer_results, start=1):
            text = extract_text(item).replace("\r", " ").replace("\n", " ").strip()
            error = self.result_error(item)
            status = "错误" if error else "成功"
            preview = error or text[:180]
            self.result_tree.insert("", END, iid=str(index - 1), values=(self.result_id(item, index), status, preview))
        self.result_detail.delete("1.0", END)
        if self.viewer_results:
            first = self.result_tree.get_children()[0]
            self.result_tree.selection_set(first)
            self.result_tree.focus(first)
            self.show_selected_result()
        self.log(f"查看器已加载 {len(self.viewer_results)} 条结果。")

    def show_selected_result(self, _event=None):
        selected = self.result_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx < 0 or idx >= len(self.viewer_results):
            return
        item = self.viewer_results[idx]
        text = extract_text(item).strip()
        raw = json.dumps(item, ensure_ascii=False, indent=2)
        self.result_detail.delete("1.0", END)
        self.result_detail.insert(END, "【输出正文】\n")
        self.result_detail.insert(END, text or "(未识别到正文，请查看原始 JSON)")
        self.result_detail.insert(END, "\n\n【原始 JSON】\n")
        self.result_detail.insert(END, raw)

    def read_result_file(self, path):
        p = Path(path)
        if p.suffix.lower() == ".csv":
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                rows = []
                for row in csv.DictReader(f):
                    normalized = dict(row)
                    if not (normalized.get("text") or "").strip() and (normalized.get("raw_json") or "").strip():
                        try:
                            raw = json.loads(normalized["raw_json"])
                            normalized["text"] = extract_text(raw)
                            normalized["_parsed_raw_json"] = raw
                        except json.JSONDecodeError:
                            pass
                    rows.append(normalized)
                return rows
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if isinstance(data.get("results"), list):
                self.last_run_mode = data.get("execution_mode", self.last_run_mode)
                self.last_batch_verified = bool(data.get("is_batch", self.last_batch_verified))
                return data["results"]
            for key in ("results", "data", "batch_requests"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        raise XAIError("无法识别的结果文件格式。")

    def open_result_file(self):
        path = filedialog.askopenfilename(
            initialdir=str(self.get_output_dir()),
            filetypes=[("Result files", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            results = self.read_result_file(path)
            self.show_results_in_viewer(results)
            self.log(f"已打开结果文件: {path}")
        except Exception as exc:
            messagebox.showerror("打开结果失败", friendly_error(exc))

    def open_latest_result(self):
        candidates = []
        for folder in {self.get_output_dir(), default_output_dir(), Path.cwd() / "outputs", Path.cwd() / "outputs" / "outputs"}:
            if folder.exists():
                candidates.extend(folder.glob("grok_batch_results_*.json"))
                candidates.extend(folder.glob("grok_batch_results_*.csv"))
        if not candidates:
            messagebox.showinfo("没有结果", "还没有找到可打开的结果文件。")
            return
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        try:
            results = self.read_result_file(latest)
            self.show_results_in_viewer(results)
            self.log(f"已打开最近结果: {latest}")
        except Exception as exc:
            messagebox.showerror("打开结果失败", friendly_error(exc))

    def copy_selected_result(self):
        selected = self.result_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        item = self.viewer_results[idx]
        text = extract_text(item).strip() or json.dumps(item, ensure_ascii=False, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log("已复制选中结果。")

    def clear_viewer(self):
        self.viewer_results = []
        self.result_tree.delete(*self.result_tree.get_children())
        self.result_detail.delete("1.0", END)
        self.log("查看器已清空。")

    def get_output_dir(self):
        configured = self.output_folder.get().strip()
        if configured:
            folder = Path(configured)
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        return default_output_dir()

    def check_status(self):
        def work():
            try:
                if self.current_mode() == "openai_chat":
                    raise XAIError("查询进度只适用于 xAI 官方异步 Batch；兼容批量调用会在处理完成后直接导出结果。")
                api_key = self.require_key()
                base = self.base_url.get().strip().rstrip("/")
                bid = self.batch_id.get().strip()
                if not bid:
                    raise XAIError("请填写 Batch ID。")
                if self.current_mode() == "xai_batch":
                    data = request_json("GET", f"/batches/{urllib.parse.quote(bid)}", api_key)
                else:
                    data = request_json_url("GET", f"{base}/batches/{urllib.parse.quote(bid)}", api_key)
                self.log(json.dumps(data.get("state", data), ensure_ascii=False, indent=2))
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"失败: {msg}")
                messagebox.showerror("查询失败", msg)

        self.run_async(work)

    def fetch_results(self):
        def work():
            try:
                mode = self.current_mode()
                if mode == "openai_chat":
                    raise XAIError("获取 Batch 结果只适用于 xAI 官方异步 Batch；兼容批量调用会自动导出结果。")
                api_key = self.require_key()
                base = self.base_url.get().strip().rstrip("/")
                bid = self.batch_id.get().strip()
                if not bid:
                    raise XAIError("请填写 Batch ID。")

                all_results = []
                if mode == "openai_batch_file":
                    batch = request_json_url("GET", f"{base}/batches/{urllib.parse.quote(bid)}", api_key)
                    output_file_id = batch.get("output_file_id")
                    if not output_file_id:
                        raise XAIError(f"Batch 尚未完成或没有 output_file_id: {json.dumps(batch, ensure_ascii=False)}")
                    raw = request_raw_url("GET", f"{base}/files/{urllib.parse.quote(output_file_id)}/content", api_key)
                    for line in raw.decode("utf-8", errors="replace").splitlines():
                        if line.strip():
                            all_results.append(json.loads(line))
                    self.export_results(all_results, bid)
                    return

                if mode in {"xai_batch", "xai_batch_file"}:
                    if mode == "xai_batch":
                        status_data = request_json("GET", f"/batches/{urllib.parse.quote(bid)}", api_key)
                    else:
                        status_data = request_json_url("GET", f"{base}/batches/{urllib.parse.quote(bid)}", api_key)
                    state = status_data.get("state", {}) if isinstance(status_data, dict) else {}
                    pending = state.get("num_pending")
                    if isinstance(pending, int) and pending > 0:
                        raise XAIError(f"Batch 还没完成：num_pending={pending}。请稍后再点“获取并导出结果”。")

                token = None
                while True:
                    query = {"limit": "1000"}
                    if token:
                        query["pagination_token"] = token
                    path = f"/batches/{urllib.parse.quote(bid)}/results?{urllib.parse.urlencode(query)}"
                    if mode in {"xai_batch", "xai_batch_file"}:
                        if base.rstrip("/") == API_BASE:
                            data = request_json("GET", path, api_key)
                        else:
                            data = request_json_url("GET", f"{base}{path}", api_key)
                    else:
                        data = request_json_url("GET", f"{base}{path}", api_key)
                    page = data.get("results") or data.get("batch_requests") or data.get("data")
                    if isinstance(page, list):
                        all_results.extend(page)
                    elif isinstance(data, list):
                        all_results.extend(data)
                    else:
                        all_results.append(data)
                    token = data.get("pagination_token") or data.get("next_page_token") if isinstance(data, dict) else None
                    if not token:
                        break

                self.last_results = all_results
                self.export_results(all_results, bid)
            except Exception as exc:
                msg = friendly_error(exc)
                self.log(f"失败: {msg}")
                messagebox.showerror("导出失败", msg)

        self.run_async(work)

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            Path(path).write_text(self.output.get("1.0", END), encoding="utf-8")
            self.log(f"日志已保存: {path}")


if __name__ == "__main__":
    root = Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    app = GrokBatchTool(root)
    root.mainloop()
