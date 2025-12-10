# Copyright (c) 2021 Dell, Inc. or its subsidiaries
# Copyright 2024 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Async Task Monitor for Redfish asynchronous operations."""

import asyncio
from datetime import datetime
from http import client as http_client
from urllib.parse import urljoin

from dateutil import parser
from oslo_log import log

from ironic.common.redfish import exceptions
from ironic.common.redfish import resource

LOG = log.getLogger(__name__)


class AsyncTaskMonitor:
    """Monitor for asynchronous Redfish operations.

    This class tracks the progress of long-running Redfish operations
    that return HTTP 202 Accepted with a task monitor URI.
    """

    def __init__(self, connector, task_monitor_uri, response=None):
        """Initialize an async task monitor.

        :param connector: AsyncConnector instance
        :param task_monitor_uri: URI for monitoring the task
        :param response: Optional initial response from the operation
        """
        self._connector = connector
        self._task_monitor_uri = task_monitor_uri
        self._task_resource = None
        self._response = response

    async def _initialize(self):
        """Initialize the task monitor.

        If we have an initial response with status 202 and content,
        use it to create the task resource. Otherwise, refresh to get
        the current state.
        """
        if (self._response and self._response.status_code
                == http_client.ACCEPTED):
            if self._response.content:
                try:
                    json_data = self._response.json()
                    self._task_resource = resource.AsyncResource(
                        self._connector,
                        self._task_monitor_uri,
                        json_data
                    )
                except Exception:
                    # If we can't parse the response, just refresh
                    await self.refresh()
            else:
                # Empty response body, refresh to get current state
                await self.refresh()
        else:
            # Not a 202 response, refresh to get current state
            await self.refresh()

        return self

    async def refresh(self):
        """Refresh the task state.

        Retrieves the current state of the task from the BMC.

        :raises: ConnectionError on request failures
        :raises: Various HTTP exceptions on HTTP errors
        """
        self._response = await self._connector.get(
            path=self.task_monitor_uri
        )

        if self._response.status_code == http_client.ACCEPTED:
            # Task is still processing
            if not self._response.content:
                self._task_resource = None
                return

            # Parse task data
            json_data = self._response.json()
            # Always create a new resource with updated data
            self._task_resource = resource.AsyncResource(
                self._connector,
                self._task_monitor_uri,
                json_data
            )
        else:
            # Task completed (or failed)
            self._task_resource = None

    @property
    def task_monitor_uri(self):
        """Get the task monitor URI.

        :returns: The task monitor URI
        """
        return self._task_monitor_uri

    @property
    def is_processing(self):
        """Check if the task is still processing.

        :returns: True if task is processing, False otherwise
        """
        return self._response.status_code == http_client.ACCEPTED

    async def check_is_processing(self):
        """Refresh and check if the task is still processing.

        :returns: True if task is processing, False otherwise
        """
        if not self.is_processing:
            return False

        await self.refresh()

        return self.is_processing

    @property
    def sleep_for(self):
        """Get recommended sleep duration before next poll.

        Uses Retry-After header if present, defaults to 1 second.

        :returns: Number of seconds to wait before next poll
        """
        retry_after = self._response.headers.get('Retry-After')
        if retry_after is None:
            return 1

        # Retry-After can be either a number of seconds or an HTTP date
        if isinstance(retry_after, int) or retry_after.isdigit():
            return int(retry_after)

        # Parse as HTTP date
        try:
            retry_time = parser.parse(retry_after)
            delay = (retry_time - datetime.now().astimezone()).total_seconds()
            return max(0, delay)
        except (ValueError, TypeError):
            # If parsing fails, default to 1 second
            return 1

    @property
    def cancellable(self):
        """Check if the task can be cancelled.

        :returns: True if task is cancellable, False otherwise
        """
        allow = self._response.headers.get('Allow')

        if allow and 'DELETE' in allow.upper():
            return True

        return False

    @property
    def task_resource(self):
        """Get the task resource.

        :returns: AsyncResource for the task, or None if not available
        """
        return self._task_resource

    @property
    def response(self):
        """Get the raw response.

        :returns: httpx.Response object
        """
        return self._response

    async def wait(self, timeout_sec):
        """Wait for the task to complete.

        Polls the task monitor URI until the task completes or times out.

        :param timeout_sec: Maximum time to wait in seconds
        :raises: ConnectionError when timeout is reached
        """
        timeout_at = asyncio.get_event_loop().time() + timeout_sec

        while await self.check_is_processing():
            sleep_duration = self.sleep_for

            LOG.debug('Waiting for task monitor %(url)s; sleeping for '
                      '%(sleep)s seconds',
                      {'url': self.task_monitor_uri,
                       'sleep': sleep_duration})

            await asyncio.sleep(sleep_duration)

            if (asyncio.get_event_loop().time() >= timeout_at
                    and await self.check_is_processing()):
                msg = (f'Timeout waiting for task monitor '
                       f'{self.task_monitor_uri} '
                       f'(timeout = {timeout_sec})')
                raise exceptions.ConnectionError(
                    url=self.task_monitor_uri,
                    error=msg
                )

    @staticmethod
    async def from_response(connector, response, target_uri):
        """Create TaskMonitor from an HTTP response.

        :param connector: AsyncConnector instance
        :param response: httpx.Response from async operation
        :param target_uri: URI that initiated the async operation
        :returns: AsyncTaskMonitor instance
        :raises: MissingHeaderError if Location header is missing
        """
        json_data = {}
        if response.content:
            try:
                json_data = response.json()
            except Exception:
                pass

        # Get task monitor URI from Location header
        header = 'Location'
        task_monitor_uri = response.headers.get(header)

        # Check if response body contains @odata.id
        task_uri_data = json_data.get('@odata.id')
        if task_uri_data:
            task_monitor_uri = urljoin(task_monitor_uri or target_uri,
                                       task_uri_data)

        if not task_monitor_uri:
            raise exceptions.MissingHeaderError(header=header)

        monitor = AsyncTaskMonitor(connector, task_monitor_uri, response)
        await monitor._initialize()
        return monitor
