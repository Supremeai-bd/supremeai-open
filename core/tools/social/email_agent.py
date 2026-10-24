import email
import imaplib
import re
from email.header import decode_header
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.security.secure_credential_store import SecureCredentialStore


class EmailAgent:
    """
    গ্যাপ ফিক্স (Anti-Silent-Failure): আগে এই ক্লাসের connect_gmail_oauth()/connect_imap()
    সবসময় True রিটার্ন করত এবং কোনো ক্রেডেনশিয়াল আসলে যাচাই বা সংরক্ষণ করত না। receive_otp()
    সবসময় একটি হার্ডকোড করা fake OTP ("849301") রিটার্ন করত — /integrations/email/gmail এবং
    /integrations/email/imap পাবলিক রাউট (api/routes/email.py) থেকে সরাসরি এক্সপোজড থাকায়
    ইউজার মনে করতেন তাদের ইমেইল সত্যিই কানেক্টেড, অথচ backend কিছুই করত না।

    এখন: IMAP-এর জন্য প্রকৃত imaplib কানেকশন যাচাই + এনক্রিপ্টেড ক্রেডেনশিয়াল সংরক্ষণ
    (SecureCredentialStore, browser.py-তে ইতিমধ্যে ব্যবহৃত একই প্যাটার্ন), এবং receive_otp()
    সত্যিকারের ইনবক্স পোল করে OTP খোঁজে — কোনো fake ডেটা রিটার্ন করে না।
    Gmail OAuth-এর জন্য প্রকৃত consent/redirect ফ্লো এখনো তৈরি হয়নি, তাই সেটি এখন সততার
    সাথে ব্যর্থ (fail-closed) হয়, silent-success দেখায় না।
    """

    def __init__(self, auth_method: str = "oauth"):
        self.auth_method = auth_method
        self.connected = False
        # Issue #1845 fix: SecureCredentialStore এখন LAZY — প্রথম ব্যবহারের সময়
        # তৈরি হয় (api/routes/browser/_credentials.py-র factory প্যাটার্নের মতো,
        # যেটা এই মডিউলের docstring নিজেই নিজের প্যাটার্ন হিসেবে দাবি করে)। আগে
        # __init__-এই তৈরি হতো, কিন্তু এই অবজেক্ট api/routes/email.py-তে module-level
        # singleton — import করার মুহূর্তে env-এ encryption key এখনো থাকে না
        # (CI/test fixture পরে সেট করে; প্রোডাকশনে vault bootstrap পরে লোড হয়)।
        # ফলে fail-closed (#1570) store চিরকালের জন্য disabled হয়ে যেত এবং
        # connect_imap() সবসময় CredentialEncryptionUnavailableError → 500 দিত।
        self._credential_store: SecureCredentialStore | None = None
        self._imap_config: dict[str, Any] | None = None
        logger.info(f"EmailAgent initialized with auth_method={auth_method}")

    @property
    def credential_store(self) -> SecureCredentialStore:
        """Key env-var-গুলো first-use-এর সময় পড়ে — import-time eager নয়।"""
        if self._credential_store is None:
            self._credential_store = SecureCredentialStore()
        return self._credential_store

    def connect_gmail_oauth(self, provider: str, scopes: list) -> bool:
        """Gmail OAuth এখনো real consent/token-exchange ফ্লো-র সাথে ওয়্যার করা হয়নি।
        আগে এখানে চুপচাপ True রিটার্ন হতো — এখন fail-closed: NotImplementedError রেইজ করে
        যাতে caller ভুল করে ধরে না নেয় যে ইমেইল অ্যাকাউন্ট আসলে কানেক্টেড এবং API রুট 501 পাঠাতে পারে।
        """
        logger.warning(
            f"Gmail OAuth connect requested (provider={provider}, scopes={scopes}) — OAuth flow not implemented yet."
        )
        raise NotImplementedError("Gmail OAuth flow is not implemented yet.")

    def connect_imap(self, host: str, port: int, username: str, app_password: str) -> bool:
        """একটি রিয়েল IMAP লগইন করে ক্রেডেনশিয়াল যাচাই করে, তারপর এনক্রিপ্ট করে সংরক্ষণ করে।"""
        try:
            with imaplib.IMAP4_SSL(host, port, timeout=10) as imap:
                imap.login(username, app_password)
        except (imaplib.IMAP4.error, OSError) as exc:
            logger.error(f"IMAP login failed for {username}@{host}:{port}: {exc}")
            self.connected = False
            return False

        ciphertext, key_ref = self.credential_store.encrypt(app_password)
        self._imap_config = {
            "host": host,
            "port": port,
            "username": username,
            "ciphertext": ciphertext,
            "key_ref": key_ref,
        }
        self.auth_method = "imap"
        self.connected = True
        logger.info(
            f"IMAP connection verified and credentials stored (encrypted) for {username}@{host}:{port}"
        )
        return True

    def receive_otp(self, website: str, lookback: int = 10) -> str:
        """সংযুক্ত ইনবক্স থেকে সাম্প্রতিক unread মেইল পোল করে `website`-সম্পর্কিত একটি রিয়েল OTP খোঁজে।
        কোনো লাইভ কানেকশন না থাকলে বা OTP না পাওয়া গেলে খালি স্ট্রিং রিটার্ন করে — কখনো fabricate করে না।
        """
        if self.auth_method != "imap" or not self._imap_config or not self.connected:
            logger.warning(
                "receive_otp() called without a live IMAP connection — cannot fetch a real OTP."
            )
            return ""

        cfg = self._imap_config
        try:
            app_password = self.credential_store.decrypt(cfg["ciphertext"], cfg["key_ref"])
        except Exception as exc:
            logger.error(f"Failed to decrypt stored IMAP credentials: {exc}")
            return ""

        try:
            with imaplib.IMAP4_SSL(cfg["host"], cfg["port"], timeout=10) as imap:
                imap.login(cfg["username"], app_password)
                imap.select("INBOX")
                status, data = imap.search(None, "UNSEEN")
                if status != "OK" or not data or not data[0]:
                    return ""
                msg_ids = data[0].split()[-lookback:]
                for msg_id in reversed(msg_ids):
                    status, msg_data = imap.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = self._decode_mime(msg.get("Subject", ""))
                    sender = msg.get("From", "")
                    body = self._extract_body(msg)
                    haystack = f"{subject} {sender} {body}".lower()
                    if website.lower() not in haystack:
                        continue
                    otp = self.extract_otp(body) or self.extract_otp(subject)
                    if otp:
                        return otp
        except (imaplib.IMAP4.error, OSError) as exc:
            logger.error(f"IMAP poll failed while looking for OTP from {website}: {exc}")
        return ""

    @staticmethod
    def _decode_mime(value: str) -> str:
        parts = decode_header(value or "")
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                decoded.append(part)
        return "".join(decoded)

    @staticmethod
    @with_error_bus("_extract_body")
    def _extract_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(
                    part.get("Content-Disposition")
                ):
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            return payload.decode(
                                part.get_content_charset() or "utf-8", errors="ignore"
                            )
                    except Exception as exc:
                        # বাংলা মন্তব্য: এক MIME part decode fail করলেও পরবর্তী part-এ চেষ্টা
                        # চালিয়ে যাওয়া উচিত, কিন্তু আগে সম্পূর্ণ silent ছিল -- এখন
                        # debug-level log রাখা হলো যাতে trace করা সহজ হয়।
                        logger.debug(f"Skipping unreadable MIME part while extracting body: {exc}")
                        continue
            return ""
        try:
            payload = msg.get_payload(decode=True)
            return (
                payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
                if payload
                else ""
            )
        except Exception:
            return ""

    def extract_otp(self, email_body: str) -> str:
        """Extract a 4 to 8 digit numeric OTP from email body text."""
        match = re.search(r"\b\d{4,8}\b", email_body or "")
        if match:
            return match.group(0)
        return ""

    def signup_flow(self, website_url: str) -> dict:
        """সংযুক্ত ইনবক্স থেকে রিয়েল OTP পোল করে — কখনো fabricated OTP বা fake 'stored_in_vault' দাবি করে না।"""
        logger.info(f"Starting automated signup flow for {website_url}")
        if not self.connected:
            return {
                "status": "failed",
                "reason": "No email account connected. Call connect_imap() first.",
            }
        otp = self.receive_otp(website_url)
        if otp:
            return {"status": "success", "credentials_encrypted": True, "otp": otp}
        return {"status": "failed", "reason": "OTP not found in recent inbox messages"}
