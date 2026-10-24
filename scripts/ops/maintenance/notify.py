import argparse
import os

import requests
from dotenv import load_dotenv

load_dotenv()

def send_telegram_alert(message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        print("Telegram notification sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Telegram alerts from CI/CD pipeline")
    parser.add_argument("--file", type=str, help="Path to file containing the message", required=False)
    parser.add_argument("--message", type=str, help="Direct message string", required=False)
    args = parser.parse_args()

    message_content = ""
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            message_content = f.read()
    elif args.message:
        message_content = args.message
    else:
        message_content = "⚠️ Immune System: Triggered with empty payload."

    # Truncate if too long (Telegram limit is 4096)
    if len(message_content) > 4000:
        message_content = message_content[:4000] + "\n...[Truncated]"

    final_message = f"🛡️ *SupremeAI Immune System Report*\n\n```text\n{message_content}\n```"
    send_telegram_alert(final_message)
