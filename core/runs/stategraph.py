"""
SupremeAI Micro StateGraph Engine
=================================
A lightweight, zero-dependency, cyclic state-machine engine designed for
stateful multi-agent workflows, self-healing code loops, and dynamic AI decision trees.

Adopts the LangGraph StateGraph architectural pattern (cyclic graphs, checkpointers,
conditional edges, and state reducers) with zero external library bloat, ensuring
complete cloud-parity and 512MB RAM compliance.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from core.logging_config import logger

END = "__end__"
START = "__start__"


class StateGraphError(Exception):
    """Base exception for StateGraph errors."""


class RecursionLimitExceeded(StateGraphError):
    """Raised when graph execution exceeds the maximum allowed iterations."""


class NodeExecutionError(StateGraphError):
    """Raised when a graph node fails execution."""


def list_append_reducer(current: list[Any] | None, new_items: list[Any] | Any) -> list[Any]:
    """Default reducer for list-based state attributes (e.g. messages, history)."""
    base = list(current) if current else []
    if isinstance(new_items, list):
        base.extend(new_items)
    else:
        base.append(new_items)
    return base


class CompiledGraph:
    """Executable graph compiled from a StateGraph specification."""

    def __init__(
        self,
        nodes: dict[str, Callable[..., Any]],
        edges: dict[str, str],
        conditional_edges: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str]]],
        entry_point: str,
        reducers: dict[str, Callable[[Any, Any], Any]],
        checkpointer: Any | None = None,
        interrupt_before: set[str] | None = None,
        interrupt_after: set[str] | None = None,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.reducers = reducers
        self.checkpointer = checkpointer
        self.interrupt_before = interrupt_before or set()
        self.interrupt_after = interrupt_after or set()

    def _apply_state_delta(
        self, current_state: dict[str, Any], delta: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Apply a node's return delta onto current state using configured reducers."""
        if not delta or not isinstance(delta, dict):
            return current_state

        updated = dict(current_state)
        for key, value in delta.items():
            if key in self.reducers:
                updated[key] = self.reducers[key](updated.get(key), value)
            else:
                updated[key] = value
        return updated

    async def _execute_node(
        self, node_name: str, node_func: Callable[..., Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a node action whether it is an async coroutine or synchronous function."""
        try:
            if inspect.iscoroutinefunction(node_func):
                result = await node_func(state)
            else:
                result = node_func(state)

            if inspect.isawaitable(result):
                result = await result

            if result is None:
                return {}
            if isinstance(result, dict):
                return result
            return {"result": result}
        except Exception as exc:
            logger.error(f"[StateGraph] Node '{node_name}' failed with error: {exc}")
            raise NodeExecutionError(f"Node '{node_name}' execution failed: {exc}") from exc

    def _save_checkpoint(
        self, run_id: str, node_name: str, state: dict[str, Any], step_index: int
    ) -> None:
        """Persist graph state snapshot to checkpointer if configured."""
        if not self.checkpointer:
            return
        try:
            if hasattr(self.checkpointer, "save_graph_state"):
                self.checkpointer.save_graph_state(
                    run_id=run_id, node=node_name, state=state, step_index=step_index
                )
            elif hasattr(self.checkpointer, "save"):
                self.checkpointer.save(task_id=run_id, step_index=step_index, state=state)
        except Exception as exc:
            logger.warning(f"[StateGraph] Checkpoint save failed: {exc}")

    async def invoke(
        self,
        initial_state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the compiled state graph.

        Args:
            initial_state: The initial dictionary state passed to the graph.
            config: Optional runtime configuration dictionary containing:
                - "run_id": Unique identifier for checkpointing/tracing (auto-generated if omitted).
                - "max_iterations": Recursion limit for cyclic graphs (default: 25).
                - "start_node": Override entry point (useful for resumption).

        Returns:
            The final output state dictionary upon reaching END or an interrupted state.
        """
        config = config or {}
        run_id = str(config.get("run_id") or uuid.uuid4())
        max_iterations = int(config.get("max_iterations", 25))
        current_node = str(config.get("start_node") or self.entry_point)
        skip_interrupt_node = config.get("skip_interrupt_node")

        state = dict(initial_state)
        state["__run_id__"] = run_id
        state.setdefault("__execution_trace__", [])

        iteration = 0
        while current_node != END:
            iteration += 1
            if iteration > max_iterations:
                err = f"Recursion limit ({max_iterations}) exceeded at node '{current_node}'"
                logger.error(f"[StateGraph] {err}")
                raise RecursionLimitExceeded(err)

            if current_node not in self.nodes:
                raise StateGraphError(f"Target node '{current_node}' not found in compiled graph")

            # 1. Interrupt Before Check
            if current_node in self.interrupt_before and current_node != skip_interrupt_node:
                logger.info(f"[StateGraph] Pausing execution before node '{current_node}' (HITL)")
                state["__interrupted__"] = True
                state["__interrupted_at__"] = current_node
                state["__resume_point__"] = current_node
                self._save_checkpoint(run_id, current_node, state, iteration)
                return state

            # Clear skip_interrupt_node after safely passing it
            skip_interrupt_node = None

            # 2. Execute Node
            node_fn = self.nodes[current_node]
            step_start = datetime.now(UTC).isoformat()
            delta = await self._execute_node(current_node, node_fn, state)

            # Record step trace
            state["__execution_trace__"].append(
                {
                    "step": iteration,
                    "node": current_node,
                    "timestamp": step_start,
                }
            )

            # Apply delta
            state = self._apply_state_delta(state, delta)

            # 3. Check for in-node interrupt signal
            if delta.get("__interrupt__"):
                logger.info(f"[StateGraph] Node '{current_node}' requested interruption (HITL)")
                state["__interrupted__"] = True
                state["__interrupted_at__"] = current_node
                self._save_checkpoint(run_id, current_node, state, iteration)
                return state

            # 4. Interrupt After Check
            if current_node in self.interrupt_after:
                logger.info(f"[StateGraph] Pausing execution after node '{current_node}' (HITL)")
                state["__interrupted__"] = True
                state["__interrupted_at__"] = current_node
                self._save_checkpoint(run_id, current_node, state, iteration)
                return state

            # Save step checkpoint
            self._save_checkpoint(run_id, current_node, state, iteration)

            # 5. Resolve Next Node
            if current_node in self.conditional_edges:
                condition_fn, path_map = self.conditional_edges[current_node]
                try:
                    condition_val = condition_fn(state)
                    if inspect.isawaitable(condition_val):
                        condition_val = await condition_val
                    next_node = path_map.get(str(condition_val), END)
                except Exception as exc:
                    logger.error(
                        f"[StateGraph] Conditional edge evaluation failed at '{current_node}': {exc}"
                    )
                    raise StateGraphError(
                        f"Condition evaluation failed at '{current_node}': {exc}"
                    ) from exc
            elif current_node in self.edges:
                next_node = self.edges[current_node]
            else:
                next_node = END

            current_node = next_node

        state["__interrupted__"] = False
        state["__completed__"] = True
        state.pop("__interrupted_at__", None)
        state.pop("__resume_point__", None)
        return state

    async def resume(
        self,
        run_id: str,
        resume_state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Resume an interrupted graph from its last stored checkpoint.
        """
        if not self.checkpointer:
            raise StateGraphError(
                "Cannot resume graph: no checkpointer was configured during compilation"
            )

        saved = None
        if hasattr(self.checkpointer, "load_graph_state"):
            saved = self.checkpointer.load_graph_state(run_id)
        elif hasattr(self.checkpointer, "load"):
            res = self.checkpointer.load(run_id)
            if res:
                saved = res.get("state")

        if not saved or not isinstance(saved, dict):
            raise StateGraphError(f"No checkpoint found for run_id '{run_id}'")

        resumed_state = dict(saved)
        if resume_state:
            resumed_state.update(resume_state)

        start_node = resumed_state.get("__resume_point__") or resumed_state.get(
            "__interrupted_at__"
        )
        if not start_node or start_node not in self.nodes:
            # Fallback to entry point
            start_node = self.entry_point

        resumed_state["__interrupted__"] = False
        merged_config = dict(config or {})
        merged_config["run_id"] = run_id
        merged_config["start_node"] = start_node
        merged_config["skip_interrupt_node"] = start_node

        logger.info(f"[StateGraph] Resuming run '{run_id}' at node '{start_node}'")
        return await self.invoke(initial_state=resumed_state, config=merged_config)


class StateGraph:
    """
    Builder for cyclic state graphs.

    Usage:
        >>> graph = StateGraph()
        >>> graph.add_node("plan", planning_func)
        >>> graph.add_node("execute", execution_func)
        >>> graph.add_node("critique", critique_func)
        >>> graph.set_entry_point("plan")
        >>> graph.add_edge("plan", "execute")
        >>> graph.add_edge("execute", "critique")
        >>> graph.add_conditional_edges("critique", should_continue, {"retry": "execute", "finish": END})
        >>> compiled = graph.compile()
        >>> result = await compiled.invoke({"input": "task description"})
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Callable[..., Any]] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[
            str, tuple[Callable[[dict[str, Any]], str], dict[str, str]]
        ] = {}
        self._entry_point: str | None = None
        self._reducers: dict[str, Callable[[Any, Any], Any]] = {
            "messages": list_append_reducer,
            "errors": list_append_reducer,
        }

    def add_node(self, name: str, action: Callable[..., Any]) -> StateGraph:
        """Register a node in the graph."""
        if name in (START, END):
            raise ValueError(f"Reserved node name '{name}' cannot be explicitly added as a node")
        self._nodes[name] = action
        return self

    def add_edge(self, start_key: str, end_key: str) -> StateGraph:
        """Add an unconditional directional transition from start_key to end_key."""
        self._edges[start_key] = end_key
        return self

    def add_conditional_edges(
        self,
        start_key: str,
        condition: Callable[[dict[str, Any]], str | Awaitable[str]],
        path_map: dict[str, str],
    ) -> StateGraph:
        """
        Add a conditional transition evaluated dynamically based on state.

        Args:
            start_key: Origin node.
            condition: Function taking `state` and returning a route key.
            path_map: Mapping of condition return values to destination node names (or END).
        """
        self._conditional_edges[start_key] = (condition, path_map)
        return self

    def set_entry_point(self, key: str) -> StateGraph:
        """Set the initial entry node of the graph."""
        self._entry_point = key
        return self

    def add_reducer(self, key: str, reducer_fn: Callable[[Any, Any], Any]) -> StateGraph:
        """Configure a custom state reducer function for a given state attribute."""
        self._reducers[key] = reducer_fn
        return self

    def compile(
        self,
        checkpointer: Any | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
    ) -> CompiledGraph:
        """Compile graph specification into an executable CompiledGraph instance."""
        if not self._entry_point:
            if not self._nodes:
                raise StateGraphError("Cannot compile empty graph: no nodes registered")
            self._entry_point = next(iter(self._nodes))

        if self._entry_point not in self._nodes:
            raise StateGraphError(
                f"Entry point '{self._entry_point}' not found among registered nodes"
            )

        return CompiledGraph(
            nodes=dict(self._nodes),
            edges=dict(self._edges),
            conditional_edges=dict(self._conditional_edges),
            entry_point=self._entry_point,
            reducers=dict(self._reducers),
            checkpointer=checkpointer,
            interrupt_before=set(interrupt_before or []),
            interrupt_after=set(interrupt_after or []),
        )

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart diagram of the graph architecture."""
        lines = ["graph TD"]
        lines.append(f"    START([Start]) --> {self._entry_point}")

        for start_k, end_k in self._edges.items():
            target = "END([End])" if end_k == END else end_k
            lines.append(f"    {start_k} --> {target}")

        for start_k, (_, path_map) in self._conditional_edges.items():
            for condition_val, dest_k in path_map.items():
                target = "END([End])" if dest_k == END else dest_k
                lines.append(f"    {start_k} -.->|{condition_val}| {target}")

        return "\n".join(lines)
