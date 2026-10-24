import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from core.logging_config import logger

# বাংলা মন্তব্য: Judge-এর জন্য consensus থ্রেশহোল্ড — hardcode value নয়, একটি নামযুক্ত
# কনস্ট্যান্ট যাতে ভবিষ্যতে routing_policy.json/settings থেকে override করা সহজ হয়।
_CONSENSUS_SCORE_THRESHOLD = 0.7

# বাংলা মন্তব্য: Proposer এজেন্টের role prefix → task_type mapping।
# LLMGateway-র TASK_MODEL_MAP-এর সাথে মিল রেখে সঠিক মডেল রাউট হবে।
_AGENT_ROLE_TASK_TYPE: dict[str, str] = {
    "architect": "reasoning",
    "coder": "coding",
    "qa": "reasoning",
}


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    """
    বাংলা মন্তব্য: LLM প্রায়ই JSON-কে markdown code fence (```json ... ```) দিয়ে
    ঘিরে ফেলে বা আশেপাশে কনভারসেশনাল টেক্সট যোগ করে। এই হেল্পার নিরাপদে সেটা
    বের করে parse করে — parse ব্যর্থ হলে exception তোলে না, None রিটার্ন করে।
    """
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(0)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class DebateState(StrEnum):
    PROPOSING = "PROPOSING"
    JUDGING = "JUDGING"
    RETHINKING = "RETHINKING"
    CONSENSUS = "CONSENSUS"


class Proposal(BaseModel):
    agent_id: str
    content: str
    score: float = 0.0
    feedback: str | None = None


class JudgeAgent:
    """
    JudgeAgent uses a heavier, more capable model (e.g., GPT-4o or Gemini-1.5-Pro)
    to evaluate proposals from smaller, faster models.
    """

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name

    async def evaluate_proposals(
        self, task_prompt: str, proposals: list[Proposal]
    ) -> dict[str, Any]:
        """
        Evaluates the given proposals against the original task prompt.
        Returns the evaluation result including decision state and the winning proposal (if any).
        """
        logger.info(f"Judge Agent [{self.model_name}] evaluating {len(proposals)} proposals...")

        if not proposals:
            return {
                "decision": DebateState.RETHINKING,
                "best_proposal": None,
                "feedback": "No proposals to evaluate.",
            }

        from core.llm.llm_gateway import get_llm_gateway

        proposals_block = "\n\n".join(
            f"### Proposal from {p.agent_id}\n{p.content}" for p in proposals
        )
        system_prompt = (
            "You are the Judge Agent in a multi-agent debate/consensus system. "
            "Evaluate the given proposals against the original task and pick the strongest one. "
            "Respond with ONLY a raw JSON object (no markdown, no commentary) matching this schema: "
            '{"winning_agent_id": string, "score": number between 0 and 1, '
            '"consensus_reached": boolean, "feedback": string}. '
            "Set consensus_reached to true only if the winning proposal genuinely and completely "
            "solves the task; otherwise set it to false and explain what is missing in feedback."
        )
        user_prompt = f"## Original Task\n{task_prompt}\n\n## Proposals\n{proposals_block}"

        try:
            gateway = get_llm_gateway()
            response = await gateway.acompletion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                task_type="reasoning",
                model=self.model_name,
            )
        except Exception as exc:
            # বাংলা মন্তব্য: LLMGateway নিজেই fallback chain ও circuit breaker চেষ্টা করে
            # সব ব্যর্থ হলে এখানে exception আসে — পুরো debate crash না করিয়ে RETHINKING-এ পাঠানো হচ্ছে
            logger.warning(f"Judge Agent LLM call failed after all fallbacks: {exc}")
            return {
                "decision": DebateState.RETHINKING,
                "best_proposal": None,
                "feedback": f"Judge evaluation unavailable (LLM error: {exc}). Retrying next cycle.",
            }

        parsed = (
            _extract_json_object(response.get("text", "")) if isinstance(response, dict) else None
        )
        if not parsed:
            logger.warning(f"Judge Agent returned non-JSON response: {response}")
            return {
                "decision": DebateState.RETHINKING,
                "best_proposal": None,
                "feedback": "Judge response could not be parsed as JSON. Retrying next cycle.",
            }

        winning_agent_id = parsed.get("winning_agent_id")
        winner = next((p for p in proposals if p.agent_id == winning_agent_id), proposals[0])
        try:
            winner.score = float(parsed.get("score", 0.0))
        except (TypeError, ValueError):
            winner.score = 0.0
        winner.feedback = parsed.get("feedback", "")

        consensus_reached = (
            bool(parsed.get("consensus_reached")) and winner.score >= _CONSENSUS_SCORE_THRESHOLD
        )
        decision = DebateState.CONSENSUS if consensus_reached else DebateState.RETHINKING

        return {
            "decision": decision,
            "best_proposal": winner,
            "feedback": winner.feedback,
        }


class ConsensusOrchestrator:
    """
    Manages the lifecycle of a multi-agent debate session.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_state = DebateState.PROPOSING
        self.judge = JudgeAgent()
        self.proposals: list[Proposal] = []
        self.iteration = 0
        self.max_iterations = 3

    async def run_debate_cycle(self, task_prompt: str) -> Proposal | None:
        """
        Executes the debate loop: Proposing -> Judging -> (Rethinking) -> Consensus.
        """
        import asyncio

        from core.swarm_pubsub import swarm_streamer

        await swarm_streamer.broadcast(
            "DEBATE_UPDATE",
            {"session_id": self.session_id, "state": self.current_state},
        )

        while self.iteration < self.max_iterations:
            self.iteration += 1
            logger.info(
                f"Debate Cycle {self.iteration}/{self.max_iterations} for session {self.session_id}"
            )

            # 1. Proposing Phase
            self.current_state = DebateState.PROPOSING
            await swarm_streamer.broadcast(
                "DEBATE_UPDATE",
                {
                    "session_id": self.session_id,
                    "state": self.current_state,
                    "iteration": self.iteration,
                },
            )

            async def generate_proposal(agent_id: str, prompt: str) -> Proposal:
                """বাংলা মন্তব্য: এজেন্টের role (agent_id প্রিফিক্স থেকে) অনুযায়ী
                system prompt ও task_type ঠিক করে LLMGateway দিয়ে আসল প্রস্তাবনা তৈরি হয়।
                কল ব্যর্থ হলে proposal-এ error marker বসে যায় — Judge সেটা কম score দিয়ে বাতিল করবে,
                কিন্তু পুরো debate cycle crash করবে না।"""
                from core.llm.llm_gateway import get_llm_gateway

                # বাংলা মন্তব্য: PLC0207 ফিক্স — maxsplit=1 যোগ করা হয়েছে, শুধু প্রথম underscore-এ ভাগ দরকার
                role = agent_id.split("_", maxsplit=1)[0].lower()
                task_type = _AGENT_ROLE_TASK_TYPE.get(role, "general")
                role_instructions = {
                    "architect": "Propose a high-level system design and architecture for the task.",
                    "coder": "Propose a concrete implementation approach, including key code structure.",
                    "qa": "Propose a test and edge-case coverage plan, and flag potential failure modes.",
                }.get(role, "Propose a solution for the task.")

                system_prompt = f"You are '{agent_id}', a specialist agent in a multi-agent debate system. {role_instructions} Be concise and specific."

                try:
                    gateway = get_llm_gateway()
                    response = await gateway.acompletion(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        task_type=task_type,
                    )
                    content = response.get("text", "") if isinstance(response, dict) else ""
                    if not content:
                        raise RuntimeError("Empty response from LLM gateway.")
                    return Proposal(agent_id=agent_id, content=content)
                except Exception as exc:
                    logger.warning(f"Proposer '{agent_id}' failed to generate a proposal: {exc}")
                    return Proposal(
                        agent_id=agent_id,
                        content="[PROPOSAL_GENERATION_FAILED]",
                        score=0.0,
                        feedback=f"Proposer error: {exc}",
                    )

            proposer_tasks = [
                generate_proposal("Architect_1", task_prompt),
                generate_proposal("Coder_1", task_prompt),
                generate_proposal("QA_1", task_prompt),
            ]
            self.proposals = await asyncio.gather(*proposer_tasks)

            # 2. Judging Phase
            self.current_state = DebateState.JUDGING
            await swarm_streamer.broadcast(
                "DEBATE_UPDATE",
                {
                    "session_id": self.session_id,
                    "state": self.current_state,
                    "proposals_count": len(self.proposals),
                },
            )

            judge_result = await self.judge.evaluate_proposals(task_prompt, self.proposals)

            if judge_result["decision"] == DebateState.CONSENSUS:
                self.current_state = DebateState.CONSENSUS
                await swarm_streamer.broadcast(
                    "DEBATE_UPDATE",
                    {
                        "session_id": self.session_id,
                        "state": self.current_state,
                        "winning_agent": judge_result["best_proposal"].agent_id,
                    },
                )
                return judge_result["best_proposal"]
            else:
                self.current_state = DebateState.RETHINKING
                await swarm_streamer.broadcast(
                    "DEBATE_UPDATE",
                    {
                        "session_id": self.session_id,
                        "state": self.current_state,
                        "feedback": judge_result.get("feedback"),
                    },
                )

                # Append feedback to the prompt for the next cycle
                task_prompt = (
                    task_prompt
                    + f"\n\nFeedback from Judge: {judge_result.get('feedback', 'Improve the proposal.')}"
                )

        # 3. Fallback Solution if no consensus
        logger.warning(
            f"Max iterations reached for session {self.session_id}. Returning FALLBACK_SOLUTION."
        )
        return Proposal(
            agent_id="Fallback_Agent",
            content="System fallback executed due to lack of consensus.",
        )
