import subprocess
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"

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
        return "Error querying model."

def execute_shell(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

@app.route("/run", methods=["POST"])
def run_command():
    data = request.json
    user_input = data.get("prompt", "")
    command = query_ollama(user_input)
    output = execute_shell(command)
    return jsonify({
        "user_input": user_input,
        "command": command,
        "output": output
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6969)
