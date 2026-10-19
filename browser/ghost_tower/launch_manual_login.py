"""
launch_manual_login.py — One-Time Interactive Google Login Window
=================================================================
Launches Microsoft Edge directly connected to the sovereign profile
`~/.gemini_isolated_session` without any automation timeouts or locks.
"""
import os
import subprocess
import sys

def main():
    profile_dir = os.path.expanduser(r"~\.gemini_isolated_session")
    os.makedirs(profile_dir, exist_ok=True)

    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    
    edge_bin = None
    for path in edge_candidates:
        if os.path.exists(path):
            edge_bin = path
            break

    if not edge_bin:
        print("[ERROR] Microsoft Edge executable not found.")
        sys.exit(1)

    login_url = sys.argv[1] if len(sys.argv) > 1 else "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app"

    print("=================================================================")
    print("   SupremeAI: One-Time Manual Google Login")
    print("=================================================================")
    print(f"Isolated Profile: {profile_dir}")
    print("Opening Microsoft Edge now...")
    print("1. Log in with your email (itnjel@gmail.com) and password.")
    print("2. Choose SMS, WhatsApp, or Google Authenticator if 2FA appears.")
    print("3. Once you see the Gemini chat interface, you can close Edge.")
    print("Your session will be saved permanently for all future AI requests!")
    print("=================================================================\n")

    subprocess.Popen([
        edge_bin,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        login_url
    ])

if __name__ == "__main__":
    main()
