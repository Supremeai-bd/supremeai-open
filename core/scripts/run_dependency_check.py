import asyncio
import json
import os
import sys

from core.logging_config import logger

# Ensure the backend tools can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.code.dependency_manager_agent import DependencyManagerAgent


async def main():
    """
    Main function to run dependency checks and potentially create PRs.
    """
    logger.info("Starting automated dependency analysis...")
    agent = DependencyManagerAgent()

    # --- Python (pip) dependencies ---
    pip_results = agent.check_pip_dependencies()
    if pip_results.get("success") and pip_results.get("count", 0) > 0:
        logger.info(f"Found {pip_results['count']} outdated pip packages.")
        logger.debug("--- Outdated Pip Packages ---")
        logger.debug(json.dumps(pip_results["outdated_packages"], indent=2))
        # Here you could add logic to automatically update a specific package
        # For example, to update the first outdated package:
        # outdated_pkg = pip_results['outdated_packages'][0]
        # await agent.auto_update_and_pr(".", outdated_pkg['name'])
    else:
        logger.info("No outdated pip packages found.")

    pip_vuln_results = agent.check_pip_vulnerabilities()
    if pip_vuln_results.get("success") and pip_vuln_results.get("count", 0) > 0:
        logger.warning(f"Found {pip_vuln_results['count']} vulnerabilities in pip packages.")
        logger.debug("--- Pip Package Vulnerabilities (pip-audit) ---")
        logger.debug(json.dumps(pip_vuln_results["vulnerabilities"], indent=2))
    else:
        logger.info("No vulnerabilities found in pip packages.")

    # --- Node.js (npm) dependencies ---
    # Assuming your frontend is in a directory like 'frontend'
    frontend_path = "./apps/studio-client"  # Adjust if necessary
    if os.path.exists(os.path.join(frontend_path, "package.json")):
        npm_results = agent.check_npm_dependencies(project_path=frontend_path)
        if npm_results.get("success") and npm_results.get("count", 0) > 0:
            logger.info(f"Found {npm_results['count']} outdated npm packages.")
            logger.debug("--- Outdated NPM Packages ---")
            logger.debug(json.dumps(npm_results["outdated_packages"], indent=2))
        else:
            logger.info("No outdated npm packages found.")

        npm_vuln_results = agent.check_npm_vulnerabilities(project_path=frontend_path)
        if npm_vuln_results.get("success") and npm_vuln_results.get("audit_results"):
            summary = (
                npm_vuln_results["audit_results"].get("metadata", {}).get("vulnerabilities", {})
            )
            logger.warning(f"NPM audit found vulnerabilities: {summary}")
            logger.debug("--- NPM Package Vulnerabilities (npm audit) ---")
            logger.debug(json.dumps(npm_vuln_results["audit_results"], indent=2))

    logger.info("Dependency analysis complete.")


if __name__ == "__main__":
    asyncio.run(main())
