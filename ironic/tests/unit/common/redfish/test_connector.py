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

"""Unit tests for async Redfish connector."""

import asyncio
from http import client as http_client
from unittest import mock

import httpx

from ironic.common.redfish import connector
from ironic.common.redfish import exceptions
from ironic.tests import base


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(self, json_data=None, status_code=200, headers=None):
        self._json_data = json_data or {}
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            request = mock.Mock(url='http://test.com')
            raise httpx.HTTPStatusError('Error', request=request,
                                        response=self)


class TestAsyncConnector(base.TestCase):
    """Test AsyncConnector class."""

    def setUp(self):
        super().setUp()
        self.base_url = 'https://bmc.example.com'
        self.connector = connector.AsyncConnector(
            url=self.base_url,
            verify=True,
            default_request_timeout=60
        )

    def test_context_manager(self):
        """Test async context manager initialization and cleanup."""
        async def run_test():
            async with connector.AsyncConnector(self.base_url) as conn:
                self.assertIsNotNone(conn._session)
                self.assertIsInstance(conn._session, httpx.AsyncClient)
                return conn

        conn = asyncio.run(run_test())
        # Session should be closed after exit
        self.assertIsNone(conn._session)

    def test_get_success(self):
        """Test successful GET request."""
        mock_response = MockResponse(
            json_data={'test': 'data', 'value': 123},
            status_code=200
        )

        async def run_test():
            # Create async methods for the mock session
            async def async_request(*args, **kwargs):
                return mock_response

            async def async_aclose():
                pass

            # Create a mock session class with required async methods
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    result = await conn.get('/test/path')
                    self.assertEqual({'test': 'data', 'value': 123}, result)

        asyncio.run(run_test())

    def test_get_with_headers(self):
        """Test GET request with custom headers."""
        mock_response = MockResponse(json_data={}, status_code=200)

        async def run_test():
            # Track the request calls
            request_calls = []

            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    request_calls.append((args, kwargs))
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    custom_headers = {'X-Custom-Header': 'value'}
                    await conn.get('/test', headers=custom_headers)

                    # Verify headers were passed
                    self.assertEqual(1, len(request_calls))
                    call_kwargs = request_calls[0][1]
                    headers = call_kwargs['headers']
                    self.assertIn('X-Custom-Header', headers)
                    self.assertEqual('value', headers['X-Custom-Header'])

        asyncio.run(run_test())

    def test_get_404_error(self):
        """Test GET request with 404 Not Found error."""
        mock_response = MockResponse(status_code=http_client.NOT_FOUND)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    try:
                        await conn.get('/nonexistent')
                        return None  # Should not reach here
                    except exceptions.ResourceNotFoundError as e:
                        return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.ResourceNotFoundError)

    def test_get_401_error(self):
        """Test GET request with 401 Unauthorized error."""
        mock_response = MockResponse(status_code=http_client.UNAUTHORIZED)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    try:
                        await conn.get('/protected')
                        return None  # Should not reach here
                    except exceptions.AccessError as e:
                        return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.AccessError)

    def test_get_500_error(self):
        """Test GET request with 500 Internal Server Error."""
        mock_response = MockResponse(
            status_code=http_client.INTERNAL_SERVER_ERROR)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    try:
                        await conn.get('/error')
                        return None  # Should not reach here
                    except exceptions.ServerSideError as e:
                        return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.ServerSideError)

    def test_get_connection_error(self):
        """Test GET request with connection error."""
        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    raise httpx.ConnectError('Connection failed')

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    try:
                        await conn.get('/test')
                        return None  # Should not reach here
                    except exceptions.ConnectionError as e:
                        return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.ConnectionError)

    def test_get_timeout_error(self):
        """Test GET request with timeout error."""
        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    raise httpx.TimeoutException('Request timed out')

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    try:
                        await conn.get('/slow')
                        return None  # Should not reach here
                    except exceptions.ConnectionError as e:
                        return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.ConnectionError)

    def test_post_success(self):
        """Test successful POST request."""
        mock_response = MockResponse(
            status_code=201,
            headers={'Location': '/resource/1'}
        )

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    data = {'key': 'value'}
                    response = await conn.post('/create', data=data)
                    self.assertEqual(201, response.status_code)
                    self.assertEqual('/resource/1',
                                     response.headers['Location'])

        asyncio.run(run_test())

    def test_set_http_basic_auth(self):
        """Test setting HTTP basic authentication."""
        async def run_test():
            async with connector.AsyncConnector(self.base_url) as conn:
                conn.set_http_basic_auth('admin', 'password')
                # httpx sets a BasicAuth object, not a tuple
                import httpx
                self.assertIsInstance(conn._session.auth, httpx.BasicAuth)

        asyncio.run(run_test())

    def test_set_http_session_auth(self):
        """Test setting session authentication."""
        async def run_test():
            async with connector.AsyncConnector(self.base_url) as conn:
                token = 'test-token-12345'
                conn.set_http_session_auth(token)
                self.assertIsNone(conn._session.auth)
                self.assertEqual(token, conn._session.headers['X-Auth-Token'])

        asyncio.run(run_test())

    def test_prepare_url_absolute(self):
        """Test URL preparation with absolute URL."""
        url = self.connector._prepare_url('https://other.example.com/path')
        self.assertEqual('https://other.example.com/path', url)

    def test_prepare_url_relative(self):
        """Test URL preparation with relative path."""
        url = self.connector._prepare_url('/redfish/v1/Systems')
        self.assertEqual('https://bmc.example.com/redfish/v1/Systems', url)

    def test_prepare_headers_defaults(self):
        """Test header preparation with defaults."""
        headers = self.connector._prepare_headers(None)
        self.assertEqual('application/json', headers['Content-Type'])
        self.assertEqual('4.0', headers['OData-Version'])
        self.assertEqual('identity', headers['Accept-Encoding'])

    def test_prepare_headers_custom(self):
        """Test header preparation with custom headers."""
        custom = {'X-Custom': 'value', 'Content-Type': 'text/plain'}
        headers = self.connector._prepare_headers(custom)
        self.assertEqual('text/plain', headers['Content-Type'])
        self.assertEqual('value', headers['X-Custom'])
        self.assertEqual('4.0', headers['OData-Version'])

    def test_prepare_headers_remove_default(self):
        """Test removing default header by setting to None."""
        custom = {'Content-Type': None}
        headers = self.connector._prepare_headers(custom)
        self.assertNotIn('Content-Type', headers)
        self.assertEqual('4.0', headers['OData-Version'])

    def test_close(self):
        """Test explicit close method."""
        async def run_test():
            async with connector.AsyncConnector(self.base_url) as conn:
                self.assertIsNotNone(conn._session)
                await conn.close()
                self.assertIsNone(conn._session)

        asyncio.run(run_test())

    def test_delete_success(self):
        """Test successful DELETE request."""
        mock_response = MockResponse(status_code=204)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    response = await conn.delete('/resource/1')
                    self.assertEqual(204, response.status_code)

        asyncio.run(run_test())

    def test_patch_success(self):
        """Test successful PATCH request."""
        mock_response = MockResponse(status_code=200)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    data = {'field': 'new_value'}
                    response = await conn.patch('/resource/1', data=data)
                    self.assertEqual(200, response.status_code)

        asyncio.run(run_test())

    def test_put_success(self):
        """Test successful PUT request."""
        mock_response = MockResponse(status_code=200)

        async def run_test():
            class MockAsyncClient:
                def __init__(self, *args, **kwargs):
                    self.auth = None
                    self.headers = {}

                async def request(self, *args, **kwargs):
                    return mock_response

                async def aclose(self):
                    pass

            with mock.patch('httpx.AsyncClient', MockAsyncClient):
                async with connector.AsyncConnector(self.base_url) as conn:
                    data = {'complete': 'replacement'}
                    response = await conn.put('/resource/1', data=data)
                    self.assertEqual(200, response.status_code)

        asyncio.run(run_test())
