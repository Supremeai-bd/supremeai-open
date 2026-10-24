import json
import os
from typing import Any

from core.logging_config import logger

try:
    import yaml  # type: ignore

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class OnPremiseDeployer:
    """
    Generates Docker Compose + Kubernetes Helm charts for air-gapped deployment.
    Closes Gap #52
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"Initialized OnPremiseDeployer (output_dir={self.output_dir})")

    def generate_compose(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = {
            "version": "3.9",
            "services": {
                "backend": {
                    "image": "supremeai/backend:latest",
                    "build": {"context": "./backend", "dockerfile": "Dockerfile"},
                    "ports": ["8000:8000"],
                    "environment": {
                        "ENV": "production",
                        "GCP_PROJECT_ID": "supremeai-a",
                    },
                    "volumes": ["backend_data:/app/data"],
                    "depends_on": ["postgres", "redis"],
                    "restart": "unless-stopped",
                },
                "frontend": {
                    "image": "supremeai/frontend:latest",
                    "build": {
                        "context": "./apps/studio-client",
                        "dockerfile": "Dockerfile",
                    },
                    "ports": ["3000:3000"],
                    "depends_on": ["backend"],
                    "restart": "unless-stopped",
                },
                "postgres": {
                    "image": "postgres:15-alpine",
                    "environment": {
                        "POSTGRES_USER": "supremeai",
                        "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:-}",
                        "POSTGRES_DB": "supremeai",
                    },
                    "volumes": ["pgdata:/var/lib/postgresql/data"],
                    "restart": "unless-stopped",
                },
                "redis": {
                    "image": "redis:7-alpine",
                    "command": ["redis-server", "--appendonly", "yes"],
                    "volumes": ["redisdata:/data"],
                    "restart": "unless-stopped",
                },
            },
            "volumes": {"pgdata": {}, "redisdata": {}, "backend_data": {}},
        }
        if overrides:
            self._deep_merge(cfg, overrides)
        return cfg

    def generate_helm_chart(
        self,
        release_name: str = "supremeai",
        namespace: str = "default",
        replicas: int = 3,
        image_tag: str = "latest",
    ) -> dict[str, Any]:
        chart: dict[str, Any] = {
            "apiVersion": "v2",
            "name": release_name,
            "description": "SupremeAI 2.0 Helm chart (air-gapped capable)",
            "version": "0.1.0",
            "appVersion": "2.0.0",
        }
        values: dict[str, Any] = {
            "replicaCount": replicas,
            "image": {
                "repository": "supremeai/backend",
                "tag": image_tag,
                "pullPolicy": "IfNotPresent",
            },
            "frontend": {
                "image": {
                    "repository": "supremeai/frontend",
                    "tag": image_tag,
                    "pullPolicy": "IfNotPresent",
                },
                "replicaCount": max(1, replicas // 2),
            },
            "postgres": {
                "image": {"repository": "postgres", "tag": "15-alpine"},
                "auth": {
                    "username": "supremeai",
                    "password": "${POSTGRES_PASSWORD}",
                    "database": "supremeai",
                },
                "persistence": {"size": "20Gi", "storageClass": "standard"},
            },
            "redis": {
                "image": {"repository": "redis", "tag": "7-alpine"},
                "auth": {"enabled": True, "password": "${REDIS_PASSWORD}"},
                "persistence": {"size": "5Gi"},
            },
            "resources": {
                "requests": {"cpu": "500m", "memory": "1Gi"},
                "limits": {"cpu": "2000m", "memory": "4Gi"},
            },
            "autoscaling": {"enabled": True, "minReplicas": 2, "maxReplicas": 20},
            "airgapped": {"enabled": False, "localRegistry": "registry.local:5000"},
            "service": {"type": "ClusterIP", "port": 8000},
        }
        return {"chart": chart, "values": values}

    def write_compose(
        self,
        filename: str = "docker-compose.yml",
        overrides: dict[str, Any] | None = None,
    ) -> str:
        cfg = self.generate_compose(overrides=overrides)
        path = os.path.join(self.output_dir, filename)
        if _YAML_AVAILABLE:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        logger.info(f"Wrote docker-compose to {path}")
        return path

    def write_helm(self, chart_dir: str | None = None) -> str:
        chart_dir = chart_dir or os.path.join(self.output_dir, "helm", "supremeai")
        os.makedirs(chart_dir, exist_ok=True)
        chart = self.generate_helm_chart()
        chart_yaml = chart["chart"]
        values = chart["values"]
        with open(os.path.join(chart_dir, "Chart.yaml"), "w", encoding="utf-8") as f:
            if _YAML_AVAILABLE:
                yaml.dump(chart_yaml, f, default_flow_style=False)
            else:
                json.dump(chart_yaml, f, indent=2)
        with open(os.path.join(chart_dir, "values.yaml"), "w", encoding="utf-8") as f:
            if _YAML_AVAILABLE:
                yaml.dump(values, f, default_flow_style=False)
            else:
                json.dump(values, f, indent=2)
        templates_dir = os.path.join(chart_dir, "templates")
        os.makedirs(templates_dir, exist_ok=True)
        deploy = self._render_deployment(values)
        svc = self._render_service(values)
        with open(os.path.join(templates_dir, "deployment.yaml"), "w", encoding="utf-8") as f:
            f.write(deploy)
        with open(os.path.join(templates_dir, "service.yaml"), "w", encoding="utf-8") as f:
            f.write(svc)
        logger.info(f"Wrote Helm chart to {chart_dir}")
        return chart_dir

    def _render_deployment(self, values: dict[str, Any]) -> str:
        repo = values["image"]["repository"]
        tag = values["image"]["tag"]
        f_repo = values["frontend"]["image"]["repository"]
        f_tag = values["frontend"]["image"]["tag"]
        replicas = values["replicaCount"]
        res = values["resources"]
        air = values.get("airgapped", {})
        air_suffix = f"-{air['localRegistry']}/{repo}" if air.get("enabled") else repo
        f_str = (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: supremeai-backend\n"
            '  namespace: "${RELEASE_NAMESPACE}"\n'
            "spec:\n"
            f"  replicas: {replicas}\n"
            "  selector:\n"
            "    matchLabels:\n"
            "      app: supremeai-backend\n"
            "  template:\n"
            "    metadata:\n"
            "      labels:\n"
            "        app: supremeai-backend\n"
            "    spec:\n"
            "      containers:\n"
            "      - name: backend\n"
            f"        image: {air_suffix}:{tag}\n"
            "        ports:\n"
            "        - containerPort: 8000\n"
            "        resources:\n"
            "          requests:\n"
            f'            cpu: "{res["requests"]["cpu"]}"\n'
            f'            memory: "{res["requests"]["memory"]}"\n'
            "          limits:\n"
            f'            cpu: "{res["limits"]["cpu"]}"\n'
            f'            memory: "{res["limits"]["memory"]}"\n'
            "      imagePullSecrets:\n"
            "{{- if .Values.image.pullSecret }}\n"
            "      - name: regcred\n"
            "{{- end }}\n"
            "---\n"
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: supremeai-frontend\n"
            '  namespace: "${RELEASE_NAMESPACE}"\n'
            "spec:\n"
            f"  replicas: {values['frontend']['replicaCount']}\n"
            "  selector:\n"
            "    matchLabels:\n"
            "      app: supremeai-frontend\n"
            "  template:\n"
            "    metadata:\n"
            "      labels:\n"
            "        app: supremeai-frontend\n"
            "    spec:\n"
            "      containers:\n"
            "      - name: frontend\n"
            f"        image: {f_repo}:{f_tag}\n"
            "        ports:\n"
            "        - containerPort: 3000\n"
        )
        return f_str.replace("${RELEASE_NAMESPACE}", "{{ .Release.Namespace }}")

    def _render_service(self, values: dict[str, Any]) -> str:
        svc_type = values["service"]["type"]
        port = values["service"]["port"]
        return (
            "apiVersion: v1\n"
            "kind: Service\n"
            "metadata:\n"
            "  name: supremeai-backend\n"
            '  namespace: "${RELEASE_NAMESPACE}"\n'
            "spec:\n"
            f"  type: {svc_type}\n"
            "  ports:\n"
            f"  - port: {port}\n"
            "    targetPort: 8000\n"
            "  selector:\n"
            "    app: supremeai-backend\n"
        ).replace("${RELEASE_NAMESPACE}", "{{ .Release.Namespace }}")

    def _deep_merge(self, base: dict[str, Any], overrides: dict[str, Any]) -> None:
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v
