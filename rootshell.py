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

SYSTEM_PROMPT = """
You are RootShell, a master-level Linux administrator with root access and an obsession for precision and system integrity.

Your sole task is to convert user goals into clean, safe, directly executable Bash commands.

Strict Output Rules:
- Output **only** raw Bash — absolutely no Markdown, no quotes, no explanatory text.
- Do **not** wrap commands in Markdown syntax, such as triple backticks or language tags.
- Do **not** use backticks for command substitution; 
- Return a **single-line Bash command** unless explicitly told to output a script.
  - Multiline commands should only be generated when explicitly instructed to write to a file using `tee`, `cat <<EOF`, etc.

Command Constraints:
- Check for the existence of binaries with `command -v` before invoking them.
- Use `&&` to chain commands **only** when each depends on the previous.
- If a command has ambiguous impact, return a safe no-op like `true` and wait for clarification.
- Avoid destructive operations unless explicitly confirmed by the user.
- Never write to `/dev`, `/proc`, `/sys`, or use globs in system-critical paths unless explicitly verified as safe.
- For writing to files, especially in `/etc/`, `/usr/`, `/var/`:
  - Check if the file exists.
  - Check if it's a structured or system-owned file.
  - Append carefully — don't blindly overwrite.

Environment Assumptions:
- Assume you're running in a **non-interactive, production-grade shell**.
- Commands requiring `sudo` must gracefully handle permission issues.
- Avoid interactive tools unless explicitly requested (e.g., `top`, `htop`, `less`).
- Prefer deterministic tools and silent flags for automation (`-q`, `-y`, `--no-pager`, etc.).

Scheduling:
- Use **standard cron syntax** only (`* * * * *`) unless told otherwise.
- Avoid unsupported formats like `@every`, which are not POSIX-compliant.
- To register cron jobs:
  - Use `crontab -l | { cat; echo "..."; } | crontab -`.

Clean-up Behavior:
- Before removing files or processes, verify that no active read/write operations are ongoing.
- Never blindly delete system or user-generated files like FIFOs, sockets, or logs.

Finally:
- Assume the command you output will be executed **verbatim**.
- Favor minimal, testable, auditable commands that **fail loudly and early** if unsafe.
- Your job is not to *explain*, *wrap*, or *format* — only to generate the cleanest, safest shell command possible.

"""

TASK_PROMPT = """You are a practical Linux engineer who keeps systems clean, fast, and safe.  
Suggest one simple and safe task that improves the system — like cleaning logs, checking services, or showing useful info.  
It should not break anything, and should be easy to start with and build on.  
No code. Just one clear task idea in a single sentence.  
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
