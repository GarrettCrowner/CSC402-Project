import os
import sys
import json
import time
import platform
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

import httpx
import psutil


# -----------------------------
# Optional NVIDIA GPU stats
# -----------------------------
def try_get_nvidia_gpu_stats() -> Optional[Dict[str, Any]]:
    """
    Returns basic NVIDIA GPU stats if pynvml is installed and NVML is available.
    """
    try:
        import pynvml  # type: ignore
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle).decode("utf-8", errors="ignore")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

            gpus.append({
                "index": i,
                "name": name,
                "memory_total_mb": round(mem.total / (1024**2), 2),
                "memory_used_mb": round(mem.used / (1024**2), 2),
                "gpu_util_percent": util.gpu,
                "mem_util_percent": util.memory,
                "temperature_c": temp,
            })
        pynvml.nvmlShutdown()
        return {"nvidia_gpus": gpus}
    except Exception:
        return None


# -----------------------------
# Hardware sampling helpers
# -----------------------------
def system_snapshot(process: psutil.Process) -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    cpu_count = psutil.cpu_count(logical=True) or 0

    # cpu_percent(None) needs a prior call; we do a quick small interval to get a reading
    cpu_percent = psutil.cpu_percent(interval=0.1)

    proc_mem = process.memory_info()
    proc_cpu = process.cpu_percent(interval=0.0)  # percent since last call

    snap = {
        "platform": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python": sys.version.split()[0],
            "cpu_logical_cores": cpu_count,
        },
        "system": {
            "cpu_percent": cpu_percent,
            "ram_total_mb": round(vm.total / (1024**2), 2),
            "ram_used_mb": round((vm.total - vm.available) / (1024**2), 2),
            "ram_percent": vm.percent,
        },
        "process": {
            "pid": process.pid,
            "rss_mb": round(proc_mem.rss / (1024**2), 2),
            "vms_mb": round(proc_mem.vms / (1024**2), 2),
            "cpu_percent": proc_cpu,
        }
    }

    gpu = try_get_nvidia_gpu_stats()
    if gpu:
        snap.update(gpu)

    return snap


# -----------------------------
# Metrics dataclass
# -----------------------------
@dataclass
class CallMetrics:
    question: str
    model: str
    streaming: bool
    status_code: int
    ttft_seconds: Optional[float]          # time-to-first-token (streaming only)
    total_seconds: float                   # end-to-end latency
    input_chars: int
    output_chars: int
    output_preview: str
    hw_before: Dict[str, Any]
    hw_after: Dict[str, Any]


# -----------------------------
# OpenAI-compatible client
# -----------------------------
class OpenAICompatibleChat:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 120.0):
        """
        base_url examples:
          - https://api.openai.com/v1
          - http://localhost:8000/v1
          - https://your-provider.example.com/v1
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout_s),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self):
        self.client.close()

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        stream: bool = True,
    ):
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if not stream:
            r = self.client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            return r.status_code, text, None  # None = ttft

        # Streaming
        ttft = None
        chunks = []
        start = time.perf_counter()

        with self.client.stream("POST", url, json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[len("data: "):]

                if line.strip() == "[DONE]":
                    break

                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                delta = evt.get("choices", [{}])[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    if ttft is None:
                        ttft = time.perf_counter() - start
                    chunks.append(piece)
                    # print as it streams
                    print(piece, end="", flush=True)

        print()  # newline after streaming
        return 200, "".join(chunks), ttft


# -----------------------------
# Main CLI app
# -----------------------------
def prompt_default(label: str, default: str) -> str:
    val = input(f"{label} [{default}]: ").strip()
    return val or default


def main():
    print("LLM Chat + Latency/Hardware Monitor (OpenAI-compatible)")
    print("-" * 60)

    base_url = prompt_default("Base URL", os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    api_key = os.environ.get("LLM_API_KEY") or input("API key (won't be echoed): ").strip()
    model = prompt_default("Model", os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    temperature = float(prompt_default("Temperature", os.environ.get("LLM_TEMPERATURE", "0.7")))
    stream_str = prompt_default("Stream responses? (y/n)", os.environ.get("LLM_STREAM", "y")).lower()
    stream = stream_str.startswith("y")

    log_path = prompt_default("Metrics log file", os.environ.get("LLM_LOG_PATH", "llm_metrics.jsonl"))

    llm = OpenAICompatibleChat(base_url=base_url, api_key=api_key)
    process = psutil.Process(os.getpid())

    # prime process CPU percent tracking
    process.cpu_percent(interval=None)

    conversation: List[Dict[str, str]] = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]

    print("\nType your question. Commands: /exit, /reset, /stats\n")

    try:
        while True:
            q = input("You: ").strip()
            if not q:
                continue
            if q == "/exit":
                break
            if q == "/reset":
                conversation = [{"role": "system", "content": "You are a helpful assistant."}]
                print("Conversation reset.\n")
                continue
            if q == "/stats":
                snap = system_snapshot(process)
                print(json.dumps(snap, indent=2))
                print()
                continue

            hw_before = system_snapshot(process)

            conversation.append({"role": "user", "content": q})

            print("Assistant:", end=" " if stream else "\n", flush=True)
            start = time.perf_counter()
            status_code = 0
            ttft = None

            try:
                status_code, answer, ttft = llm.chat(
                    model=model,
                    messages=conversation,
                    temperature=temperature,
                    stream=stream,
                )
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                answer = f"[HTTP error] {status_code}: {e.response.text}"
                print(answer)
            except Exception as e:
                status_code = -1
                answer = f"[Error] {type(e).__name__}: {e}"
                print(answer)

            total = time.perf_counter() - start

            conversation.append({"role": "assistant", "content": answer})

            hw_after = system_snapshot(process)

            metrics = CallMetrics(
                question=q,
                model=model,
                streaming=stream,
                status_code=status_code,
                ttft_seconds=ttft,
                total_seconds=total,
                input_chars=len(q),
                output_chars=len(answer),
                output_preview=(answer[:180] + "…") if len(answer) > 180 else answer,
                hw_before=hw_before,
                hw_after=hw_after,
            )

            # Print a short metrics summary
            if stream and ttft is not None:
                print(f"\n[metrics] TTFT: {ttft:.3f}s | Total: {total:.3f}s | Status: {status_code}")
            else:
                print(f"\n[metrics] Total: {total:.3f}s | Status: {status_code}")

            # Append metrics to JSONL log
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(metrics)) + "\n")

            print(f"[metrics] Logged -> {log_path}\n")

    finally:
        llm.close()
        print("Goodbye!")


if __name__ == "__main__":
    main()
