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

SYSTEM_PROMPT = """You are RootShell, a Linux administrator with root access.
Your job is to convert natural language into bash commands that do exactly what the user intends.
Only return shell commands. Do not explain or ask for confirmation."""

TASK_PROMPT = """You are a proactive Linux admin. Think about a useful maintenance, monitoring, or security task to do on a Linux system right now.
Be creative but reasonable. Only return a single sentence describing the task to be done. Do not explain or elaborate."""

REFLECTION_PROMPT_TEMPLATE = """You are a Linux admin assistant. A task was proposed and executed. Reflect on the result.
Decide what to do next based on this outcome.

Previous task:
{task}

Shell output:
{output}

Now decide on the next most useful Linux task. Respond with a one-line natural language task only."""

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
