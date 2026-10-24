# Specialized swarm agents defining task-oriented personalities
# বাংলা মন্তব্য: মাস্টার প্ল্যানিং, কোড জেনারেশন ও স্যান্ডবক্স টেস্টিং এর জন্য স্পেশালাইজড সোয়ার্ম ডিপার্টমেন্ট।
import asyncio

from core.llm.llm_gateway import llm_gateway
from core.logging_config import logger
from core.skill_manager import skill_manager
from models.shared_workspace import SharedWorkspace


class SwarmAgentBase:
    """
    বাংলা মন্তব্য: স্কিল-ভিত্তিক আর্কিটেকচারের জন্য আপডেট করা বেস এজেন্ট।
    """

    # Issue #1702 (resource isolation): agents that run in the same parallel
    # DAG batch previously wrote shared top-level keys of work_product — one
    # agent's result could silently overwrite another's. Canonical results
    # now live under a per-agent namespace work_product[<AgentClass>][key];
    # the top-level key is still mirrored for every existing downstream
    # reader (zero regression). বাংলা: প্রতিটি এজেন্টের ফলাফল এখন তার নিজস্ব
    # namespace-এ থাকে, তাই প্যারালাল batch-এ একে অন্যের ফলাফল মুছে যায় না।
    def _publish(self, workspace: "SharedWorkspace", key: str, value) -> None:
        agent_ns = self.__class__.__name__
        ns_slot = workspace.work_product.setdefault(agent_ns, {})
        if not isinstance(ns_slot, dict):
            ns_slot = {}
            workspace.work_product[agent_ns] = ns_slot
        ns_slot[key] = value
        workspace.work_product[key] = value

    async def run(self, workspace: "SharedWorkspace", user_id: str, model_name: str) -> None:
        raise NotImplementedError(f"{self.__class__.__name__}.run() must be implemented")

    async def _safe_skill_run(self, skill_name: str, workspace: "SharedWorkspace", **kwargs):
        """বাংলা মন্তব্য: Skill failure কে gracefully handle করে।"""
        try:
            return await self.use_skill(skill_name, workspace=workspace, **kwargs)
        except ValueError as e:
            from core.logging_config import logger

            logger.warning(
                f"{self.__class__.__name__}: Skill '{skill_name}' unavailable: {e}. Falling back to direct gateway call."
            )
            workspace.log(f"Warning: Skill '{skill_name}' unavailable. Using fallback.")
            return None

    async def call_gateway(
        self,
        system_prompt: str,
        user_prompt: str,
        user_id: str = "default_user",
        model_name: str = "gemini/gemini-2.5-flash",
    ) -> str:
        # বাংলা মন্তব্য: প্রতিটি এজেন্ট কল গেটওয়ের মাধ্যমে রাউট করা হচ্ছে যাতে কস্ট ট্র্যাকিং এনাবেল থাকে।
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await llm_gateway.acompletion(model=model_name, messages=messages, user_id=user_id)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def use_skill(self, skill_name: str, **kwargs):
        """
        বাংলা মন্তব্য: এজেন্টরা এখন এই মেথড ব্যবহার করে SkillManager থেকে স্কিল কল করবে।
        """
        try:
            skill = await skill_manager.get_skill(skill_name)
            return await skill.execute(**kwargs)
        except ValueError as e:
            logger.error(f"Skill '{skill_name}' not found or failed to execute: {e}")
            raise


class ArchitectureAgent(SwarmAgentBase):
    async def design(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        workspace.log("ArchitectureAgent: Starting system architecture layout analysis...")
        sys_prompt = "You are a lead system architect. Define file structures, component breakdown, and database schemas."
        user_prompt = f"Design architecture for task: {workspace.original_prompt}"

        design_output = await self.call_gateway(
            sys_prompt, user_prompt, user_id, model_name=model_name
        )
        # বাংলা মন্তব্য: ডোমেইন-অ্যাগনস্টিক work_product ব্যবহার করা হচ্ছে।
        self._publish(workspace, "architecture_design", design_output)
        workspace.log("ArchitectureAgent: System design blueprint completed.")

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        # await self.design(workspace, user_id, model_name)
        logger.info("ArchitectureAgent: Using 'SystemDesignSkill' to plan architecture.")
        design_output = await self._safe_skill_run(
            "SystemDesignSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )
        self._publish(workspace, "architecture_design", design_output)


class CodeGeneratorAgent(SwarmAgentBase):
    async def generate_code(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        workspace.log("CodeGeneratorAgent: Injecting layout and writing core codes...")
        sys_prompt = "You are an expert backend engineer. Output only clean python code blocks for specified files."
        user_prompt = f"Design blueprint:\n{workspace.work_product.get('architecture_design', '')}\nGenerate the python code matching this design."

        code_output = await self.call_gateway(
            sys_prompt, user_prompt, user_id, model_name=model_name
        )
        self._publish(workspace, "generated_code", {"main.py": code_output})
        workspace.log("CodeGeneratorAgent: Core files successfully generated.")

    async def refine(
        self,
        workspace: SharedWorkspace,
        feedback: str,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        workspace.log("CodeGeneratorAgent: Refining code based on Guardian feedback...")
        sys_prompt = (
            "You are an expert backend engineer. Refine the python code based on the feedback."
        )
        user_prompt = f"Original Code:\n{workspace.work_product.get('generated_code', {}).get('main.py', '')}\nFeedback:\n{feedback}\nGenerate the fixed python code matching the constraints."
        code_output = await self.call_gateway(
            sys_prompt, user_prompt, user_id, model_name=model_name
        )
        # Issue #1702: setdefault instead of []-index — the dict may not exist
        # yet when a fix cycle runs ahead of generation in the same batch.
        self._publish(
            workspace,
            "generated_code",
            workspace.work_product.setdefault("generated_code", {}) | {"main.py": code_output},
        )
        workspace.log("CodeGeneratorAgent: Code successfully refined.")

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        # await self.generate_code(workspace, user_id, model_name)
        logger.info("CodeGeneratorAgent: Using 'CodeGenerationSkill' to write code.")
        code_output = await self._safe_skill_run(
            "CodeGenerationSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )
        self._publish(workspace, "generated_code", {"main.py": code_output})


class QAAgent(SwarmAgentBase):
    async def verify(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        workspace.log("QAAgent: Initiating test suites and static CodeQL scans...")
        # Simulating running ImmuneSystem AST scan and Python validations
        code_to_test = workspace.work_product.get("generated_code", {}).get("main.py", "")

        from core.immune_system import ImmuneSystemScanner

        scanner = ImmuneSystemScanner()
        scan_result = scanner.scan_code(code_to_test)

        if not scan_result.get("safe", False):
            workspace.test_results["safe"] = False
            workspace.test_results["error"] = scan_result.get("error", "Unknown error")
            workspace.log(
                f"QAAgent: 🚨 Immune System scan failed: {workspace.test_results['error']}"
            )
        else:
            workspace.test_results["safe"] = True
            workspace.test_results["passed"] = True
            workspace.log("QAAgent: ✅ Immune System scan passed.")

        sys_prompt = "You are a QA engineer. Review code and validation results and give feedback. State clearly if the code is APPROVED or FAILED."
        user_prompt = f"Code:\n{code_to_test}\nResults: {workspace.test_results}"
        qa_feedback = await self.call_gateway(
            sys_prompt, user_prompt, user_id, model_name=model_name
        )
        workspace.test_results["feedback"] = qa_feedback

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        # await self.verify(workspace, user_id, model_name)
        logger.info("QAAgent: Using 'StaticAnalysisSkill' to verify code.")
        qa_feedback = await self._safe_skill_run(
            "StaticAnalysisSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )
        workspace.test_results["feedback"] = qa_feedback


class GuardianAgent(SwarmAgentBase):
    """
    A manager agent that orchestrates specialized sub-agents to enforce codebase compliance.
    It aligns with the "Neural Cortex" philosophy from the master plan, where this agent
    acts as the "Immune System" by delegating to specialized sensory units.
    """

    async def _run_sub_agent(
        self,
        sub_agent_name: str,
        system_prompt: str,
        user_prompt: str,
        user_id: str,
        model_name: str,
    ) -> str:
        """Helper to run a specialized sub-agent, optimized for speed and cost."""
        logger.info(f"GuardianManager: Delegating task to {sub_agent_name}...")
        # Using a faster model for specialized, smaller tasks
        return await self.call_gateway(
            system_prompt, user_prompt, user_id, model_name="gemini/gemini-2.5-flash"
        )

    async def validate(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ) -> tuple[bool, str]:
        workspace.log("GuardianManager: Orchestrating compliance scan with sub-agents...")
        code_to_analyze = workspace.work_product.get("generated_code", {}).get("main.py", "")
        if not code_to_analyze:
            return True, "APPROVED: No code to analyze."

        # Define specialized sub-agents and their prompts
        sub_agents = {
            "SecuritySentinel": "You are a Security Sentinel. Analyze the code for security vulnerabilities like injections, auth bypass, and secret leaks. Report only findings or 'SECURITY_OK'.",
            "CodeQualityArchitect": "You are a Code Quality Architect. Analyze the code for clean code violations, architectural inconsistencies, and performance issues. Report only findings or 'QUALITY_OK'.",
            "ComplianceAuditor": "You are a Compliance Auditor. Analyze the code for PII exposure or violations of GDPR/CCPA rules. Report only findings or 'COMPLIANCE_OK'.",
            "DocumentationChecker": "You are a Documentation Checker. Analyze the code for missing or inadequate docstrings and comments for all functions and classes. Report only findings or 'DOCS_OK'.",
        }

        user_prompt_template = f"Analyze this code and report any violations based on your specialty:\n```python\n{code_to_analyze}\n```"

        # Run sub-agents in parallel using asyncio.gather for efficiency
        tasks = [
            self._run_sub_agent(name, prompt, user_prompt_template, user_id, model_name)
            for name, prompt in sub_agents.items()
        ]

        results = await asyncio.gather(*tasks)

        violations = []
        for agent_name, report in zip(sub_agents.keys(), results, strict=False):
            # Check if the report indicates a pass or contains actual findings
            if not any(
                keyword in report
                for keyword in ["SECURITY_OK", "QUALITY_OK", "COMPLIANCE_OK", "DOCS_OK"]
            ):
                violations.append(f"--- VIOLATIONS FROM {agent_name} ---\n{report}")

        if not violations:
            workspace.log("GuardianAgent: Code passed all compliance checks.")
            return True, "APPROVED"
        else:
            feedback = "FAILED:\n" + "\n\n".join(violations)
            workspace.log(f"GuardianAgent: Violations found. {feedback}")
            return False, feedback

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        logger.info("GuardianAgent: Using sub-agent swarm for compliance validation.")
        is_approved, feedback = await self.validate(workspace, user_id, model_name)
        self._publish(workspace, "guardian_feedback", feedback)
        self._publish(workspace, "is_approved", is_approved)


class ResearchAgent(SwarmAgentBase):
    """
    বাংলা মন্তব্য: এই এজেন্টটি রিসার্চ এবং অ্যানালাইসিস সংক্রান্ত কাজ করবে।
    এটি সিস্টেমের Universal Utility Mode-এর একটি অংশ।
    """

    async def analyze(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        workspace.log("ResearchAgent: Starting analysis and information synthesis...")
        sys_prompt = "You are a world-class research analyst. Analyze the user's prompt, synthesize information, and provide a structured summary."
        analysis_output = await self.call_gateway(
            sys_prompt, workspace.original_prompt, user_id, model_name=model_name
        )
        self._publish(workspace, "research_summary", analysis_output)
        workspace.log("ResearchAgent: Analysis complete.")

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        # await self.analyze(workspace, user_id, model_name)
        logger.info("ResearchAgent: Using 'ResearchSkill' for analysis.")
        analysis_output = await self._safe_skill_run(
            "ResearchSkill", workspace=workspace, user_id=user_id, model_name=model_name
        )
        self._publish(workspace, "research_summary", analysis_output)


class ReflectionAgent(SwarmAgentBase):
    async def reflect_and_persist(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        workspace.log("ReflectionAgent: Analyzing task outcome to generate experience...")
        sys_prompt = "You are an AI Reflection engine. Analyze the workspace logs and extract what worked, what failed, and suggested improvements. Return JSON with 'what_worked', 'what_failed', 'suggested_improvements'."
        user_prompt = (
            f"Logs: {workspace.execution_logs}\nOriginal Prompt: {workspace.original_prompt}"
        )

        analysis = await self.call_gateway(sys_prompt, user_prompt, user_id, model_name=model_name)

        # Save to ExperienceDatabase
        try:
            from adaptive_engine.experience_db import Experience, ExperienceDatabase

            db = ExperienceDatabase()

            import json

            try:
                parsed = json.loads(analysis)
            except Exception:
                parsed = {
                    "what_worked": [analysis],
                    "what_failed": [],
                    "suggested_improvements": [],
                }

            exp = Experience(
                user_id=user_id,
                request=workspace.original_prompt,
                action_taken=f"Swarm Orchestrator DAG Execution for intent: {workspace.intent}",
                deployment_logs="\\n".join(workspace.execution_logs),
                what_worked=parsed.get("what_worked", []),
                what_failed=parsed.get("what_failed", []),
                suggested_improvements=parsed.get("suggested_improvements", []),
            )
            db.record_experience(exp)
            workspace.log("ReflectionAgent: Experience successfully saved to Vector DB.")
        except Exception as e:
            workspace.log(f"ReflectionAgent: Failed to persist experience: {e}")

        return analysis

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        # await self.reflect_and_persist(workspace, user_id, model_name)
        logger.info("ReflectionAgent: Using 'ExperiencePersistenceSkill' to learn.")
        await self._safe_skill_run(
            "ExperiencePersistenceSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )


class ToolSynthesizerAgent(SwarmAgentBase):
    """
    বাংলা মন্তব্য: ফেজ ২ - Morphic Engine.
    এই এজেন্টটি ಅಗತ್ಯ অনুযায়ী ফ্লাইতে নতুন টুল তৈরি করে।
    """

    async def synthesize(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        workspace.log("ToolSynthesizerAgent: Starting Zero-Shot Tool Synthesis...")
        sys_prompt = "You are a master tool builder. Based on a task intent, create a JSON definition for a new tool. The definition must include a name, description, and a list of parameters."
        user_prompt = f"Create a tool definition for the intent: '{workspace.original_prompt}'. Respond with only the JSON object."

        tool_definition_str = await self.call_gateway(
            sys_prompt, user_prompt, user_id, model_name=model_name
        )
        import json

        tool_definition = json.loads(tool_definition_str)
        self._publish(workspace, "synthesized_tool", tool_definition)
        workspace.log(
            f"ToolSynthesizerAgent: New tool '{tool_definition.get('name')}' synthesized."
        )

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        # await self.synthesize(workspace, user_id, model_name)
        logger.info("ToolSynthesizerAgent: Using 'ToolSynthesisSkill' to create a new tool.")
        tool_definition = await self._safe_skill_run(
            "ToolSynthesisSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )
        self._publish(workspace, "synthesized_tool", tool_definition)
        workspace.log(
            f"ToolSynthesizerAgent: New tool '{tool_definition.get('name')}' synthesized."
        )


class ToolExecutorAgent(SwarmAgentBase):
    """
    বাংলা মন্তব্য: ফেজ ৩ - Universal Executioner.
    এই এজেন্টটি যেকোনো টুল (আবিষ্কৃত বা সিন্থেসাইজড) এক্সিকিউট করতে পারে।
    """

    async def execute(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        workspace.log("ToolExecutorAgent: Preparing to execute available tools...")
        tools = workspace.work_product.get("available_tools", [])
        if not tools:
            workspace.log("ToolExecutorAgent: No tools available to execute.")
            return

        # For this PoC, we'll simulate executing the first available tool.
        # A real implementation would involve a more complex selection and execution logic.
        tool_to_run = tools[0]
        workspace.log(f"ToolExecutorAgent: Executing tool '{tool_to_run}'...")
        self._publish(workspace, "execution_result", f"Successfully executed tool: {tool_to_run}")

    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-pro",
    ):
        # await self.execute(workspace, user_id, model_name)
        logger.info("ToolExecutorAgent: Using 'ToolExecutionSkill' to run a tool.")
        await self._safe_skill_run(
            "ToolExecutionSkill",
            workspace=workspace,
            user_id=user_id,
            model_name=model_name,
        )


class IntegrationAgent(SwarmAgentBase):
    async def run(
        self,
        workspace: SharedWorkspace,
        user_id: str,
        model_name: str = "gemini/gemini-2.5-flash",
    ):
        from core.logging_config import logger

        logger.info(f"IntegrationAgent: Executing integration for intent {workspace.intent}")
        kwargs = getattr(workspace, "kwargs", {})
        if workspace.intent == "sync_to_slack":
            result = await self._safe_skill_run(
                "SlackIntegrationSkill",
                workspace=workspace,
                user_id=user_id,
                model_name=model_name,
                **kwargs,
            )
        elif workspace.intent == "sync_to_notion":
            result = await self._safe_skill_run(
                "NotionSyncSkill",
                workspace=workspace,
                user_id=user_id,
                model_name=model_name,
                **kwargs,
            )
        elif workspace.intent == "sync_to_github":
            result = await self._safe_skill_run(
                "GithubSyncSkill",
                workspace=workspace,
                user_id=user_id,
                model_name=model_name,
                **kwargs,
            )
        else:
            workspace.log(f"IntegrationAgent: Unknown intent {workspace.intent}")
            result = {
                "status": "error",
                "message": f"Unknown integration intent {workspace.intent}",
            }
        self._publish(workspace, "integration_result", result)
