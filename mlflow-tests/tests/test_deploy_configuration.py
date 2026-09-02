"""Unit coverage for test-deployment topology decisions."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


_DEPLOY_PATH = Path(__file__).parents[2] / ".github" / "actions" / "deploy" / "deploy.py"
_DEPLOY_SPEC = importlib.util.spec_from_file_location("mlflow_operator_deploy", _DEPLOY_PATH)
assert _DEPLOY_SPEC is not None and _DEPLOY_SPEC.loader is not None
_DEPLOY_MODULE = importlib.util.module_from_spec(_DEPLOY_SPEC)
_DEPLOY_SPEC.loader.exec_module(_DEPLOY_MODULE)


@pytest.fixture(scope="module", autouse=True)
def create_experiments_and_runs() -> dict:
    """Override the integration bootstrap fixture for deployment-policy tests."""
    return {}


@pytest.mark.parametrize(
    ("artifact_storage", "backend_store", "registry_store", "expected"),
    [
        ("file", "postgres", "postgres", False),
        ("s3", "sqlite", "sqlite", False),
        ("s3", "sqlite", "postgres", False),
        ("s3", "postgres", "sqlite", False),
        ("s3", "postgres", "postgres", True),
        ("externals3", "postgres", "postgres", True),
    ],
)
def test_trace_archival_requires_object_storage_and_remote_metadata(
    artifact_storage: str,
    backend_store: str,
    registry_store: str,
    expected: bool,
) -> None:
    deployer = object.__new__(_DEPLOY_MODULE.MLflowDeployer)
    deployer.args = SimpleNamespace(
        artifact_storage=artifact_storage,
        backend_store=backend_store,
        registry_store=registry_store,
    )

    assert deployer._trace_archival_enabled() is expected


@pytest.mark.parametrize(
    ("backend_store", "registry_store", "expected"),
    [
        ("sqlite", "sqlite", False),
        ("sqlite", "postgres", False),
        ("postgres", "sqlite", False),
        ("postgres", "postgres", True),
    ],
)
def test_generated_s3_cr_only_enables_safe_trace_archival(
    backend_store: str,
    registry_store: str,
    expected: bool,
) -> None:
    deployer = object.__new__(_DEPLOY_MODULE.MLflowDeployer)
    deployer.args = SimpleNamespace(
        backend_store=backend_store,
        registry_store=registry_store,
        artifact_storage="s3",
        namespace="opendatahub",
        mlflow_image="localhost/mlflow:test",
        backend_store_uri="sqlite:////mlflow/mlflow.db",
        registry_store_uri="sqlite:////mlflow/mlflow.db",
        serve_artifacts="true",
        s3_bucket="mlpipeline",
        s3_endpoint="http://minio-service:9000",
        trace_archival_retention="1m",
        artifacts_destination="file:///mlflow/artifacts",
        artifacts_server=False,
        workspace_label_selector="",
        ca_bundle_configmap="",
        ca_bundle_path="",
    )
    deployer._tls_ca_bundle_cm = None
    deployer._ca_cert_pem = None
    deployer.run_command = lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", "")
    deployer.wait_for_deployment_to_exist = lambda *args, **kwargs: None
    deployer.wait_for_mlflow_ready = lambda *args, **kwargs: None

    deployer.deploy_mlflow()

    mlflow_cr = yaml.safe_load(Path("/tmp/mlflow-cr.yaml").read_text())
    assert ("traceArchival" in mlflow_cr["spec"]) is expected
    if not expected:
        assert mlflow_cr["spec"]["storage"]["accessModes"] == ["ReadWriteOnce"]
    else:
        assert "storage" not in mlflow_cr["spec"]
