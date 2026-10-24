#!/usr/bin/env python3
"""
AI Bias Detector
Detects and mitigates bias in AI models through fairness analysis.
Priority: 🟡 Medium
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BiasType(Enum):
    """Types of bias detected."""
    GENDER = "gender_bias"
    RACIAL = "racial_bias"
    AGE = "age_bias"
    RELIGIOUS = "religious_bias"
    SOCIOECONOMIC = "socioeconomic_bias"
    DISABILITY = "disability_bias"


@dataclass
class BiasMetric:
    """Bias metric for a protected attribute."""
    attribute: str
    bias_type: BiasType
    ratio: float
    disparate_impact: float
    statistical_parity: float
    confidence: float
    sample_size: int


@dataclass
class BiasDetectionResult:
    """Result of bias detection analysis."""
    model_id: str
    timestamp: datetime
    bias_metrics: list[BiasMetric]
    overall_fairness_score: float
    recommendations: list[str]
    data_drift_detected: bool


class BiasDetector:
    """
    Detects and analyzes bias in AI model predictions and training data.
    """

    # Protected attribute terms for analysis
    PROTECTED_TERMS = {
        BiasType.GENDER: ['he', 'she', 'him', 'her', 'male', 'female', 'man', 'woman',
                         'boy', 'girl', 'mr.', 'mrs.', 'ms.', 'mister', 'miss'],
        BiasType.RACIAL: ['black', 'white', 'asian', 'hispanic', 'latino', 'african',
                         'caucasian', 'minority', 'majority', 'ethnic'],
        BiasType.AGE: ['young', 'old', 'elderly', 'teen', 'senior', 'child', 'adult'],
        BiasType.RELIGIOUS: ['christian', 'muslim', 'jewish', 'hindu', 'buddhist',
                            'religion', 'faith', 'worship', 'pray'],
        BiasType.SOCIOECONOMIC: ['rich', 'poor', 'wealthy', 'expensive', 'cheap',
                                'luxury', 'budget', 'premium'],
    }

    # Fairness thresholds
    FAIRNESS_THRESHOLDS = {
        'disparate_impact': 0.8,  # Below this indicates bias
        'statistical_parity': 0.1,  # Difference threshold
        'demographic_parity': 0.1,
    }

    def __init__(self, output_path: str = "bias_reports"):
        self.output_path = Path(output_path)
        self.output_path.mkdir(exist_ok=True)

    def compute_disparate_impact(
        self,
        predictions: np.ndarray,
        protected_attribute_mask: np.ndarray
    ) -> float:
        """
        Compute disparate impact ratio.
        Ratio of positive prediction rate for protected group vs reference group.
        """
        protected_positive_rate = np.mean(predictions[protected_attribute_mask == 1])
        reference_positive_rate = np.mean(predictions[protected_attribute_mask == 0])

        if reference_positive_rate == 0:
            return 1.0 if protected_positive_rate == 0 else float('inf')

        return float(protected_positive_rate / reference_positive_rate)

    def compute_statistical_parity_difference(
        self,
        predictions: np.ndarray,
        protected_attribute_mask: np.ndarray
    ) -> float:
        """Compute statistical parity difference."""
        return float(abs(np.mean(predictions[protected_attribute_mask == 1]) -
                       np.mean(predictions[protected_attribute_mask == 0])))

    def analyze_text_bias(self, text_samples: list[str]) -> dict[BiasType, int]:
        """Analyze text samples for bias indicators."""
        bias_counts = {}
        text_lower = [t.lower() for t in text_samples]

        for bias_type, terms in self.PROTECTED_TERMS.items():
            count = sum(
                sum(1 for term in terms if term in text)
                for text in text_lower
            )
            bias_counts[bias_type] = count

        return bias_counts

    def compute_bias_metrics(
        self,
        predictions: np.ndarray,
        labels: np.ndarray,
        protected_attributes: dict[str, np.ndarray],
        prediction_threshold: float = 0.5
    ) -> list[BiasMetric]:
        """Compute bias metrics for all protected attributes."""
        metrics = []
        binary_predictions = (predictions >= prediction_threshold).astype(int)

        for attr_name, attr_mask in protected_attributes.items():
            sample_size = len(predictions)

            disparate_impact = self.compute_disparate_impact(binary_predictions, attr_mask)
            stat_parity = self.compute_statistical_parity_difference(binary_predictions, attr_mask)

            bias_type = next(
                (bt for bt in BiasType if bt.value.replace('_bias', '') in attr_name.lower()),
                BiasType.SOCIOECONOMIC
            )

            # Confidence based on sample size
            confidence = min(sample_size / 1000, 1.0)

            metrics.append(BiasMetric(
                attribute=attr_name,
                bias_type=bias_type,
                ratio=disparate_impact,
                disparate_impact=disparate_impact,
                statistical_parity=stat_parity,
                confidence=confidence,
                sample_size=sample_size
            ))

        return metrics

    def detect_bias(
        self,
        model_id: str,
        predictions: np.ndarray,
        labels: np.ndarray | None = None,
        protected_attributes: dict[str, np.ndarray] | None = None,
        text_samples: list[str] | None = None
    ) -> BiasDetectionResult:
        """Run comprehensive bias detection."""
        bias_metrics = []
        recommendations = []

        # Compute metrics for protected attributes
        if protected_attributes:
            bias_metrics = self.compute_bias_metrics(predictions, labels or np.array([]), protected_attributes)

        # Analyze text bias
        if text_samples:
            text_bias = self.analyze_text_bias(text_samples)
            for bias_type, count in text_bias.items():
                if count > 0:
                    recommendations.append(
                        f"Review {bias_type.value} indicators in training/inference data"
                    )

        # Generate recommendations from metrics
        for metric in bias_metrics:
            if metric.disparate_impact < self.FAIRNESS_THRESHOLDS['disparate_impact']:
                recommendations.append(
                    f"High {metric.bias_type.value} detected. Consider reweighing or adversarial debiasing."
                )
            if metric.statistical_parity > self.FAIRNESS_THRESHOLDS['statistical_parity']:
                recommendations.append(
                    f"Statistical parity violation for {metric.attribute}. Apply fairness constraints."
                )

        # Overall fairness score (higher is better)
        if bias_metrics:
            fairness_scores = []
            for m in bias_metrics:
                score = min(m.disparate_impact / self.FAIRNESS_THRESHOLDS['disparate_impact'], 1.0)
                fairness_scores.append(score)
            overall_score = float(np.mean(fairness_scores))
        else:
            overall_score = 1.0

        # Check for data drift
        data_drift = self._check_data_drift(predictions)

        return BiasDetectionResult(
            model_id=model_id,
            timestamp=datetime.now(),
            bias_metrics=bias_metrics,
            overall_fairness_score=overall_score,
            recommendations=recommendations,
            data_drift_detected=data_drift
        )

    def _check_data_drift(self, predictions: np.ndarray) -> bool:
        """Check for significant data distribution shifts."""
        # Simple variance-based drift detection
        variance = np.var(predictions)
        return variance < 0.01 or variance > 0.9  # Suspicious variance ranges

    def generate_report(self, result: BiasDetectionResult) -> str:
        """Generate bias detection report."""
        report_path = self.output_path / f"bias_report_{result.model_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report = {
            'model_id': result.model_id,
            'timestamp': result.timestamp.isoformat(),
            'overall_fairness_score': result.overall_fairness_score,
            'data_drift_detected': bool(result.data_drift_detected),
            'bias_metrics': [
                {
                    'attribute': m.attribute,
                    'bias_type': m.bias_type.value,
                    'ratio': m.ratio,
                    'disparate_impact': m.disparate_impact,
                    'statistical_parity': m.statistical_parity,
                    'confidence': m.confidence,
                    'sample_size': m.sample_size
                }
                for m in result.bias_metrics
            ],
            'recommendations': result.recommendations
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Bias report saved to: {report_path}")
        return str(report_path)

    def get_fairness_summary(self, result: BiasDetectionResult) -> dict[str, Any]:
        """Get summary of fairness analysis."""
        return {
            'model_id': result.model_id,
            'fairness_score': round(result.overall_fairness_score, 3),
            'bias_detected': any(m.disparate_impact < self.FAIRNESS_THRESHOLDS['disparate_impact']
                                for m in result.bias_metrics),
            'attributes_analyzed': len(result.bias_metrics),
            'recommendations_count': len(result.recommendations)
        }


def main():
    """Main entry point for bias detection."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect bias in AI models")
    parser.add_argument('--model-id', required=True, help='Model identifier to analyze')
    parser.add_argument('--predictions-file', help='Path to predictions JSON file')
    parser.add_argument('--output-dir', default='bias_reports', help='Output directory for reports')
    parser.add_argument('--report-json', help='Path to output JSON report file')

    args = parser.parse_args()

    detector = BiasDetector(output_path=args.output_dir)

    # Generate sample predictions for demonstration
    np.random.seed(42)
    predictions = np.random.rand(1000)
    protected_attributes = {
        'gender_male': np.random.randint(0, 2, 1000),
        'age_minority': np.random.randint(0, 2, 1000),
    }

    result = detector.detect_bias(
        model_id=args.model_id,
        predictions=predictions,
        protected_attributes=protected_attributes,
        text_samples=["Sample text with male and female references", "Another sample"]
    )

    detector.generate_report(result)

    if args.report_json:
        json_data = {
            "model_id": result.model_id,
            "timestamp": result.timestamp.isoformat(),
            "overall_fairness_score": result.overall_fairness_score,
            "data_drift_detected": bool(result.data_drift_detected),
            "summary": detector.get_fairness_summary(result),
            "recommendations": result.recommendations,
        }
        json_path = Path(args.report_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        print(f"Exported JSON report to {args.report_json}")

    print(f"\nBias Detection Summary for {args.model_id}:")
    summary = detector.get_fairness_summary(result)
    for key, value in summary.items():
        print(f"  {key}: {value}")

    if result.recommendations:
        print("\nRecommendations:")
        for rec in result.recommendations[:5]:
            print(f"  • {rec}")


if __name__ == "__main__":
    main()
