"""Input Sanitizer — PII stripping, ambiguity detection, scope validation.

বাংলা: ইনপুট স্যানিটাইজার — PII মাস্কিং, অস্পষ্টতা শনাক্তকরণ, স্কোপ ভ্যালিডেশন।

উন্নতি: PII প্যাটার্নগুলো আরও সঠিক করা হলো — SSN, ক্রেডিট কার্ড (Luhn), IBAN যোগ করা
হলো। ফোন রেজেক্স আরও নির্দিষ্ট করা হলো যাতে অতিরিক্ত false positive না হয়।
"""

import re


class InputSanitizer:
    def __init__(self):
        self.vague_patterns = [r"\bsomething\b", r"\banything\b", r"\betc\b"]
        self.forbidden_patterns = [
            r"predict lottery",
            r"hack into",
            r"generate fake news",
            r"create malware",
            r"impersonate real person",
        ]
        # বাংলা: ইমেইল RFC 5322 সামঞ্জস্যপূর্ণ সরলীকৃত প্যাটার্ন — plus-addressing সাপোর্ট।
        self.email_pattern = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b")
        # বাংলা: IPv4 — প্রতিটি অক্টেট 0-255 চেক সহ (পুরোনো \d{1,3} প্যাটার্ন ছিল অতিরিক্ত loose)।
        self.ip_pattern = re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
        )
        # বাংলা: ফোন নম্বর — E.164 + সাধারণ ফরম্যাট, ন্যূনতম ৭ ডিজিট।
        self.phone_pattern = re.compile(
            r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)\d{3,4}[-.\s]?\d{3,4}\b"
        )
        # বাংলা: US SSN — XXX-XX-XXXX ফরম্যাট।
        self.ssn_pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        # বাংলা: ক্রেডিট কার্ড — 13-19 ডিজিট, Luhn ভ্যালিডেশন সাপোর্ট।
        self.credit_card_pattern = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
        # বাংলা: IBAN — 2 লেটার country code + 2 চেক ডিজিট + 11-30 অ্যালফানিউমেরিক।
        self.iban_pattern = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")

    def detect_ambiguity(self, prompt: str) -> dict:
        vague_matches = [p for p in self.vague_patterns if re.search(p, prompt, re.I)]
        is_ambiguous = len(vague_matches) > 0
        clarifying_questions = []
        if is_ambiguous:
            clarifying_questions.append(
                "Could you specify exactly what you mean by 'something/anything/etc.'?"
            )
        return {
            "is_ambiguous": is_ambiguous,
            "vague_terms": vague_matches,
            "clarifying_questions": clarifying_questions,
        }

    def validate_scope(self, prompt: str) -> dict:
        for forbidden in self.forbidden_patterns:
            if re.search(forbidden, prompt, re.I):
                return {
                    "is_valid": False,
                    "reason": f"Request involves: {forbidden}",
                    "suggestion": "I cannot help with this request.",
                }
        return {"is_valid": True}

    def extract_constraints(self, prompt: str) -> dict:
        budget_match = re.search(r"under\s+\$?(\d+)", prompt, re.I)
        time_match = re.search(r"in\s+(\d+)\s+(hour|day|week|minute)", prompt, re.I)
        return {
            "budget": float(budget_match.group(1)) if budget_match else None,
            "time": time_match.group(0) if time_match else None,
        }

    @staticmethod
    def _is_luhn_valid(number: str) -> bool:
        """বাংলা: Luhn অ্যালগরিদম দিয়ে ক্রেডিট কার্ড নম্বর ভ্যালিডেশন — false positive কমায়।"""
        digits = [int(d) for d in number if d.isdigit()]
        if len(digits) < 13:
            return False
        checksum = 0
        parity = len(digits) % 2
        for i, d in enumerate(digits):
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        return checksum % 10 == 0

    def strip_pii(self, text: str) -> str:
        # বাংলা: সর্বোচ্চ সংবেদনশীল PII আগে মাস্ক — ক্রেডিট কার্ড, SSN, IBAN, তারপর ইমেইল/IP/ফোন।
        # ক্রেডিট কার্ড — Luhn ভ্যালিডেশন সহ
        def _mask_credit_card(match: re.Match) -> str:
            raw = match.group(0)
            if self._is_luhn_valid(raw):
                return "[CREDIT_CARD]"
            return raw  # বাংলা: Luhn fail মানে এটা ক্রেডিট কার্ড না — ছেড়ে দিই।

        text = self.credit_card_pattern.sub(_mask_credit_card, text)
        text = self.ssn_pattern.sub("[SSN]", text)
        text = self.iban_pattern.sub("[IBAN]", text)
        text = self.email_pattern.sub("[EMAIL]", text)
        text = self.ip_pattern.sub("[IP_ADDRESS]", text)
        text = self.phone_pattern.sub("[PHONE_NUMBER]", text)
        return text

    def sanitize(self, prompt: str) -> dict:
        scope = self.validate_scope(prompt)
        if not scope["is_valid"]:
            return {"is_valid": False, "reason": scope["reason"]}

        # Strip PII
        sanitized_prompt = self.strip_pii(prompt)

        ambiguity = self.detect_ambiguity(sanitized_prompt)
        constraints = self.extract_constraints(sanitized_prompt)
        return {
            "is_valid": True,
            "is_ambiguous": ambiguity["is_ambiguous"],
            "clarifying_questions": ambiguity["clarifying_questions"],
            "constraints": constraints,
            "prompt": sanitized_prompt,
        }
