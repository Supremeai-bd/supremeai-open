import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

router = APIRouter(prefix="/style", tags=["style-learner"])


class StyleRequest(BaseModel):
    repo_path: str
    language: str | None = "python"


class StyleLearner:
    def __init__(self):
        self.indexer = None
        self.learned_styles: dict[str, Any] = {}
        # Issue #451: durable mirror — learned styles survive restarts and
        # hydrate back into memory at boot (Supabase remains the slow path).
        from core.state_store import durable_state

        self._state = durable_state("style_profiles")
        logger.info("Initialized StyleLearner")

    def _get_indexer(self):
        if self.indexer is None:
            try:
                from tools.knowledge.repo_deep_indexer import RepoDeepIndexer

                self.indexer = RepoDeepIndexer()
            except ImportError:
                logger.warning("RepoDeepIndexer not available.")
        return self.indexer

    # ------------------------------------------------------------------ #
    # tree-sitter AST-level pattern analysis
    # ------------------------------------------------------------------ #
    @with_error_bus("_analyze_ast_patterns")
    def _analyze_ast_patterns(self, repo_path: str) -> dict[str, Any]:
        """
        tree-sitter দিয়ে AST-level কোড pattern বিশ্লেষণ করে।

        Variable naming convention, function length preference, import ordering style,
        comment style ইত্যাদি শিখা হয়।
        """
        patterns: dict[str, Any] = {
            "naming_convention": "snake_case",
            "class_naming": "PascalCase",
            "function_length_preference": "short",
            "import_ordering": "grouped",
            "comment_style": "docstring",
            "type_hints": "strict",
        }

        try:
            from tree_sitter import Language, Parser

            try:
                PY_LANG = Language("build/my-languages.so", "python")
            except Exception:
                # বাংলা মন্তব্য: prebuilt language না থাকলে AST বিশ্লেষণ বাদ দেওয়া হচ্ছে।
                logger.debug("tree-sitter python grammar not compiled; skipping AST analysis.")
                return patterns

            parser = Parser()
            parser.set_language(PY_LANG)

            snake = 0
            camel = 0
            func_lengths: list[int] = []
            docstring_count = 0
            func_count = 0

            skipped_ast_files: list[str] = []

            for root, _, files in os.walk(repo_path):
                if any(x in root for x in [".venv", "node_modules", "__pycache__", ".git"]):
                    continue
                for file in files:
                    if not file.endswith(".py"):
                        continue
                    path = os.path.join(root, file)
                    try:
                        with open(path, encoding="utf-8") as f:
                            tree = parser.parse(f.read().encode("utf-8"))
                    except Exception as parse_err:
                        skipped_ast_files.append(f"{path} ({parse_err})")
                        continue

                    for node in tree.root_node.children:
                        if node.type == "function_definition":
                            func_count += 1
                            # বাংলা মন্তব্য: ফাংশনের নামের নিচের শিশু (identifier) থেকে naming বোঝা যায়।
                            name_node = node.child_by_field_name("name")
                            if name_node:
                                name = name_node.text.decode("utf-8")
                                if "_" in name:
                                    snake += 1
                                elif name and name[0].islower() and any(c.isupper() for c in name):
                                    camel += 1
                            # ফাংশন লেন্থ (লাইন সংখ্যা)
                            start = node.start_point[0]
                            end = node.end_point[0]
                            func_lengths.append(end - start + 1)
                            # docstring আছে কিনা
                            for child in node.children:
                                if child.type == "block":
                                    for stmt in child.children:
                                        if stmt.type == "expression_statement":
                                            for leaf in stmt.children:
                                                if leaf.type == "string":
                                                    docstring_count += 1
                                                    break

            if snake + camel > 0:
                patterns["naming_convention"] = "snake_case" if snake >= camel else "camelCase"
            if func_lengths:
                avg_len = sum(func_lengths) / len(func_lengths)
                patterns["function_length_preference"] = (
                    "short" if avg_len < 30 else ("medium" if avg_len < 60 else "long")
                )
                patterns["avg_function_lines"] = round(avg_len, 1)
            if func_count > 0:
                patterns["comment_style"] = (
                    "docstring" if docstring_count >= func_count * 0.5 else "inline"
                )
                patterns["docstring_coverage"] = round(docstring_count / func_count, 2)

            if skipped_ast_files:
                logger.warning(
                    f"[StyleLearner] Skipped AST parsing for {len(skipped_ast_files)} files. Samples: {skipped_ast_files[:3]}"
                )

        except ImportError:
            logger.debug("tree-sitter not installed; using heuristic fallback.")
        except Exception as e:
            logger.warning(f"AST pattern analysis failed: {e}")

        return patterns

    @with_error_bus("analyze_codebase")
    async def analyze_codebase(self, repo_path: str) -> dict[str, Any]:
        """রিপোজিটরি বিশ্লেষণ করে স্টাইল প্রোফাইল তৈরি করে (tree-sitter + LLM)।"""
        logger.info(f"Analyzing {repo_path} for style guidelines...")
        ast_patterns = self._analyze_ast_patterns(repo_path)

        code_samples: list[str] = []
        skipped_sample_files: list[str] = []
        for root, _, files in os.walk(repo_path):
            if any(x in root for x in [".venv", "node_modules", "__pycache__", ".git"]):
                continue
            for file in files:
                if file.endswith((".py", ".ts", ".tsx", ".js")):
                    path = os.path.join(root, file)
                    try:
                        with open(path, encoding="utf-8") as f:
                            code_samples.append(f.read()[:1500])
                    except Exception as read_err:
                        skipped_sample_files.append(f"{path} ({read_err})")
                        continue
                if len(code_samples) >= 20:
                    break
            if len(code_samples) >= 20:
                break

        if skipped_sample_files:
            logger.warning(
                f"[StyleLearner] Skipped reading {len(skipped_sample_files)} files for sampling. Samples: {skipped_sample_files[:3]}"
            )

        if code_samples:
            try:
                from brain.model_router import ModelRouter

                router_llm = ModelRouter()
                combined = "\n\n---FILE---\n\n".join(code_samples[:5])
                prompt = (
                    "Analyze the following code samples from a repository and extract strict style guidelines. "
                    "Return a JSON object with keys: python, typescript, general_patterns. "
                    "Do not include any markdown or explanation.\n\n"
                    f"Code:\n{combined[:5000]}"
                )
                result = await router_llm.async_route_and_generate(
                    prompt, task_type="coding", max_cost=0.03
                )
                text = result.get("text", "") if isinstance(result, dict) else ""
                try:
                    cleaned = text.strip()
                    if cleaned.startswith("```"):
                        cleaned = "\n".join(cleaned.splitlines()[1:])
                    if cleaned.endswith("```"):
                        cleaned = "\n".join(cleaned.splitlines()[:-1])
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict):
                        # বাংলা মন্তব্য: AST প্যাটার্নগুলো LLM আউটপুটের সাথে মার্জ করা হচ্ছে।
                        parsed.setdefault("ast_patterns", ast_patterns)
                        self.learned_styles[repo_path] = parsed
                        await self._persist_style(repo_path, parsed)
                        return parsed
                except Exception:
                    logger.warning("Failed to parse style guidelines JSON from LLM.")
            except Exception as e:
                logger.warning(f"LLM style analysis failed: {e}")

        guidelines = self._default_guidelines()
        guidelines["ast_patterns"] = ast_patterns
        self.learned_styles[repo_path] = guidelines
        # Issue #451: default guidelines were previously never persisted at all.
        await self._persist_style(repo_path, guidelines)
        return guidelines

    async def generate_with_style(self, prompt: str, user_id: str) -> dict[str, Any]:
        """ব্যবহারকারীর শেখা স্টাইল ইনজেক্ট করে কোড জেনারেট করে।"""
        style_prompt = self.generate_style_prompt(user_id, "python")
        try:
            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            full_prompt = f"{style_prompt}\n\nTask: {prompt}\nReturn only the code."
            result = await router_llm.async_route_and_generate(
                full_prompt, task_type="coding", max_cost=0.03
            )
            code = result.get("text", "") if isinstance(result, dict) else ""
            return {"status": "success", "code": code.strip(), "style_injected": True}
        except Exception as e:
            logger.warning(f"Styled generation failed: {e}")
            return {"status": "error", "error": str(e)}

    async def sync_team_style(self, repo_path: str, team_id: str) -> dict[str, Any]:
        """টিমের স্টাইল প্রোফাইল সিঙ্ক করে।"""
        profile = await self.analyze_codebase(repo_path)
        profile["team_id"] = team_id
        await self._persist_style(f"team:{team_id}", profile)
        return profile

    async def _persist_style(self, repo_path: str, style: dict[str, Any]) -> None:
        """Persist learned style to Supabase or local fallback."""
        # Issue #451: durable state mirror FIRST (1 Redis op, always fresh for
        # boot hydration), then Supabase (authoritative) / file fallback.
        try:
            import hashlib

            from core.state_store import durable_state as _ds

            await _ds("style_profiles").set_async(
                hashlib.sha1(repo_path.encode()).hexdigest()[:16],
                {"__rp__": repo_path, "style": style},
            )
        except Exception as mirror_err:
            logger.debug(f"[StyleLearner] state-store mirror failed: {mirror_err}")
        try:
            from database.supabase_client import db

            if db.client:
                await (
                    db.client.table("user_preferences")
                    .upsert(
                        {
                            "user_id": f"repo:{repo_path}",
                            "custom_shortcuts": style,
                        }
                    )
                    .execute()
                )
                return
        except Exception as persist_err:
            # বাংলা মন্তব্য: Supabase persist ব্যর্থ হলে warning দেওয়া হচ্ছে যাতে DB সমস্যাটি অগোচরে না থাকে।
            logger.warning(
                f"[StyleLearner] Supabase style persist failed for {repo_path}: {persist_err}. Falling back to local storage."
            )
        # Local fallback
        try:
            os.makedirs("data/styles", exist_ok=True)
            safe_name = repo_path.replace("/", "_").replace("\\", "_")[:50]
            with open(f"data/styles/{safe_name}.json", "w") as f:
                json.dump(style, f, indent=2)
        except Exception as e:
            logger.debug(f"Style persist fallback failed: {e}")

    def hydrate(self) -> None:
        """Issue #451: reload learned styles from the durable state mirror."""
        try:
            for data in self._state.mirror_items().values():
                repo_path = data.get("__rp__")
                style = data.get("style")
                if repo_path and isinstance(style, dict):
                    self.learned_styles.setdefault(repo_path, style)
        except Exception as hydrate_err:
            logger.warning(f"[StyleLearner] hydrate failed: {hydrate_err}")

    def _default_guidelines(self) -> dict[str, Any]:
        return {
            "python": {
                "naming_convention": "snake_case",
                "class_naming": "PascalCase",
                "type_hints": "strict",
                "docstrings": "google_style",
            },
            "typescript": {
                "interfaces": "prefix_with_I",
                "quotes": "single",
                "semicolons": "always",
            },
            "general_patterns": [
                "Early returns preferred",
                "Dependency injection used for external services",
                "Loguru used for logging",
            ],
        }

    def generate_style_prompt(self, repo_path: str, language: str) -> str:
        if repo_path not in self.learned_styles:
            return "Follow standard industry best practices for the language."
        styles = self.learned_styles[repo_path]
        lang_style = styles.get(language.lower(), {})
        general = styles.get("general_patterns", [])

        prompt = "CRITICAL STYLE GUIDELINES:\n"
        for key, value in lang_style.items():
            prompt += f"- {key.replace('_', ' ').capitalize()}: {value}\n"
        if general:
            prompt += "\nGeneral Patterns:\n"
            for pattern in general:
                prompt += f"- {pattern}\n"
        return prompt


_learner = StyleLearner()


@router.post("/learn")
async def learn_style(request: StyleRequest):
    """Extract and persist coding style from a repository path."""
    if not os.path.isdir(request.repo_path):
        raise HTTPException(status_code=400, detail=f"Path not found: {request.repo_path}")
    guidelines = await _learner.analyze_codebase(request.repo_path)
    return {"status": "success", "guidelines": guidelines}


@router.post("/generate")
async def generate_styled(request: StyleRequest):
    """Generate code following the learned style for a repo/user."""
    if not os.path.isdir(request.repo_path):
        raise HTTPException(status_code=400, detail=f"Path not found: {request.repo_path}")
    result = await _learner.generate_with_style(request.repo_path, request.repo_path)
    return result


@router.get("/prompt")
async def get_style_prompt(repo_path: str, language: str = "python"):
    """Get a style-injection prompt for the given repo and language."""
    prompt = _learner.generate_style_prompt(repo_path, language)
    return {"status": "success", "prompt": prompt}
