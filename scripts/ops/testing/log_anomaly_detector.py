#!/usr/bin/env python3
"""
SupremeAI 2.0 — Log Anomaly Detector 🔍
========================================
Purpose: ML-based log anomaly detection using Isolation Forest, LSTM patterns,
         and statistical Z-score analysis. Supports real-time log streaming,
         batch processing, and auto-training on historical patterns.
Priority: 🟡 MEDIUM
Author: SupremeAI Architecture Team
Date: July 20, 2026

বাংলা: এমএল-বেজড লগ এনোমালি ডিটেকশন — আইসোলেশন ফরেস্ট, LSTM প্যাটার্ন,
স্ট্যাটিস্টিক্যাল Z-স্কোর অ্যানালাইসিস সহ। রিয়েল-টাইম লগ স্ট্রিমিং,
ব্যাচ প্রসেসিং, এবং অটো-ট্রেইনিং সাপোর্ট।
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

# ── Path Setup ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from backend.core.config import settings
except ImportError:
    settings = None  # type: ignore[assignment]

# ── Configuration ───────────────────────────────────────────
MODEL_DIR = Path(__file__).parent / ".anomaly_models"
LOG_PATTERNS_FILE = MODEL_DIR / "log_patterns.json"
ANOMALY_HISTORY_FILE = MODEL_DIR / "anomaly_history.json"
TRAINING_DATA_FILE = MODEL_DIR / "training_data.jsonl"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_SIZE = int(os.getenv("ANOMALY_WINDOW_SIZE", "100"))
Z_THRESHOLD = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.5"))
ISOLATION_CONTAMINATION = float(os.getenv("ISOLATION_CONTAMINATION", "0.05"))
LSTM_SEQUENCE_LENGTH = int(os.getenv("LSTM_SEQUENCE_LENGTH", "10"))
RETRAIN_INTERVAL_HOURS = int(os.getenv("ANOMALY_RETRAIN_INTERVAL_HOURS", "24"))

# Optional ML libraries
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("⚠️ scikit-learn not available. Isolation Forest disabled.")

try:
    import torch
    from torch import nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("⚠️ PyTorch not available. LSTM detector disabled.")


# ── Data Models ─────────────────────────────────────────────
@dataclass
class LogEntry:
    """একটি লগ এন্ট্রির স্ট্রাকচার।"""
    timestamp: str
    level: str
    source: str
    message: str
    raw_line: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyReport:
    """এনোমালি রিপোর্ট।"""
    id: str
    timestamp: str
    log_entry: LogEntry
    anomaly_score: float
    anomaly_type: str  # 'statistical', 'isolation_forest', 'lstm', 'pattern'
    severity: str  # 'critical', 'warning', 'info'
    explanation: str
    explanation_bn: str
    suggested_action: str
    model_confidence: float


@dataclass
class PatternTemplate:
    """Regex pattern template for known log types."""
    name: str
    regex: str
    severity: str
    description: str
    description_bn: str


# ── Pattern Database ────────────────────────────────────────
DEFAULT_PATTERNS = [
    PatternTemplate(
        "database_connection_fail",
        r"(?i)(connection.*(?:refused|timeout|failed)|cannot connect.*database|too many connections)",
        "critical",
        "Database connection failure detected",
        "ডাটাবেস কানেকশন ব্যর্থতা সনাক্ত",
    ),
    PatternTemplate(
        "memory_oom",
        r"(?i)(out of memory|oom|memory exhausted|cannot allocate memory)",
        "critical",
        "Out of memory error",
        "মেমোরি শেষ হয়ে গেছে",
    ),
    PatternTemplate(
        "disk_full",
        r"(?i)(no space left on device|disk full|write error.*disk)",
        "critical",
        "Disk space exhausted",
        "ডিস্ক স্পেস শেষ",
    ),
    PatternTemplate(
        "auth_failure",
        r"(?i)(authentication failed|unauthorized|invalid (token|credentials)|jwt.*expired)",
        "warning",
        "Authentication failure",
        "অথেনটিকেশন ব্যর্থতা",
    ),
    PatternTemplate(
        "rate_limit_hit",
        r"(?i)(rate limit exceeded|too many requests|429)",
        "warning",
        "Rate limit exceeded",
        "রেট লিমিট অতিক্রম",
    ),
    PatternTemplate(
        "slow_query",
        r"(?i)(slow query|query took \d+ms|execution time.*exceeded)",
        "warning",
        "Slow database query detected",
        "ধীর ডাটাবেস কুয়েরি সনাক্ত",
    ),
    PatternTemplate(
        "exception_traceback",
        r"(?i)(traceback|exception|error.*at line|raise .*Error)",
        "warning",
        "Exception/Error traceback",
        "এক্সেপশন/এরর ট্রেসব্যাক",
    ),
    PatternTemplate(
        "service_restart",
        r"(?i)(service restarted|server shutdown|graceful shutdown|sigterm received)",
        "info",
        "Service restart/shutdown",
        "সার্ভিস রিস্টার্ট/শাটডাউন",
    ),
]


# ── Feature Extractor ───────────────────────────────────────
class LogFeatureExtractor:
    """Extracts numerical features from log messages for ML models."""

    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None
        self.scaler: StandardScaler | None = None
        self._fitted = False

    def _extract_handcrafted(self, entry: LogEntry) -> np.ndarray:
        """Extract handcrafted statistical features."""
        msg = entry.message.lower()
        features = [
            len(entry.message),  # Message length
            len(entry.message.split()),  # Word count
            entry.message.count(" "),  # Space count
            sum(c.isdigit() for c in entry.message),  # Digit count
            sum(c.isupper() for c in entry.message),  # Uppercase count
            msg.count("error"),  # Error keyword count
            msg.count("fail"),  # Fail keyword count
            msg.count("timeout"),  # Timeout keyword count
            msg.count("exception"),  # Exception keyword count
            msg.count(" "),  # Whitespace density
            ord(entry.message[0]) if entry.message else 0,  # First char ASCII
            hash(entry.source) % 1000,  # Source hash
            {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}.get(entry.level.upper(), 1),
        ]
        return np.array(features, dtype=np.float32)

    def fit(self, entries: list[LogEntry]) -> None:
        if not SKLEARN_AVAILABLE:
            return
        messages = [e.message for e in entries]
        self.vectorizer = TfidfVectorizer(max_features=50, ngram_range=(1, 2))
        tfidf = self.vectorizer.fit_transform(messages).toarray()

        handcrafted = np.array([self._extract_handcrafted(e) for e in entries])
        combined = np.hstack([handcrafted, tfidf])

        self.scaler = StandardScaler()
        self.scaler.fit(combined)
        self._fitted = True

    def transform(self, entry: LogEntry) -> np.ndarray:
        if not self._fitted or not SKLEARN_AVAILABLE:
            return self._extract_handcrafted(entry).reshape(1, -1)

        handcrafted = self._extract_handcrafted(entry).reshape(1, -1)
        tfidf = self.vectorizer.transform([entry.message]).toarray()
        combined = np.hstack([handcrafted, tfidf])
        return self.scaler.transform(combined)


# ── LSTM Anomaly Detector ───────────────────────────────────
class LSTMDetector(nn.Module if TORCH_AVAILABLE else object):
    """LSTM-based sequence anomaly detector for temporal log patterns."""

    def __init__(self, input_size: int = 63, hidden_size: int = 64, num_layers: int = 2):
        if not TORCH_AVAILABLE:
            return
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, input_size)
        self.criterion = nn.MSELoss()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out)


class LSTMAnomalyEngine:
    """Manages LSTM training and inference for log sequences."""

    def __init__(self, sequence_length: int = LSTM_SEQUENCE_LENGTH):
        self.sequence_length = sequence_length
        self.model: LSTMDetector | None = None
        self.device = torch.device("cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu") if TORCH_AVAILABLE else None
        self._buffer: deque[np.ndarray] = deque(maxlen=sequence_length)
        self._trained = False

    def _init_model(self, feature_size: int) -> None:
        if not TORCH_AVAILABLE:
            return
        self.model = LSTMDetector(input_size=feature_size).to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)

    def train(self, sequences: list[np.ndarray], epochs: int = 10) -> None:
        if not TORCH_AVAILABLE or not sequences:
            return

        if self.model is None:
            self._init_model(sequences[0].shape[-1])

        dataset = torch.FloatTensor(np.array(sequences)).to(self.device)
        self.model.train()

        for epoch in range(epochs):
            total_loss = 0
            for i in range(len(dataset)):
                seq = dataset[i:i+1]
                self.optimizer.zero_grad()
                output = self.model(seq)
                loss = self.model.criterion(output, seq)
                loss.backward()
                self.optimizer.step()
                total_loss += loss.item()
            logger.info(f"🧠 LSTM Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(dataset):.4f}")

        self._trained = True

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        """Returns (reconstruction_error, anomaly_score)."""
        if not TORCH_AVAILABLE or not self._trained or self.model is None:
            return 0.0, 0.0

        self._buffer.append(features.flatten())
        if len(self._buffer) < self.sequence_length:
            return 0.0, 0.0

        seq = torch.FloatTensor(np.array(self._buffer)).unsqueeze(0).to(self.device)
        self.model.eval()
        with torch.no_grad():
            reconstructed = self.model(seq)
            error = torch.mean((seq - reconstructed) ** 2).item()

        # Normalize to 0-1 score
        score = min(error * 10, 1.0)
        return error, score


# ── Main Anomaly Detector ───────────────────────────────────
class LogAnomalyDetector:
    """Unified log anomaly detector combining multiple detection methods."""

    def __init__(self):
        self.patterns = DEFAULT_PATTERNS
        self.extractor = LogFeatureExtractor()
        self.isolation_forest: IsolationForest | None = None
        self.lstm_engine = LSTMAnomalyEngine()
        self._window: deque[LogEntry] = deque(maxlen=WINDOW_SIZE)
        self._feature_window: deque[np.ndarray] = deque(maxlen=WINDOW_SIZE)
        self._pattern_counts: Counter = Counter()
        self._last_retrain = 0.0
        self._reports: deque[AnomalyReport] = deque(maxlen=1000)
        self._load_state()

    def _load_state(self) -> None:
        if LOG_PATTERNS_FILE.exists():
            try:
                data = json.loads(LOG_PATTERNS_FILE.read_text(encoding="utf-8"))
                self.patterns = [PatternTemplate(**p) for p in data.get("patterns", [])]
                logger.info(f"📚 Loaded {len(self.patterns)} custom patterns")
            except Exception as e:
                logger.warning(f"⚠️ Pattern load failed: {e}")

    def _save_state(self) -> None:
        try:
            data = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "patterns": [asdict(p) for p in self.patterns],
            }
            LOG_PATTERNS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Pattern save failed: {e}")

    def _pattern_match(self, entry: LogEntry) -> PatternTemplate | None:
        """Check if log matches any known anomaly pattern."""
        for pattern in self.patterns:
            if re.search(pattern.regex, entry.message):
                return pattern
        return None

    def _statistical_anomaly(self, entry: LogEntry, features: np.ndarray) -> tuple[bool, float]:
        """Z-score based statistical anomaly detection."""
        if len(self._feature_window) < 10:
            return False, 0.0

        window_array = np.array(list(self._feature_window))
        means = np.mean(window_array, axis=0)
        stds = np.std(window_array, axis=0)
        stds = np.where(stds == 0, 1e-8, stds)

        z_scores = np.abs((features.flatten() - means) / stds)
        max_z = np.max(z_scores)

        return max_z > Z_THRESHOLD, max_z

    def _isolation_anomaly(self, features: np.ndarray) -> tuple[bool, float]:
        """Isolation Forest based anomaly detection."""
        if not SKLEARN_AVAILABLE or self.isolation_forest is None:
            return False, 0.0

        prediction = self.isolation_forest.predict(features.reshape(1, -1))
        score = -self.isolation_forest.score_samples(features.reshape(1, -1))[0]
        return prediction[0] == -1, score

    def _auto_retrain(self) -> None:
        """Auto-retrain models on accumulated window data."""
        now = time.time()
        if now - self._last_retrain < RETRAIN_INTERVAL_HOURS * 3600:
            return
        if len(self._feature_window) < 50:
            return

        logger.info("🔄 Auto-retraining anomaly models...")

        # Fit feature extractor
        self.extractor.fit(list(self._window))

        # Train Isolation Forest
        if SKLEARN_AVAILABLE:
            X = np.array([self.extractor.transform(e).flatten() for e in self._window])
            self.isolation_forest = IsolationForest(
                contamination=ISOLATION_CONTAMINATION,
                random_state=42,
                n_estimators=100,
            )
            self.isolation_forest.fit(X)
            logger.info("✅ Isolation Forest retrained")

        # Train LSTM
        if TORCH_AVAILABLE and len(self._feature_window) > LSTM_SEQUENCE_LENGTH:
            sequences = []
            arr = np.array([f.flatten() for f in self._feature_window])
            for i in range(len(arr) - LSTM_SEQUENCE_LENGTH):
                sequences.append(arr[i:i + LSTM_SEQUENCE_LENGTH])
            self.lstm_engine.train(sequences)
            logger.info("✅ LSTM retrained")

        self._last_retrain = now

    def analyze(self, entry: LogEntry) -> AnomalyReport | None:
        """Analyze a single log entry for anomalies."""
        self._window.append(entry)

        # Extract features
        features = self.extractor._extract_handcrafted(entry)
        self._feature_window.append(features)

        # Auto-retrain check
        self._auto_retrain()

        # Method 1: Pattern matching (fastest, highest confidence)
        pattern = self._pattern_match(entry)
        if pattern:
            report = AnomalyReport(
                id=hashlib.sha256(f"{entry.timestamp}:{entry.message[:50]}".encode()).hexdigest()[:16],
                timestamp=datetime.now(timezone.utc).isoformat(),
                log_entry=entry,
                anomaly_score=1.0,
                anomaly_type="pattern",
                severity=pattern.severity,
                explanation=f"Matched known pattern: {pattern.name} — {pattern.description}",
                explanation_bn=pattern.description_bn,
                suggested_action=f"Investigate {pattern.name} immediately. Check related services.",
                model_confidence=0.95,
            )
            self._reports.append(report)
            return report

        # Method 2: Statistical Z-score
        is_stat_anomaly, z_score = self._statistical_anomaly(entry, features)
        if is_stat_anomaly:
            report = AnomalyReport(
                id=hashlib.sha256(f"{entry.timestamp}:{entry.message[:50]}".encode()).hexdigest()[:16],
                timestamp=datetime.now(timezone.utc).isoformat(),
                log_entry=entry,
                anomaly_score=min(z_score / 5.0, 1.0),
                anomaly_type="statistical",
                severity="warning" if z_score < Z_THRESHOLD * 1.5 else "critical",
                explanation=f"Statistical anomaly: Z-score={z_score:.2f} exceeds threshold {Z_THRESHOLD}",
                explanation_bn=f"স্ট্যাটিস্টিক্যাল এনোমালি: Z-স্কোর={z_score:.2f} থ্রেশহোল্ড {Z_THRESHOLD} অতিক্রম করেছে",
                suggested_action="Review recent system changes. Check for unusual load patterns.",
                model_confidence=min(z_score / 5.0, 0.9),
            )
            self._reports.append(report)
            return report

        # Method 3: Isolation Forest
        if self.isolation_forest is not None:
            is_iso_anomaly, iso_score = self._isolation_anomaly(features.reshape(1, -1))
            if is_iso_anomaly:
                report = AnomalyReport(
                    id=hashlib.sha256(f"{entry.timestamp}:{entry.message[:50]}".encode()).hexdigest()[:16],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    log_entry=entry,
                    anomaly_score=min(iso_score, 1.0),
                    anomaly_type="isolation_forest",
                    severity="warning",
                    explanation=f"Isolation Forest anomaly detected with score {iso_score:.3f}",
                    explanation_bn=f"আইসোলেশন ফরেস্ট এনোমালি সনাক্ত, স্কোর {iso_score:.3f}",
                    suggested_action="Cluster analysis recommended. Check for outlier behavior.",
                    model_confidence=min(iso_score, 0.85),
                )
                self._reports.append(report)
                return report

        # Method 4: LSTM temporal anomaly
        lstm_error, lstm_score = self.lstm_engine.predict(features)
        if lstm_score > 0.7:
            report = AnomalyReport(
                id=hashlib.sha256(f"{entry.timestamp}:{entry.message[:50]}".encode()).hexdigest()[:16],
                timestamp=datetime.now(timezone.utc).isoformat(),
                log_entry=entry,
                anomaly_score=lstm_score,
                anomaly_type="lstm",
                severity="warning" if lstm_score < 0.9 else "critical",
                explanation=f"LSTM temporal anomaly: reconstruction error={lstm_error:.4f}",
                explanation_bn=f"LSTM টেম্পোরাল এনোমালি: রিকনস্ট্রাকশন এরর={lstm_error:.4f}",
                suggested_action="Check for sequential pattern disruption. Review recent events.",
                model_confidence=lstm_score,
            )
            self._reports.append(report)
            return report

        return None

    def analyze_batch(self, entries: list[LogEntry]) -> list[AnomalyReport]:
        """Analyze multiple log entries."""
        reports = []
        for entry in entries:
            report = self.analyze(entry)
            if report:
                reports.append(report)
        return reports

    def get_recent_anomalies(self, n: int = 50, severity: str | None = None) -> list[AnomalyReport]:
        """Get recent anomaly reports."""
        reports = list(self._reports)[-n:]
        if severity:
            reports = [r for r in reports if r.severity == severity]
        return reports

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_analyzed": len(self._window),
            "total_anomalies": len(self._reports),
            "by_type": Counter(r.anomaly_type for r in self._reports),
            "by_severity": Counter(r.severity for r in self._reports),
            "patterns_loaded": len(self.patterns),
            "models_ready": {
                "isolation_forest": self.isolation_forest is not None,
                "lstm": self.lstm_engine._trained,
            },
        }

    def add_custom_pattern(self, name: str, regex: str, severity: str, description: str, description_bn: str) -> None:
        self.patterns.append(PatternTemplate(name, regex, severity, description, description_bn))
        self._save_state()
        logger.info(f"➕ Custom pattern added: {name}")


# ── Log Stream Handler ────────────────────────────────────────
class LogStreamHandler:
    """Handles real-time log streaming from files or APIs."""

    def __init__(self, detector: LogAnomalyDetector):
        self.detector = detector
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def tail_file(self, filepath: Path, callback: Callable[[AnomalyReport], Any] | None = None) -> None:
        """Async tail -f equivalent for log files."""
        if not filepath.exists():
            logger.error(f"❌ Log file not found: {filepath}")
            return

        logger.info(f"📁 Tailing log file: {filepath}")
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            # Seek to end
            f.seek(0, 2)
            while self._running:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue

                entry = self._parse_line(line.strip())
                if entry:
                    report = self.detector.analyze(entry)
                    if report and callback:
                        await callback(report)

    def _parse_line(self, line: str) -> LogEntry | None:
        """Parse a log line into structured entry."""
        match = re.match(
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*)\s+\[?(\w+)\]?\s+(.*)",
            line,
        )
        if match:
            ts, level, rest = match.groups()
            source_match = re.match(r"(\S+):\s+(.*)", rest)
            if source_match:
                source, message = source_match.groups()
            else:
                source, message = "unknown", rest

            return LogEntry(
                timestamp=ts,
                level=level,
                source=source,
                message=message[:500],
                raw_line=line[:1000],
            )

        return LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level="UNKNOWN",
            source="unknown",
            message=line[:500],
            raw_line=line[:1000],
        )

    async def tail_journal(self, service: str = "supremeai", callback: Callable | None = None) -> None:
        """Tail systemd journal for a service."""
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", f"{service}.service", "-f", "-n", "0", "-o", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        while self._running:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line.decode())
                entry = LogEntry(
                    timestamp=data.get("__REALTIME_TIMESTAMP", datetime.now(timezone.utc).isoformat()),
                    level=data.get("PRIORITY", "INFO"),
                    source=data.get("SYSLOG_IDENTIFIER", service),
                    message=data.get("MESSAGE", ""),
                    raw_line=line.decode()[:1000],
                )
                report = self.detector.analyze(entry)
                if report and callback:
                    await callback(report)
            except json.JSONDecodeError:
                continue

    def start(self, sources: list[Path | str], callback: Callable | None = None) -> None:
        self._running = True
        for source in sources:
            if isinstance(source, Path):
                task = asyncio.create_task(self.tail_file(source, callback))
            else:
                task = asyncio.create_task(self.tail_journal(source, callback))
            self._tasks.append(task)

    def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        logger.info("🛑 Log stream handler stopped")


# ── Entry Point ─────────────────────────────────────────────
async def demo():
    """Run anomaly detection demo."""
    detector = LogAnomalyDetector()

    test_logs = [
        "2024-01-15 10:30:45,123 [INFO] uvicorn: Application startup complete",
        "2024-01-15 10:31:02,456 [ERROR] database: Connection refused to postgres://localhost:5432/supremeai",
        "2024-01-15 10:31:15,789 [WARNING] api: Rate limit exceeded for client 192.168.1.100",
        "2024-01-15 10:32:01,234 [CRITICAL] memory: Out of memory error: cannot allocate 2048 bytes",
        "2024-01-15 10:32:45,567 [ERROR] auth: Authentication failed for user 'admin' — invalid JWT token",
        "2024-01-15 10:33:12,890 [INFO] cache: Cache flush completed successfully",
    ]

    print("=" * 60)
    print("🔍 SupremeAI Log Anomaly Detector — Demo")
    print("=" * 60)

    for raw in test_logs:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level="INFO",
            source="demo",
            message=raw,
            raw_line=raw,
        )
        report = detector.analyze(entry)
        if report:
            print("\n🚨 ANOMALY DETECTED!")
            print(f"   Type: {report.anomaly_type}")
            print(f"   Severity: {report.severity}")
            print(f"   Score: {report.anomaly_score:.3f}")
            print(f"   EN: {report.explanation}")
            print(f"   BN: {report.explanation_bn}")
            print(f"   Action: {report.suggested_action}")
        else:
            print(f"✅ Normal: {raw[:60]}...")

    print(f"\n📊 Stats: {detector.get_stats()}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SupremeAI Log Anomaly Detector")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--tail", type=Path, help="Tail a log file")
    parser.add_argument("--service", default="supremeai", help="Systemd service to tail")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    args = parser.parse_args()

    if args.demo:
        asyncio.run(demo())
    elif args.tail:
        detector = LogAnomalyDetector()
        handler = LogStreamHandler(detector)

        async def print_report(report: AnomalyReport) -> None:
            print(f"\n🚨 [{report.severity.upper()}] {report.anomaly_type}")
            print(f"   {report.explanation}")
            print(f"   BN: {report.explanation_bn}")

        handler.start([args.tail], print_report)
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            handler.stop()
    elif args.stats:
        detector = LogAnomalyDetector()
        print(json.dumps(detector.get_stats(), indent=2))
    else:
        print("Usage:")
        print("  python log_anomaly_detector.py --demo")
        print("  python log_anomaly_detector.py --tail /var/log/supremeai.log")
        print("  python log_anomaly_detector.py --stats")


if __name__ == "__main__":
    main()
