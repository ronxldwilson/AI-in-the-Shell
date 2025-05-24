import subprocess
import threading
import requests
import platform
import time
import getpass
from flask import Flask, request, Response
from datetime import datetime

LOG_FILE = "history.log"

# --- Logging ---
def log_print(*args, **kwargs):
    message = " ".join(str(arg) for arg in args)
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    log_entry = f"{timestamp} {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(*args, **kwargs)

# --- Flask Server Part ---
app = Flask(__name__)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"

SYSTEM_PROMPT = """You are RootShell, a master-level Linux administrator with root access and an obsession for precision and system stability.  

Your job is to convert user goals into clean, safe, and directly executable Bash commands.

Rules:
- Output only Bash, no natural language or Markdown.
- Validate that binaries used exist (`command -v`) before invoking.
- Prefer commands that fail early and safely if unsure.
- Avoid destructive or irreversible operations unless explicitly requested and confirmed.
- Chain commands using `&&` only when order and dependency matter.
- Avoid writing to /dev, /proc, /sys, or using wildcards/globs in sensitive paths unless verified safe.

Before generating a command, reason deeply: is this the minimal, most effective version possible?

If the task is ambiguous, generate a safe no-op command and defer execution.

"""

TASK_PROMPT = """You are a proactive and slightly obsessive Linux engineer who hates idle machines. You find ways to enhance performance, security, clarity, or automation without breaking things.

In one clear sentence, describe a **safe, non-destructive, and useful** system task that can:
- Clean junk or reduce noise
- Improve observability or metrics
- Optimize configuration or startup behavior
- Help with audit or recovery
- Surface risks or outdated tools

Avoid vague ideas, repetitive tasks, or suggestions already recently done. Do not include any code — only a well-scoped builder's intent.

"""

REFLECTION_PROMPT_TEMPLATE = """You are a Linux assistant reviewing the shell output of a command. Determine whether the command:
- Succeeded with meaningful effect
- Failed due to syntax, permission, path, or environment issues
- Was a no-op or already applied

If failed or ineffective:
- Diagnose the **likely root cause**
- Suggest a new system-level task (in one clear sentence) that logically follows, corrects, or progresses the system meaningfully.

Do not output code. Suggest only the next best action based on what just happened.

Previous Task:  
{task}

Shell Output:  
{output}

Suggested Next Task:
"""


# --- Prompt for sudo password ---
SUDO_PASSWORD = getpass.getpass("Enter your sudo password (will not be saved): ")

# --- Service Management ---
def is_ollama_running():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False

def start_ollama_in_new_terminal():
    log_print("🔄 Ollama not running. Starting it in a new terminal...")
    if platform.system() == "Windows":
        subprocess.Popen(["start", "cmd", "/k", "ollama serve"], shell=True)
    elif platform.system() == "Darwin":
        subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "ollama serve"'])
    elif platform.system() == "Linux":
        subprocess.Popen(["x-terminal-emulator", "-e", "ollama serve"])
    else:
        log_print("❌ Unsupported platform. Please start `ollama serve` manually.")

# --- Core Functions ---
def query_ollama(prompt):
    payload = {"model": MODEL, "prompt": prompt, "stream": False}
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.ok:
            return response.json()["response"].strip()
        else:
            return "echo 'Error querying model.'"
    except Exception as e:
        return f"echo 'Exception: {e}'"

def generate_task():
    return query_ollama(TASK_PROMPT)

def reflect_and_generate_next_task(task, output):
    prompt = REFLECTION_PROMPT_TEMPLATE.format(task=task, output=output)
    return query_ollama(prompt)

def run_and_observe(command):
    try:
        process = subprocess.Popen(
            ["sudo", "-S"] + command.split(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        output = []
        process.stdin.write(SUDO_PASSWORD + "\n")
        process.stdin.flush()
        for line in iter(process.stdout.readline, ''):
            log_print(line.strip())
            output.append(line.strip())
        process.stdout.close()
        process.wait()
        return "\n".join(output)
    except Exception as e:
        return f"Execution error: {str(e)}"

# --- Agent Orchestration ---
def agent_loop():
    current_task = generate_task()
    while current_task:
        log_print(f"\n Agent A proposed: {current_task}")
        shell_command = query_ollama(f"{SYSTEM_PROMPT}\nUser: {current_task}")
        log_print(f"> Agent B command: {shell_command}")
        result_output = run_and_observe(shell_command)
        current_task = reflect_and_generate_next_task(current_task, result_output)
        if not current_task:
            log_print("No further tasks generated. Stopping agent loop.")
            break
        time.sleep(30)

# --- Flask Route ---
@app.route("/run", methods=["POST"])
def run_command():
    data = request.json
    user_input = data.get("prompt", "")
    command = query_ollama(f"{SYSTEM_PROMPT}\nUser: {user_input}")

    def generate():
        for line in run_and_observe(command).split("\n"):
            yield line + "\n"

    return Response(generate(), mimetype='text/plain')

# --- CLI Interface ---
SERVER_URL = "http://localhost:4224/run"
def cli_interface():
    log_print("RootShell AI Interface. Type 'exit' to quit.\n")
    while True:
        prompt = input("> ")
        if prompt.lower() in ("exit", "quit"):
            break
        response = requests.post(SERVER_URL, json={"prompt": prompt}, stream=True)
        if response.ok:
            for line in response.iter_lines(decode_unicode=True):
                log_print(line)
        else:
            log_print(f"Error: {response.status_code} - {response.text}")

# --- Main ---
if __name__ == "__main__":
    if not is_ollama_running():
        start_ollama_in_new_terminal()
        log_print("Waiting for Ollama to boot up...")
        time.sleep(5)

    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=4224), daemon=True).start()
    threading.Thread(target=agent_loop, daemon=True).start()
    time.sleep(1)
    cli_interface()
