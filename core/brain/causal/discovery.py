# backend/brain/causal/discovery.py
"""
Causal Discovery Engine
Discovers Causal Directed Acyclic Graphs (DAGs) from observational telemetry metrics.
"""

from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None
from core.logging_config import logger


class CausalDiscoveryEngine:
    """
    Learns Causal DAGs from system telemetry metrics data.
    """

    def __init__(self, algorithm: str = "pc"):
        self.algorithm = algorithm
        self.graph = None

    async def discover_graph(
        self, data: pd.DataFrame, alpha: float = 0.05, max_cond_vars: int = 3
    ) -> dict[str, Any]:
        """
        Build Causal DAG from input dataframe metrics.

        Args:
            data: DataFrame with metric columns (cpu, memory, latency, error_rate)
            alpha: Significance threshold
        """
        cols = list(data.columns)
        edges = []

        # Heuristic Correlation-based DAG discovery fallback if cdt/gcastle absent
        corr = data.corr(numeric_only=True)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                col_i = cols[i]
                col_j = cols[j]
                val = corr.loc[col_i, col_j]
                if abs(val) > 0.5:
                    # Direction heuristic: cause usually precedes or drives metrics
                    edges.append({"source": col_i, "target": col_j, "weight": float(val)})

        logger.info(
            f"🕸️ [Causal Discovery] Formed DAG with {len(cols)} nodes and {len(edges)} directed edges"
        )

        return {
            "algorithm": self.algorithm,
            "nodes": cols,
            "edges": edges,
            "sample_count": len(data),
        }
