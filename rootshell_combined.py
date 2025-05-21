import subprocess
import threading
import requests
import platform
import time
from flask import Flask, request, Response

# --- Flask Server Part ---
app = Flask(__name__)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"

SYSTEM_PROMPT = """You are RootShell, a Linux administrator with root access.
Your job is to convert natural language into bash commands that do exactly what the user intends.
Only return shell commands. Do not explain or ask for confirmation."""

def is_ollama_running():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False

def start_ollama_in_new_terminal():
    print("🔄 Ollama not running. Starting it in a new terminal...")
    if platform.system() == "Windows":
        subprocess.Popen(["start", "cmd", "/k", "ollama serve"], shell=True)
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["osascript", "-e", 'tell app "Terminal" to do script "ollama serve"'])
    elif platform.system() == "Linux":
        subprocess.Popen(["x-terminal-emulator", "-e", "ollama serve"])
    else:
        print("❌ Unsupported platform. Please start `ollama serve` manually.")

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
    command = query_ollama(user_input).strip()

    def generate():
        yield f"\n> {command}\n\n"
        yield from stream_shell(command)

    return Response(generate(), mimetype='text/plain')

# --- CLI Interface ---
SERVER_URL = "http://localhost:4224/run"

def cli_interface():
    print("RootShell AI Interface. Type 'exit' to quit.\n")
    while True:
        prompt = input("> ")
        if prompt.lower() in ("exit", "quit"):
            break
        try:
            response = requests.post(SERVER_URL, json={"prompt": prompt}, stream=True)
            if response.ok:
                for line in response.iter_lines(decode_unicode=True):
                    print(line)
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Exception: {str(e)}")

# --- Main Entry ---
if __name__ == "__main__":
    if not is_ollama_running():
        start_ollama_in_new_terminal()
        print("⏳ Waiting for Ollama to boot up...")
        time.sleep(5)

    server_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=4224), daemon=True)
    server_thread.start()

    time.sleep(1)
    cli_interface()
