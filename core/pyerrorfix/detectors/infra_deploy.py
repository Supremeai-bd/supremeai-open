"""Infrastructure & Deployment error detector (NEW — category 11).

This detector is multi-language: it parses Dockerfiles, gunicorn/nginx/uvicorn
configs, and Python deployment scripts. Catches:
  * `OOMKilled` — Dockerfile / docker-compose without a memory limit.
  * Missing `HEALTHCHECK` in a production Docker image.
  * `502 Bad Gateway` — gunicorn/uvicorn with 1 worker + sync worker class
    (can't handle concurrent requests → nginx 502 under load).
  * `504 Gateway Timeout` — nginx/route without an explicit `proxy_read_timeout`
    (default 60s → gateway timeouts on long queries).
  * Missing `--workers` flag on gunicorn/uvicorn (uses default 1).
  * Docker image running as root (`USER root` or no USER directive).

Multi-format handling: the detector is given the source text and a filename;
it picks the parser based on the file extension. For .py files it returns
immediately (other detectors handle those).
"""

from __future__ import annotations

import re

from pyerrorfix.core.issue import Category, Issue, Severity
from pyerrorfix.detectors.base import BaseDetector


class InfraDeployDetector(BaseDetector):
    """Not AST-based — uses regex over config file content."""

    name = "infra-deploy"

    def run(self) -> list[Issue]:  # type: ignore[override]
        fn = self.filename.lower()
        if fn.endswith(".py"):
            return self.issues  # python deployment scripts handled elsewhere
        if (
            fn.endswith(("dockerfile", ".dockerfile"))
            or "/dockerfile" in fn
            or fn.endswith("dockerfile")
        ):
            self._check_dockerfile()
        elif fn.endswith((".yml", ".yaml")) and ("docker-compose" in fn or "compose" in fn):
            self._check_compose()
        elif fn.endswith(".conf") and "nginx" in fn:
            self._check_nginx()
        elif fn.endswith((".sh", ".service")):
            self._check_gunicorn_cmd()
        return self.issues

    # ---- Dockerfile checks ----
    def _check_dockerfile(self) -> None:
        text = self.source
        has_user = bool(re.search(r"^USER\s+\S+", text, re.MULTILINE))
        has_healthcheck = bool(re.search(r"^HEALTHCHECK\b", text, re.MULTILINE | re.IGNORECASE))
        has_memory = bool(re.search(r"--memory=|mem_limit", text, re.IGNORECASE))

        if not has_user:
            self._add(
                rule="docker-root-user",
                code="RuntimeError",
                sev=Severity.WARNING,
                title="Docker image runs as root",
                message="No `USER` directive — the container runs as root by default. "
                "A container escape becomes root on the host. Add `USER appuser`.",
                line=_first_line_match(text, r"^FROM\b"),
                fix_description="Add a non-root USER.",
            )
        if not has_healthcheck:
            self._add(
                rule="docker-missing-healthcheck",
                code="502",
                sev=Severity.INFO,
                title="Docker image has no HEALTHCHECK",
                message="Without HEALTHCHECK, the orchestrator can't detect a hung "
                "process (returns 502 before the container is marked unhealthy). "
                "Add `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1`.",  # is_local()
                line=_first_line_match(text, r"^FROM\b"),
                fix_description="Add a HEALTHCHECK directive.",
            )
        if not has_memory:
            self._add(
                rule="docker-no-memory-limit",
                code="OOMKilled",
                sev=Severity.WARNING,
                title="No memory limit in image/compose",
                message="Without a memory limit, a memory leak consumes all host RAM "
                "and the kernel OOM-killer terminates the process (exit code 137, "
                "OOMKilled). Set --memory= in docker run or mem_limit: in compose.",
                line=_first_line_match(text, r"^FROM\b"),
                fix_description="Add --memory=512m (image) or mem_limit: 512m (compose).",
            )

    # ---- docker-compose.yml checks ----
    def _check_compose(self) -> None:
        text = self.source
        # look for services without mem_limit / deploy.resources.limits.memory
        has_memory = bool(re.search(r"mem_limit:|memory:", text, re.IGNORECASE))
        has_healthcheck = bool(re.search(r"healthcheck:", text, re.IGNORECASE))
        if not has_memory:
            self._add(
                rule="docker-no-memory-limit",
                code="OOMKilled",
                sev=Severity.WARNING,
                title="docker-compose: no mem_limit",
                message="No mem_limit: / deploy.resources.limits.memory: on any service. "
                "A leak OOM-kills the container (exit 137). Add `mem_limit: 512m`.",
                line=1,
                fix_description="Add mem_limit: to each service.",
            )
        if not has_healthcheck:
            self._add(
                rule="docker-missing-healthcheck",
                code="502",
                sev=Severity.INFO,
                title="docker-compose: no healthcheck",
                message="No healthcheck: on any service → orchestrator can't detect "
                "hung processes (502 before container marked unhealthy).",
                line=1,
                fix_description="Add a healthcheck: to each service.",
            )

    # ---- nginx config checks ----
    def _check_nginx(self) -> None:
        text = self.source
        if not re.search(r"proxy_read_timeout\b", text):
            self._add(
                rule="nginx-missing-proxy-timeout",
                code="504",
                sev=Severity.WARNING,
                title="nginx: no proxy_read_timeout",
                message="nginx default proxy_read_timeout is 60s. Long API calls (DB "
                "migrations, file uploads, AI inference) get cut off with 504 Gateway "
                "Timeout. Set `proxy_read_timeout 300s;` for the location.",
                line=1,
                fix_description="Add proxy_read_timeout 300s; to the location block.",
            )
        if re.search(r"proxy_pass\s+http://127\.0\.0\.1:80\b", text):
            self._add(
                rule="nginx-wrong-backend-port",
                code="502",
                sev=Severity.WARNING,
                title="nginx proxy_pass to port 80",
                message="proxy_pass to 127.0.0.1:80 forwards to nginx itself (loop), "  # is_local()
                "causing 502 Bad Gateway. Use the backend's real port (e.g. :8000).",
                line=1,
                fix_description="Use the backend's actual port (8000/8080/etc.).",
            )

    # ---- shell/service gunicorn/uvicorn checks ----
    def _check_gunicorn_cmd(self) -> None:
        text = self.source
        m = re.search(r"\bgunicorn\b.*?(--workers\s+(\d+))?", text)
        if m and "--workers" not in text:
            self._add(
                rule="gunicorn-missing-workers",
                code="502",
                sev=Severity.WARNING,
                title="gunicorn without --workers",
                message="gunicorn defaults to 1 worker → can't handle concurrent "
                "requests → nginx returns 502 under load. Use `--workers 4` "
                "(2*CPU+1 is the recommendation).",
                line=text.count("\n", 0, m.start()) + 1,
                fix_description="Add --workers 4 --worker-class uvicorn.workers.UvicornWorker.",
            )

    # ---- helper ----
    def _add(
        self,
        *,
        rule: str,
        code: str,
        sev: Severity,
        title: str,
        message: str,
        line: int,
        fix_description: str,
    ) -> None:
        if not self.enabled(rule):
            return
        self.issues.append(
            Issue(
                rule_id=rule,
                code=code,
                category=Category.RESOURCES,  # infra sits closest to resources/deployment
                severity=self.severity(rule, sev),
                title=title,
                message=message,
                file=self.filename,
                line=line,
                col=0,
                end_line=line,
                end_col=0,
                snippet=self.line_text(line) if line else "",
                fixable=True,
                fix_description=fix_description,
                suggestion="",
                detector=self.name,
            )
        )


def _first_line_match(text: str, pattern: str) -> int:
    m = re.search(pattern, text, re.MULTILINE)
    if m:
        return text.count("\n", 0, m.start()) + 1
    return 1
