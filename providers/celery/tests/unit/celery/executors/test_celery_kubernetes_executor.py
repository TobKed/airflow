#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from unittest import mock

import pytest

from airflow.callbacks.callback_requests import CallbackRequest, DagCallbackRequest
from airflow.configuration import conf
from airflow.providers.celery.executors.celery_executor import CeleryExecutor
from airflow.providers.celery.executors.celery_kubernetes_executor import CeleryKubernetesExecutor
from airflow.providers.cncf.kubernetes.executors.kubernetes_executor import KubernetesExecutor

from tests_common.test_utils.version_compat import AIRFLOW_V_3_0_PLUS

KUBERNETES_QUEUE = "kubernetes"


@pytest.mark.skipif(AIRFLOW_V_3_0_PLUS, reason="Airflow 3 does not support this executor anymore")
class TestCeleryKubernetesExecutor:
    def test_supports_pickling(self):
        assert CeleryKubernetesExecutor.supports_pickling

    def test_supports_sentry(self):
        assert not CeleryKubernetesExecutor.supports_sentry

    def test_is_local_default_value(self):
        assert not CeleryKubernetesExecutor.is_local

    def test_is_production_default_value(self):
        assert CeleryKubernetesExecutor.is_production

    def test_serve_logs_default_value(self):
        assert not CeleryKubernetesExecutor.serve_logs

    def test_cli_commands_vended(self):
        assert CeleryKubernetesExecutor.get_cli_commands()

    def test_queued_tasks(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        celery_queued_tasks = {("dag_id", "task_id", "2020-08-30", 1): "queued_command"}
        k8s_queued_tasks = {("dag_id_2", "task_id_2", "2020-08-30", 2): "queued_command"}

        celery_executor_mock.queued_tasks = celery_queued_tasks
        k8s_executor_mock.queued_tasks = k8s_queued_tasks

        expected_queued_tasks = {**celery_queued_tasks, **k8s_queued_tasks}
        assert cke.queued_tasks == expected_queued_tasks

    def test_running(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        celery_running_tasks = {("dag_id", "task_id", "2020-08-30", 1)}
        k8s_running_tasks = {("dag_id_2", "task_id_2", "2020-08-30", 2)}

        celery_executor_mock.running = celery_running_tasks
        k8s_executor_mock.running = k8s_running_tasks

        assert cke.running == celery_running_tasks.union(k8s_running_tasks)

    def test_start(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        cke.start()

        celery_executor_mock.start.assert_called()
        k8s_executor_mock.start.assert_called()

    @pytest.mark.parametrize("test_queue", ["any-other-queue", KUBERNETES_QUEUE])
    @mock.patch.object(CeleryExecutor, "queue_command")
    @mock.patch.object(KubernetesExecutor, "queue_command")
    def test_queue_command(self, k8s_queue_cmd, celery_queue_cmd, test_queue):
        kwargs = dict(
            command=["airflow", "run", "dag"],
            priority=1,
            queue="default",
        )
        kwarg_values = kwargs.values()
        cke = CeleryKubernetesExecutor(CeleryExecutor(), KubernetesExecutor())

        simple_task_instance = mock.MagicMock()
        simple_task_instance.queue = test_queue

        cke.queue_command(simple_task_instance, **kwargs)

        if test_queue == KUBERNETES_QUEUE:
            k8s_queue_cmd.assert_called_once_with(simple_task_instance, *kwarg_values)
            celery_queue_cmd.assert_not_called()
        else:
            celery_queue_cmd.assert_called_once_with(simple_task_instance, *kwarg_values)
            k8s_queue_cmd.assert_not_called()

    @pytest.mark.parametrize("test_queue", ["any-other-queue", KUBERNETES_QUEUE])
    def test_queue_task_instance(self, test_queue):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        ti = mock.MagicMock()
        ti.queue = test_queue

        kwargs = dict(
            task_instance=ti,
            mark_success=False,
            pickle_id=None,
            ignore_all_deps=False,
            ignore_depends_on_past=False,
            wait_for_past_depends_before_skipping=False,
            ignore_task_deps=False,
            ignore_ti_state=False,
            pool=None,
            cfg_path=None,
        )
        cke.queue_task_instance(**kwargs)
        if test_queue == KUBERNETES_QUEUE:
            k8s_executor_mock.queue_task_instance.assert_called_once_with(**kwargs)
            celery_executor_mock.queue_task_instance.assert_not_called()
        else:
            celery_executor_mock.queue_task_instance.assert_called_once_with(**kwargs)
            k8s_executor_mock.queue_task_instance.assert_not_called()

    @pytest.mark.parametrize(
        "celery_has, k8s_has, cke_has",
        [
            (True, True, True),
            (False, True, True),
            (True, False, True),
            (False, False, False),
        ],
    )
    def test_has_tasks(self, celery_has, k8s_has, cke_has):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        celery_executor_mock.has_task.return_value = celery_has
        k8s_executor_mock.has_task.return_value = k8s_has
        ti = mock.MagicMock()
        assert cke.has_task(ti) == cke_has
        celery_executor_mock.has_task.assert_called_once_with(ti)
        if not celery_has:
            k8s_executor_mock.has_task.assert_called_once_with(ti)

    @pytest.mark.parametrize("num_k8s, num_celery", [(1, 0), (0, 1), (2, 1)])
    def test_adopt_tasks(self, num_k8s, num_celery):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()

        def mock_ti(queue):
            ti = mock.MagicMock()
            ti.queue = queue
            return ti

        celery_tis = [mock_ti("default") for _ in range(num_celery)]
        k8s_tis = [mock_ti(KUBERNETES_QUEUE) for _ in range(num_k8s)]

        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)
        cke.try_adopt_task_instances(celery_tis + k8s_tis)
        celery_executor_mock.try_adopt_task_instances.assert_called_once_with(celery_tis)
        k8s_executor_mock.try_adopt_task_instances.assert_called_once_with(k8s_tis)

    def test_log_is_fetched_from_k8s_executor_only_for_k8s_queue(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)
        simple_task_instance = mock.MagicMock()
        simple_task_instance.queue = KUBERNETES_QUEUE
        cke.get_task_log(ti=simple_task_instance, try_number=1)
        k8s_executor_mock.get_task_log.assert_called_once_with(ti=simple_task_instance, try_number=1)

        k8s_executor_mock.reset_mock()

        simple_task_instance.queue = "test-queue"
        log = cke.get_task_log(ti=simple_task_instance, try_number=1)
        k8s_executor_mock.get_task_log.assert_not_called()
        assert log == ([], [])

    def test_get_event_buffer(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        dag_ids = ["dag_ids"]

        events_in_celery = {("dag_id", "task_id", "2020-08-30", 1): ("failed", "failed task")}
        events_in_k8s = {("dag_id_2", "task_id_2", "2020-08-30", 1): ("success", None)}

        celery_executor_mock.get_event_buffer.return_value = events_in_celery
        k8s_executor_mock.get_event_buffer.return_value = events_in_k8s

        events = cke.get_event_buffer(dag_ids)

        assert events == {**events_in_celery, **events_in_k8s}

        celery_executor_mock.get_event_buffer.assert_called_once_with(dag_ids)
        k8s_executor_mock.get_event_buffer.assert_called_once_with(dag_ids)

    def test_end(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        cke.end()

        celery_executor_mock.end.assert_called_once()
        k8s_executor_mock.end.assert_called_once()

    def test_terminate(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        cke = CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        cke.terminate()

        celery_executor_mock.terminate.assert_called_once()
        k8s_executor_mock.terminate.assert_called_once()

    def test_job_id_setter(self):
        cel_exec = CeleryExecutor()
        k8s_exec = KubernetesExecutor()
        cel_k8s_exec = CeleryKubernetesExecutor(cel_exec, k8s_exec)
        job_id = "this-job-id"
        cel_k8s_exec.job_id = job_id
        assert cel_exec.job_id == k8s_exec.job_id == cel_k8s_exec.job_id == job_id

    def test_kubernetes_executor_knows_its_queue(self):
        celery_executor_mock = mock.MagicMock()
        k8s_executor_mock = mock.MagicMock()
        CeleryKubernetesExecutor(celery_executor_mock, k8s_executor_mock)

        assert k8s_executor_mock.kubernetes_queue == conf.get(
            "celery_kubernetes_executor", "kubernetes_queue"
        )

    def test_send_callback(self):
        cel_exec = CeleryExecutor()
        k8s_exec = KubernetesExecutor()
        cel_k8s_exec = CeleryKubernetesExecutor(cel_exec, k8s_exec)
        cel_k8s_exec.callback_sink = mock.MagicMock()

        if AIRFLOW_V_3_0_PLUS:
            callback = DagCallbackRequest(
                filepath="fake", dag_id="fake", run_id="fake", bundle_name="testing", bundle_version=None
            )
        else:
            callback = CallbackRequest(full_filepath="fake")
        cel_k8s_exec.send_callback(callback)

        cel_k8s_exec.callback_sink.send.assert_called_once_with(callback)
