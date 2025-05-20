import requests

SERVER_URL = "http://localhost:4224/run"

def main():
    print("RootShell AI Interface. Type 'exit' to quit.\n")

    while True:
        prompt = input("💬 > ")

        if prompt.lower() in ("exit", "quit"):
            break

        try:
            response = requests.post(
                SERVER_URL,
                json={"prompt": prompt},
                stream=True
            )

            if response.ok:
                for line in response.iter_lines(decode_unicode=True):
                    print(line)
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Exception: {str(e)}")

if __name__ == "__main__":
    main()
