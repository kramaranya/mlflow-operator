"""Live trace-archival smoke coverage against object storage.

Creates several real traces, persists them as DB-backed spans via OTLP
log_spans (prefixed tracking URI, then unprefixed Kind port-forward path),
waits them past the harness-configured archival retention, runs a Job from
the operator-managed CronJob template, then verifies that archive objects
were written, traces remain readable via MLflow, and
`SPANS_LOCATION=ARCHIVE_REPO`.
"""

from __future__ import annotations

import logging
from typing import ClassVar

import mlflow
import pytest

from .actions import (
    action_create_experiment,
    action_persist_archival_spans_via_otlp,
    action_prepare_archival_smoke,
    action_reload_archival_traces,
    action_run_archival_job_from_cronjob,
    action_seed_archival_traces,
    action_wait_for_archival_retention,
    action_wait_for_archive_objects,
)
from .base import TestBase
from .constants.config import Config
from .shared import TestData, TestStep
from .validations import (
    validate_archival_experiment_created,
    validate_archival_job_completed,
    validate_archival_smoke_ready,
    validate_archival_traces_db_backed,
    validate_archival_traces_readable,
    validate_archival_traces_visible,
    validate_archive_objects_written,
    validate_no_error,
)

logger = logging.getLogger(__name__)


@pytest.mark.smoke
class TestTraceArchival(TestBase):
    """Live trace-archival Job coverage using the shared actions/validations style."""

    test_scenarios: ClassVar[list[TestData]] = [
        TestData(
            test_name="Job created from the trace archival CronJob archives traces and keeps them readable",
            workspace_to_use=Config.WORKSPACES[0],
            test_steps=[
                TestStep(
                    action_func=action_prepare_archival_smoke,
                    validate_func=validate_archival_smoke_ready,
                ),
                TestStep(
                    action_func=action_create_experiment,
                    validate_func=validate_archival_experiment_created,
                ),
                TestStep(
                    action_func=action_seed_archival_traces,
                    validate_func=validate_archival_traces_visible,
                ),
                TestStep(
                    action_func=action_persist_archival_spans_via_otlp,
                    validate_func=validate_archival_traces_db_backed,
                ),
                TestStep(
                    action_func=action_wait_for_archival_retention,
                    validate_func=validate_no_error,
                ),
                TestStep(
                    action_func=action_run_archival_job_from_cronjob,
                    validate_func=validate_archival_job_completed,
                ),
                TestStep(
                    action_func=action_wait_for_archive_objects,
                    validate_func=validate_archive_objects_written,
                ),
                TestStep(
                    action_func=action_reload_archival_traces,
                    validate_func=validate_archival_traces_readable,
                ),
            ],
        ),
    ]

    @pytest.mark.skipif(
        Config.ARTIFACT_STORAGE != "s3" or not Config.TRACE_ARCHIVAL_ENABLED,
        reason="trace archival live Job requires object storage and an enabled trace archival configuration",
    )
    @pytest.mark.parametrize("test_data", test_scenarios, ids=lambda x: x.test_name)
    def test_trace_archival_job_archives_multiple_traces(self, test_data: TestData) -> None:
        logger.info("=" * 80)
        logger.info("Starting test: %s", test_data.test_name)
        logger.info("Workspace: %s", test_data.workspace_to_use)
        logger.info("=" * 80)

        self.test_context.last_error = None
        self.test_context.user_client = self.admin_client
        if test_data.workspace_to_use:
            self.test_context.active_workspace = test_data.workspace_to_use
            mlflow.set_workspace(self.test_context.active_workspace)

        self._execute_test_steps(test_data)
