"""pyerrorfix detectors package."""

from pyerrorfix.detectors.asyncio_err import AsyncioDetector
from pyerrorfix.detectors.auth_security import AuthSecurityDetector
from pyerrorfix.detectors.concurrency import ConcurrencyDetector
from pyerrorfix.detectors.core_python import CorePythonDetector
from pyerrorfix.detectors.database import DatabaseDetector
from pyerrorfix.detectors.deprecation import DeprecationDetector
from pyerrorfix.detectors.files import FileDetector
from pyerrorfix.detectors.imports import ImportDetector
from pyerrorfix.detectors.infra_deploy import InfraDeployDetector
from pyerrorfix.detectors.linter_quality import LinterQualityDetector
from pyerrorfix.detectors.logging_err import LoggingDetector
from pyerrorfix.detectors.network_io import NetworkIoDetector
from pyerrorfix.detectors.resources import ResourceDetector
from pyerrorfix.detectors.security import SecurityDetector
from pyerrorfix.detectors.syntax import SyntaxDetector
from pyerrorfix.detectors.testing import TestingDetector
from pyerrorfix.detectors.typing_err import TypingDetector
from pyerrorfix.detectors.web_api import WebApiDetector

ALL_DETECTORS = [
    AsyncioDetector,
    AuthSecurityDetector,
    ConcurrencyDetector,
    CorePythonDetector,
    DatabaseDetector,
    DeprecationDetector,
    FileDetector,
    ImportDetector,
    InfraDeployDetector,
    LinterQualityDetector,
    LoggingDetector,
    NetworkIoDetector,
    ResourceDetector,
    SecurityDetector,
    SyntaxDetector,
    TestingDetector,
    TypingDetector,
    WebApiDetector,
]

__all__ = ["ALL_DETECTORS"]
