#!/usr/bin/env python3
"""
Blue/Green Deployment Script
Zero-downtime deployment strategy for applications.
Priority: 🟡 Medium
"""

import json
import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentStatus(Enum):
    """Deployment status."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    TESTING = "testing"
    SWITCHING = "switching"
    ROLLED_BACK = "rolled_back"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class DeploymentResult:
    """Result of blue-green deployment."""
    deployment_id: str
    status: DeploymentStatus
    blue_active: bool
    green_active: bool
    start_time: datetime
    end_time: datetime | None
    error_message: str | None
    health_checks_passed: int
    health_checks_total: int


class BlueGreenDeployer:
    """
    Manages blue-green deployments for zero-downtime releases.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.blue_active = True  # Start with blue as active
        self.green_active = False
        self.current_deployment: DeploymentResult | None = None
        self.health_endpoint = self.config.get('health_endpoint', '/health')
        self.deployment_timeout = self.config.get('timeout', 300)

    def get_active_environment(self) -> str:
        """Get the currently active environment."""
        return "blue" if self.blue_active else "green"

    def get_inactive_environment(self) -> str:
        """Get the currently inactive environment."""
        return "green" if self.blue_active else "blue"

    def pre_deployment_checks(self) -> bool:
        """Run pre-deployment validation."""
        logger.info("Running pre-deployment checks...")

        # Check required environment variables
        required_vars = ['DEPLOY_TOKEN', 'REGISTRY_URL']
        for var in required_vars:
            if not os.environ.get(var):
                logger.warning(f"Missing environment variable: {var}")

        # Check deployment scripts exist
        deploy_script = self.config.get('deploy_script')
        if deploy_script and not Path(deploy_script).exists():
            logger.error(f"Deploy script not found: {deploy_script}")
            return False

        return True

    async def deploy_to_inactive(
        self,
        deployment_id: str,
        image_tag: str,
        config_overrides: dict[str, Any] | None = None
    ) -> DeploymentResult:
        """Deploy new version to inactive environment."""
        target_env = self.get_inactive_environment()

        result = DeploymentResult(
            deployment_id=deployment_id,
            status=DeploymentStatus.DEPLOYING,
            blue_active=self.blue_active,
            green_active=self.green_active,
            start_time=datetime.now(),
            end_time=None,
            error_message=None,
            health_checks_passed=0,
            health_checks_total=0
        )

        try:
            # Build deployment command
            deploy_cmd = self._build_deploy_command(target_env, image_tag, config_overrides)
            logger.info(f"Deploying to {target_env}: {deploy_cmd[:50]}...")

            # Execute deployment
            proc = subprocess.run(
                deploy_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.deployment_timeout
            )

            if proc.returncode != 0:
                result.status = DeploymentStatus.FAILED
                result.error_message = proc.stderr
                logger.error(f"Deployment failed: {proc.stderr}")
            else:
                result.status = DeploymentStatus.TESTING

        except subprocess.TimeoutExpired:
            result.status = DeploymentStatus.FAILED
            result.error_message = "Deployment timed out"
            logger.error("Deployment timed out")
        except Exception as e:
            result.status = DeploymentStatus.FAILED
            result.error_message = str(e)
            logger.error(f"Deployment error: {e}")

        return result

    def _build_deploy_command(
        self,
        environment: str,
        image_tag: str,
        config_overrides: dict[str, Any] | None = None
    ) -> str:
        """Build deployment command with shell quoting."""
        base_cmd = self.config.get('deploy_script', 'echo "Deploy simulation"')
        config_flag = ""
        if config_overrides:
            config_str = json.dumps(config_overrides)
            config_flag = f" --config {shlex.quote(config_str)}"
        return f"{base_cmd} --env {shlex.quote(environment)} --image {shlex.quote(image_tag)}{config_flag}"

    def _build_switch_command(self, environment: str) -> str:
        """Build traffic switch command with shell quoting."""
        shlex.quote(environment)
        patch_payload = json.dumps({"spec": {"selector": {"version": environment}}})
        return f"kubectl patch svc/app-router -p {shlex.quote(patch_payload)}"

    async def run_health_checks(
        self,
        environment: str,
        checks: list[str] | None = None
    ) -> tuple[int, int]:
        """Run health checks on the deployed environment."""
        import aiohttp

        default_checks = [
            f"http://{environment}.internal{self.health_endpoint}",
            f"http://{environment}.internal/api/ping",
        ]
        check_urls = checks or default_checks

        passed = 0
        total = len(check_urls)

        for url in check_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            passed += 1
                            logger.info(f"Health check passed: {url}")
                        else:
                            logger.warning(f"Health check failed: {url} (status: {response.status})")
            except Exception as e:
                logger.warning(f"Health check error for {url}: {e}")

        return passed, total

    async def switch_traffic(
        self,
        deployment_id: str,
        target_env: str
    ) -> bool:
        """Switch traffic to the new environment."""
        try:
            # Update load balancer / router configuration
            switch_cmd = self._build_switch_command(target_env)
            logger.info(f"Switching traffic to {target_env}...")

            proc = subprocess.run(
                switch_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )

            if proc.returncode == 0:
                # Update active state
                self.blue_active = (target_env == "blue")
                self.green_active = (target_env == "green")
                logger.info(f"Traffic switched to {target_env}")
                return True
            else:
                logger.error(f"Traffic switch failed: {proc.stderr}")
                return False

        except Exception as e:
            logger.error(f"Traffic switch error: {e}")
            return False



    async def rollback(
        self,
        deployment_id: str
    ) -> bool:
        """Rollback to previous active environment."""
        # Switch back to the other environment
        target_env = self.get_active_environment()
        success = await self.switch_traffic(deployment_id, target_env)

        if success:
            logger.warning(f"Rollback completed: switched back to {target_env}")

        return success

    async def run_full_deployment(
        self,
        image_tag: str,
        config_overrides: dict[str, Any] | None = None
    ) -> DeploymentResult:
        """Run complete blue-green deployment."""
        deployment_id = f"deploy_{int(time.time())}"

        result = DeploymentResult(
            deployment_id=deployment_id,
            status=DeploymentStatus.PENDING,
            blue_active=self.blue_active,
            green_active=self.green_active,
            start_time=datetime.now(),
            end_time=None,
            error_message=None,
            health_checks_passed=0,
            health_checks_total=0
        )

        # Pre-deployment checks
        if not self.pre_deployment_checks():
            result.status = DeploymentStatus.FAILED
            result.error_message = "Pre-deployment checks failed"
            return result

        # Deploy to inactive environment
        target_env = self.get_inactive_environment()
        deployment_result = await self.deploy_to_inactive(deployment_id, image_tag, config_overrides)

        if deployment_result.status == DeploymentStatus.FAILED:
            return deployment_result

        # Health checks
        passed, total = await self.run_health_checks(target_env)
        result.health_checks_passed = passed
        result.health_checks_total = total

        if passed == total:
            # All checks passed, switch traffic
            if await self.switch_traffic(deployment_id, target_env):
                result.status = DeploymentStatus.SUCCESS
            else:
                result.status = DeploymentStatus.FAILED
                result.error_message = "Traffic switch failed"
        else:
            # Health checks failed
            result.status = DeploymentStatus.FAILED
            result.error_message = f"Health checks failed: {passed}/{total}"
            # Attempt rollback
            await self.rollback(deployment_id)

        result.end_time = datetime.now()
        self.current_deployment = result
        return result

    def save_deployment_report(self, result: DeploymentResult, output_dir: str = "deploy_reports") -> str:
        """Save deployment report."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        report_path = output_path / f"blue_green_deploy_{result.deployment_id}.json"

        report = {
            'deployment_id': result.deployment_id,
            'status': result.status.value,
            'active_environment': self.get_active_environment(),
            'start_time': result.start_time.isoformat(),
            'end_time': result.end_time.isoformat() if result.end_time else None,
            'error_message': result.error_message,
            'health_checks': {
                'passed': result.health_checks_passed,
                'total': result.health_checks_total
            }
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Deployment report saved to {report_path}")
        return str(report_path)


def main():
    """Main entry point for blue-green deployment."""
    import argparse

    parser = argparse.ArgumentParser(description="Blue-green zero-downtime deployment")
    parser.add_argument('--image-tag', required=True, help='Docker image tag to deploy')
    parser.add_argument('--environment', choices=['blue', 'green'],
                       help='Target environment (auto-detected if not specified)')
    parser.add_argument('--timeout', type=int, default=300, help='Deployment timeout in seconds')
    parser.add_argument('--dry-run', action='store_true', help='Simulate deployment without changes')

    args = parser.parse_args()

    deployer = BlueGreenDeployer({'timeout': args.timeout})

    async def run():
        if args.dry_run:
            print(f"DRY RUN: Would deploy {args.image_tag} to {deployer.get_inactive_environment()}")
            return None

        result = await deployer.run_full_deployment(args.image_tag)
        deployer.save_deployment_report(result)

        print("\nDeployment Result:")
        print(f"  Status: {result.status.value}")
        print(f"  Active Environment: {deployer.get_active_environment()}")
        print(f"  Health Checks: {result.health_checks_passed}/{result.health_checks_total}")

        return result

    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
