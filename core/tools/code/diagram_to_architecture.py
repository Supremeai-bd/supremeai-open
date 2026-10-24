import base64
import os
import tempfile
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core.logging_config import logger
from core.upload_validator import validate_upload

router = APIRouter(prefix="/diagram", tags=["diagram-to-architecture"])


# বাংলা মন্তব্য: Terraform, Kubernetes ও Schema কোডের জন্য ডেটাক্লাস-সদৃশ টাইপ।
class TerraformCode:
    def __init__(self, code: str, provider: str = "gcp"):
        self.code = code
        self.provider = provider

    def to_dict(self) -> dict[str, Any]:
        return {"iac_tool": "terraform", "provider": self.provider, "code": self.code}


class K8sManifest:
    def __init__(self, code: str):
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {"iac_tool": "kubernetes", "code": self.code}


class SchemaCode:
    def __init__(self, code: str, orm: str = "sqlalchemy"):
        self.code = code
        self.orm = orm

    def to_dict(self) -> dict[str, Any]:
        return {"orm": self.orm, "code": self.code}


class DiagramToArchitecture:
    # বাংলা: আগে vision_model ডিফোল্ট "gpt-4o" ছিল — OpenAI key না থাকলে ডায়াগ্রাম বিশ্লেষণ ব্যর্থ হতো।
    # এখন None দিয়ে gateway task_type="vision" ফেলোভার চেইন ব্যবহার করবে।
    def __init__(self, vision_model: str | None = None):
        self.vision_model = vision_model
        logger.info(
            f"Initialized DiagramToArchitecture with model {self.vision_model or 'auto (gateway-routed)'}"
        )

    def _encode_image(self, image_path: str) -> str:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Diagram not found at {image_path}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def generate_infrastructure(
        self, diagram_path: str, provider: str = "aws", iac_tool: str = "terraform"
    ) -> dict[str, Any]:
        logger.info(f"Generating {iac_tool} for {provider} from diagram: {diagram_path}")
        try:
            base64_image = self._encode_image(diagram_path)
            ext = os.path.splitext(diagram_path)[1].lower().lstrip(".")
            mime = "image/png" if ext in ("png", "") else f"image/{ext}"

            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            prompt = (
                f"You are an expert infrastructure architect. Analyze the provided architecture diagram "
                f"and generate {iac_tool} code for {provider}. "
                "Identify ALL components (VPC, EC2, RDS, S3, Load Balancers, Lambda, API Gateway, etc.) "
                "and their relationships/connections. "
                "Return only valid, production-ready code. No explanations, no markdown fences."
            )

            # ✅ FIXED: added await; pass image via messages kwarg
            result = await router_llm.async_route_and_generate(
                prompt,
                task_type="vision",
                max_cost=0.08,
                images=[{"base64": base64_image, "mime": mime}],
            )
            code = result.get("text", "") if isinstance(result, dict) else ""

            if not code:
                raise RuntimeError("Model returned empty response.")

            components = self._parse_components_from_code(code, iac_tool)
            return {
                "status": "success",
                "iac_tool": iac_tool,
                "provider": provider,
                "identified_components": components,
                "code": code.strip(),
            }
        except Exception as e:
            # ✅ FIXED: ImportError (ModelRouter unavailable) no longer silently returns
            # hardcoded infrastructure — every failure path now surfaces the real error
            # so the API caller knows generation did not actually happen.
            logger.error(f"Architecture generation failed: {e!s}")
            return {"status": "error", "error": str(e)}

    async def to_terraform(self, diagram_path: str, cloud_provider: str = "gcp") -> TerraformCode:
        """হাতে আঁকা ডায়াগ্রাম → Terraform HCL কনফিগারেশন।"""
        logger.info(f"Generating Terraform for {cloud_provider} from: {diagram_path}")
        try:
            base64_image = self._encode_image(diagram_path)
            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            prompt = (
                f"You are an expert {cloud_provider} infrastructure engineer. Analyze the provided architecture "
                f"diagram and generate complete, production-ready Terraform HCL for {cloud_provider}. "
                "Include all resources, variables, and outputs. Return ONLY valid HCL, no markdown."
            )
            result = await router_llm.async_route_and_generate(
                prompt,
                task_type="vision",
                max_cost=0.08,
                images=[{"base64": base64_image, "mime": "image/png"}],
            )
            code = result.get("text", "") if isinstance(result, dict) else ""
            if not code:
                raise RuntimeError("Model returned empty Terraform response.")
            return TerraformCode(code=code.strip(), provider=cloud_provider)
        except Exception as e:
            # ✅ FIXED: removed hardcoded HCL fallback — a generation failure must be
            # visible to the caller, not disguised as a valid (fake) result.
            logger.error(f"Terraform generation failed: {e}")
            raise RuntimeError(f"Terraform generation failed: {e}") from e

    async def to_kubernetes(self, diagram_path: str) -> K8sManifest:
        """Cloud architecture diagram → Kubernetes YAML (Deployment, Service, Ingress)।"""
        logger.info(f"Generating Kubernetes manifests from: {diagram_path}")
        try:
            base64_image = self._encode_image(diagram_path)
            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            prompt = (
                "You are an expert Kubernetes engineer. Analyze the provided architecture diagram and generate "
                "complete Kubernetes YAML including Deployments, Services, ConfigMaps, and Ingress for each "
                "service shown. Return ONLY valid multi-document YAML, no markdown."
            )
            result = await router_llm.async_route_and_generate(
                prompt,
                task_type="vision",
                max_cost=0.08,
                images=[{"base64": base64_image, "mime": "image/png"}],
            )
            code = result.get("text", "") if isinstance(result, dict) else ""
            if not code:
                raise RuntimeError("Model returned empty Kubernetes manifest response.")
            return K8sManifest(code=code.strip())
        except Exception as e:
            # ✅ FIXED: removed hardcoded manifest fallback for the same reason as Terraform above.
            logger.error(f"Kubernetes generation failed: {e}")
            raise RuntimeError(f"Kubernetes generation failed: {e}") from e

    async def to_database_schema(self, er_diagram_path: str, orm: str = "sqlalchemy") -> SchemaCode:
        """ER diagram → SQLAlchemy Model / Prisma Schema।"""
        logger.info(f"Generating {orm} schema from ER diagram: {er_diagram_path}")
        try:
            base64_image = self._encode_image(er_diagram_path)
            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            if orm == "prisma":
                prompt = (
                    "You are an expert database architect. Analyze the provided ER diagram and generate a complete "
                    "Prisma schema with models, relations, and enums. Return ONLY valid Prisma schema, no markdown."
                )
            else:
                prompt = (
                    "You are an expert database architect. Analyze the provided ER diagram and generate complete "
                    "SQLAlchemy ORM models (Python) with relationships, columns, and types. "
                    "Return ONLY valid Python code, no markdown."
                )
            result = await router_llm.async_route_and_generate(
                prompt,
                task_type="vision",
                max_cost=0.08,
                images=[{"base64": base64_image, "mime": "image/png"}],
            )
            code = result.get("text", "") if isinstance(result, dict) else ""
            if not code:
                raise RuntimeError("Model returned empty schema response.")
            return SchemaCode(code=code.strip(), orm=orm)
        except Exception as e:
            # ✅ FIXED: removed hardcoded schema fallback for the same reason as Terraform above.
            logger.error(f"Schema generation failed: {e}")
            raise RuntimeError(f"Schema generation failed: {e}") from e

    async def generate_api_spec(self, diagram_path: str) -> dict[str, Any]:
        """Generate OpenAPI spec from a sequence/flowchart diagram."""
        base64_image = self._encode_image(diagram_path)
        try:
            from brain.model_router import ModelRouter

            router_llm = ModelRouter()
            prompt = (
                "Analyze this sequence diagram or flowchart and generate a valid OpenAPI 3.0 YAML spec. "
                "Identify all API endpoints, request/response schemas, and HTTP methods. "
                "Return only the YAML, no markdown."
            )
            result = await router_llm.async_route_and_generate(
                prompt,
                task_type="vision",
                max_cost=0.06,
                images=[{"base64": base64_image, "mime": "image/png"}],
            )
            yaml_spec = result.get("text", "") if isinstance(result, dict) else ""
            return {"status": "success", "openapi_yaml": yaml_spec}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _parse_components_from_code(self, code: str, iac_tool: str) -> list[dict[str, str]]:
        components: list[dict[str, str]] = []
        for line in code.splitlines():
            line_stripped = line.strip()
            if iac_tool == "terraform":
                if line_stripped.startswith("resource "):
                    parts = line_stripped.split('"')
                    if len(parts) >= 4:
                        components.append({"type": parts[1], "details": parts[3]})
                elif line_stripped.startswith("module "):
                    parts = line_stripped.split('"')
                    if len(parts) >= 2:
                        components.append({"type": "module", "details": parts[1]})
            elif iac_tool in ("cloudformation", "cdk") and "Type:" in line_stripped:
                type_val = line_stripped.replace("Type:", "").strip()
                components.append({"type": type_val, "details": ""})
        return components


_converter = DiagramToArchitecture()


@router.post("/generate")
async def generate_from_diagram(
    file: UploadFile = File(...),
    provider: str = Form("aws"),
    iac_tool: str = Form("terraform"),
):
    """Upload a diagram image and get infrastructure-as-code."""
    await validate_upload(file)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    suffix = os.path.splitext(file.filename or "diagram.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await _converter.generate_infrastructure(
            tmp_path, provider=provider, iac_tool=iac_tool
        )
    finally:
        os.unlink(tmp_path)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("error"))
    return result


@router.post("/to-terraform")
async def api_to_terraform(file: UploadFile = File(...), cloud_provider: str = Form("gcp")):
    """ডায়াগ্রাম → Terraform HCL।"""
    await validate_upload(file)
    suffix = os.path.splitext(file.filename or "diagram.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await _converter.to_terraform(tmp_path, cloud_provider=cloud_provider)
        return {"status": "success", **result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Terraform generation failed: {e}") from e
    finally:
        os.unlink(tmp_path)


@router.post("/to-kubernetes")
async def api_to_kubernetes(file: UploadFile = File(...)):
    """ডায়াগ্রাম → Kubernetes YAML।"""
    await validate_upload(file)
    suffix = os.path.splitext(file.filename or "diagram.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await _converter.to_kubernetes(tmp_path)
        return {"status": "success", **result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kubernetes generation failed: {e}") from e
    finally:
        os.unlink(tmp_path)


@router.post("/to-schema")
async def api_to_schema(file: UploadFile = File(...), orm: str = Form("sqlalchemy")):
    """ER ডায়াগ্রাম → SQLAlchemy/Prisma schema।"""
    await validate_upload(file)
    suffix = os.path.splitext(file.filename or "diagram.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await _converter.to_database_schema(tmp_path, orm=orm)
        return {"status": "success", **result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Schema generation failed: {e}") from e
    finally:
        os.unlink(tmp_path)


@router.post("/api-spec")
async def generate_api_spec(file: UploadFile = File(...)):
    """Upload sequence diagram and get OpenAPI spec."""
    await validate_upload(file)
    suffix = os.path.splitext(file.filename or "diagram.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await _converter.generate_api_spec(tmp_path)
    finally:
        os.unlink(tmp_path)
    return result
