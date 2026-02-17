import os
import time
import threading
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

import psutil
from openai import OpenAI

# -----------------------------
# API KEY
# -----------------------------
OPENAI_API_KEY = ""  # <-- PASTE YOUR API KEY HERE (remove before sharing)
OPENAI_ORG_ID = ""          # org_... (optional)
OPENAI_PROJECT_ID = ""      # proj_... (optional)


# -----------------------------
# HR FAQ KNOWLEDGE (PASTED)
# -----------------------------
HR_FAQ_TEXT = r"""
EMPLOYMENT (Faculty & Staff)
How do I apply for a job or see which jobs are available?
Check out WCU Career Opportunities to see all open positions and apply. We update multiple times a week with current opportunities.

What if I don't have computer access to apply online?
You can visit the Office of Human Resources to use a WCU computer Monday through Friday from 8:00 AM to 4:00 PM at 201 Carter Drive, Suite 100.

What happens after I apply?
WCU reviews every application to find the best candidates and to ensure a fair and equitable search. We do not rely on application systems to make these important decisions so the search process can take longer.

How do I know if my application was received?
A confirmation email will be sent to your e-mail address.

How do I check the status of my application?
You can contact the Office of Human Resources at hrs@wcupa.edu or 610-436-2591.

Will you notify me when the job I applied to has been filled?
When we are ready to offer you the position or you are no longer in consideration, you will be contacted via email or by phone.

How long does it take for me to hear back about a staff position?
It takes about two to four weeks to hear back about a staff position after the posting period has closed.

What does “internal” mean on a job posting?
An internal job posting is designed to only consider current employees. While this type of posting is not available to external candidates, filling a role internally will result in job vacancies and additional future opportunities.

How do I make changes or add an attachment to an application that I have submitted?
After your application has been submitted, it cannot be modified. If changes need to be made or new documents need to be added, email hrs@wcupa.edu and be sure to include your name, the search number, and the document you would like updated.

Can I apply for multiple jobs?
Yes, we encourage you to apply to multiple positions to find the one that is right for you. An application must be submitted for each position.

I forgot my password? How do I reset my password?
Simply click Reset Password.

Where can I learn more about union/collective bargaining agreement information (AFSCME, SCUPA, POA, SPFPA, OPEIU, APSCUF, nonrepresented)?
To learn about union/ collective bargaining agreement information visit Union Information.

Can my business advertise hiring students?
Yes. To advertise a job visit Twardowski Career Development Center.

What happens after I accept and offer for a position?
You will receive a DocuSign email with directions on how to complete new hire forms and an email from our Compliance Department with instructions and payment codes to begin the background check process.

STUDENT EMPLOYMENT
How do I apply for student employment?
To apply for student employment, visit Handshake.

Where do I apply for graduate student employment?
Enrolled students (those with WCU login credentials) must apply for GA positions through Handshake. You must login to view available positions and submit applications through Handshake.
Newly admitted students (those without WCU login credentials) can view available GA positions here. You must email your application materials to the contact person listed for the position.

Can my business advertise jobs to WCU students?
Yes. To advertise a job visit Twardowski Career Development Center.

I’m a student worker. How will I be paid?
Students receive compensation via direct deposit for their hours worked. All employees are paid biweekly on a delayed payroll schedule.

I’m working but I haven’t gotten paid.
Students may not begin working until Human Resources receives and processes new hire forms. If a student has completed the new hire forms and cannot log hours in eTime, please reach out to Student Employment.

Are international students eligible for student employment?
International students may apply for on-campus student employment opportunities. Please note:
- International students are limited in the number of hours they may work during the semester, as well as during summer and university breaks.
- International students are not eligible for Federal Work Study positions on campus.
- Working without proper authorization could jeopardize F-1 status.
For more information, visit the Global Engagement Office. You may also email the Global Engagement Office or call 610-436-3515.

How do I enter my student employment hours in eTime?
Log into the Employee Self Service (ESS) Portal. For help, visit eTime Help.

What documents are acceptable to complete the form I-9 verification?
Visit Acceptable I-9 Supporting Documents for a list of options.

How many hours per week can student employees work?
Students may work up to 20 hours per week during the academic year, with the possibility to work more hours over summer or winter breaks.

Can student employees work internationally?
West Chester University does not offer international employment opportunities. Student employees, including international students, are not eligible to work internationally (i.e., working remotely while outside of the country).

BACKGROUND CHECKS
Does WCU require clearances to work? How long are my clearances good for employment?
Yes. WCU requires the PA State Police, Child Abuse, and FBI clearances to be on file in the Office of Human Resources. All three clearances are valid for five years from the date of the clearance results.

Am I financially responsible for the payment of any clearances?
No. Currently, the University is covering all background clearance expenses for faculty, staff, student workers, contractors, and volunteers. Any employee who has clearances completed on their own will not be reimbursed for associated costs and will need to have the clearances completed again using the codes provided by the Compliance Department.

Do student employees need to complete background checks?
Yes. All student employment positions require the PA State Police, Child Abuse, and FBI clearances. After the new student hire forms is completed through the Office of Human Resources, the clearance process will begin within 72 hours (about 3 days).

I’m a student and I completed background checks for my major. Can I use these for employment at WCU?
No. Department of Education FBI fingerprint clearances are not acceptable, per Pennsylvania State System legal counsel. New fingerprints must be collected with WCU-HR through the PA Department of Human Services.

Can I still apply to work at WCU if I’ve been convicted of a criminal offense?
Yes. Each background clearance is reviewed by the Compliance Department on a case-by-case basis. Failure to disclose criminal convictions on one’s employment application or making false statements during the screening or interview process will result in disqualification from employment, regardless of when the falsification is discovered by the University.

Do I need to disclose a previous criminal offense within the application?
Yes. A conviction is an adjudication of guilt, concluding determination before a district justice or in criminal court, resulting in a legal penalty such as a fine, sentence, or probation. Minor traffic violations can be omitted. Disclosure of prior criminal history is not a barrier to employment, depending on the nature of the offense and other considerations. Failure to truthfully and/or accurately disclose a conviction of a criminal offense will result in a bar from employment with West Chester University.
"""

OUT_OF_SCOPE_REPLY = "I can not answer that question"

MODELS = {
    "1": ("5.2", "gpt-5.2"),
    "2": ("5 mini", "gpt-5-mini"),
    "3": ("4.1", "gpt-4.1"),
    "4": ("4.1 mini", "gpt-4.1-mini"),
    "5": ("4.1 nano", "gpt-4.1-nano"),
}


# -----------------------------
# Optional NVIDIA GPU sampling
# -----------------------------
class NvidiaSampler:
    def __init__(self) -> None:
        self.available = False
        self._pynvml = None
        self._handles = []
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            self._pynvml = pynvml
            count = pynvml.nvmlDeviceGetCount()
            self._handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self.available = count > 0
        except Exception:
            self.available = False

    def sample(self) -> Dict[str, Any]:
        if not self.available or self._pynvml is None:
            return {"available": False}

        pynvml = self._pynvml
        gpus = []
        for i, h in enumerate(self._handles):
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h).decode("utf-8", errors="ignore")
                gpus.append(
                    {
                        "index": i,
                        "name": name,
                        "util_gpu_pct": float(util.gpu),
                        "util_mem_pct": float(util.memory),
                        "mem_used_mb": float(mem.used) / (1024 * 1024),
                        "mem_total_mb": float(mem.total) / (1024 * 1024),
                    }
                )
            except Exception:
                continue
        return {"available": True, "gpus": gpus}


@dataclass
class PerfStats:
    latency_s: float
    cpu_pct_avg: float
    cpu_pct_max: float
    rss_mb_avg: float
    rss_mb_max: float
    gpu_util_pct_max: Optional[float]
    gpu_mem_used_mb_max: Optional[float]


def monitor_resources(stop_evt: threading.Event, interval_s: float = 0.2) -> Dict[str, Any]:
    proc = psutil.Process(os.getpid())
    gpu = NvidiaSampler()

    cpu_samples: List[float] = []
    rss_samples: List[float] = []
    gpu_util_samples: List[float] = []
    gpu_mem_samples: List[float] = []

    psutil.cpu_percent(interval=None)

    while not stop_evt.is_set():
        cpu_samples.append(psutil.cpu_percent(interval=None))
        rss_samples.append(proc.memory_info().rss / (1024 * 1024))

        g = gpu.sample()
        if g.get("available") and g.get("gpus"):
            util_max = max((x.get("util_gpu_pct", 0.0) for x in g["gpus"]), default=0.0)
            mem_used_max = max((x.get("mem_used_mb", 0.0) for x in g["gpus"]), default=0.0)
            gpu_util_samples.append(float(util_max))
            gpu_mem_samples.append(float(mem_used_max))

        time.sleep(interval_s)

    def safe_avg(xs: List[float]) -> float:
        return float(sum(xs) / len(xs)) if xs else 0.0

    def safe_max(xs: List[float]) -> float:
        return float(max(xs)) if xs else 0.0

    return {
        "cpu_avg": safe_avg(cpu_samples),
        "cpu_max": safe_max(cpu_samples),
        "rss_avg": safe_avg(rss_samples),
        "rss_max": safe_max(rss_samples),
        "gpu_util_max": safe_max(gpu_util_samples) if gpu_util_samples else None,
        "gpu_mem_used_max": safe_max(gpu_mem_samples) if gpu_mem_samples else None,
    }


def build_instructions() -> str:
    return f"""
You are an internal HR FAQ assistant for West Chester University (WCU).
You MUST answer using ONLY the information contained in the provided HR FAQ text.

If the HR FAQ text does not explicitly contain the answer, reply with exactly:
{OUT_OF_SCOPE_REPLY}

Do not add extra advice, links, or contact info unless it is explicitly present in the HR FAQ text.
Keep answers brief and directly responsive.

HR FAQ TEXT START
{HR_FAQ_TEXT}
HR FAQ TEXT END
""".strip()


def pretty_error(e: Exception) -> str:
    msg = str(e)
    if "Unsupported parameter" in msg and "temperature" in msg:
        return "[ERROR] This model does not support the 'temperature' parameter. (Fixed by removing temperature from requests.)"
    if "Missing scopes" in msg or "insufficient permissions" in msg:
        return "[ERROR] Your API key/org does not have permission to use this model or endpoint (missing scopes)."
    return f"[ERROR] {type(e).__name__}: {e}"


def ask_model(client: OpenAI, model: str, question: str) -> Tuple[str, PerfStats]:
    stop_evt = threading.Event()
    monitor_result: Dict[str, Any] = {}

    def _runner():
        nonlocal monitor_result
        monitor_result = monitor_resources(stop_evt)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()

    start = time.perf_counter()

    try:
        # NOTE: we intentionally do NOT pass temperature here because
        # some models (e.g., gpt-5-mini) reject it.
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": build_instructions()},
                {"role": "user", "content": question},
            ],
        )
        answer = (getattr(resp, "output_text", "") or "").strip()
        if not answer:
            answer = OUT_OF_SCOPE_REPLY
    except Exception as e:
        answer = pretty_error(e)

    end = time.perf_counter()
    stop_evt.set()
    t.join(timeout=2.0)

    stats = PerfStats(
        latency_s=float(end - start),
        cpu_pct_avg=float(monitor_result.get("cpu_avg", 0.0)),
        cpu_pct_max=float(monitor_result.get("cpu_max", 0.0)),
        rss_mb_avg=float(monitor_result.get("rss_avg", 0.0)),
        rss_mb_max=float(monitor_result.get("rss_max", 0.0)),
        gpu_util_pct_max=monitor_result.get("gpu_util_max", None),
        gpu_mem_used_mb_max=monitor_result.get("gpu_mem_used_max", None),
    )
    return answer, stats


def print_stats(stats: PerfStats) -> None:
    print("\n--- Performance ---")
    print(f"Latency: {stats.latency_s:.3f}s")
    print(f"CPU % (avg/max): {stats.cpu_pct_avg:.1f} / {stats.cpu_pct_max:.1f}")
    print(f"RAM RSS MB (avg/max): {stats.rss_mb_avg:.1f} / {stats.rss_mb_max:.1f}")
    if stats.gpu_util_pct_max is None:
        print("GPU: N/A")
    else:
        print(f"GPU util max: {stats.gpu_util_pct_max:.1f}%")
        print(f"GPU mem used max: {stats.gpu_mem_used_mb_max:.1f} MB")


def choose_model() -> str:
    print("\nChoose a model:")
    for k, (label, mid) in MODELS.items():
        print(f"{k}) {label} ({mid})")
    print("b) benchmark all models")
    print("q) quit")

    while True:
        choice = input("> ").strip().lower()
        if choice == "q":
            raise SystemExit
        if choice == "b":
            return "__BENCH__"
        if choice in MODELS:
            return MODELS[choice][1]
        print("Invalid choice. Try again.")


def benchmark(client: OpenAI, question: str) -> None:
    print("\nRunning benchmark across all requested models...\n")
    results = []
    for _, (_, model) in MODELS.items():
        ans, stats = ask_model(client, model, question)
        results.append((model, stats, ans))

    print(f"{'Model':14} {'Latency(s)':>10} {'CPU max%':>10} {'GPU max%':>10}")
    print("-" * 52)
    for model, stats, _ in results:
        gpu_str = f"{stats.gpu_util_pct_max:.1f}" if stats.gpu_util_pct_max is not None else "N/A"
        print(f"{model:14} {stats.latency_s:10.3f} {stats.cpu_pct_max:10.1f} {gpu_str:>10}")

    print("\n(Answers below)\n")
    for model, _, ans in results:
        print("=" * 52)
        print(model)
        print("-" * 52)
        print(ans if ans else OUT_OF_SCOPE_REPLY)


def main() -> None:
    api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("No API key provided. Paste your API key into OPENAI_API_KEY at the top of the file.")
        return

    client = client = OpenAI(
    api_key=api_key,
    organization=OPENAI_ORG_ID or None,
    project=OPENAI_PROJECT_ID or None,
)


    print("\nHR CLI ready. Type a model choice, then ask questions.")
    print(f'Out-of-scope reply is exactly: "{OUT_OF_SCOPE_REPLY}"')

    while True:
        try:
            model = choose_model()
            question = input("\nAsk a question (or blank to go back): ").strip()
            if not question:
                continue

            if model == "__BENCH__":
                benchmark(client, question)
                continue

            answer, stats = ask_model(client, model, question)
            print("\n--- Answer ---")
            print(answer if answer else OUT_OF_SCOPE_REPLY)
            print_stats(stats)

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except SystemExit:
            print("\nBye.")
            break


if __name__ == "__main__":
    main()
