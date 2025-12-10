# Copyright (c) 2021 Dell, Inc. or its subsidiaries
# Copyright 2024 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Unit tests for async Redfish task monitor."""

import asyncio
from http import client as http_client
import json
from unittest import mock

from ironic.common.redfish import exceptions
from ironic.common.redfish import taskmonitor
from ironic.tests import base


class AsyncTaskMonitorTestCase(base.TestCase):
    """Test AsyncTaskMonitor class."""

    def setUp(self):
        super().setUp()
        self.mock_connector = mock.AsyncMock()
        self.task_uri = '/redfish/v1/TaskService/Tasks/1'

        self.task_json = {
            '@odata.id': '/redfish/v1/TaskService/Tasks/1',
            'Id': '1',
            'Name': 'Task 1',
            'TaskState': 'Running',
            'TaskStatus': 'OK',
            'PercentComplete': 50
        }

    def test_init_with_response_accepted(self):
        """Test initialization with 202 Accepted response."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {
            'Location': self.task_uri,
            'Retry-After': '5'
        }

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            self.assertEqual(self.task_uri, monitor.task_monitor_uri)
            self.assertTrue(monitor.is_processing)
            self.assertIsNotNone(monitor.task_resource)

        asyncio.run(run_test())

    def test_init_with_response_no_content(self):
        """Test initialization with 202 Accepted but no content."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = None
        mock_response.headers = {
            'Location': self.task_uri
        }

        self.mock_connector.get = mock.AsyncMock(return_value=mock_response)

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            self.assertIsNone(monitor.task_resource)

        asyncio.run(run_test())

    def test_init_no_response(self):
        """Test initialization without initial response."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {}

        self.mock_connector.get = mock.AsyncMock(return_value=mock_response)

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri
            )
            await monitor._initialize()

            self.mock_connector.get.assert_called_once_with(
                path=self.task_uri
            )
            self.assertIsNotNone(monitor.task_resource)

        asyncio.run(run_test())

    def test_refresh_still_processing(self):
        """Test refresh when task is still processing."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {}

        self.mock_connector.get = mock.AsyncMock(return_value=mock_response)

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            # Update progress
            updated_json = self.task_json.copy()
            updated_json['PercentComplete'] = 75
            mock_response.json.return_value = updated_json

            await monitor.refresh()

            self.assertTrue(monitor.is_processing)
            self.assertIsNotNone(monitor.task_resource)
            self.assertEqual(75,
                             monitor.task_resource.json['PercentComplete'])

        asyncio.run(run_test())

    def test_refresh_completed(self):
        """Test refresh when task has completed."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {}

        completed_response = mock.MagicMock()
        completed_response.status_code = http_client.OK
        completed_response.headers = {}

        self.mock_connector.get = mock.AsyncMock(
            return_value=completed_response
        )

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            # Change mock to return completed
            self.mock_connector.get.return_value = completed_response

            await monitor.refresh()

            self.assertFalse(monitor.is_processing)
            self.assertIsNone(monitor.task_resource)

        asyncio.run(run_test())

    def test_is_processing(self):
        """Test is_processing property."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            self.assertTrue(monitor.is_processing)

            # Change to completed
            monitor._response.status_code = http_client.OK
            self.assertFalse(monitor.is_processing)

        asyncio.run(run_test())

    def test_check_is_processing(self):
        """Test check_is_processing method."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json

        completed_response = mock.MagicMock()
        completed_response.status_code = http_client.OK

        self.mock_connector.get = mock.AsyncMock(
            return_value=completed_response
        )

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )
            await monitor._initialize()

            # Should refresh and return False
            result = await monitor.check_is_processing()

            self.assertFalse(result)
            self.mock_connector.get.assert_called_with(path=self.task_uri)

        asyncio.run(run_test())

    def test_sleep_for_default(self):
        """Test sleep_for with no Retry-After header."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.headers = {}

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )

            self.assertEqual(1, monitor.sleep_for)

        asyncio.run(run_test())

    def test_sleep_for_integer(self):
        """Test sleep_for with integer Retry-After."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.headers = {'Retry-After': '10'}

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )

            self.assertEqual(10, monitor.sleep_for)

        asyncio.run(run_test())

    def test_cancellable_true(self):
        """Test cancellable property when DELETE is allowed."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.headers = {'Allow': 'DELETE'}

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )

            self.assertTrue(monitor.cancellable)

        asyncio.run(run_test())

    def test_cancellable_false(self):
        """Test cancellable property when DELETE is not allowed."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.headers = {'Allow': 'GET'}

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                mock_response
            )

            self.assertFalse(monitor.cancellable)

        asyncio.run(run_test())

    def test_wait_completes(self):
        """Test wait method when task completes."""
        processing_response = mock.MagicMock()
        processing_response.status_code = http_client.ACCEPTED
        processing_response.content = json.dumps(self.task_json).encode(
            'utf-8'
        )
        processing_response.json.return_value = self.task_json
        processing_response.headers = {'Retry-After': '0'}

        completed_response = mock.MagicMock()
        completed_response.status_code = http_client.OK
        completed_response.headers = {}

        # First call returns processing, second returns completed
        self.mock_connector.get = mock.AsyncMock(
            side_effect=[processing_response, completed_response]
        )

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                processing_response
            )
            await monitor._initialize()

            await monitor.wait(timeout_sec=10)

            # Should have called refresh once during wait
            self.assertEqual(2, self.mock_connector.get.call_count)

        asyncio.run(run_test())

    def test_wait_timeout(self):
        """Test wait method timeout."""
        processing_response = mock.MagicMock()
        processing_response.status_code = http_client.ACCEPTED
        processing_response.content = json.dumps(self.task_json).encode(
            'utf-8'
        )
        processing_response.json.return_value = self.task_json
        processing_response.headers = {'Retry-After': '0'}

        # Always return processing
        self.mock_connector.get = mock.AsyncMock(
            return_value=processing_response
        )

        async def run_test():
            monitor = taskmonitor.AsyncTaskMonitor(
                self.mock_connector,
                self.task_uri,
                processing_response
            )
            await monitor._initialize()

            try:
                await monitor.wait(timeout_sec=1)
                return None  # Should not reach here
            except exceptions.ConnectionError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.ConnectionError)
        self.assertIn('Timeout', str(exception))

    def test_from_response_with_location(self):
        """Test from_response with Location header."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {'Location': self.task_uri}

        async def run_test():
            monitor = await taskmonitor.AsyncTaskMonitor.from_response(
                self.mock_connector,
                mock_response,
                '/redfish/v1/Systems/1'
            )

            self.assertEqual(self.task_uri, monitor.task_monitor_uri)
            self.assertTrue(monitor.is_processing)

        asyncio.run(run_test())

    def test_from_response_with_odata_id(self):
        """Test from_response with @odata.id in body."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps(self.task_json).encode('utf-8')
        mock_response.json.return_value = self.task_json
        mock_response.headers = {}

        async def run_test():
            monitor = await taskmonitor.AsyncTaskMonitor.from_response(
                self.mock_connector,
                mock_response,
                '/redfish/v1/Systems/1'
            )

            self.assertEqual(self.task_uri, monitor.task_monitor_uri)

        asyncio.run(run_test())

    def test_from_response_missing_location(self):
        """Test from_response without Location header."""
        mock_response = mock.MagicMock()
        mock_response.status_code = http_client.ACCEPTED
        mock_response.content = json.dumps({}).encode('utf-8')
        mock_response.json.return_value = {}
        mock_response.headers = {}

        async def run_test():
            try:
                await taskmonitor.AsyncTaskMonitor.from_response(
                    self.mock_connector,
                    mock_response,
                    '/redfish/v1/Systems/1'
                )
                return None  # Should not reach here
            except exceptions.MissingHeaderError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.MissingHeaderError)
