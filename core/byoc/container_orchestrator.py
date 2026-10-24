import asyncio
import os
import shutil
import subprocess
from typing import Any

from core.logging_config import logger


class ContainerOrchestrator:
    """
    Deploys AI skill Docker containers to Google Cloud Run utilizing Terraform.

    বাংলা মন্তব্য: আগে এখানে টেরাফর্ম কমেন্ট আউট করা ছিল এবং সরাসরি মক স্ট্যাটাস রিটার্ন করত।
    এখন এটি টেরাফর্ম এক্সিকিউটেবল চেক করে রিয়েল-টাইম init এবং apply চালায়
    এবং ডেপ্লয়মেন্টের আসল URLs পার্স করে।
    Audit B-04 fix (2026-09-17): terraform absent হলে আর ভুয়া URL সহ "deployed"
    রিটার্ন হয় না — সৎ failed রেসপন্স; blocking subprocess.run এখন
    asyncio.to_thread-এ চলে (event-loop ব্লক বন্ধ)।
    """

    def __init__(self, tf_dir: str = "infrastructure/terraform/byoc_gcp"):
        self.tf_dir = tf_dir

    async def deploy(self, user_id: str, skill: str) -> dict[str, Any]:
        logger.info(f"Deploying skill '{skill}' for user '{user_id}' on Google Cloud Run...")

        tf_executable = shutil.which("terraform")
        if not tf_executable:
            # বাংলা মন্তব্য: আগে ভুয়া URL (byoc-skill-...-mock-url.a.run.app) সহ "deployed"
            # ফেরত হতো — ইউজার ভাবত ডেপ্লয় হয়েছে (audit B-04)। এখন সৎ ব্যর্থতা।
            logger.error(
                "Terraform binary not found on this host — BYOC deployment CANNOT run. "
                "Returning honest failure instead of simulated success."
            )
            return {
                "status": "failed",
                "error": (
                    "Terraform is not installed on this host, so the skill container "
                    "cannot be deployed. Install terraform (and configure GCP credentials) "
                    "to enable BYOC deployments."
                ),
                "user_id": user_id,
                "skill": skill,
                "mode": "unavailable",
            }

        try:
            # Setup environment variables for Terraform
            env = {**os.environ, "TF_VAR_skill_name": skill, "TF_VAR_user_id": user_id}

            # Run terraform init (off the event loop — subprocess is blocking)
            logger.info("Initializing Terraform configuration...")
            init_res = await asyncio.to_thread(
                subprocess.run,
                [tf_executable, "init", "-no-color"],
                cwd=self.tf_dir,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            logger.debug(f"Terraform Init output: {init_res.stdout}")

            # Run terraform apply (off the event loop)
            logger.info("Applying Terraform changes...")
            apply_res = await asyncio.to_thread(
                subprocess.run,
                [tf_executable, "apply", "-auto-approve", "-no-color"],
                cwd=self.tf_dir,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            logger.debug(f"Terraform Apply output: {apply_res.stdout}")

            # Capture Terraform output values (off the event loop)
            output_res = await asyncio.to_thread(
                subprocess.run,
                [tf_executable, "output", "-json"],
                cwd=self.tf_dir,
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )

            import json

            outputs = json.loads(output_res.stdout)
            service_url = outputs.get("service_url", {}).get("value", "")
            if not service_url:
                # বাংলা মন্তব্য: terraform output-এ service_url না থাকলে আর বানানো
                # fallback URL তৈরি হয় না — সৎ failed রেসপন্স।
                logger.error(
                    "Terraform succeeded but 'service_url' output is missing — "
                    "refusing to fabricate a URL."
                )
                return {
                    "status": "failed",
                    "error": (
                        "Terraform apply finished but produced no 'service_url' output; "
                        "deployment state is unverifiable."
                    ),
                    "user_id": user_id,
                    "skill": skill,
                    "mode": "live",
                }

            logger.info(f"Successfully deployed skill '{skill}' to Google Cloud Run.")
            return {
                "status": "deployed",
                "user_id": user_id,
                "skill": skill,
                "service_url": service_url,
                "mode": "live",
            }
        except subprocess.CalledProcessError as err:
            logger.error(f"Terraform process execution failed: {err.stderr}")
            return {
                "status": "failed",
                "error": err.stderr or err.stdout,
                "user_id": user_id,
                "skill": skill,
            }
        except Exception as err:
            logger.error(f"BYOC deployment failed: {err}")
            return {
                "status": "failed",
                "error": str(err),
                "user_id": user_id,
                "skill": skill,
            }

    async def rollback(self, deployment_id: str) -> dict[str, Any]:
        logger.warning(f"Initiating rollback for deployment '{deployment_id}'...")
        tf_executable = shutil.which("terraform")
        if not tf_executable:
            # বাংলা মন্তব্য: আগে terraform না থাকলেও "rolled_back" বলা হতো (ভুয়া সাফল্য)।
            logger.error(
                "Terraform binary not found — rollback CANNOT run. Returning honest failure."
            )
            return {
                "status": "failed",
                "error": (
                    "Terraform is not installed on this host, so the deployment cannot "
                    "be rolled back. Install terraform to enable rollbacks."
                ),
                "deployment_id": deployment_id,
                "mode": "unavailable",
            }
        try:
            # Destroy dynamic deployment using terraform destroy (off the event loop)
            logger.info("Destroying Terraform resources for rollback...")
            await asyncio.to_thread(
                subprocess.run,
                [tf_executable, "destroy", "-auto-approve", "-no-color"],
                cwd=self.tf_dir,
                check=True,
            )
            return {
                "status": "rolled_back",
                "deployment_id": deployment_id,
                "mode": "live",
            }
        except Exception as e:
            # বাংলা মন্তব্য: destroy ব্যর্থ হলে আর "rolled_back" বলা যাবে না — সৎ failed।
            logger.error(f"Rollback terraform execution failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "deployment_id": deployment_id,
                "mode": "live",
            }
