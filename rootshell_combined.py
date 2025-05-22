import subprocess
import threading
import requests
import platform
import time
from flask import Flask, request, Response
from datetime import datetime

LOG_FILE = "history.log"

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
Be creative but reasonable. Only return a **single sentence** describing the task to be done. Do not explain or elaborate.
"""

def generate_task():
    payload = {
        "model": MODEL,
        "prompt": TASK_PROMPT,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.ok:
            return response.json()["response"].strip()
        else:
            return "Check system uptime."
    except Exception as e:
        return f"Check failed task gen: {e}"

def autonomous_loop():
    while True:
        task = generate_task()
        log_print(f"\n🤖 Agent A suggested task: {task}")
        
        # Ask Agent B (RootShell) to convert it to a command
        command = query_ollama(task).strip()
        log_print(f"> RootShell command: {command}")

        for line in stream_shell(command):
            log_print(line.strip())

        time.sleep(120)  # wait before next task

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
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "ollama serve"'])
    elif platform.system() == "Linux":
        subprocess.Popen(["x-terminal-emulator", "-e", "ollama serve"])
    else:
        log_print("❌ Unsupported platform. Please start `ollama serve` manually.")

def query_ollama(user_input):
    payload = {
        "model": MODEL,
        "prompt": f"{SYSTEM_PROMPT}\nUser: {user_input}",
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.ok:
            return response.json()["response"]
        else:
            return "echo 'Error querying model.'"
    except Exception as e:
        return f"echo 'Exception: {e}'"

def stream_shell(command):
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in iter(process.stdout.readline, ''):
            yield line
        process.stdout.close()
        process.wait()
    except Exception as e:
        yield f"Error: {str(e)}\n"

@app.route("/run", methods=["POST"])
def run_command():
    data = request.json
    user_input = data.get("prompt", "")
    # log_print(f"User input (from API): {user_input}")  
    command = query_ollama(user_input).strip()

    def generate():
        log_print(f"\n> {command}\n")  
        for line in stream_shell(command):
            log_print(line.strip())     # Log each line from shell output
            yield line


    return Response(generate(), mimetype='text/plain')

# --- CLI Interface ---
SERVER_URL = "http://localhost:4224/run"

def cli_interface():
    log_print("RootShell AI Interface. Type 'exit' to quit.\n")
    while True:
        prompt = input("> ")
        if prompt.lower() in ("exit", "quit"):
            break
        log_print(f"User input: {prompt}")  
        try:
            response = requests.post(SERVER_URL, json={"prompt": prompt}, stream=True)
            if response.ok:
                for line in response.iter_lines(decode_unicode=True):
                    log_print(line)
            else:
                log_print(f"Error: {response.status_code} - {response.text}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log_print(f"Exception: {str(e)}")

if __name__ == "__main__":
    if not is_ollama_running():
        start_ollama_in_new_terminal()
        log_print("⏳ Waiting for Ollama to boot up...")
        time.sleep(5)

    # Start Flask server
    server_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=4224), daemon=True)
    server_thread.start()

    # Start autonomous agent
    auto_thread = threading.Thread(target=autonomous_loop, daemon=True)
    auto_thread.start()

    time.sleep(1)
    cli_interface()
