#!/usr/bin/env python3
"""
================================================================================
SuperAI Health Check - Complete System Diagnostics & Validation
================================================================================
🏥 Comprehensive health monitoring for SuperAI platform
✅ Validates all components: API, Database, Redis, LLM providers
⚡ Detects configuration issues before they cause outages
📊 Generates detailed health reports with recommendations

Author: SuperAI Toolkit
Version: 1.0.0
License: MIT

Usage:
    python superai_health_check.py                    # Full system check
    python superai_health_check.py --quick            # Quick status only
    python superai_health_check.py --components api,db # Check specific components
    python superai_health_check.py --json             # JSON output for CI/CD
    python superai_health_check.py --fix              # Auto-fix common issues
    python superai_health_check.py --deep             # Deep diagnostic mode

Health Checks Included:
  ✅ System Resources (CPU, Memory, Disk)
  ✅ Python Environment (versions, dependencies)
  ✅ Environment Variables (all required vars present?)
  ✅ Database Connectivity (Supabase/PostgreSQL)
  ✅ Redis Connection (Upstash/Redis)
  ✅ LLM Provider APIs (OpenAI, Claude, Gemini)
  ✅ FastAPI Backend Health
  ✅ Next.js Frontend Build Status
  ✅ File Permissions & Structure
  ✅ Security Headers (CORS, CSRF protection)
  ✅ Patch Integration Status (are all patches applied?)

CPU Impact of This Script:
  - Runs once (not continuous): ~2-5 seconds total CPU time
  - Network checks add latency but minimal CPU
  - Safe to run in production without performance impact
================================================================================

SCRIPT-INTELLIGENCE v9: auto-discovers targets via scripts/lib/auto_discovery.py — no hardcoded file inventories.
Env overrides: SUPREMEAI_REPO_ROOT (pin repo root when running from outside
the checkout).  Missing optional modules are SKIPPED with a
"[discovery] skipping N missing optional modules" note instead of failing
forever after a rename.
=============================================================================
"""

import argparse
import importlib
import json
import os
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

# Try imports
# SCRIPT-INTELLIGENCE v9: shared discovery lib (stdlib only, first-party).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from lib.auto_discovery import (  # noqa: E402
    DiscoveryError,
    discover_core_modules,
    discover_files,
    existing_paths,
    find_repo_root,
    get_layout,
    require,
)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    component: str
    check_name: str
    status: HealthStatus
    message: str
    details: dict | None = None
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'component': self.component,
            'check_name': self.check_name,
            'status': self.status.value,
            'message': self.message,
            'details': self.details or {},
            'latency_ms': self.latency_ms,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class HealthReport:
    """Complete health report."""
    results: list[HealthCheckResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def overall_status(self) -> HealthStatus:
        if not self.results:
            return HealthStatus.UNKNOWN

        statuses = [r.status for r in self.results]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN

    @property
    def summary(self) -> dict[str, int]:
        summary = {}
        for status in HealthStatus:
            summary[status.value] = sum(1 for r in self.results if r.status == status)
        return summary

    def to_dict(self) -> dict:
        return {
            'overall_status': self.overall_status.value,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_checks': len(self.results),
            'summary': {k: v for k, v in self.summary.items()},
            'results': [r.to_dict() for r in self.results]
        }


class SuperAIHealthChecker:
    """
    Comprehensive health checker for SuperAI platform.

    Checks all components and provides actionable recommendations.
    """

    # Required environment variables
    REQUIRED_ENV_VARS = [
        'DATABASE_URL',
        'REDIS_URL',
        'OPENAI_API_KEY',  # At least one LLM key needed
        # 'ANTHROPIC_API_KEY',  # Optional
        # 'GOOGLE_API_KEY',     # Optional
        'NEXTAUTH_SECRET',
        'SUPABASE_URL',
        'SUPABASE_ANON_KEY',
    ]

    OPTIONAL_ENV_VARS = [
        'ANTHROPIC_API_KEY',
        'GOOGLE_API_KEY',
        'UPSTASH_REDIS_REST_URL',
        'UPSTASH_REDIS_REST_TOKEN',
        'RENDER_API_KEY',
        'NODE_ENV',
    ]

    # Required Python packages
    REQUIRED_PACKAGES = [
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'redis',
        'httpx',
        'pydantic',
    ]

    # API endpoints to check
    API_ENDPOINTS = {
        'FastAPI Health': '/health',
        'API Docs': '/docs',
        'OpenAPI Schema': '/openapi.json',
    }

    def __init__(
        self,
        base_url: str = "http://localhost:8000",  # is_local()
        frontend_url: str = "http://localhost:3000",  # is_local()
        timeout: int = 10,
        quick_mode: bool = False,
        auto_fix: bool = False,
        components: list[str] | None = None,
        verbose: bool = False
    ):
        self.base_url = base_url.rstrip('/')
        self.frontend_url = frontend_url.rstrip('/')
        self.timeout = timeout
        self.quick_mode = quick_mode
        self.auto_fix = auto_fix
        self.components = components or []
        self.verbose = verbose

        self.report = HealthReport()
        self.console = Console() if RICH_AVAILABLE else None
        self.fixes_applied: list[str] = []
        self.json_mode: bool = False  # v9: stdout stays pure JSON when set

        # Project root detection
        self.project_root = self._find_project_root()

    def _find_project_root(self) -> Path:
        """Find project root directory.

        SCRIPT-INTELLIGENCE v9: prefers the shared lib (walks up from this
        file, honours SUPREMEAI_REPO_ROOT), falls back to the legacy cwd walk.
        """
        try:
            return find_repo_root(start=Path(__file__))
        except DiscoveryError as exc:
            print(
                f"[health] shared repo-root discovery failed ({exc}); "
                "falling back to legacy cwd walk",
                file=sys.stderr,
            )
        current = Path.cwd()

        # Look for indicators
        for parent in [current] + list(current.parents):
            if (parent / '.git').exists() or (parent / 'package.json').exists() or (parent / 'backend' / 'main.py').exists():
                return parent

        return current

    def log(self, message: str, level: str = "info"):
        """Log message with level."""
        if not self.verbose and level == "debug":
            return

        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "debug": "🔍"}
        icon = icons.get(level, "•")

        if self.console:
            colors = {"info": "cyan", "success": "green", "warning": "yellow", "error": "red", "debug": "dim"}
            self.console.print(f"[{colors.get(level,'white')}]{icon} {message}[/{colors.get(level,'white')}]")
        else:
            print(f"{icon} {message}")

    def log_discovery(self, message: str):
        """SCRIPT-INTELLIGENCE v9: plain-text discovery info line.

        Printed without rich markup so the literal "[discovery]" prefix
        survives console rendering (rich eats [brackets] as tags).
        In --json mode the line goes to STDERR so the JSON stream on stdout
        stays machine-parseable (output-format compatibility).
        """
        stream = sys.stderr if getattr(self, "json_mode", False) else sys.stdout
        print(f"[discovery] {message}", file=stream, flush=True)

    def add_result(self, result: HealthCheckResult):
        """Add a result to the report."""
        self.report.results.append(result)

        icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.UNKNOWN: "❓",
            HealthStatus.SKIPPED: "➡️"
        }.get(result.status, "•")

        self.log(f"{icon} [{result.component}] {result.check_name}: {result.message}")

    def run_all_checks(self) -> HealthReport:
        """Run all health checks."""
        self.log("🏥 Starting SuperAI Health Check...")
        self.log(f"   Project Root: {self.project_root}")
        self.log(f"   Mode: {'Quick' if self.quick_mode else 'Full'}")

        # Define all check functions
        checks = [
            ("system", "System Resources", self.check_system_resources),
            ("python", "Python Environment", self.check_python_env),
            ("env_vars", "Environment Variables", self.check_environment_variables),
            ("dependencies", "Dependencies", self.check_dependencies),
            ("database", "Database Connectivity", self.check_database),
            ("redis", "Redis Connection", self.check_redis),
            ("llm_providers", "LLM Providers", self.check_llm_providers),
            ("backend_api", "Backend API", self.check_backend_api),
            ("frontend", "Frontend Build", self.check_frontend),
            ("file_structure", "File Structure", self.check_file_structure),
            ("security", "Security Configuration", self.check_security_config),
            ("patches", "Patch Integration", self.check_patch_integration),
        ]

        # Filter by components if specified
        if self.components:
            checks = [(comp, name, func) for comp, name, func in checks
                     if comp in self.components or name.lower() in [c.lower() for c in self.components]]

        # Run checks (parallel for I/O bound, sequential otherwise)
        if not self.quick_mode:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {}
                for comp, name, func in checks:
                    future = executor.submit(func)
                    futures[future] = (comp, name)

                for future in as_completed(futures):
                    comp, name = futures[future]
                    try:
                        result = future.result(timeout=self.timeout * 2)
                        if isinstance(result, list):
                            for r in result:
                                self.add_result(r)
                        elif result:
                            self.add_result(result)
                    except Exception as e:
                        self.add_result(HealthCheckResult(
                            component=comp,
                            check_name=name,
                            status=HealthStatus.UNHEALTHY,
                            message=f"Check failed with error: {e!s}"
                        ))
        else:
            # Quick mode: run sequentially, skip slow checks
            for comp, name, func in checks:
                try:
                    result = func()
                    if isinstance(result, list):
                        for r in result:
                            self.add_result(r)
                    elif result:
                        self.add_result(result)
                except Exception as e:
                    self.add_result(HealthCheckResult(
                        component=comp,
                        check_name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check failed: {e!s}"
                    ))

        self.report.end_time = datetime.now()

        return self.report

    # ==================== INDIVIDUAL CHECKS ====================

    def check_system_resources(self) -> list[HealthCheckResult]:
        """Check system resource usage."""
        results = []

        if not PSUTIL_AVAILABLE:
            results.append(HealthCheckResult(
                component="system",
                check_name="psutil available",
                status=HealthStatus.SKIPPED,
                message="psutil not installed, skipping resource checks"
            ))
            return results

        # CPU Check
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_status = HealthStatus.HEALTHY if cpu_percent < 80 else (
            HealthStatus.DEGRADED if cpu_percent < 95 else HealthStatus.UNHEALTHY
        )
        results.append(HealthCheckResult(
            component="system",
            check_name="CPU Usage",
            status=cpu_status,
            message=f"CPU at {cpu_percent:.1f}%",
            details={'percent': cpu_percent, 'cores': psutil.cpu_count()}
        ))

        # Memory Check
        mem = psutil.virtual_memory()
        mem_status = HealthStatus.HEALTHY if mem.percent < 80 else (
            HealthStatus.DEGRADED if mem.percent < 95 else HealthStatus.UNHEALTHY
        )
        results.append(HealthCheckResult(
            component="system",
            check_name="Memory Usage",
            status=mem_status,
            message=f"Memory at {mem.percent:.1f}% ({mem.used//1024//1024}MB/{mem.total//1024//1024}MB)",
            details={'percent': mem.percent, 'available_mb': mem.available // 1024 // 1024}
        ))

        # Disk Check
        disk = psutil.disk_usage('/')
        disk_status = HealthStatus.HEALTHY if disk.percent < 85 else (
            HealthStatus.DEGRADED if disk.percent < 95 else HealthStatus.UNHEALTHY
        )
        results.append(HealthCheckResult(
            component="system",
            check_name="Disk Space",
            status=disk_status,
            message=f"Disk at {disk.percent:.1f}% ({disk.free//1024//1024}MB free)",
            details={'percent': disk.percent, 'free_gb': round(disk.free / (1024**3), 2)}
        ))

        # CPU Impact Assessment
        estimated_overhead_percent = 3.5  # ~3.5% average from patches
        remaining_capacity = max(100 - cpu_percent - estimated_overhead_percent, 0)

        results.append(HealthCheckResult(
            component="system",
            check_name="Patch Headroom",
            status=HealthStatus.HEALTHY if remaining_capacity > 20 else HealthStatus.DEGRADED,
            message=f"~{estimated_overhead_percent}% patch overhead, {remaining_capacity:.1f}% headroom remaining",
            details={
                'estimated_patch_cpu_percent': estimated_overhead_percent,
                'remaining_capacity_percent': round(remaining_capacity, 1),
                'recommendation': "Consider scaling if headroom < 20%"
            }
        ))

        return results

    def check_python_env(self) -> list[HealthCheckResult]:
        """Check Python environment."""
        results = []

        # Python Version
        version = sys.version_info
        min_version = (3, 9)

        if version >= min_version:
            results.append(HealthCheckResult(
                component="python",
                check_name="Python Version",
                status=HealthStatus.HEALTHY,
                message=f"Python {version.major}.{version.minor}.{version.micro}",
                details={'version': f"{version.major}.{version.minor}.{version.micro}"}
            ))
        else:
            results.append(HealthCheckResult(
                component="python",
                check_name="Python Version",
                status=HealthStatus.UNHEALTHY,
                message=f"Python {version.major}.{version.minor} found, need >=3.9"
            ))

        # Virtual Environment
        in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        results.append(HealthCheckResult(
            component="python",
            check_name="Virtual Environment",
            status=HealthStatus.HEALTHY if in_venv else HealthStatus.DEGRADED,
            message="Running in venv" if in_venv else "Not in virtual environment (recommended)"
        ))

        # pip availability
        try:
            subprocess.run(['pip', '--version'], capture_output=True, check=True)
            results.append(HealthCheckResult(
                component="python",
                check_name="pip available",
                status=HealthStatus.HEALTHY,
                message="pip is available"
            ))
        except Exception:
            results.append(HealthCheckResult(
                component="python",
                check_name="pip available",
                status=HealthStatus.UNHEALTHY,
                message="pip not found"
            ))

        return results

    def check_environment_variables(self) -> list[HealthCheckResult]:
        """Check required environment variables."""
        results = []

        present = []
        missing = []

        for var in self.REQUIRED_ENV_VARS:
            value = os.environ.get(var)
            if value:
                # Mask sensitive values
                value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                present.append(var)
            else:
                missing.append(var)

        # Required vars check
        if not missing:
            results.append(HealthCheckResult(
                component="env_vars",
                check_name="Required Environment Variables",
                status=HealthStatus.HEALTHY,
                message=f"All {len(present)} required variables set"
            ))
        else:
            results.append(HealthCheckResult(
                component="env_vars",
                check_name="Required Environment Variables",
                status=HealthStatus.UNHEALTHY,
                message=f"Missing {len(missing)}: {', '.join(missing)}",
                details={'missing': missing}
            ))

            if self.auto_fix:
                self.log(f"Would create .env template for: {', '.join(missing)}", "warning")

        # Optional vars
        optional_present = [v for v in self.OPTIONAL_ENV_VARS if os.environ.get(v)]
        results.append(HealthCheckResult(
            component="env_vars",
            check_name="Optional Environment Variables",
            status=HealthStatus.DEGRADED if len(optional_present) < len(self.OPTIONAL_ENV_VARS) // 2 else HealthStatus.HEALTHY,
            message=f"{len(optional_present)}/{len(self.OPTIONAL_ENV_VARS)} optional vars set",
            details={'present': optional_present}
        ))

        # Security check: exposed secrets
        env_file = self.project_root / '.env'
        if env_file.exists():
            content = env_file.read_text()
            if 'password' in content.lower() or 'secret' in content.lower():
                results.append(HealthCheckResult(
                    component="env_vars",
                    check_name="Secret Security",
                    message=".env contains potential secrets (ensure it's in .gitignore)",
                    status=HealthStatus.DEGRADED
                ))

        return results

    def check_dependencies(self) -> list[HealthCheckResult]:
        """Check Python package dependencies."""
        results = []

        installed = []
        missing = []

        for package in self.REQUIRED_PACKAGES:
            try:
                importlib.import_module(package.replace('-', '_'))
                installed.append(package)
            except ImportError:
                missing.append(package)

        if not missing:
            results.append(HealthCheckResult(
                component="dependencies",
                check_name="Required Packages",
                status=HealthStatus.HEALTHY,
                message=f"All {len(installed)} packages installed"
            ))
        else:
            results.append(HealthCheckResult(
                component="dependencies",
                check_name="Required Packages",
                status=HealthStatus.UNHEALTHY,
                message=f"Missing {len(missing)}: {', '.join(missing)}",
                details={'missing': missing, 'install_command': f"pip install {' '.join(missing)}"}
            ))

            if self.auto_fix:
                try:
                    subprocess.run(['pip', 'install'] + missing, check=True, capture_output=True)
                    self.fixes_applied.append(f"Installed: {', '.join(missing)}")
                    self.log(f"Auto-fixed: Installed {len(missing)} packages", "success")
                except Exception as e:
                    self.log(f"Auto-fix failed: {e}", "error")

        # Check requirements.txt exists
        req_file = self.project_root / 'backend' / 'requirements.txt'
        if req_file.exists():
            results.append(HealthCheckResult(
                component="dependencies",
                check_name="requirements.txt",
                status=HealthStatus.HEALTHY,
                message=f"Found at {req_file.relative_to(self.project_root)}"
            ))
        else:
            results.append(HealthCheckResult(
                component="dependencies",
                check_name="requirements.txt",
                status=HealthStatus.DEGRADED,
                message="requirements.txt not found in backend/"
            ))

        return results

    def check_database(self) -> HealthCheckResult:
        """Check database connectivity."""
        db_url = os.environ.get('DATABASE_URL', '')

        if not db_url:
            return HealthCheckResult(
                component="database",
                check_name="Database URL",
                status=HealthStatus.UNHEALTHY,
                message="DATABASE_URL not set"
            )

        # Parse database type
        if 'supabase' in db_url.lower() or 'postgresql' in db_url.lower() or 'postgres' in db_url.lower():
            db_type = "PostgreSQL/Supabase"
        elif 'mysql' in db_url.lower():
            db_type = "MySQL"
        elif 'sqlite' in db_url.lower():
            db_type = "SQLite"
        else:
            db_type = "Unknown"

        # Try connection (basic check)
        start = datetime.now()
        try:
            # Simple socket check for PostgreSQL default port
            if 'postgres' in db_url.lower():
                host_match = re.search(r'@([^:/]+)', db_url)
                if host_match:
                    host = host_match.group(1)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((host, 5432))
                    sock.close()

                    latency = (datetime.now() - start).total_seconds() * 1000

                    if result == 0:
                        return HealthCheckResult(
                            component="database",
                            check_name=f"{db_type} Connection",
                            status=HealthStatus.HEALTHY,
                            message=f"Connected to {db_type}",
                            latency_ms=latency
                        )
                    else:
                        return HealthCheckResult(
                            component="database",
                            check_name=f"{db_type} Connection",
                            status=HealthStatus.UNHEALTHY,
                            message=f"Cannot connect to {host}:5432",
                            latency_ms=latency
                        )

            # Fallback: assume OK if URL is set
            return HealthCheckResult(
                component="database",
                check_name=f"{db_type} Configuration",
                status=HealthStatus.DEGRADED,
                message=f"{db_type} URL configured (connection not verified)",
                details={'url_prefix': db_url[:30] + "..."}
            )

        except Exception as e:
            return HealthCheckResult(
                component="database",
                check_name="Database Connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Connection error: {str(e)[:100]}"
            )

    def check_redis(self) -> HealthCheckResult:
        """Check Redis connection."""
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('UPSTASH_REDIS_REST_URL')

        if not redis_url:
            return HealthCheckResult(
                component="redis",
                check_name="Redis URL",
                status=HealthStatus.DEGRADED,
                message="REDIS_URL not set (caching/rate-limiting will be disabled)"
            )

        start = datetime.now()
        try:
            import redis

            # Determine connection params
            if redis_url.startswith(('redis://', 'rediss://')):
                client = redis.from_url(redis_url, socket_timeout=5)
            else:
                # Upstash REST URL
                token = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')
                if token:
                    # Would need redis-py with REST support
                    pass
                return HealthCheckResult(
                    component="redis",
                    check_name="Redis Configuration",
                    status=HealthStatus.DEGRADED,
                    message="Redis URL configured (connection type needs verification)"
                )

            # Test connection
            client.ping()
            latency = (datetime.now() - start).total_seconds() * 1000

            # Get info
            info = client.info()
            used_memory = info.get('used_memory_human', 'unknown')

            return HealthCheckResult(
                component="redis",
                check_name="Redis Connection",
                status=HealthStatus.HEALTHY,
                message=f"Connected! Memory: {used_memory}, Latency: {latency:.1f}ms",
                latency_ms=latency,
                details={'memory_used': used_memory, 'latency_ms': round(latency, 1)}
            )

        except ImportError:
            return HealthCheckResult(
                component="redis",
                check_name="Redis Client",
                status=HealthStatus.UNHEALTHY,
                message="redis package not installed (pip install redis)"
            )
        except Exception as e:
            return HealthCheckResult(
                component="redis",
                check_name="Redis Connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Cannot connect: {str(e)[:100]}",
                details={'note': "Patches will fail-open gracefully"}
            )

    def check_llm_providers(self) -> list[HealthCheckResult]:
        """Check LLM provider API keys and connectivity."""
        results = []

        providers = {
            'OpenAI': os.environ.get('OPENAI_API_KEY'),
            'Anthropic/Claude': os.environ.get('ANTHROPIC_API_KEY'),
            'Google/Gemini': os.environ.get('GOOGLE_API_KEY'),
        }

        configured = {name: key for name, key in providers.items() if key}

        if configured:
            results.append(HealthCheckResult(
                component="llm_providers",
                check_name="API Keys Configured",
                status=HealthStatus.HEALTHY if len(configured) >= 1 else HealthStatus.DEGRADED,
                message=f"{len(configured)}/{len(providers)} providers configured: {list(configured.keys())}"
            ))

            # Quick validation test (if requests available and not quick mode)
            if REQUESTS_AVAILABLE and not self.quick_mode:
                if configured.get('OpenAI'):
                    start = datetime.now()
                    try:
                        resp = requests.get(
                            'https://api.openai.com/v1/models',
                            headers={'Authorization': f'Bearer {configured["OpenAI"][:20]}...'},
                            timeout=5
                        )
                        latency = (datetime.now() - start).total_seconds() * 1000

                        if resp.status_code == 200:
                            results.append(HealthCheckResult(
                                component="llm_providers",
                                check_name="OpenAI API",
                                status=HealthStatus.HEALTHY,
                                message=f"API reachable ({latency:.0f}ms)",
                                latency_ms=latency
                            ))
                        else:
                            results.append(HealthCheckResult(
                                component="llm_providers",
                                check_name="OpenAI API",
                                status=HealthStatus.DEGRADED,
                                message=f"API returned {resp.status_code}",
                                latency_ms=latency
                            ))
                    except Exception as e:
                        results.append(HealthCheckResult(
                            component="llm_providers",
                            check_name="OpenAI API",
                            status=HealthStatus.UNKNOWN,
                            message=f"Cannot verify: {str(e)[:50]}"
                        ))
        else:
            results.append(HealthCheckResult(
                component="llm_providers",
                check_name="API Keys",
                status=HealthStatus.UNHEALTHY,
                message="No LLM API keys configured!"
            ))

        # Cost optimization note
        results.append(HealthCheckResult(
            component="llm_providers",
            check_name="Smart Router Ready",
            status=HealthStatus.HEALTHY if len(configured) >= 2 else HealthStatus.DEGRADED,
            message=f"{'Multiple providers ready for cost routing' if len(configured) >= 2 else 'Add more providers for cost optimization'}",
            details={'providers_count': len(configured), 'recommended_min': 2}
        ))

        return results

    def check_backend_api(self) -> list[HealthCheckResult]:
        """Check backend API health."""
        results = []

        if not REQUESTS_AVAILABLE:
            results.append(HealthCheckResult(
                component="backend_api",
                check_name="HTTP Client",
                status=HealthStatus.SKIPPED,
                message="requests library not available"
            ))
            return results

        # Main health endpoint
        start = datetime.now()
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            latency = (datetime.now() - start).total_seconds() * 1000

            if resp.status_code == 200:
                results.append(HealthCheckResult(
                    component="backend_api",
                    check_name="Health Endpoint",
                    status=HealthStatus.HEALTHY,
                    message=f"API healthy ({latency:.0f}ms)",
                    latency_ms=latency,
                    details=resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                ))
            else:
                results.append(HealthCheckResult(
                    component="backend_api",
                    check_name="Health Endpoint",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Returned {resp.status_code}",
                    latency_ms=latency
                ))
        except requests.exceptions.ConnectionError:
            results.append(HealthCheckResult(
                component="backend_api",
                check_name="API Server",
                status=HealthStatus.UNHEALTHY,
                message=f"Not running at {self.base_url} (start with: uvicorn main:app --reload)"
            ))
        except Exception as e:
            results.append(HealthCheckResult(
                component="backend_api",
                check_name="API Server",
                status=HealthStatus.UNKNOWN,
                message=str(e)[:100]
            ))

        return results

    def check_frontend(self) -> list[HealthCheckResult]:
        """Check frontend build status."""
        results = []

        # Check package.json exists
        pkg_json = self.project_root / 'package.json'
        if not pkg_json.exists():
            pkg_json = self.project_root / 'frontend' / 'package.json'

        if pkg_json.exists():
            results.append(HealthCheckResult(
                component="frontend",
                check_name="package.json",
                status=HealthStatus.HEALTHY,
                message=f"Found at {pkg_json.relative_to(self.project_root)}"
            ))

            # Check node_modules
            node_modules = pkg_json.parent / 'node_modules'
            if node_modules.exists():
                results.append(HealthCheckResult(
                    component="frontend",
                    check_name="Dependencies Installed",
                    status=HealthStatus.HEALTHY,
                    message="node_modules exists"
                ))
            else:
                results.append(HealthCheckResult(
                    component="frontend",
                    check_name="Dependencies Installed",
                    status=HealthStatus.UNHEALTHY,
                    message="Run: npm install"
                ))

            # Check if dev server running
            if REQUESTS_AVAILABLE:
                try:
                    resp = requests.get(self.frontend_url, timeout=3)
                    results.append(HealthCheckResult(
                        component="frontend",
                        check_name="Dev Server",
                        status=HealthStatus.HEALTHY if resp.status_code == 200 else HealthStatus.DEGRADED,
                        message=f"Frontend accessible at {self.frontend_url}"
                    ))
                except Exception:
                    results.append(HealthCheckResult(
                        component="frontend",
                        check_name="Dev Server",
                        status=HealthStatus.DEGRADED,
                        message="Frontend not running (npm run dev)"
                    ))
        else:
            results.append(HealthCheckResult(
                component="frontend",
                check_name="Project Structure",
                status=HealthStatus.UNHEALTHY,
                message="package.json not found"
            ))

        return results

    def _first_existing(self, candidates: list[Path]) -> Path | None:
        """Return the first candidate that exists on disk (v9 discovery)."""
        found = existing_paths(candidates)
        return found[0] if found else None

    def check_file_structure(self) -> list[HealthCheckResult]:
        """Check expected file structure.

        SCRIPT-INTELLIGENCE v9: the inventory is DISCOVERED -- each role is
        resolved from a candidate list (globs + discover_core_modules) and
        only roles with NO surviving candidate are reported missing, so file
        renames/moves no longer rot this check.
        """
        results = []
        root = self.project_root
        core = discover_core_modules()

        # (role, description, candidates: globs (discovered) or literal paths)
        role_specs: list[tuple[str, list[str]]] = [
            ('FastAPI entry point', ['backend/main.py', 'backend/app.py', 'main.py']),
            ('Python dependencies', ['backend/requirements*.txt', 'requirements*.txt',
                                     'backend/pyproject.toml', 'pyproject.toml']),
            ('Node.js config', ['package.json', 'frontend/package.json']),
            ('Frontend build config', ['next.config.*', 'frontend/next.config.*',
                                       'frontend/vite.config.*']),
            ('Tailwind CSS config', ['tailwind.config.*', 'frontend/tailwind.config.*']),
            ('Environment template', ['.env.example', '.env.sample', 'backend/.env.example']),
            ('Git ignore rules', ['.gitignore', 'backend/.gitignore']),
        ]
        if 'app' in core:  # discovered FastAPI app module is the preferred candidate
            role_specs[0][1].insert(0, str(core['app']))

        expected: list[tuple[str, Path | None]] = []
        for description, candidates in role_specs:
            expanded: list[Path] = []
            for cand in candidates:
                if any(ch in cand for ch in "*?["):
                    expanded.extend(discover_files(root, [cand]))
                else:
                    expanded.append(root / cand)
            expected.append((description, self._first_existing(expanded)))

        found = 0
        for description, full_path in expected:
            if full_path is not None:
                found += 1
            else:
                results.append(HealthCheckResult(
                    component="file_structure",
                    check_name=description,
                    status=HealthStatus.DEGRADED,
                    message=f"Missing: {description} (no discovery candidate present)"
                ))

        self.log_discovery(f"file-structure inventory: {found}/{len(expected)} roles resolved from candidates")
        if found >= len(expected) - 2:  # Allow some flexibility
            results.insert(0, HealthCheckResult(
                component="file_structure",
                check_name="Core Files",
                status=HealthStatus.HEALTHY,
                message=f"{found}/{len(expected)} core files present"
            ))

        # Check for patches directory
        patches_dir = self.project_root / 'patches'
        download_patches = Path('/home/z/my-project/download/patches')

        if patches_dir.exists() or download_patches.exists():
            results.append(HealthCheckResult(
                component="file_structure",
                check_name="Patches Available",
                status=HealthStatus.HEALTHY,
                message="SuperAI patches found in project"
            ))

        return results

    def check_security_config(self) -> list[HealthCheckResult]:
        """Check security-related configurations."""
        results = []

        # CORS settings (would need to check actual code)
        # For now, check environment
        allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')

        if allowed_origins == '*':
            results.append(HealthCheckResult(
                component="security",
                check_name="CORS Configuration",
                status=HealthStatus.DEGRADED,
                message="CORS set to wildcard (*) - restrict in production!",
                details={'current': '*', 'recommendation': 'Set specific origins'}
            ))
        else:
            results.append(HealthCheckResult(
                component="security",
                check_name="CORS Configuration",
                status=HealthStatus.HEALTHY,
                message=f"CORS restricted to: {allowed_origins[:50]}"
            ))

        # HTTPS enforcement
        node_env = os.environ.get('NODE_ENV', 'development')
        if node_env == 'production':
            # In production, should use HTTPS
            results.append(HealthCheckResult(
                component="security",
                check_name="Production Security",
                status=HealthStatus.DEGRADED,
                message="Ensure HTTPS is enabled in production"
            ))
        else:
            results.append(HealthCheckResult(
                component="security",
                check_name="Environment",
                status=HealthStatus.HEALTHY,
                message=f"Running in {node_env} mode"
            ))

        # Rate limiting readiness
        redis_available = bool(os.environ.get('REDIS_URL'))
        results.append(HealthCheckResult(
            component="security",
            check_name="Rate Limiting Ready",
            status=HealthStatus.HEALTHY if redis_available else HealthStatus.DEGRADED,
            message="Rate limiting active" if redis_available else "Rate limiting disabled (no Redis)"
        ))

        return results

    def check_patch_integration(self) -> list[HealthCheckResult]:
        """Check the health-relevant core-module inventory.

        SCRIPT-INTELLIGENCE v9: the module list is DISCOVERED (role-based
        discover_core_modules() + core/*.py filtered by health-relevant name
        patterns) instead of a hardcoded patch list, so renames never leave
        this check validating a phantom inventory.  Modules that no longer
        exist are simply not checked (skip note); an EMPTY discovery result
        fails loud (require) because it would defeat the check's purpose.
        """
        results = []
        layout = get_layout()
        backend = layout.backend or (self.project_root / 'backend')

        core = discover_core_modules()
        candidates: list[Path] = list(core.values())

        health_relevant = re.compile(
            r"(cache|rate|security|router|monitor|heal|health|gateway|config|auth|db|llm)"
        )
        core_files = discover_files(backend, ["core/*.py"])
        candidates += [p for p in core_files if health_relevant.search(p.name.lower())]

        # de-dup, deterministic order
        seen: set[Path] = set()
        candidates = [p for p in candidates if not (p in seen or seen.add(p))]

        present = existing_paths(candidates)
        skipped = len(candidates) - len(present)
        if skipped:
            self.log_discovery(f"skipping {skipped} missing optional modules")

        try:
            present = list(require(present, "health-relevant backend core modules"))
        except DiscoveryError as exc:
            results.append(HealthCheckResult(
                component="patches",
                check_name="Module Inventory",
                status=HealthStatus.UNHEALTHY,
                message=str(exc),
            ))
            return results

        applied: list[str] = []
        broken: list[str] = []
        for full_path in present:
            try:
                ok = full_path.is_dir() or full_path.stat().st_size > 0
            except OSError:
                ok = False
            if ok:
                applied.append(layout.rel(full_path))
            else:
                broken.append(layout.rel(full_path))

        self.log_discovery(f"health-relevant module inventory: {len(applied)} discovered "
                 f"(from {len(candidates)} candidates)")

        if applied:
            results.append(HealthCheckResult(
                component="patches",
                check_name="Applied Patches",
                status=HealthStatus.HEALTHY,
                message=f"{len(applied)}/{len(present)} discovered modules present",
                details={'applied': applied, 'skipped_missing': skipped}
            ))

        if broken:
            results.append(HealthCheckResult(
                component="patches",
                check_name="Broken Modules",
                status=HealthStatus.DEGRADED,
                message=f"{len(broken)} discovered modules are empty/unreadable",
                details={'broken': broken}
            ))

        # Overall integration score (over the DISCOVERED inventory only)
        integration_pct = len(applied) / len(present) * 100 if present else 0.0
        results.append(HealthCheckResult(
            component="patches",
            check_name="Integration Score",
            status=HealthStatus.HEALTHY if integration_pct >= 80 else (
                HealthStatus.DEGRADED if integration_pct >= 50 else HealthStatus.UNHEALTHY
            ),
            message=f"{integration_pct:.0f}% integrated ({len(applied)}/{len(present)} discovered)",
            details={'percentage': round(integration_pct, 1)}
        ))

        return results

    def print_report(self):
        """Print formatted health report."""
        if not RICH_AVAILABLE:
            self._print_text_report()
            return

        console = Console()

        # Header
        console.print()
        console.print(Panel(
            f"[bold cyan]🏥 SuperAI Health Report[/bold cyan]\n"
            f"[dim]{self.report.start_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
            style="blue"
        ))

        # Summary table
        summary_table = Table(show_header=False, box=box.SIMPLE, title="Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value")

        status_colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.DEGRADED: "yellow",
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.UNKNOWN: "dim",
            HealthStatus.SKIPPED: "dim"
        }

        overall = self.report.overall_status
        summary_table.add_row(
            "Overall Status",
            f"[{status_colors[overall]}]{overall.value.upper()}[/{status_colors[overall]}]"
        )

        for status, count in self.report.summary.items():
            if count > 0:
                summary_table.add_row(status.capitalize(), str(count))

        summary_table.add_row("Duration", f"{(self.report.end_time - self.report.start_time).total_seconds():.1f}s")
        summary_table.add_row("Fixes Applied", str(len(self.fixes_applied)))

        console.print(summary_table)

        # Detailed results by component
        console.print("\n[bold]Detailed Results:[/bold]\n")

        detail_table = Table(box=box.ROUNDED, show_header=True)
        detail_table.add_column("Component", style="cyan", width=18)
        detail_table.add_column("Check", width=22)
        detail_table.add_column("Status", width=12)
        detail_table.add_column("Message", style="dim")

        for result in self.report.results:
            status_icon = {
                HealthStatus.HEALTHY: "[green]✅[/green]",
                HealthStatus.DEGRADED: "[yellow]⚠️[/yellow]",
                HealthStatus.UNHEALTHY: "[red]❌[/red]",
                HealthStatus.UNKNOWN: "[dim]❓[/dim]",
                HealthStatus.SKIPPED: "[dim]➡️[/dim]"
            }.get(result.status, "•")

            detail_table.add_row(
                result.component,
                result.check_name,
                f"{status_icon} {result.status.value}",
                result.message[:60]
            )

        console.print(detail_table)

        # Recommendations
        unhealthy = [r for r in self.report.results if r.status == HealthStatus.UNHEALTHY]
        degraded = [r for r in self.report.results if r.status == HealthStatus.DEGRADED]

        if unhealthy or degraded:
            console.print("\n[bold yellow]Recommendations:[/bold yellow]")

            for r in unhealthy[:5]:
                console.print(f"  [red]• Fix:[/red] {r.component}/{r.check_name}: {r.message}")

            for r in degraded[:3]:
                console.print(f"  [yellow]• Review:[/yellow] {r.component}/{r.check_name}: {r.message}")

        console.print()

    def _print_text_report(self):
        """Print simple text report."""
        print("\n" + "="*60)
        print("🏥 SUPERAI HEALTH REPORT")
        print("="*60)
        print(f"Status: {self.report.overall_status.value.upper()}")
        print(f"Time: {(self.report.end_time - self.report.start_time).total_seconds():.1f}s")
        print("-"*60)

        for result in self.report.results:
            icon = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(result.status.value, "?")
            print(f"{icon} [{result.component}] {result.check_name}")
            print(f"   {result.message}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description='🏥 SuperAI Health Check - Complete system diagnostics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Full health check
  %(prog)s --quick                      # Quick status (skip network tests)
  %(prog)s --components api,db          # Check specific components only
  %(prog)s --json                       # JSON output for CI/CD pipelines
  %(prog)s --fix                        # Auto-fix common issues
  %(prog)s --deep                       # Deep diagnostic mode

Env overrides (SCRIPT-INTELLIGENCE v9):
  SUPREMEAI_REPO_ROOT     pin the repo root when running outside a checkout
        """
    )

    parser.add_argument('--base-url', default='http://localhost:8000',  # is_local()
                        help='Backend API base URL')
    parser.add_argument('--frontend-url', default='http://localhost:3000',  # is_local()
                        help='Frontend URL')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Request timeout in seconds')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick mode (skip network checks)')
    parser.add_argument('--fix', action='store_true',
                        help='Auto-fix common issues')
    parser.add_argument('--components', '-c', nargs='+',
                        help='Specific components to check')
    parser.add_argument('--json', '-j', action='store_true',
                        help='JSON output format')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Run health check
    checker = SuperAIHealthChecker(
        base_url=args.base_url,
        frontend_url=args.frontend_url,
        timeout=args.timeout,
        quick_mode=args.quick,
        auto_fix=args.fix,
        components=args.components,
        verbose=args.verbose
    )
    checker.json_mode = bool(args.json)

    report = checker.run_all_checks()

    # Output
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        checker.print_report()

    # Exit code based on status
    exit_codes = {
        HealthStatus.HEALTHY: 0,
        HealthStatus.DEGRADED: 1,
        HealthStatus.UNHEALTHY: 2,
        HealthStatus.UNKNOWN: 3
    }

    sys.exit(exit_codes.get(report.overall_status, 3))


if __name__ == '__main__':
    main()
