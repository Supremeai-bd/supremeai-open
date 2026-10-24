#!/usr/bin/env python3
"""
AI Model Drift Detector
Detects performance drift in AI/ML models by comparing current performance against baselines.
Priority: 🔴 High
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import json
import logging
import pickle
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DriftType(Enum):
    """Types of model drift detected."""
    FEATURE_DRIFT = "feature_drift"
    CONCEPT_DRIFT = "concept_drift"
    PREDICTION_DRIFT = "prediction_drift"
    LABEL_DISTRIBUTION_DRIFT = "label_distribution_drift"


@dataclass
class DriftResult:
    """Result of drift detection."""
    drift_type: DriftType
    detected: bool
    confidence: float
    metric_value: float
    threshold: float
    timestamp: datetime
    details: dict[str, Any]


class ModelDriftDetector:
    """
    Detects AI model performance drift using statistical tests.
    """

    def __init__(self, db_path: str = "drift_metrics.db"):
        self.db_path = db_path
        self.baseline_stats: dict[str, Any] = {}
        self.drift_thresholds = {
            'ks_test_pvalue': 0.05,
            'psi_threshold': 0.2,
            'accuracy_drop': 0.1,
            'prediction_std_change': 2.0
        }
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for drift metrics storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drift_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL,
                drift_type TEXT NOT NULL,
                metric_value REAL,
                threshold REAL,
                detected INTEGER,
                timestamp TEXT NOT NULL,
                details TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def compute_ks_test(self, baseline: np.ndarray, current: np.ndarray) -> tuple[float, float]:
        """Compute Kolmogorov-Smirnov test for distribution drift."""
        statistic, pvalue = None, None
        try:
            from scipy import stats
            statistic, pvalue = stats.ks_2samp(baseline, current)
        except ImportError:
            # Fallback implementation without scipy
            n1, n2 = len(baseline), len(current)
            combined = np.concatenate([baseline, current])
            cdf1 = np.searchsorted(np.sort(baseline), combined) / n1
            cdf2 = np.searchsorted(np.sort(current), combined) / n2
            statistic = np.max(np.abs(cdf1 - cdf2))
            pvalue = 0.01 if statistic > 0.05 else 0.5  # Simplified p-value estimation

        return float(statistic), float(pvalue)

    def compute_psi(self, baseline: np.ndarray, current: np.ndarray, buckets: int = 10) -> float:
        """Compute Population Stability Index (PSI) for feature drift."""
        baseline_percents = np.histogram(baseline, bins=buckets, density=True)[0]
        current_percents = np.histogram(current, bins=buckets, density=True)[0]

        # Avoid division by zero
        baseline_percents = np.clip(baseline_percents, 0.0001, None)
        current_percents = np.clip(current_percents, 0.0001, None)

        psi = np.sum((current_percents - baseline_percents) *
                    np.log(current_percents / baseline_percents))
        return float(abs(psi))

    def detect_feature_drift(
        self,
        model_id: str,
        baseline_features: np.ndarray,
        current_features: np.ndarray
    ) -> DriftResult:
        """Detect feature distribution drift using PSI."""
        psi = self.compute_psi(baseline_features.flatten(), current_features.flatten())
        detected = psi > self.drift_thresholds['psi_threshold']

        return DriftResult(
            drift_type=DriftType.FEATURE_DRIFT,
            detected=detected,
            confidence=min(psi / self.drift_thresholds['psi_threshold'], 1.0),
            metric_value=psi,
            threshold=self.drift_thresholds['psi_threshold'],
            timestamp=datetime.now(),
            details={'baseline_shape': baseline_features.shape, 'current_shape': current_features.shape}
        )

    def detect_prediction_drift(
        self,
        model_id: str,
        baseline_predictions: np.ndarray,
        current_predictions: np.ndarray
    ) -> DriftResult:
        """Detect prediction distribution drift."""
        _, pvalue = self.compute_ks_test(baseline_predictions, current_predictions)
        detected = pvalue < self.drift_thresholds['ks_test_pvalue']

        return DriftResult(
            drift_type=DriftType.PREDICTION_DRIFT,
            detected=detected,
            confidence=1 - pvalue,
            metric_value=pvalue,
            threshold=self.drift_thresholds['ks_test_pvalue'],
            timestamp=datetime.now(),
            details={'baseline_mean': float(baseline_predictions.mean()),
                    'current_mean': float(current_predictions.mean())}
        )

    def detect_concept_drift(
        self,
        model_id: str,
        baseline_accuracy: float,
        current_accuracy: float,
        min_samples: int = 100
    ) -> DriftResult:
        """Detect concept drift based on accuracy drop."""
        accuracy_drop = baseline_accuracy - current_accuracy
        detected = accuracy_drop > self.drift_thresholds['accuracy_drop']

        return DriftResult(
            drift_type=DriftType.CONCEPT_DRIFT,
            detected=detected,
            confidence=min(accuracy_drop / self.drift_thresholds['accuracy_drop'], 1.0),
            metric_value=accuracy_drop,
            threshold=self.drift_thresholds['accuracy_drop'],
            timestamp=datetime.now(),
            details={'baseline_accuracy': baseline_accuracy, 'current_accuracy': current_accuracy}
        )

    def save_baseline(self, model_id: str, features: np.ndarray, predictions: np.ndarray):
        """Save baseline statistics for a model."""
        self.baseline_stats[model_id] = {
            'features': features,
            'predictions': predictions,
            'timestamp': datetime.now()
        }
        # Save to disk
        baseline_path = Path(f"baselines/{model_id}_baseline.pkl")
        baseline_path.parent.mkdir(exist_ok=True)
        with open(baseline_path, 'wb') as f:
            pickle.dump(self.baseline_stats[model_id], f)

    def load_baseline(self, model_id: str) -> dict | None:
        """Load baseline statistics for a model."""
        baseline_path = Path(f"baselines/{model_id}_baseline.pkl")
        if baseline_path.exists():
            with open(baseline_path, 'rb') as f:
                return pickle.load(f)
        return None

    def log_drift(self, model_id: str, result: DriftResult):
        """Log drift detection result to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO drift_metrics
            (model_id, drift_type, metric_value, threshold, detected, timestamp, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            model_id,
            result.drift_type.value,
            result.metric_value,
            result.threshold,
            int(result.detected),
            result.timestamp.isoformat(),
            json.dumps(result.details)
        ))
        conn.commit()
        conn.close()

        if result.detected:
            logger.warning(f"⚠️ Drift detected for {model_id}: {result.drift_type.value} "
                          f"(confidence: {result.confidence:.2f})")

    def run_full_drift_check(
        self,
        model_id: str,
        current_features: np.ndarray,
        current_predictions: np.ndarray,
        current_accuracy: float | None = None
    ) -> list[DriftResult]:
        """Run all drift detection checks."""
        results = []
        baseline = self.load_baseline(model_id)

        if baseline:
            results.append(self.detect_feature_drift(
                model_id, baseline['features'], current_features
            ))
            results.append(self.detect_prediction_drift(
                model_id, baseline['predictions'], current_predictions
            ))

            if current_accuracy:
                # Calculate baseline accuracy from stored predictions if available
                baseline_accuracy = baseline.get('accuracy', 0.9)  # Default baseline
                results.append(self.detect_concept_drift(
                    model_id, baseline_accuracy, current_accuracy
                ))

        for result in results:
            self.log_drift(model_id, result)

        return results


def main():
    """Main entry point for drift detection."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect AI model drift")
    parser.add_argument('--model-id', required=True, help='Model identifier')
    parser.add_argument('--check-feature-drift', action='store_true',
                       help='Check feature distribution drift')
    parser.add_argument('--check-prediction-drift', action='store_true',
                       help='Check prediction distribution drift')
    parser.add_argument('--update-baseline', action='store_true',
                       help='Update baseline statistics')
    parser.add_argument('--alert-on-drift', action='store_true',
                       help='Exit with status 1 if any drift is detected')
    parser.add_argument('--export-promql', help='Export PromQL metrics to specified file')

    args = parser.parse_args()

    detector = ModelDriftDetector()

    # Generate sample data for demonstration
    np.random.seed(42)
    current_features = np.random.randn(1000, 10)
    current_predictions = np.random.randn(1000)

    if args.update_baseline:
        detector.save_baseline(args.model_id, current_features, current_predictions)
        logger.info(f"Baseline updated for model: {args.model_id}")

    results = detector.run_full_drift_check(
        args.model_id,
        current_features,
        current_predictions,
        current_accuracy=0.85
    )

    print(f"\nDrift Detection Results for {args.model_id}:")
    drift_detected = False
    prom_metrics = []
    for result in results:
        status = "DETECTED" if result.detected else "OK"
        if result.detected:
            drift_detected = True
        print(f"  {result.drift_type.value}: {status} "
              f"(confidence: {result.confidence:.2f})")
        prom_metrics.append(
            f'model_drift_status{{model_id="{args.model_id}",drift_type="{result.drift_type.value}"}} {1 if result.detected else 0}\n'
            f'model_drift_confidence{{model_id="{args.model_id}",drift_type="{result.drift_type.value}"}} {result.confidence:.4f}'
        )

    if args.export_promql:
        prom_file = Path(args.export_promql)
        prom_file.parent.mkdir(parents=True, exist_ok=True)
        prom_file.write_text("\n".join(prom_metrics) + "\n", encoding="utf-8")
        print(f"PromQL metrics exported to {args.export_promql}")

    if drift_detected and args.alert_on_drift:
        import sys
        logger.error(f"🚨 [DRIFT_ALERT]: Model drift detected for {args.model_id}!")
        sys.exit(1)


if __name__ == "__main__":
    main()
