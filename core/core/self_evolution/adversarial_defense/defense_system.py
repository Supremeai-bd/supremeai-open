from __future__ import annotations

"""
SupremeAI Adversarial Defense System
====================================

Implements multiple layers of defense against adversarial attacks:
- Input sanitization and anomaly detection
- Adversarial example detection
- Robust training techniques
- Runtime monitoring and response

Based on state-of-the-art adversarial defense research.

Bengali:
অ্যাডভারসেরিয়াল ডিফেন্স সিস্টেম
অ্যাডভারসেরিয়াল এটাক থেকে রক্ষার জন্য একাধিক স্তরের প্রতিরোধ ব্যবস্থা
"""

# ══════════════════════════════════════════════════════════════════════════════
# ✅ PRODUCTION FIX: Guarded ML imports — graceful degradation if torch unavailable
# ══════════════════════════════════════════════════════════════════════════════
import logging
import time

# বাংলা মন্তব্য: cv2 টপ-লেভেলে import করলে CI-তে `No module named 'cv2'` এরর
# core/__init__.py → evolution → এই ফাইলের মাধ্যমে পুরো টেস্ট স্যুটকে ক্র্যাশ করায়।
# তাই এটি lazily শুধুমাত্র apply_robust_preprocessing()-এ import করা হচ্ছে।
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Optional PyTorch dependency — evolution features degrade gracefully
try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    nn = None  # type: ignore
    logger.debug("torch not installed; evolution ML features disabled")

# Additional torch submodules (file-specific)
try:
    import torch.optim as optim
    from torch.utils.data import DataLoader

    TORCH_UTILS_AVAILABLE = True
except ImportError:
    optim = None  # type: ignore
    DataLoader = None  # type: ignore
    TORCH_UTILS_AVAILABLE = False

from core.logging_config import logger

warnings.filterwarnings("ignore")


class AttackType(Enum):
    FGSM = "fgsm"  # Fast Gradient Sign Method
    PGD = "pgd"  # Projected Gradient Descent
    CW = "carlini_wagner"  # Carlini & Wagner attack
    JSMA = "jsma"  # Jacobian-based Saliency Map Attack
    BIM = "bim"  # Basic Iterative Method
    MIM = "mim"  # Momentum Iterative Method
    TEXT_POISONING = "text_poisoning"
    PROMPT_INJECTION = "prompt_injection"


@dataclass
class DefenseConfig:
    """Configuration for adversarial defense system."""

    # Perturbation detection thresholds
    l2_norm_threshold: float = 0.1
    linf_norm_threshold: float = 0.03
    correlation_threshold: float = 0.95

    # Detection sensitivity
    detection_sensitivity: float = 0.8
    confidence_threshold: float = 0.7

    # Robust training parameters
    adversarial_training_eps: float = 0.03
    adversarial_training_alpha: float = 0.01
    adversarial_training_iterations: int = 10

    # Runtime monitoring
    monitoring_interval: float = 1.0  # seconds
    anomaly_batch_size: int = 32
    defense_logging: bool = True


class InputSanitizer:
    """
    Sanitizes inputs to remove obvious adversarial perturbations.
    """

    @staticmethod
    def normalize_input(x: torch.Tensor, mean: float = 0.0, std: float = 1.0) -> torch.Tensor:
        """Normalize input tensor."""
        return (x - mean) / std

    @staticmethod
    def clip_input(x: torch.Tensor, min_val: float = 0.0, max_val: float = 1.0) -> torch.Tensor:
        """Clip input tensor to valid range."""
        return torch.clamp(x, min_val, max_val)

    @staticmethod
    def gaussian_smoothing(
        x: torch.Tensor, kernel_size: int = 3, sigma: float = 1.0
    ) -> torch.Tensor:
        """Apply Gaussian smoothing to reduce high-frequency noise."""
        # Create Gaussian kernel
        coords = torch.arange(kernel_size, dtype=torch.float32)
        coords -= (kernel_size - 1) / 2.0
        g = torch.exp(-(coords**2) / (2 * sigma**2))
        g /= g.sum()

        # Create 2D kernel
        kernel_1d = g.view(1, 1, -1).repeat(1, 1, 1, 1)
        kernel_2d = torch.matmul(kernel_1d.transpose(-1, -2), kernel_1d)

        # Apply convolution
        padding = kernel_size // 2
        if x.dim() == 4:  # Batch of images
            channels = x.shape[1]
            kernel = kernel_2d.repeat(channels, 1, 1, 1)
            x_smooth = torch.nn.functional.conv2d(x, kernel, groups=channels, padding=padding)
        else:
            raise ValueError("Expected 4D input for Gaussian smoothing")

        return x_smooth


class AnomalyDetector:
    """
    Detects anomalous patterns in inputs that may indicate adversarial examples.
    """

    def __init__(self, config: DefenseConfig):
        self.config = config
        self.reference_features = []
        self.feature_mean = None
        self.feature_std = None

    def update_reference_distribution(self, features: torch.Tensor):
        """Update the reference distribution with new clean features."""
        self.reference_features.append(features.detach().cpu())

        # Recalculate statistics periodically
        if len(self.reference_features) > 10:  # Keep last 10 batches
            self.reference_features = self.reference_features[-10:]

        # Calculate mean and std of reference features
        all_features = torch.cat(self.reference_features, dim=0)
        self.feature_mean = torch.mean(all_features, dim=0)
        self.feature_std = torch.std(all_features, dim=0) + 1e-8  # Avoid division by zero

    def detect_anomaly(self, features: torch.Tensor) -> tuple[bool, float]:
        """
        Detect if features are anomalous compared to reference distribution.

        Returns:
            (is_anomalous, anomaly_score)
        """
        if self.feature_mean is None or self.feature_std is None:
            # No reference distribution yet
            return False, 0.0

        # Calculate standardized distances
        distances = (features - self.feature_mean) / self.feature_std
        anomaly_score = torch.mean(torch.abs(distances)).item()

        is_anomalous = anomaly_score > self.config.l2_norm_threshold * 10  # Heuristic threshold

        return is_anomalous, anomaly_score


class AdversarialDetector:
    """
    Detects adversarial examples using multiple detection methods.
    """

    def __init__(self, config: DefenseConfig):
        self.config = config
        self.input_sanitizer = InputSanitizer()
        self.anomaly_detector = AnomalyDetector(config)
        self.attack_signatures = {}  # Known attack signatures

    def detect_perturbation_norm(
        self, original: torch.Tensor, perturbed: torch.Tensor
    ) -> dict[str, float]:
        """Detect perturbations using different norm measures."""
        diff = perturbed - original

        l2_norm = torch.norm(diff, p=2).item()
        linf_norm = torch.norm(diff, p=float("inf")).item()
        l1_norm = torch.norm(diff, p=1).item()

        return {"l2_norm": l2_norm, "linf_norm": linf_norm, "l1_norm": l1_norm}

    def detect_correlation(self, original: torch.Tensor, perturbed: torch.Tensor) -> float:
        """Detect correlation between original and perturbed inputs."""
        if original.dim() == 4:  # Images
            flat_orig = original.view(original.size(0), -1)
            flat_pert = perturbed.view(perturbed.size(0), -1)
        else:
            flat_orig = original
            flat_pert = perturbed

        # Calculate Pearson correlation coefficient
        orig_mean = torch.mean(flat_orig, dim=-1, keepdim=True)
        pert_mean = torch.mean(flat_pert, dim=-1, keepdim=True)

        numerator = torch.sum((flat_orig - orig_mean) * (flat_pert - pert_mean), dim=-1)
        denom_orig = torch.sqrt(torch.sum((flat_orig - orig_mean) ** 2, dim=-1))
        denom_pert = torch.sqrt(torch.sum((flat_pert - pert_mean) ** 2, dim=-1))

        correlation = numerator / (denom_orig * denom_pert + 1e-8)
        return correlation.mean().item()

    def detect_high_frequency_noise(self, x: torch.Tensor) -> float:
        """Detect high-frequency noise components that may indicate adversarial perturbations."""
        if x.dim() != 4:  # Only works with images
            return 0.0

        # Convert to numpy for FFT
        x_np = x.detach().cpu().numpy()

        # Calculate average noise level across batch
        noise_levels = []
        for i in range(min(4, x_np.shape[0])):  # Check first 4 samples
            img = x_np[i].transpose(1, 2, 0)  # CHW to HWC
            if img.shape[-1] == 1:  # Grayscale
                img = img.squeeze(-1)

            # Apply FFT
            fft = np.fft.fft2(img)
            magnitude = np.abs(fft)

            # Calculate high frequency energy (central region contains low freq)
            center_x, center_y = magnitude.shape[0] // 2, magnitude.shape[1] // 2
            crop_size = min(magnitude.shape) // 4
            center_region = magnitude[
                center_x - crop_size : center_x + crop_size,
                center_y - crop_size : center_y + crop_size,
            ]
            total_energy = np.sum(magnitude)
            center_energy = np.sum(center_region)

            # High frequency energy ratio
            hf_ratio = (total_energy - center_energy) / total_energy
            noise_levels.append(hf_ratio)

        return np.mean(noise_levels)

    def detect_adversarial(
        self, original: torch.Tensor, processed: torch.Tensor, model: nn.Module
    ) -> dict[str, Any]:
        """
        Comprehensive adversarial detection.

        Returns:
            Dictionary with detection results
        """
        # Calculate perturbation norms
        norms = self.detect_perturbation_norm(original, processed)

        # Calculate correlation
        correlation = self.detect_correlation(original, processed)

        # Detect high frequency noise
        hf_noise = self.detect_high_frequency_noise(processed)

        # Run model on both inputs to check for inconsistent predictions
        model.eval()
        with torch.no_grad():
            orig_logits = model(original)
            proc_logits = model(processed)

            orig_probs = torch.softmax(orig_logits, dim=-1)
            proc_probs = torch.softmax(proc_logits, dim=-1)

            # Calculate confidence change
            orig_conf = torch.max(orig_probs, dim=-1)[0].mean().item()
            proc_conf = torch.max(proc_probs, dim=-1)[0].mean().item()
            conf_change = abs(orig_conf - proc_conf)

            # Calculate prediction entropy change
            orig_entropy = (
                torch.sum(-orig_probs * torch.log(orig_probs + 1e-8), dim=-1).mean().item()
            )
            proc_entropy = (
                torch.sum(-proc_probs * torch.log(proc_probs + 1e-8), dim=-1).mean().item()
            )
            entropy_change = abs(orig_entropy - proc_entropy)

        # Aggregate detection results
        is_adv_l2 = norms["l2_norm"] > self.config.l2_norm_threshold
        is_adv_linf = norms["linf_norm"] > self.config.linf_norm_threshold
        is_low_corr = correlation < self.config.correlation_threshold
        is_high_noise = hf_noise > 0.3  # Heuristic threshold
        is_high_conf_change = conf_change > 0.2  # Heuristic threshold

        # Ensemble decision
        num_indicators = sum(
            [is_adv_l2, is_adv_linf, is_low_corr, is_high_noise, is_high_conf_change]
        )

        is_adversarial = num_indicators >= 3  # At least 3 indicators

        detection_score = num_indicators / 5.0  # Normalize to [0, 1]

        return {
            "is_adversarial": is_adversarial,
            "detection_score": detection_score,
            "perturbation_norms": norms,
            "correlation": correlation,
            "high_freq_noise": hf_noise,
            "confidence_change": conf_change,
            "entropy_change": entropy_change,
            "indicators": {
                "high_l2_norm": is_adv_l2,
                "high_linf_norm": is_adv_linf,
                "low_correlation": is_low_corr,
                "high_noise": is_high_noise,
                "high_conf_change": is_high_conf_change,
            },
        }


class AdversarialDefenseSystem:
    """
    Main adversarial defense system that integrates multiple defense mechanisms.
    """

    def __init__(self, config: DefenseConfig = None):
        self.config = config or DefenseConfig()
        self.adversarial_detector = AdversarialDetector(self.config)
        self.input_sanitizer = InputSanitizer()
        self.attack_history = []
        self.defense_countermeasures = {}

    def preprocess_input(self, x: torch.Tensor) -> torch.Tensor:
        """Apply preprocessing to input to remove obvious perturbations."""
        x = self.input_sanitizer.clip_input(x)
        x = self.input_sanitizer.gaussian_smoothing(x)
        return x

    def detect_and_respond(
        self, original_input: torch.Tensor, model: nn.Module
    ) -> tuple[torch.Tensor, dict[str, Any]]:
        """
        Detect adversarial inputs and respond appropriately.

        Returns:
            (processed_input, detection_results)
        """
        # Preprocess input
        processed_input = self.preprocess_input(original_input)

        # Detect adversarial examples
        detection_results = self.adversarial_detector.detect_adversarial(
            original_input, processed_input, model
        )

        if detection_results["is_adversarial"] and self.config.defense_logging:
            logger.warning(
                f"Adversarial input detected with score {detection_results['detection_score']:.3f}"
            )

            # Log attack for future analysis
            self.attack_history.append(
                {
                    "timestamp": time.time(),
                    "detection_score": detection_results["detection_score"],
                    "norms": detection_results["perturbation_norms"],
                    "attack_indicators": detection_results["indicators"],
                }
            )

        # Apply additional defenses if adversarial detected
        if detection_results["is_adversarial"]:
            # Additional robust preprocessing
            processed_input = self.apply_robust_preprocessing(original_input)

            # Update detection results
            detection_results["defense_applied"] = True
            detection_results["defense_type"] = "robust_preprocessing"

        return processed_input, detection_results

    def apply_robust_preprocessing(self, x: torch.Tensor) -> torch.Tensor:
        """Apply more aggressive preprocessing when adversarial input is detected."""
        # বাংলা মন্তব্য: cv2 এখানে lazily import করা হচ্ছে — deferred import রাখলে opencv
        # CI-তে না থাকলেও শুধু এই মেথড ব্যর্থ হবে, পুরো মডিউল import ব্যর্থ হবে না।
        import cv2  # deferred: keeps this optional dep out of the core import graph

        # Multiple preprocessing steps
        x = self.input_sanitizer.clip_input(x)
        x = self.input_sanitizer.gaussian_smoothing(x, kernel_size=5, sigma=1.5)

        # Additional denoising step
        x_np = x.detach().cpu().numpy()
        # Apply bilateral filter for edge-preserving smoothing
        if x_np.ndim == 4:  # Batch of images
            for i in range(x_np.shape[0]):
                for c in range(x_np.shape[1]):  # Channels
                    # Apply bilateral filter to each channel separately
                    channel = x_np[i, c]
                    filtered = (
                        cv2.bilateralFilter(
                            (channel * 255).astype(np.uint8), d=3, sigmaColor=50, sigmaSpace=50
                        ).astype(np.float32)
                        / 255.0
                    )
                    x_np[i, c] = filtered
            x = torch.from_numpy(x_np).to(x.device).to(x.dtype)

        return x

    def get_defense_statistics(self) -> dict[str, Any]:
        """Get statistics about defense effectiveness."""
        if not self.attack_history:
            return {"attacks_detected": 0, "average_detection_score": 0.0, "last_attack_time": None}

        detection_scores = [attack["detection_score"] for attack in self.attack_history]

        return {
            "attacks_detected": len(self.attack_history),
            "average_detection_score": np.mean(detection_scores),
            "median_detection_score": np.median(detection_scores),
            "last_attack_time": self.attack_history[-1]["timestamp"],
            "attacks_per_hour": len(self.attack_history)
            / max(1, (time.time() - self.attack_history[0]["timestamp"]) / 3600),
        }

    def add_custom_defense(self, name: str, defense_func: callable):  # type: ignore
        """Add a custom defense mechanism."""
        self.defense_countermeasures[name] = defense_func

    def apply_custom_defenses(self, x: torch.Tensor) -> torch.Tensor:
        """Apply all registered custom defenses."""
        for name, defense_func in self.defense_countermeasures.items():
            try:
                x = defense_func(x)
            except Exception as e:
                logger.error(f"Custom defense {name} failed: {e}")

        return x


class AdversarialTrainer:
    """
    Trainer that incorporates adversarial training for improved robustness.
    """

    def __init__(
        self, model: nn.Module, defense_system: AdversarialDefenseSystem, config: DefenseConfig
    ):
        self.model = model
        self.defense_system = defense_system
        self.config = config

    def generate_fgsm_adversarial(
        self, x: torch.Tensor, y: torch.Tensor, eps: float = 0.03
    ) -> torch.Tensor:
        """Generate FGSM adversarial examples for training."""
        self.model.eval()
        x_adv = x.clone().detach().requires_grad_(True)

        outputs = self.model(x_adv)
        loss = torch.nn.functional.cross_entropy(outputs, y)

        # Compute gradients
        loss.backward()

        # Generate adversarial perturbation
        sign_data_grad = x_adv.grad.data.sign()
        x_adv = x_adv + eps * sign_data_grad

        # Clip to maintain valid input range
        x_adv = torch.clamp(x_adv, x.min(), x.max())

        return x_adv.detach()

    def train_step_with_adversarial_regularization(
        self, x: torch.Tensor, y: torch.Tensor, optimizer: torch.optim.Optimizer
    ) -> dict[str, float]:
        """Single training step with adversarial regularization."""
        self.model.train()
        optimizer.zero_grad()

        # Clean loss
        clean_outputs = self.model(x)
        clean_loss = torch.nn.functional.cross_entropy(clean_outputs, y)

        # Generate adversarial examples
        x_adv = self.generate_fgsm_adversarial(x, y, eps=self.config.adversarial_training_eps)

        # Adversarial loss
        adv_outputs = self.model(x_adv)
        adv_loss = torch.nn.functional.cross_entropy(adv_outputs, y)

        # Combined loss
        total_loss = 0.5 * clean_loss + 0.5 * adv_loss

        # Backpropagate
        total_loss.backward()
        optimizer.step()

        return {
            "clean_loss": clean_loss.item(),
            "adversarial_loss": adv_loss.item(),
            "total_loss": total_loss.item(),
        }

    def train_epoch_with_adversarial_augmentation(
        self, data_loader, optimizer: torch.optim.Optimizer
    ) -> dict[str, float]:
        """Train one epoch with adversarial augmentation."""
        total_clean_loss = 0
        total_adv_loss = 0
        total_loss = 0
        num_batches = 0

        for x_batch, y_batch in data_loader:
            losses = self.train_step_with_adversarial_regularization(x_batch, y_batch, optimizer)

            total_clean_loss += losses["clean_loss"]
            total_adv_loss += losses["adversarial_loss"]
            total_loss += losses["total_loss"]
            num_batches += 1

        return {
            "avg_clean_loss": total_clean_loss / num_batches,
            "avg_adversarial_loss": total_adv_loss / num_batches,
            "avg_total_loss": total_loss / num_batches,
        }


# Example usage and testing
def demo_adversarial_defense():
    """Demonstrate adversarial defense capabilities."""
    logger.debug("Initializing Adversarial Defense System...")

    # Create a simple model for demonstration
    class SimpleClassifier(nn.Module):
        def __init__(self, input_size=784, num_classes=10):
            super().__init__()
            self.flatten = nn.Flatten()
            self.fc1 = nn.Linear(input_size, 128)
            self.relu = nn.ReLU()
            self.dropout = nn.Dropout(0.2)
            self.fc2 = nn.Linear(128, num_classes)

        def forward(self, x):
            x = self.flatten(x)
            x = self.fc1(x)
            x = self.relu(x)
            x = self.dropout(x)
            x = self.fc2(x)
            return x

    model = SimpleClassifier()

    # Initialize defense system
    config = DefenseConfig()
    defense_system = AdversarialDefenseSystem(config)

    logger.debug("Testing defense system...")

    # Create dummy input
    dummy_input = torch.randn(4, 1, 28, 28)  # Batch of 4, 1x28x28 images

    # Apply defense
    processed_input, detection_results = defense_system.detect_and_respond(dummy_input, model)

    logger.debug(f"Original input shape: {dummy_input.shape}")
    logger.debug(f"Processed input shape: {processed_input.shape}")
    logger.debug(f"Detection results: {detection_results}")

    # Get defense statistics
    stats = defense_system.get_defense_statistics()
    logger.debug(f"Defense statistics: {stats}")

    # Test adversarial trainer
    logger.debug("\nTesting adversarial training...")
    trainer = AdversarialTrainer(model, defense_system, config)

    # Create dummy data loader
    dummy_dataset = [(torch.randn(2, 1, 28, 28), torch.randint(0, 10, (2,)))]

    # Simulate one training step
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    losses = trainer.train_step_with_adversarial_regularization(
        dummy_dataset[0][0], dummy_dataset[0][1], optimizer
    )

    logger.debug(f"Training losses: {losses}")


if __name__ == "__main__":
    demo_adversarial_defense()
