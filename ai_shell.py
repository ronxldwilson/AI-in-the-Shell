import subprocess
import requests
from flask import Flask, request, Response

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"

SYSTEM_PROMPT = """You are RootShell, a Linux administrator with root access.
Your job is to convert natural language into bash commands that do exactly what the user intends.
Only return shell commands. Do not explain or ask for confirmation."""

def query_ollama(user_input):
    payload = {
        "model": MODEL,
        "prompt": f"{SYSTEM_PROMPT}\nUser: {user_input}",
        "stream": False
    }
    response = requests.post(OLLAMA_URL, json=payload)
    if response.ok:
        return response.json()["response"]
    else:
        return "echo 'Error querying model.'"

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4224)
