import argparse
import ast
import concurrent.futures
import hashlib
import json
import logging
import os
import sys
import threading
from pathlib import Path

import litellm

# --- Merged from ai_scribe_historian.py ---

# SupremeAI - AI Scribe Agent (The Codebase Historian)
# Purpose: To automatically scan the codebase, generate docstrings for Python files,
# and create README.md files for directories.
# Author: Gemini Code Assist
# Date: July 12, 2026



# বাংলা মন্তব্য: প্রজেক্ট রুট থেকে সঠিক সিস্টেম পাথ রেজোলিউশন করা হচ্ছে যাতে CI-তে ModuleNotFoundError না হয়।
# লগে দেখা গিয়েছিল: scripts/devops/ai_scribe_historian.py:28 → ModuleNotFoundError: No module named 'knowledge_indexer'
_project_root = Path(__file__).resolve().parent.parent.parent  # scripts/devops/../../.. = project root

try:
    sys.path.insert(0, str(_project_root / "backend"))
    from core.config import settings
except ImportError:
    settings = None

# বাংলা মন্তব্য: যদি settings ইম্পোর্ট করা না যায় বা None হয়, তবে সরাসরি env vars থেকে fallback করা হবে।
if settings is None:
    class FallbackSettings:
        @property
        def gemini_api_key(self) -> str:
            # বাংলা মন্তব্য: সরাসরি পরিবেশ ভেরিয়েবল থেকে Gemini API কী পড়া হচ্ছে।
            return os.environ.get("GEMINI_API_KEY", "")

        @property
        def gemini_model_name(self) -> str:
            # বাংলা মন্তব্য: সরাসরি পরিবেশ ভেরিয়েবল থেকে Gemini মডেলের নাম পড়া হচ্ছে, না থাকলে ডিফল্ট মডেল ব্যবহার হবে।
            return os.environ.get("GEMINI_MODEL_NAME", "gemini/gemini-2.0-flash")
    settings = FallbackSettings()  # type: ignore[assignment]

try:
    sys.path.insert(0, str(_project_root / "scripts"))
    sys.path.insert(0, str(_project_root))
    from knowledge_indexer import run_indexing as run_knowledge_indexing
except ImportError:
    # বাংলা মন্তব্য: knowledge_indexer বা chromadb লাইব্রেরি না থাকলে ইনডেক্সিং এড়ানো হবে।
    def run_knowledge_indexing(*_args, **_kwargs):  # type: ignore[misc]
        pass


# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# বাংলা মন্তব্য: এখানে আমরা litellm ব্যবহার করছি যাতে ভবিষ্যতে সহজেই মডেল পরিবর্তন করা যায় (Gemini, GPT, Claude ইত্যাদি)।
litellm.set_verbose=False
CACHE_FILE = Path(__file__).parent / ".scribe_cache.json"
litellm.max_retries = 3

# বাংলা মন্তব্য: অনির্দিষ্ট Exceptions-এ রিট্রাই বন্ধ করা হলো এবং litellm এর ডিফল্ট হ্যান্ডলিং বা নির্দিষ্ট ক্লাস ব্যবহার করা হচ্ছে।
try:
    import litellm.exceptions
    litellm.retry_strategy = {
        "wait_time": 16,
        "allowed_exceptions": [
            litellm.exceptions.RateLimitError,
            litellm.exceptions.Timeout,
            litellm.exceptions.APIConnectionError,
            litellm.exceptions.InternalServerError
        ]
    }
except Exception as e:
    import logging
    logging.getLogger(__name__).exception(f"Silenced error: {e}")



TARGET_DIRECTORIES = ["backend/core", "backend/tools"]
FILE_PATTERN = "*.py"
EXCLUDE_FILES = ["__init__.py"]

# --- AI Prompts ---

DOCSTRING_PROMPT_TEMPLATE = """
You are an expert Python programmer, the "Codebase Historian" for the SupremeAI project.
Your task is to generate a comprehensive and structured PEP 257 compliant module-level docstring for the given Python code.

**Analysis Context:**
- The file path is `{file_path}`.
- The project is a highly scalable AI ecosystem with a FastAPI backend and multiple agentic tools.

**Instructions:**
1.  **Analyze:** Deeply analyze the entire code provided below.
2.  **Summarize:** Write a concise one-paragraph summary of the module's primary purpose and its role within the SupremeAI project.
3.  **Structure:** After the summary, create the following sections:
    - `Key Components`: List the main classes and functions (e.g., `MyClass`, `my_function`) and provide a one-sentence description for each.
    - `Dependencies`: List key internal (e.g., `core.utils`) and external (e.g., `litellm`, `fastapi`) libraries this module depends on.
4.  **Format:** The entire output must be a single, valid Python docstring enclosed in triple quotes (`\"\"\"...\"\"\"`). Do not add any other text, code, or explanations outside the docstring.
5.  **Clarity:** The docstring should be clear and helpful for new developers to quickly grasp the module's functionality and context.

**Example Output Structure:**
```python
\"\"\"
<One-paragraph summary of the module's purpose and role.>

Key Components:
- `ClassName`: Brief description of the class.
- `function_name()`: Brief description of the function.

Dependencies:
- `core.config`: For accessing application settings.
- `external_library`: For providing specific functionality.
\"\"\"
```

**Code to Analyze:**
```python
{file_content}
```
"""

README_PROMPT_TEMPLATE = """
You are the "AI Scribe" and technical writer for the SupremeAI project. Your goal is to create a beautiful, informative, and developer-friendly `README.md` file.

**Analysis Context:**
- You are generating a README.md for the directory: `{dir_path}`.
- This directory contains the following modules, each with a summary of its purpose and key components:

---
{file_summaries}
---

**Instructions:**
1.  **Main Heading:** Start with a main heading (`#`) using the directory name (e.g., `# core/cache`).
2.  **Overview:** Write a high-level overview of the directory's purpose. Explain its role within the SupremeAI architecture and how its modules collaborate.
3.  **Modules Table:** Create a Markdown table with two columns: "Module" and "Description".
    - In the "Module" column, list each file name (e.g., `autocache_proxy.py`).
    - In the "Description" column, provide a concise, one-sentence summary for that module based on the provided summaries.
4.  **Interaction Flow (Mermaid Diagram):** Create a simple Mermaid.js `graph TD` diagram to visualize the interaction between the modules in this directory. If there's only one file, show its main purpose. This is crucial for developer understanding.
    - Example: `A[module_a] --> B[module_b]`
5.  **Detailed Summaries:** Under a "Module Details" section (`##`), list each file again with its full summary (the content from `{file_summaries}`).
6.  **Final Output:** The final output should be clean, well-formatted Markdown. Return ONLY the Markdown content.

**Example Structure:**
# Directory Name

<High-level overview...>

## Modules Overview
| Module | Description |
|---|---|
| `file_one.py` | Brief one-sentence summary. |

## Interaction Flow
```mermaid
graph TD;
    A --> B;
```

## Module Details
### `file_one.py`
<Full summary from file_summaries...>
"""

# বাংলা মন্তব্য: সব রিট্রাই শেষে LLM কল পুরোপুরি ব্যর্থ হলে সাইলেন্ট ফেইলর এড়াতে এই এরর ব্যবহার করা হবে।
class LLMCallError(Exception):
    """সব রিট্রাই শেষে LLM কল ব্যর্থ হলে এই এরর রেইজ হবে।"""

key_index = 0
api_key_lock = threading.Lock()

def get_ai_response(prompt: str, max_retries_per_key: int = 3, retry_backoff_seconds: float = 2.0) -> str:
    """
    বাংলা মন্তব্য: প্রম্পট পাঠায় এবং LLM-এর উত্তর রিটার্ন করে। ব্যর্থ হলে LLMCallError রেইজ করে।
    """
    global key_index
    api_keys_str = settings.gemini_api_key
    if not api_keys_str:
        raise LLMCallError("settings.gemini_api_key কনফিগার করা নেই।")

    keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    if not keys:
        raise LLMCallError("কোনো বৈধ Gemini API key পাওয়া যায়নি।")

    max_retries = max_retries_per_key * len(keys)
    last_error: Exception | None = None

    for attempt in range(max_retries):
        current_key = keys[key_index % len(keys)]
        try:
            response = litellm.completion(
                model=settings.gemini_model_name,  # বাংলা মন্তব্য: হার্ডকোড না করে সেটিংস থেকে আনা হচ্ছে।
                messages=[{"content": prompt, "role": "user"}],
                temperature=0.1,
                api_key=current_key
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            error_msg = str(e)
            # বাংলা মন্তব্য: শুধুমাত্র transient/rate limit এবং key block এররের জন্য কী রোটেট বা রিট্রাই করা হবে। অথরাইজেশন এরর (403, PERMISSION_DENIED) সরাসরি রেইজ করা হবে।
            recoverable = any(code in error_msg for code in ("429", "RESOURCE_EXHAUSTED", "RateLimit", "500", "502", "503", "504", "Timeout", "API_KEY_SERVICE_BLOCKED"))
            if not recoverable:
                # বাংলা মন্তব্য: অপ্রত্যাশিত বা স্থায়ী এরর সাথে সাথে থ্রো করা হচ্ছে।
                raise


            logging.warning(f"Key ending in ...{current_key[-4:]} failed (attempt {attempt+1}/{max_retries}), rotating key...")
            with api_key_lock:
                key_index += 1
            # বাংলা মন্তব্য: rate limit এবং temporary ব্লকের ক্ষেত্রে exponential backoff দিয়ে sleep করা হচ্ছে।
            import time
            time.sleep(retry_backoff_seconds * (2 ** (attempt // len(keys))))

    raise LLMCallError(f"সব API key দিয়ে চেষ্টার পরও ব্যর্থ: {last_error}")

def get_existing_docstring(content: str) -> str | None:
    """Safely extracts the module-level docstring using AST."""
    try:
        tree = ast.parse(content)
        return ast.get_docstring(tree)
    except SyntaxError:
        return None

def load_cache() -> dict:
    """Loads the cache file from disk."""
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}

def save_cache(cache: dict):
    """Saves the cache to disk."""
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

def get_file_hash(content: str) -> str:
    """Generates a SHA-256 hash of the file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def update_file_with_docstring(file_path: Path, content: str, new_docstring: str) -> bool:
    """
    Updates a Python file with a new module-level docstring using AST.
    This is safer than string replacement.
    """
    try:
        tree = ast.parse(content)

        # Create a new docstring node
        new_docstring_node = ast.Expr(value=ast.Constant(value=new_docstring.strip()))

        # Check if a docstring already exists
        existing_docstring = ast.get_docstring(tree)

        if existing_docstring:
            # Replace the existing docstring node
            tree.body.pop(0)
            tree.body.insert(0, new_docstring_node)
        else:
            # Insert the new docstring at the top
            tree.body.insert(0, new_docstring_node)

        # Add a newline after the docstring if it's not the only thing in the file
        if len(tree.body) > 1:
            tree.body[1].lineno = new_docstring_node.lineno + new_docstring.strip().count('\n') + 3

        # Unparse the AST back to code (requires Python 3.9+)
        new_content = ast.unparse(tree)
        file_path.write_text(new_content, encoding="utf-8")
        return True
    except (SyntaxError, AttributeError, TypeError) as e:
        logging.error(f"Failed to update file {file_path} using AST: {e}. Falling back to simple prepend.")
        # Fallback for safety, though less ideal
        final_content = f'"""{new_docstring.strip()}"""\n\n{content}'
        file_path.write_text(final_content, encoding="utf-8")
        return True
    except Exception as e:
        logging.error(f"An unexpected error occurred during file update for {file_path}: {e}")
        return False

def generate_docstring_for_file(file_path: Path, cache: dict, force: bool = False) -> str | None:
    """
    Generates a module-level docstring for a given Python file.
    Returns the docstring content if generated/updated, otherwise None.
    """
    logging.info(f"Analyzing file for docstring: {file_path}")
    content = file_path.read_text(encoding="utf-8")
    content_hash = get_file_hash(content)
    existing_docstring = get_existing_docstring(content)

    # Cache check: যদি হ্যাশ একই থাকে এবং force=False না হয়, তবে ক্যাশ থেকে ডকস্ট্রিং ব্যবহার করা হবে
    if not force and file_path.name in cache and cache[file_path.name]["hash"] == content_hash:
        logging.info(f"Skipping {file_path}, content unchanged (from cache).")
        return cache[file_path.name]["docstring"]

    prompt = DOCSTRING_PROMPT_TEMPLATE.format(file_path=file_path, file_content=content)
    docstring = get_ai_response(prompt)

    if docstring:
        clean_docstring = docstring.replace("```python", "").replace("```", "").replace('"""', '').strip()
        if update_file_with_docstring(file_path, content, clean_docstring):
            logging.info(f"✅ Docstring {'updated' if existing_docstring else 'added'} for {file_path}")
            # Update cache
            cache[file_path.name] = {"hash": content_hash, "docstring": clean_docstring}
            return clean_docstring
    logging.warning(f"Could not generate docstring for {file_path}")
    return None

def generate_readme_for_dir(dir_path: Path, summaries: dict):
    """
    Generates a README.md file for a directory using summaries of its files.
    """
    logging.info(f"Generating README for directory: {dir_path}")

    summary_text = "\n".join([f"### {fname}\n{summary}\n" for fname, summary in summaries.items()])

    prompt = README_PROMPT_TEMPLATE.format(dir_path=dir_path, file_summaries=summary_text)
    readme_content = get_ai_response(prompt)

    if readme_content:
        readme_path = dir_path / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        logging.info(f"✅ README.md generated for {dir_path}")
    else:
        logging.warning(f"Could not generate README for {dir_path}")

def process_file(file_path: Path, cache: dict, force: bool, dry_run: bool) -> tuple[str, str | None]:
    """Helper function to process a single file, for concurrency."""
    if dry_run:
        logging.info(f"[DRY-RUN] Would analyze {file_path}")
        return file_path.name, f"This is a placeholder summary for {file_path.name}."

    summary = generate_docstring_for_file(file_path, cache, force)
    return file_path.name, summary

def main(dry_run: bool = False, force: bool = False, workers: int = 4, files: list[str] | None = None):
    """
    Main function to orchestrate the documentation generation process.
    """
    if not settings.gemini_api_key:
        logging.error("FATAL: GEMINI_API_KEY is not set in backend settings.")
        sys.exit(1)

    if dry_run:
        logging.warning("Running in DRY-RUN mode. No files will be modified.")
    if force:
        logging.warning("Running in FORCE mode. All docstrings will be regenerated.")

    cache = load_cache()

    if files:
        # --- Git Hook Mode: Process specific files ---
        logging.info(f"AI Scribe (Git Hook Mode): Processing {len(files)} changed files...")
        file_paths = [Path(f) for f in files if Path(f).exists() and Path(f).name not in EXCLUDE_FILES]

        if not file_paths:
            logging.info("No relevant Python files to process.")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_file = {executor.submit(process_file, fp, cache, force, dry_run): fp for fp in file_paths}
            for future in concurrent.futures.as_completed(future_to_file):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Error processing file in git-hook mode: {e}")

        if not dry_run:
            save_cache(cache)
        logging.info("Git hook processing complete. ✨")
        return

    # --- Full Scan Mode: Process directories ---
    logging.info("Starting AI Scribe (Full Scan Mode): The Codebase Historian...")
    logging.info(f"Using {workers} workers for concurrent processing.")

    for target_dir in TARGET_DIRECTORIES:
        base_path = Path(target_dir)
        if not base_path.exists():
            logging.warning(f"Directory not found: {base_path}. Skipping.")
            continue

        # প্রতিটি সাব-ডিরেক্টরির জন্য আলাদাভাবে কাজ করা হবে
        # We walk the directory tree to process parent directories before children.
        for dir_path, _, _ in os.walk(base_path):
            dir_path = Path(dir_path)
            py_files = list(dir_path.glob(FILE_PATTERN))
            # Filter out files in subdirectories, only process files in the current dir_path
            py_files = [f for f in py_files if f.parent == dir_path and f.name not in EXCLUDE_FILES]

            if not py_files: # যদি কোনো পাইথন ফাইল না থাকে
                continue

            file_summaries = {}
            logging.info(f"\n--- Processing Directory: {dir_path} ---")

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                # Submit all file processing tasks to the executor
                future_to_file = {executor.submit(process_file, fp, cache, force, dry_run): fp for fp in py_files}
                for future in concurrent.futures.as_completed(future_to_file):
                    fname, summary = future.result()
                    if summary:
                        file_summaries[fname] = summary

            if file_summaries and not dry_run:
                generate_readme_for_dir(dir_path, file_summaries)
            elif file_summaries and dry_run:
                logging.info(f"[DRY-RUN] Would generate README.md for {dir_path}")

    if not dry_run:
        save_cache(cache)

    # ধাপ ৩: ডকুমেন্টেশন আপডেট হওয়ার পর নলেজ বেস রি-ইনডেক্স করা
    if not dry_run:
        logging.info("\n--- Triggering Knowledge Base Re-indexing ---")
        run_knowledge_indexing(TARGET_DIRECTORIES)

    logging.info("\nHistorian's work complete. The past is now documented. ✨")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Scribe: Codebase Historian - Auto-Doc Generator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the script without modifying any files."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration of all docstrings, ignoring the cache."
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of concurrent workers to use for processing files."
    )
    parser.add_argument(
        "--files",
        nargs='*',
        help="Run the script on a specific list of files (used by pre-commit hook)."
    )
    args = parser.parse_args()
    main(args.dry_run, args.force, args.workers, args.files)

# --- কিভাবে ব্যবহার করবেন? ---
#
# ১. API কী সেট করুন:
#    এই স্ক্রিপ্টটি চালানোর জন্য আপনার GEMINI_API_KEY এনভায়রনমেন্ট ভেরিয়েবল সেট করা থাকতে হবে।
#    ```bash
#    export GEMINI_API_KEY="your_gemini_api_key_here"
#    ```
#
# ২. স্ক্রিপ্ট চালান:
#    টার্মিনাল থেকে নিচের কমান্ডটি রান করুন।
#    ```bash
#    python scripts/ai_scribe_historian.py
#    ```
#
# ৩. ড্রাই রান (Dry Run):
#    আপনি যদি ফাইল পরিবর্তন না করে শুধু দেখতে চান কোন কোন ফাইল এবং ফোল্ডার প্রভাবিত হবে, তাহলে --dry-run ফ্ল্যাগ ব্যবহার করুন।
#    ```bash
#    python scripts/ai_scribe_historian.py --dry-run
#    ```
#
# ৪. ফোর্স রি-জেনারেশন (Force Regeneration):
#    ক্যাশ (cache) উপেক্ষা করে সমস্ত ডকস্ট্রিং পুনরায় তৈরি করতে --force ফ্ল্যাগ ব্যবহার করুন।
#    ```bash
#    python scripts/ai_scribe_historian.py --force
#    ```
#
# ৫. কনকারেন্সি লেভেল সেট করা (Set Concurrency Level):
#    একসাথে কতগুলো ফাইল প্রসেস হবে তা নির্ধারণ করতে --workers ফ্ল্যাগ ব্যবহার করুন।
#    ```bash
#    python scripts/ai_scribe_historian.py --workers 8
#    ```
#
# ৬. গিট হুক (Git Hook):
#    `pre-commit` ইনস্টল করা থাকলে, `git commit` করার সময় পরিবর্তিত ফাইলগুলির জন্য এই স্ক্রিপ্টটি স্বয়ংক্রিয়ভাবে চলবে।
#    ```bash
#    git commit -m "feat: new feature"
#    ```


# --- Merged from ask_scribe.py ---

#!/usr/bin/env python3
"""
SupremeAI - Ask the Scribe
==========================

A conversational interface to query the project's knowledge base.
It uses a Retrieval-Augmented Generation (RAG) approach to answer questions
about the codebase using the documentation indexed in ChromaDB.

Author: Gemini Code Assist
Date: July 12, 2026
"""

import argparse
import asyncio
import sys
from pathlib import Path

import chromadb
import litellm
from chromadb.utils import embedding_functions

# বাংলা মন্তব্য: ক্লিন ইমপোর্ট স্ট্রাকচার যাতে sys.path.insert হ্যাক এড়ানো যায়।
try:
    from backend.core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
    from core.config import settings

# --- Configuration ---
# বাংলা মন্তব্য: হার্ডকোডেড পাথের বদলে সেটিংসের chromadb_path ব্যবহার করা হলো।
DB_PATH = settings.chromadb_path
COLLECTION_NAME = "codebase_docs"


# --- AI Prompt Template (RAG) ---
RAG_PROMPT_TEMPLATE = """
You are a helpful AI assistant for the SupremeAI project, acting as an expert guide to the codebase.
Your task is to answer the user's question based *only* on the context provided below.
The context is extracted from the project's own documentation.

If the context does not contain the information needed to answer the question, state clearly:
"I'm sorry, I don't have information about that in my knowledge base."

Do not make up answers or use external knowledge.

--- CONTEXT FROM CODEBASE ---
{context}
---

QUESTION: {question}

ANSWER:
"""


async def answer_question(question: str) -> str:
    """
    Answers a question about the codebase using RAG.
    This is the core async logic callable from an API.
    """
    # বাংলা মন্তব্য: settings থেকে Gemini API কী নেওয়া হচ্ছে।
    api_key_str = settings.gemini_api_key
    if not api_key_str:
        return "I'm sorry, I don't have GEMINI_API_KEY configured in settings."

    litellm.api_key = api_key_str.split(",")[0].strip()

    try:
        sentence_transformer_ef = (
            embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        )
        client = chromadb.PersistentClient(path=DB_PATH)
        collection = client.get_collection(
            name=COLLECTION_NAME, embedding_function=sentence_transformer_ef
        )
    except Exception as e:
        return f"Error: ChromaDB কালেকশন বা ক্লায়েন্ট লোড করতে ব্যর্থ হয়েছে — {e}"

    # ১. প্রাসঙ্গিক তথ্যের জন্য ChromaDB কোয়েরি করা
    try:
        results = collection.query(query_texts=[question], n_results=7)
        if not results or not results.get("documents") or not results["documents"][0]:
            return "I'm sorry, no relevant context was found in the knowledge base."
        context = "\n\n---\n\n".join(results["documents"][0])
    except Exception as e:
        return f"Error: ChromaDB কোয়েরি করার সময় এরর ঘটেছে — {e}"

    # ২. কনটেক্সট ব্যবহার করে LLM-কে উত্তর তৈরি করতে বলা
    try:
        prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)
        # বাংলা মন্তব্য: হার্ডকোডেড মডেল নামের বদলে সেটিংসের সেন্ট্রালাইজড মডেল নাম ব্যবহার করা হচ্ছে।
        model_name = settings.gemini_model_name
        response = await litellm.acompletion(
            model=model_name, messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
        return answer
    except Exception as e:
        return f"Error: LLM উত্তর তৈরি করতে ব্যর্থ হয়েছে — {e}"


async def main(question: str):
    """Answers a question about the codebase using the indexed knowledge."""
    answer = await answer_question(question)
    print("\n🤖 AI Scribe's Answer:\n")
    print(answer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ask the AI Scribe about the SupremeAI codebase."
    )
    parser.add_argument("question", type=str, help="Your question about the codebase.")
    args = parser.parse_args()
    asyncio.run(main(args.question))
