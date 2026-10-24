"""backend/core/kernel/__init__.py — SupremeKernel exports.

Phase-4 (issue #2260): canonical primitives live in the kernel package.
Wave 1 wires the Audit primitive pair:
  - ``core/kernel/audit_logger.py``  — blueprint ৪.৩ canonical audit trail (PG write-behind)
  - ``core/kernel/audit_chain.py``   — MCP hash-chain (the only tamper evidence)
"""

from core.kernel.audit_chain import (
    MCPAuditChainStore,
    args_fingerprint,
    compute_entry_hash,
    get_audit_chain_store,
)
from core.kernel.audit_logger import AuditLogger
from core.kernel.dispatcher import SupremeKernel, supreme_kernel
from core.kernel.interface import CircleScope, ExecutionMode, KernelRequest, KernelResponse

__all__ = [
    "AuditLogger",
    "CircleScope",
    "ExecutionMode",
    "KernelRequest",
    "KernelResponse",
    "MCPAuditChainStore",
    "SupremeKernel",
    "args_fingerprint",
    "compute_entry_hash",
    "get_audit_chain_store",
    "supreme_kernel",
]
