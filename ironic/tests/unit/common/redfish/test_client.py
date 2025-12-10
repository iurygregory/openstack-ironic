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

"""Unit tests for async Redfish client."""

import asyncio
from unittest import mock

from ironic.common.redfish import client
from ironic.common.redfish import exceptions
from ironic.common.redfish import resource
from ironic.tests import base


class TestAsyncRedfishClient(base.TestCase):
    """Test AsyncRedfishClient class."""

    def setUp(self):
        super().setUp()
        self.base_url = 'https://bmc.example.com'
        self.username = 'admin'
        self.password = 'password123'

    def test_init(self):
        """Test client initialization."""
        client_obj = client.AsyncRedfishClient(
            self.base_url,
            username=self.username,
            password=self.password,
            auth_type='basic'
        )

        self.assertEqual(self.base_url, client_obj._base_url)
        self.assertEqual('/redfish/v1', client_obj._root_prefix)
        self.assertEqual('basic', client_obj._auth_type)

    def test_init_invalid_auth_type(self):
        """Test initialization with invalid auth type."""
        self.assertRaises(
            ValueError,
            client.AsyncRedfishClient,
            self.base_url,
            auth_type='invalid'
        )

    def test_ensure_initialized_not_initialized(self):
        """Test accessing methods before initialization."""
        client_obj = client.AsyncRedfishClient(self.base_url)
        self.assertRaises(RuntimeError, client_obj._ensure_initialized)

    def test_close(self):
        """Test explicit close method."""
        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    client_obj = client.AsyncRedfishClient(self.base_url)
                    await client_obj.close()

                    mock_auth.close.assert_called_once()
                    mock_conn.close.assert_called_once()

        asyncio.run(run_test())

    def test_collection_systems(self):
        """Test getting the Systems collection."""
        root_data = {
            'Systems': {'@odata.id': '/redfish/v1/Systems'}
        }

        collection_data = {
            'Members': [
                {'@odata.id': '/redfish/v1/Systems/1'},
                {'@odata.id': '/redfish/v1/Systems/2'},
                {'@odata.id': '/redfish/v1/Systems/3'}
            ]
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(
                    side_effect=[root_data, collection_data]
                )
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        collection = await client_obj.collection('Systems')

                        self.assertIsInstance(
                            collection, resource.AsyncResourceCollection)
                        self.assertEqual(3, len(collection))

        asyncio.run(run_test())

    def test_collection_managers(self):
        """Test getting the Managers collection."""
        root_data = {
            'Managers': {'@odata.id': '/redfish/v1/Managers'}
        }

        collection_data = {
            'Members': [
                {'@odata.id': '/redfish/v1/Managers/BMC'}
            ]
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(
                    side_effect=[root_data, collection_data]
                )
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        collection = await client_obj.collection('Managers')

                        self.assertIsInstance(
                            collection, resource.AsyncResourceCollection)
                        self.assertEqual(1, len(collection))

        asyncio.run(run_test())

    def test_collection_not_found(self):
        """Test getting a collection that doesn't exist."""
        root_data = {
            'Systems': {'@odata.id': '/redfish/v1/Systems'}
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(return_value=root_data)
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        try:
                            await client_obj.collection('NonExistent')
                            return None  # Should not reach here
                        except exceptions.ResourceNotFoundError as e:
                            return e

            exception = asyncio.run(run_test())
            self.assertIsNotNone(exception)
            self.assertIsInstance(exception, exceptions.ResourceNotFoundError)

        asyncio.run(run_test())

    def test_resource_by_name(self):
        """Test getting a resource by name."""
        root_data = {
            'UpdateService': {'@odata.id': '/redfish/v1/UpdateService'}
        }

        update_service_data = {
            '@odata.id': '/redfish/v1/UpdateService',
            'ServiceEnabled': True
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(
                    side_effect=[root_data, update_service_data]
                )
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        update_service = await client_obj.resource(
                            'UpdateService')

                        self.assertIsInstance(update_service,
                                              resource.AsyncResource)
                        self.assertEqual('/redfish/v1/UpdateService',
                                         update_service.path)
                        self.assertTrue(
                            update_service.field('ServiceEnabled'))

        asyncio.run(run_test())

    def test_resource_by_path(self):
        """Test getting a resource by absolute path."""
        root_data = {
            'RedfishVersion': '1.6.0'
        }

        system_data = {
            '@odata.id': '/redfish/v1/Systems/1',
            'Manufacturer': 'Dell',
            'Model': 'PowerEdge R640'
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(
                    side_effect=[root_data, system_data]
                )
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        system = await client_obj.resource(
                            '/redfish/v1/Systems/1')

                        self.assertIsInstance(system, resource.AsyncResource)
                        self.assertEqual('/redfish/v1/Systems/1', system.path)
                        self.assertEqual('Dell', system.field('Manufacturer'))
                        self.assertEqual('PowerEdge R640',
                                         system.field('Model'))

        asyncio.run(run_test())

    def test_resource_not_found(self):
        """Test getting a resource that doesn't exist."""
        root_data = {
            'UpdateService': {'@odata.id': '/redfish/v1/UpdateService'}
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(return_value=root_data)
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        try:
                            await client_obj.resource('NonExistent')
                            return None  # Should not reach here
                        except exceptions.ResourceNotFoundError as e:
                            return e

            exception = asyncio.run(run_test())
            self.assertIsNotNone(exception)
            self.assertIsInstance(exception, exceptions.ResourceNotFoundError)

        asyncio.run(run_test())

    def test_redfish_version(self):
        """Test getting Redfish version."""
        root_data = {
            'RedfishVersion': '1.6.0'
        }

        async def run_test():
            with mock.patch('ironic.common.redfish.connector.AsyncConnector',
                            autospec=True) as mock_conn_class:
                mock_conn = mock.AsyncMock()
                mock_conn.get = mock.AsyncMock(return_value=root_data)
                mock_conn.__aenter__ = mock.AsyncMock(return_value=mock_conn)
                mock_conn.__aexit__ = mock.AsyncMock()
                mock_conn.close = mock.AsyncMock()
                mock_conn_class.return_value = mock_conn

                with mock.patch(
                        'ironic.common.redfish.auth.AsyncSessionOrBasicAuth',
                        autospec=True
                ) as mock_auth_class:
                    mock_auth = mock.AsyncMock()
                    mock_auth.set_context = mock.AsyncMock()
                    mock_auth.close = mock.AsyncMock()
                    mock_auth_class.return_value = mock_auth

                    async with client.AsyncRedfishClient(
                        self.base_url,
                        username=self.username,
                        password=self.password
                    ) as client_obj:
                        version = client_obj.redfish_version
                        self.assertEqual('1.6.0', version)

        asyncio.run(run_test())
