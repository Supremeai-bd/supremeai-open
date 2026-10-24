import json
import os
import subprocess
import time
from typing import Any

from core.logging_config import logger


class DependencyManagerAgent:
    """
    An agent to automatically manage project dependencies.
    - Scans for outdated packages.
    - Checks for known security vulnerabilities.
    - Can attempt to auto-update packages and create a PR.
    """

    def __init__(self):
        logger.info("Initialized DependencyManagerAgent")
        try:
            from tools.code.auto_pr_pipeline import AutoPRPipeline

            self.pr_pipeline = AutoPRPipeline()
        except ImportError:
            self.pr_pipeline = None

    def _run_command(self, command: list[str], check_exit_code: bool = True) -> dict[str, Any]:
        """Runs a command and returns its JSON output."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=check_exit_code,
            )
            # For commands that return non-zero on success with findings (like npm audit)
            # we might get here with check_exit_code=False. The output could be on stdout or stderr.
            output_to_parse = result.stdout if result.stdout.strip() else result.stderr
            if not output_to_parse.strip():
                return {}  # No output to parse, return empty dict

            return json.loads(output_to_parse)
        except FileNotFoundError:
            logger.error(f"Command not found: {command[0]}. Is it installed?")
            return {"error": f"{command[0]} not found."}
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {e.stderr}")
            return {"error": e.stderr}
        except json.JSONDecodeError:
            logger.error("Failed to parse command output as JSON.")
            return {"error": "Invalid JSON output."}
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return {"error": str(e)}

    def check_npm_dependencies(self, project_path: str) -> dict[str, Any]:
        """
        Checks for outdated npm packages in a project.
        """
        logger.info(f"Checking npm dependencies for {project_path}")
        outdated_command = ["npm", "outdated", "--json", "--prefix", project_path]

        outdated_data = self._run_command(outdated_command)

        if "error" in outdated_data:
            return {"success": False, "error": outdated_data["error"]}

        return {
            "success": True,
            "outdated_packages": outdated_data,
            "count": len(outdated_data),
            "recommendation": "Run 'npm update' or use 'npm-check-updates' to upgrade packages.",
        }

    def check_pip_dependencies(self) -> dict[str, Any]:
        """
        Checks for outdated pip packages in the current environment.
        """
        logger.info("Checking pip dependencies")
        # Using --format json is crucial for parsing
        outdated_command = ["pip", "list", "--outdated", "--format", "json"]

        outdated_data = self._run_command(outdated_command)

        if "error" in outdated_data:
            return {"success": False, "error": outdated_data["error"]}

        return {
            "success": True,
            "outdated_packages": outdated_data,
            "count": len(outdated_data),
            "recommendation": "Run 'pip install --upgrade <package>' for each outdated package.",
        }

    def find_and_remove_unused_pip_dependencies(self, project_path: str) -> dict[str, Any]:
        """
        Finds and removes unused pip dependencies using deptry and poetry.
        Assumes it's run in a poetry environment from the backend directory.
        """
        logger.info(f"Scanning for unused pip dependencies in {project_path} with deptry...")
        # Requires `poetry add deptry --group dev`
        # The command needs to be run from the directory with pyproject.toml
        # deptry returns a non-zero exit code if it finds issues, so check_exit_code=False
        find_command = ["poetry", "run", "deptry", ".", "--output-format", "json"]

        # We need to run this from the backend directory
        original_cwd = os.getcwd()
        try:
            os.chdir(project_path)
            deptry_result = self._run_command(find_command, check_exit_code=False)
        finally:
            os.chdir(original_cwd)

        if "error" in deptry_result:
            return {"success": False, "error": deptry_result["error"]}

        unused_dependencies = [
            dep["name"] for dep in deptry_result if dep["error"]["code"] == "DEP002"
        ]

        if not unused_dependencies:
            return {
                "success": True,
                "removed_packages": [],
                "count": 0,
                "message": "No unused dependencies found.",
            }

        logger.info(
            f"Found {len(unused_dependencies)} unused dependencies: {', '.join(unused_dependencies)}"
        )

        removed_packages = []
        for package in unused_dependencies:
            logger.info(f"Removing unused package '{package}' with poetry...")
            remove_command = ["poetry", "remove", package]
            try:
                os.chdir(project_path)
                remove_result = self._run_command(remove_command)
                if "error" not in remove_result:
                    removed_packages.append(package)
            finally:
                os.chdir(original_cwd)

        return {
            "success": True,
            "removed_packages": removed_packages,
            "count": len(removed_packages),
        }

    def find_and_remove_unused_npm_dependencies(self, project_path: str) -> dict[str, Any]:
        """
        Finds and removes unused npm dependencies using depcheck.
        """
        logger.info(f"Scanning for unused npm dependencies in {project_path} with depcheck...")
        # Requires `npm install -g depcheck` or as a dev dependency
        # depcheck returns non-zero exit code if unused are found.
        find_command = ["depcheck", "--json", project_path]

        depcheck_result = self._run_command(find_command, check_exit_code=False)

        if "error" in depcheck_result:
            # depcheck might return an error in stderr even with valid JSON in stdout
            if "dependencies" not in depcheck_result and "devDependencies" not in depcheck_result:
                return {"success": False, "error": depcheck_result["error"]}

        unused_dependencies = depcheck_result.get("dependencies", [])

        if not unused_dependencies:
            return {
                "success": True,
                "removed_packages": [],
                "count": 0,
                "message": "No unused npm dependencies found.",
            }

        logger.info(
            f"Found {len(unused_dependencies)} unused npm dependencies: {', '.join(unused_dependencies)}"
        )

        removed_packages = []
        for package in unused_dependencies:
            logger.info(f"Removing unused npm package '{package}'...")
            # Use --prefix to run npm in the target project directory
            remove_command = ["npm", "uninstall", package, "--prefix", project_path]
            # We need to run this without os.chdir
            remove_result = self._run_command(remove_command)
            if "error" not in remove_result:
                removed_packages.append(package)

        return {
            "success": True,
            "removed_packages": removed_packages,
            "count": len(removed_packages),
        }

    def check_pip_vulnerabilities(self) -> dict[str, Any]:
        """
        Scans for vulnerabilities in pip packages using pip-audit.
        """
        logger.info("Scanning pip dependencies for vulnerabilities with pip-audit...")
        # Requires `pip install pip-audit`
        vuln_command = ["pip-audit", "--format", "json"]

        # pip-audit exits with 1 if vulnerabilities are found, so we don't check exit code
        vuln_data = self._run_command(vuln_command, check_exit_code=False)

        if "error" in vuln_data:
            return {"success": False, "error": vuln_data["error"]}

        return {
            "success": True,
            "vulnerabilities": vuln_data.get("vulnerabilities", []),
            "count": len(vuln_data.get("vulnerabilities", [])),
        }

    def check_npm_vulnerabilities(self, project_path: str) -> dict[str, Any]:
        """
        Scans for vulnerabilities in npm packages using npm audit.
        """
        logger.info(f"Scanning npm dependencies for vulnerabilities in {project_path}")
        vuln_command = ["npm", "audit", "--json", "--prefix", project_path]

        # npm audit exits with 1 if vulnerabilities are found
        vuln_data = self._run_command(vuln_command, check_exit_code=False)

        if "error" in vuln_data:
            return {"success": False, "error": vuln_data["error"]}

        # The summary is in the 'metadata' or 'summary' field
        return {"success": True, "audit_results": vuln_data}

    async def auto_update_and_pr(
        self, repo_path: str, package_name: str, package_manager: str = "pip"
    ):
        """Automates updating a dependency and creating a PR."""
        if not self.pr_pipeline:
            logger.error("AutoPRPipeline is not available. Cannot create PR.")
            return {"status": "error", "message": "AutoPRPipeline not found."}

        logger.info(
            f"Attempting to auto-update '{package_name}' using {package_manager} in {repo_path}"
        )

        # Define update command
        if package_manager == "pip":
            update_command = ["pip", "install", "--upgrade", package_name]
        elif package_manager == "npm":
            update_command = [
                "npm",
                "install",
                f"{package_name}@latest",
                "--prefix",
                repo_path,
            ]
        else:
            return {
                "status": "error",
                "message": f"Unsupported package manager: {package_manager}",
            }

        # Run the update
        update_result = self._run_command(update_command)
        if "error" in update_result:
            return {
                "status": "error",
                "message": f"Failed to update package: {update_result['error']}",
            }

        # Create a PR with the changes
        branch_name = f"chore/update-{package_name}-{int(time.time())}"
        title = f"chore: Update {package_manager} dependency {package_name}"
        body = f"Automatically updated `{package_name}` to the latest version."

        # This assumes the CI runner has git configured and write access to the repo
        return await self.pr_pipeline.execute_pipeline(
            repo_path=repo_path,
            branch_name=branch_name,
            commit_message=title,
            pr_title=title,
            pr_body=body,
            target_repo="your-org/your-repo-name",  # Replace with your repo name
        )
