try:
    from tools.checkpoint_manager import CheckpointManager
except ImportError:
    from checkpoint_manager import CheckpointManager


class CheckpointResume:
    def __init__(self, db_path: str | None = None):
        self.manager = CheckpointManager(db_path=db_path)

    def save(self, task_id: str, step_index: int, state: dict):
        return self.manager.save(task_id, step_index, state)

    def load(self, task_id: str):
        checkpoint = self.manager.load(task_id)
        if not checkpoint:
            return None
        return {
            "task_id": checkpoint.task_id,
            "step_index": checkpoint.step_index,
            "state": checkpoint.state,
            "resumed": checkpoint.resumed,
        }

    def list_all(self):
        return self.manager.list_all()

    def clear(self, task_id: str):
        return self.manager.clear(task_id)

    def save_graph_state(self, run_id: str, node: str, state: dict, step_index: int = 0):
        """Save graph execution snapshot keyed by run_id and active node."""
        snapshot = dict(state)
        snapshot["__current_node__"] = node
        return self.save(task_id=run_id, step_index=step_index, state=snapshot)

    def load_graph_state(self, run_id: str) -> dict | None:
        """Load graph execution snapshot for a given run_id."""
        res = self.load(task_id=run_id)
        if not res:
            return None
        return res.get("state")
