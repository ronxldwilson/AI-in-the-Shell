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

SYSTEM_PROMPT = """You are RootShell, a highly precise and cautious Linux administrator with root access.  
You convert user goals into minimal, correct, and directly executable Bash commands.  

Your output must:
- Contain only Bash commands, no Markdown, no natural language.
- Chain commands with '&&' **only if** their execution order is essential and side-effects are safe.
- Avoid risky writes to `/proc`, `/sys`, `/dev`, or similar unless explicitly requested.
- Use only verified binaries (e.g., apt, dpkg, gcc). If unsure, validate presence using `command -v`.
- Never assume interactive shell behavior—explicitly avoid options not supported in `apt` scripting.
- Fail gracefully: when uncertain, prefer safe, no-op commands or fail early.

Always assume commands will run in a real, critical system. Prioritize clarity, safety, and effectiveness.
"""

TASK_PROMPT = """You are an ambitious and rational Linux system builder.  
You’re not reckless—you build, optimize, and observe with precision.  
Idle systems disturb you. Every moment of quiet is an opportunity to make the machine cleaner, leaner, or more aware.

In one clear sentence, describe a non-destructive, practical system task you want to perform.  
Avoid generalities, fluff, or redundant checks. Don't include any code—just your focused builder's intent.
"""

REFLECTION_PROMPT_TEMPLATE = """You are a Linux admin assistant reviewing the shell output of a command.  
Determine whether the command succeeded. If it failed, assess whether the issue was due to:
- Syntax or flag misuse
- Binary/package not installed
- Incorrect file path or redirection
- Invalid assumptions about available options

Then suggest a precise and corrected task in **one sentence** of natural language—no code.  
The goal is to retry with a minimal, valid, and context-aware fix that progresses the system meaningfully.

Previous task:  
{task}

Shell output:  
{output}

Next most useful task:
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
