from __future__ import annotations

"""
SupremeAI Continual Learning - Elastic Weight Consolidation (EWC)
==================================================================

Implements Elastic Weight Consolidation algorithm to enable continual learning
while preventing catastrophic forgetting. Based on the paper:
"Continual Learning in Practice" (Kirkpatrick et al., 2017).

EWC selectively constrains weights that are important for previous tasks,
allowing new learning while preserving old knowledge.

Bengali:
অবিরাম শিক্ষা - ইলাস্টিক ওয়েট কনসোলিডেশন (EWC)
পূর্ববর্তী টাস্কগুলোর জন্য গুরুত্বপূর্ণ ওজনগুলো নির্বাচিতভাবে সীমিত করে নতুন শেখা বাধা দেয়া থেকে রক্ষা করে
"""

# ══════════════════════════════════════════════════════════════════════════════
# ✅ PRODUCTION FIX: Guarded ML imports — graceful degradation if torch unavailable
# ══════════════════════════════════════════════════════════════════════════════
import logging
import os
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

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

# বাংলা মন্তব্য (DEP-AUDIT): এখানে একটি আনগার্ডেড ডুপ্লিকেট
# `from torch.utils.data import DataLoader` ছিল — একই import উপরের
# try/except ImportError ব্লকে (guarded, fallback None) ইতিমধ্যেই হয়ে গেছে।
# torch core image-এ নেই (optional `ml` group), তাই ডুপ্লিকেটটি module import
# ক্র্যাশ করাত — সরানো হলো। DataLoader guarded fallback (None) থেকেই আসবে।


@dataclass
class EWCConfig:
    """Configuration for EWC implementation."""

    lambda_reg: float = 100.0  # Regularization strength
    gamma: float = 1.0  # Decay factor for importance weights
    online: bool = True  # Whether to use online EWC
    fisher_sample_size: int = 64  # Sample size for Fisher computation
    save_dir: str = "./ewc_checkpoints"  # Directory to save EWC parameters


class EWC:
    """
    Elastic Weight Consolidation implementation for continual learning.

    Prevents catastrophic forgetting by selectively constraining weights
    that are important for previous tasks.
    """

    def __init__(self, model: nn.Module, config: EWCConfig):
        self.model = model
        self.config = config
        self.device = next(model.parameters()).device

        # Store previous parameters and importance weights
        self.params_prev: dict[str, torch.Tensor] | None = None
        self.params_importance: dict[str, torch.Tensor] | None = None
        self.task_count = 0

        # Create save directory
        Path(config.save_dir).mkdir(parents=True, exist_ok=True)

    def compute_fisher_matrix(
        self, dataloader: DataLoader, criterion: nn.Module, num_samples: int | None = None
    ) -> dict[str, torch.Tensor]:
        """
        Compute Fisher Information Matrix for the model parameters.

        Args:
            dataloader: DataLoader with data from previous task
            criterion: Loss function
            num_samples: Number of samples to use (None for all)

        Returns:
            Dictionary mapping parameter names to Fisher values
        """
        logger.info("Computing Fisher Information Matrix...")

        # Store original training mode
        train_mode = self.model.training
        self.model.eval()  # Set to eval mode for Fisher computation

        # Initialize Fisher matrices
        fisher_dict = {}
        for n, p in self.model.named_parameters():
            if p.requires_grad:
                fisher_dict[n] = torch.zeros_like(p.data)

        # Sample data points
        total_samples = 0
        if num_samples is None:
            num_samples = float("inf")

        for batch_idx, (inputs, targets) in enumerate(dataloader):
            if total_samples >= num_samples:
                break

            inputs, targets = inputs.to(self.device), targets.to(self.device)

            # Forward pass
            outputs = self.model(inputs)
            loss = criterion(outputs, targets)

            # Compute gradients squared (Fisher diagonal approximation)
            self.model.zero_grad()
            loss.backward(retain_graph=True)

            for n, p in self.model.named_parameters():
                if p.grad is not None:
                    fisher_dict[n] += p.grad.data.pow(2)

            total_samples += inputs.size(0)

            if batch_idx >= self.config.fisher_sample_size:
                break

        # Normalize by number of samples
        for n in fisher_dict:
            fisher_dict[n] /= total_samples

        # Restore original training mode
        self.model.train(train_mode)

        logger.info(f"Computed Fisher matrix using {total_samples} samples")
        return fisher_dict

    def update_importance_weights(self, dataloader: DataLoader, criterion: nn.Module):
        """
        Update importance weights based on Fisher Information Matrix.
        """
        logger.info(f"Updating importance weights for task {self.task_count}")

        # Compute Fisher Information Matrix
        fisher_current = self.compute_fisher_matrix(dataloader, criterion)

        if self.params_importance is None:
            # First task - initialize importance weights
            self.params_importance = {n: fisher_current[n] for n in fisher_current}
        else:
            # Subsequent tasks - update with decayed previous importance
            for n in self.params_importance:
                if n in fisher_current:
                    # Combine current Fisher with previous importance (with decay)
                    self.params_importance[n] = (
                        self.config.gamma * self.params_importance[n]
                        + (1 - self.config.gamma) * fisher_current[n]
                    )

        # Store current parameters
        self.params_prev = {
            n: p.clone().detach() for n, p in self.model.named_parameters() if p.requires_grad
        }

        # Increment task counter
        self.task_count += 1

    def compute_ewc_loss(self) -> torch.Tensor:
        """
        Compute EWC regularization loss.

        Returns:
            EWC regularization term to be added to main loss
        """
        if self.params_prev is None or self.params_importance is None:
            # No previous task, no regularization needed
            return torch.tensor(0.0, device=self.device)

        ewc_loss = torch.tensor(0.0, device=self.device)

        for n, p in self.model.named_parameters():
            if n in self.params_prev and p.requires_grad:
                # Compute quadratic penalty around previous parameter values
                _loss = self.params_importance[n] * (p - self.params_prev[n]).pow(2)
                ewc_loss += _loss.sum()

        # Apply regularization strength
        ewc_loss *= self.config.lambda_reg / 2

        return ewc_loss

    def save_checkpoint(self, task_id: str):
        """
        Save EWC parameters to checkpoint.

        Args:
            task_id: Identifier for the current task
        """
        checkpoint_path = os.path.join(self.config.save_dir, f"ewc_checkpoint_task_{task_id}.pkl")

        checkpoint = {
            "task_count": self.task_count,
            "params_prev": self.params_prev,
            "params_importance": self.params_importance,
            "lambda_reg": self.config.lambda_reg,
            "gamma": self.config.gamma,
        }

        with open(checkpoint_path, "wb") as f:
            pickle.dump(checkpoint, f)

        logger.info(f"Saved EWC checkpoint for task {task_id} at {checkpoint_path}")

    def load_checkpoint(self, task_id: str) -> bool:
        """
        Load EWC parameters from checkpoint.

        Args:
            task_id: Identifier for the task to load

        Returns:
            True if successful, False otherwise
        """
        # বাংলা: task_id ফাইল পাথে বসানোর আগে sanitize করা হলো, যাতে path-traversal
        # (যেমন task_id="../../etc/passwd") সম্ভব না হয়।
        safe_task_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id))
        checkpoint_path = os.path.join(
            self.config.save_dir, f"ewc_checkpoint_task_{safe_task_id}.pkl"
        )

        if not os.path.exists(checkpoint_path):
            logger.warning(f"No EWC checkpoint found for task {task_id}")
            return False

        # বাংলা: এই pickle ফাইলগুলো আমাদের নিজস্ব save_checkpoint()-এর তৈরি, বাইরের/আপলোড করা
        # ডেটা না — তাই এখানে untrusted deserialization ঝুঁকি নেই, কিন্তু ভবিষ্যতে যদি
        # multi-tenant শেয়ার্ড স্টোরেজে যায়, তাহলে এটা torch.save/load বা JSON-এ migrate করা উচিত।
        with open(checkpoint_path, "rb") as f:
            checkpoint = pickle.load(
                f
            )  # -- trusted, self-written checkpoint file (see comment above)

        self.task_count = checkpoint["task_count"]
        self.params_prev = checkpoint["params_prev"]
        self.params_importance = checkpoint["params_importance"]
        self.config.lambda_reg = checkpoint["lambda_reg"]
        self.config.gamma = checkpoint["gamma"]

        logger.info(f"Loaded EWC checkpoint for task {task_id}")
        return True

    def get_importance_map(self) -> dict[str, torch.Tensor]:
        """
        Get the current importance map for all parameters.

        Returns:
            Dictionary mapping parameter names to importance values
        """
        return self.params_importance or {}


class OnlineEWC(EWC):
    """
    Online version of EWC that updates importance weights incrementally.

    More suitable for streaming or continual learning scenarios where
    data from previous tasks is not available.
    """

    def __init__(self, model: nn.Module, config: EWCConfig):
        super().__init__(model, config)
        self.online_fisher: dict[str, torch.Tensor] | None = None
        self.samples_seen = 0

    def update_online_fisher(
        self, inputs: torch.Tensor, targets: torch.Tensor, criterion: nn.Module
    ):
        """
        Update Fisher matrix incrementally with new data.
        """
        # Store original training mode
        train_mode = self.model.training
        self.model.eval()

        # Forward pass
        outputs = self.model(inputs)
        loss = criterion(outputs, targets)

        # Compute gradients squared
        self.model.zero_grad()
        loss.backward(retain_graph=True)

        if self.online_fisher is None:
            # Initialize online Fisher
            self.online_fisher = {}
            for n, p in self.model.named_parameters():
                if p.requires_grad:
                    self.online_fisher[n] = torch.zeros_like(p.data)

        # Update Fisher estimates incrementally
        for n, p in self.model.named_parameters():
            if p.grad is not None:
                if self.samples_seen == 0:
                    self.online_fisher[n] = p.grad.data.pow(2)
                else:
                    # Moving average update
                    alpha = 1.0 / (self.samples_seen + 1)
                    self.online_fisher[n] = (1 - alpha) * self.online_fisher[
                        n
                    ] + alpha * p.grad.data.pow(2)

        self.samples_seen += inputs.size(0)

        # Restore original training mode
        self.model.train(train_mode)

    def update_importance_weights(self, dataloader: DataLoader, criterion: nn.Module):
        """
        Override parent method to use online Fisher updates.
        """
        logger.info(f"Updating online importance weights for task {self.task_count}")

        # Update online Fisher matrix with data from this task
        for inputs, targets in dataloader:
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            self.update_online_fisher(inputs, targets, criterion)

        if self.params_importance is None:
            # First task - initialize importance weights
            self.params_importance = {n: self.online_fisher[n].clone() for n in self.online_fisher}
        else:
            # Subsequent tasks - update with decayed previous importance
            for n in self.params_importance:
                if n in self.online_fisher:
                    self.params_importance[n] = (
                        self.config.gamma * self.params_importance[n]
                        + (1 - self.config.gamma) * self.online_fisher[n]
                    )

        # Store current parameters
        self.params_prev = {
            n: p.clone().detach() for n, p in self.model.named_parameters() if p.requires_grad
        }

        # Increment task counter
        self.task_count += 1


class EWCTrainer:
    """
    Trainer class that incorporates EWC into the training loop.
    """

    def __init__(
        self,
        model: nn.Module,
        ewc_config: EWCConfig,
        optimizer: optim.Optimizer,
        ewc_enabled: bool = True,
    ):
        self.model = model
        self.ewc = EWC(model, ewc_config) if not ewc_config.online else OnlineEWC(model, ewc_config)
        self.optimizer = optimizer
        self.ewc_enabled = ewc_enabled
        self.device = next(model.parameters()).device

    def train_step(
        self, inputs: torch.Tensor, targets: torch.Tensor, criterion: nn.Module
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Single training step with optional EWC regularization.

        Args:
            inputs: Input tensor
            targets: Target tensor
            criterion: Loss function

        Returns:
            (total_loss, prediction_loss)
        """
        inputs, targets = inputs.to(self.device), targets.to(self.device)

        # Forward pass
        outputs = self.model(inputs)
        prediction_loss = criterion(outputs, targets)

        # Add EWC regularization if enabled
        if self.ewc_enabled:
            ewc_loss = self.ewc.compute_ewc_loss()
            total_loss = prediction_loss + ewc_loss
        else:
            total_loss = prediction_loss
            ewc_loss = torch.tensor(0.0, device=self.device)

        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()

        return total_loss, prediction_loss

    def train_task(self, dataloader: DataLoader, criterion: nn.Module, epochs: int, task_id: str):
        """
        Train on a specific task with EWC regularization.

        Args:
            dataloader: Training data for current task
            criterion: Loss function
            epochs: Number of training epochs
            task_id: Identifier for this task
        """
        logger.info(f"Training on task {task_id} with EWC regularization")

        self.model.train()

        for epoch in range(epochs):
            epoch_loss = 0.0
            num_batches = 0

            for inputs, targets in dataloader:
                total_loss, _pred_loss = self.train_step(inputs, targets, criterion)
                epoch_loss += total_loss.item()
                num_batches += 1

            avg_loss = epoch_loss / num_batches
            logger.info(f"Task {task_id}, Epoch {epoch + 1}/{epochs}, Avg Loss: {avg_loss:.4f}")

        # Update importance weights after training
        if self.ewc_enabled:
            self.ewc.update_importance_weights(dataloader, criterion)

            # Save checkpoint
            self.ewc.save_checkpoint(task_id)

    def evaluate_importance(self) -> dict[str, dict[str, float]]:
        """
        Evaluate parameter importance across layers.

        Returns:
            Dictionary with layer-wise importance statistics
        """
        importance_map = self.ewc.get_importance_map()

        importance_stats = {}

        for param_name, importance_values in importance_map.items():
            importance_stats[param_name] = {
                "mean": importance_values.mean().item(),
                "std": importance_values.std().item(),
                "min": importance_values.min().item(),
                "max": importance_values.max().item(),
                "num_params": importance_values.numel(),
            }

        return importance_stats


# Example usage and testing
def create_example_model():
    """Create a simple example model for testing EWC."""

    class SimpleMLP(nn.Module):
        def __init__(self, input_size=784, hidden_size=256, output_size=10):
            super().__init__()
            self.fc1 = nn.Linear(input_size, hidden_size)
            self.relu = nn.ReLU()
            self.fc2 = nn.Linear(hidden_size, hidden_size)
            self.fc3 = nn.Linear(hidden_size, output_size)

        def forward(self, x):
            x = x.view(x.size(0), -1)  # Flatten
            x = self.fc1(x)
            x = self.relu(x)
            x = self.fc2(x)
            x = self.relu(x)
            x = self.fc3(x)
            return x

    return SimpleMLP()


def demo_ewc():
    """Demonstrate EWC functionality."""
    logger.debug("Initializing EWC Demo...")

    # Create model and EWC configuration
    model = create_example_model()
    config = EWCConfig(lambda_reg=100.0, fisher_sample_size=32)

    # Create optimizer
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    # Create dummy data for demonstration
    dummy_data = torch.randn(100, 784)
    dummy_targets = torch.randint(0, 10, (100,))

    # Create trainer with EWC
    trainer = EWCTrainer(model, config, optimizer)

    # Simulate training on Task 1
    logger.debug("\nTraining on Task 1...")
    [(dummy_data[:50], dummy_targets[:50])]  # Simplified loader
    criterion = nn.CrossEntropyLoss()

    # Convert to proper DataLoader for demo
    from torch.utils.data import TensorDataset

    dataset1 = TensorDataset(dummy_data[:50], dummy_targets[:50])
    dataloader1 = DataLoader(dataset1, batch_size=10, shuffle=True)

    trainer.train_task(dataloader1, criterion, epochs=2, task_id="task1")

    # Simulate training on Task 2 (different data distribution)
    logger.debug("\nTraining on Task 2 with EWC protection...")
    dataset2 = TensorDataset(dummy_data[50:], dummy_targets[50:])  # Different subset
    dataloader2 = DataLoader(dataset2, batch_size=10, shuffle=True)

    trainer.train_task(dataloader2, criterion, epochs=2, task_id="task2")

    # Evaluate importance
    importance_stats = trainer.evaluate_importance()
    logger.debug(f"\nParameter importance statistics computed for {len(importance_stats)} layers")

    # Show some importance statistics
    for name, stats in list(importance_stats.items())[:3]:  # Show first 3
        logger.debug(f"Layer {name}: Mean importance = {stats['mean']:.6f}")


if __name__ == "__main__":
    demo_ewc()
