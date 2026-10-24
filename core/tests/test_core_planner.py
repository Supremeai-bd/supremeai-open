import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from core.context_synthesizer import ContextStage, ContextSynthesizer
    from core.dag_planner import CycleDetectedError, DAGPlanner, TaskNode
    from core.decision_engine import AgentRole, DecisionEngine
    from core.state_machine import (
        AgentState,
        AgentStateMachine,
        InvalidStateTransitionError,
    )
except ImportError:
    from context_synthesizer import ContextStage, ContextSynthesizer
    from dag_planner import CycleDetectedError, DAGPlanner, TaskNode
    from decision_engine import AgentRole, DecisionEngine
    from state_machine import (
        AgentState,
        AgentStateMachine,
        InvalidStateTransitionError,
    )


class TestAgentStateMachine(unittest.TestCase):
    def test_initial_state_idle(self):
        fsm = AgentStateMachine("agent-007")
        self.assertEqual(fsm.current_state, AgentState.IDLE)
        self.assertFalse(fsm.is_terminal)

    def test_valid_lifecycle_transitions(self):
        fsm = AgentStateMachine("agent-007")
        fsm.transition_to(AgentState.CLAIMED, reason="Atomic claim acquired")
        self.assertEqual(fsm.current_state, AgentState.CLAIMED)

        fsm.transition_to(AgentState.EXECUTING, reason="Started work")
        self.assertEqual(fsm.current_state, AgentState.EXECUTING)

        fsm.transition_to(AgentState.VERIFYING, reason="Running tests")
        self.assertEqual(fsm.current_state, AgentState.VERIFYING)

        fsm.transition_to(AgentState.TERMINATED, reason="Merged and landed")
        self.assertEqual(fsm.current_state, AgentState.TERMINATED)
        self.assertTrue(fsm.is_terminal)
        self.assertEqual(len(fsm.history), 4)

    def test_invalid_transition_rejected(self):
        fsm = AgentStateMachine("agent-007")
        with self.assertRaises(InvalidStateTransitionError):
            fsm.transition_to(AgentState.TERMINATED)  # IDLE -> TERMINATED is forbidden


class TestDAGPlanner(unittest.TestCase):
    def test_linear_topological_sort(self):
        planner = DAGPlanner()
        planner.add_task(TaskNode("t1", "Schema", "api"))
        planner.add_task(TaskNode("t2", "Backend", "core", dependencies={"t1"}))
        planner.add_task(TaskNode("t3", "UI", "studio", dependencies={"t2"}))

        order = planner.topological_sort()
        self.assertEqual(order, ["t1", "t2", "t3"])

    def test_cycle_detection(self):
        planner = DAGPlanner()
        planner.add_task(TaskNode("t1", "Task A", "core", dependencies={"t2"}))
        planner.add_task(TaskNode("t2", "Task B", "core", dependencies={"t1"}))

        with self.assertRaises(CycleDetectedError):
            planner.topological_sort()

    def test_execution_tiers(self):
        planner = DAGPlanner()
        planner.add_task(TaskNode("base1", "Base 1", "sdk"))
        planner.add_task(TaskNode("base2", "Base 2", "api"))
        planner.add_task(
            TaskNode("mid", "Mid Layer", "core", dependencies={"base1", "base2"})
        )
        planner.add_task(TaskNode("top", "Top Layer", "studio", dependencies={"mid"}))

        tiers = planner.compute_execution_tiers()
        self.assertEqual(tiers, [["base1", "base2"], ["mid"], ["top"]])


class TestDecisionEngine(unittest.TestCase):
    def test_critical_path_classification(self):
        classification = DecisionEngine.classify_task(
            "P0: hotfix auth token", ["core/state_machine.py"]
        )
        self.assertEqual(classification.recommended_role, AgentRole.AUDITOR)
        self.assertEqual(classification.risk_tier, "L3")
        self.assertTrue(classification.requires_approval)

    def test_docs_only_classification(self):
        classification = DecisionEngine.classify_task(
            "docs: update runbook", ["docs/architecture.md"]
        )
        self.assertEqual(classification.recommended_role, AgentRole.SCOUT)
        self.assertEqual(classification.risk_tier, "L1")
        self.assertFalse(classification.requires_approval)

    def test_standard_feature_classification(self):
        classification = DecisionEngine.classify_task(
            "feat(api): add route", ["gateway/routes.py"]
        )
        self.assertEqual(classification.recommended_role, AgentRole.CODER)
        self.assertEqual(classification.risk_tier, "L2")


class TestContextSynthesizer(unittest.TestCase):
    def test_stage1_discovery_budget(self):
        huge_text = "A" * 10000
        fitted = ContextSynthesizer.fit_context(
            ContextStage.STAGE1_DISCOVERY, huge_text
        )
        self.assertLessEqual(len(fitted), 4000 + 100)
        self.assertIn("TRUNCATED", fitted)

    def test_small_text_not_truncated(self):
        small_text = "Brief summary"
        fitted = ContextSynthesizer.fit_context(
            ContextStage.STAGE1_DISCOVERY, small_text
        )
        self.assertEqual(fitted, small_text)


if __name__ == "__main__":
    unittest.main()
