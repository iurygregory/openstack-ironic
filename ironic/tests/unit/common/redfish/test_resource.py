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

"""Unit tests for lightweight async Redfish resource."""

import asyncio
from unittest import mock

from ironic.common.redfish import exceptions
from ironic.common.redfish import resource
from ironic.tests import base


class TestAsyncResource(base.TestCase):
    """Test AsyncResource class."""

    def setUp(self):
        super().setUp()
        self.mock_connector = mock.AsyncMock()
        self.path = '/redfish/v1/Systems/1'

    def test_init_with_data(self):
        """Test initialization with pre-fetched data."""
        data = {'Manufacturer': 'Dell', 'Model': 'PowerEdge'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.assertEqual(self.path, res.path)
        self.assertEqual(data, res.json)

    def test_init_without_data(self):
        """Test initialization without data."""
        res = resource.AsyncResource(self.mock_connector, self.path)

        self.assertEqual(self.path, res.path)
        self.assertEqual({}, res.json)

    def test_refresh(self):
        """Test refreshing resource data."""
        data = {
            'Manufacturer': 'Dell',
            'Model': 'PowerEdge R640'
        }
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        res = resource.AsyncResource(self.mock_connector, self.path)

        async def run_test():
            result = await res.refresh()
            self.assertIs(result, res)  # Should return self
            self.assertEqual(data, res.json)
            self.mock_connector.get.assert_called_once_with(self.path)

        asyncio.run(run_test())

    def test_field_simple(self):
        """Test getting a simple field."""
        data = {
            'Manufacturer': 'Dell',
            'Model': 'PowerEdge',
            'SerialNumber': 'ABC123'
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.assertEqual('Dell', res.field('Manufacturer'))
        self.assertEqual('PowerEdge', res.field('Model'))
        self.assertEqual('ABC123', res.field('SerialNumber'))

    def test_field_nested(self):
        """Test getting nested fields with slash notation."""
        data = {
            'Boot': {
                'BootSourceOverrideTarget': 'Pxe',
                'BootSourceOverrideEnabled': 'Once'
            },
            'ProcessorSummary': {
                'Count': 2,
                'Model': 'Intel Xeon'
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.assertEqual('Pxe', res.field('Boot/BootSourceOverrideTarget'))
        self.assertEqual('Once', res.field('Boot/BootSourceOverrideEnabled'))
        self.assertEqual(2, res.field('ProcessorSummary/Count'))
        self.assertEqual('Intel Xeon', res.field('ProcessorSummary/Model'))

    def test_field_not_found(self):
        """Test accessing non-existent field."""
        data = {'Manufacturer': 'Dell'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.assertIsNone(res.field('NonExistent'))
        self.assertIsNone(res.field('Boot/BootTarget'))

    def test_field_with_default(self):
        """Test field with default value."""
        data = {'Manufacturer': 'Dell'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.assertEqual('Unknown', res.field('Model', default='Unknown'))
        self.assertEqual(0, res.field('Count', default=0))

    def test_field_with_adapter(self):
        """Test field with adapter function."""
        data = {
            'PowerState': 'On',
            'PowerWatts': '450',
            'Count': '10'
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        # Adapter to convert to lowercase
        self.assertEqual('on', res.field('PowerState', adapter=str.lower))

        # Adapter to convert to int
        self.assertEqual(450, res.field('PowerWatts', adapter=int))
        self.assertEqual(10, res.field('Count', adapter=int))

    def test_field_with_adapter_error(self):
        """Test field with adapter that raises exception."""
        data = {'Value': 'not-a-number'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        # Adapter fails, should return default
        self.assertIsNone(res.field('Value', adapter=int))
        self.assertEqual(0, res.field('Value', adapter=int, default=0))

    def test_action_success(self):
        """Test executing an action."""
        data = {
            'Actions': {
                '#ComputerSystem.Reset': {
                    'target': '/redfish/v1/Systems/1/Actions/'
                              'ComputerSystem.Reset',
                    'ResetType@Redfish.AllowableValues': ['On', 'ForceOff']
                }
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        mock_response = mock.MagicMock()
        self.mock_connector.post = mock.AsyncMock(return_value=mock_response)

        async def run_test():
            payload = {'ResetType': 'ForceOff'}
            result = await res.action('ComputerSystem.Reset', payload)

            self.assertEqual(mock_response, result)
            self.mock_connector.post.assert_called_once_with(
                '/redfish/v1/Systems/1/Actions/ComputerSystem.Reset',
                data=payload
            )

        asyncio.run(run_test())

    def test_action_with_hash_prefix(self):
        """Test action with hash prefix in name."""
        data = {
            'Actions': {
                '#ComputerSystem.Reset': {
                    'target': '/redfish/v1/Systems/1/Actions/'
                              'ComputerSystem.Reset'
                }
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.mock_connector.post = mock.AsyncMock()

        async def run_test():
            await res.action('#ComputerSystem.Reset', {'ResetType': 'On'})
            self.mock_connector.post.assert_called_once()

        asyncio.run(run_test())

    def test_action_not_found(self):
        """Test action that doesn't exist."""
        data = {'Actions': {}}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            try:
                await res.action('NonExistent', {})
                return None  # Should not reach here
            except ValueError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, ValueError)
        self.assertIn('not found', str(exception))

    def test_action_no_target(self):
        """Test action without target URL."""
        data = {
            'Actions': {
                '#SomeAction': {}
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            try:
                await res.action('SomeAction', {})
                return None  # Should not reach here
            except ValueError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, ValueError)
        self.assertIn('no target', str(exception))

    def test_patch_simple(self):
        """Test PATCH operation."""
        data = {'AssetTag': 'old-tag'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        mock_response = mock.MagicMock()
        updated_data = {'AssetTag': 'new-tag'}

        self.mock_connector.patch = mock.AsyncMock(return_value=mock_response)
        self.mock_connector.get = mock.AsyncMock(return_value=updated_data)

        async def run_test():
            payload = {'AssetTag': 'new-tag'}
            result = await res.patch(payload)

            self.assertEqual(mock_response, result)
            self.mock_connector.patch.assert_called_once_with(
                self.path,
                data=payload,
                etag=None
            )
            # Should refresh after patch
            self.assertEqual(updated_data, res.json)

        asyncio.run(run_test())

    def test_patch_with_etag(self):
        """Test PATCH with explicit ETag."""
        data = {'AssetTag': 'old-tag'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        self.mock_connector.patch = mock.AsyncMock()
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        async def run_test():
            payload = {'AssetTag': 'new-tag'}
            await res.patch(payload, etag='W/"12345"')

            self.mock_connector.patch.assert_called_once_with(
                self.path,
                data=payload,
                etag='W/"12345"'
            )

        asyncio.run(run_test())

    def test_patch_with_cached_etag(self):
        """Test PATCH using cached ETag from refresh."""
        data = {'AssetTag': 'old-tag'}
        res = resource.AsyncResource(self.mock_connector, self.path, data)
        res._etag = 'W/"cached"'

        self.mock_connector.patch = mock.AsyncMock()
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        async def run_test():
            payload = {'AssetTag': 'new-tag'}
            await res.patch(payload)

            self.mock_connector.patch.assert_called_once_with(
                self.path,
                data=payload,
                etag='W/"cached"'
            )

        asyncio.run(run_test())

    def test_link_simple(self):
        """Test following a simple link."""
        data = {
            'Bios': {
                '@odata.id': '/redfish/v1/Systems/1/Bios'
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        bios_data = {'BootMode': 'Uefi'}
        self.mock_connector.get = mock.AsyncMock(return_value=bios_data)

        async def run_test():
            bios = await res.link('Bios')

            self.assertIsInstance(bios, resource.AsyncResource)
            self.assertEqual('/redfish/v1/Systems/1/Bios', bios.path)
            self.assertEqual(bios_data, bios.json)

        asyncio.run(run_test())

    def test_link_in_links_object(self):
        """Test following a link in the Links object."""
        data = {
            'Links': {
                'Chassis': [
                    {'@odata.id': '/redfish/v1/Chassis/1'}
                ]
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            # This will return an AsyncResourceCollection
            chassis_collection = await res.link('Chassis')

            self.assertIsInstance(
                chassis_collection, resource.AsyncResourceCollection)
            self.assertEqual(1, len(chassis_collection))

        asyncio.run(run_test())

    def test_link_not_found(self):
        """Test link that doesn't exist."""
        data = {'Bios': {'@odata.id': '/redfish/v1/Systems/1/Bios'}}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            try:
                await res.link('NonExistent')
                return None  # Should not reach here
            except ValueError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, ValueError)
        self.assertIn('not found', str(exception))

    def test_collection_links(self):
        """Test getting all members from a collection."""
        data = {
            'Members': [
                {'@odata.id': '/redfish/v1/Systems/1'},
                {'@odata.id': '/redfish/v1/Systems/2'}
            ]
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        system1_data = {'Manufacturer': 'Dell'}
        system2_data = {'Manufacturer': 'HPE'}

        self.mock_connector.get = mock.AsyncMock(
            side_effect=[system1_data, system2_data]
        )

        async def run_test():
            systems = await res.collection('Members').get_all()

            self.assertEqual(2, len(systems))
            self.assertEqual(system1_data, systems[0].json)
            self.assertEqual(system2_data, systems[1].json)

        asyncio.run(run_test())

    def test_collection_links_empty(self):
        """Test collection with no members."""
        data = {'Members': []}
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            systems = await res.collection('Members').get_all()
            self.assertEqual(0, len(systems))

        asyncio.run(run_test())

    def test_refresh_with_expand(self):
        """Test refreshing resource data with $expand."""
        data = {'Id': '1', 'Thermal': {'Fans': []}}
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        res = resource.AsyncResource(self.mock_connector, self.path)

        async def run_test():
            result = await res.refresh(expand=True)
            self.assertIs(result, res)
            self.assertEqual(data, res.json)
            expected_path = self.path + '?$expand=.($levels=1)'
            self.mock_connector.get.assert_called_once_with(expected_path)

        asyncio.run(run_test())

    def test_refresh_without_expand(self):
        """Test that refresh without expand uses the plain path."""
        data = {'Id': '1'}
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        res = resource.AsyncResource(self.mock_connector, self.path)

        async def run_test():
            await res.refresh(expand=False)
            self.mock_connector.get.assert_called_once_with(self.path)

        asyncio.run(run_test())

    def test_link_with_expand(self):
        """Test following a link with $expand."""
        data = {
            'Storage': {
                '@odata.id': '/redfish/v1/Systems/1/Storage'
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        storage_data = {'Members': []}
        self.mock_connector.get = mock.AsyncMock(return_value=storage_data)

        async def run_test():
            storage = await res.link('Storage', expand=True)

            self.assertIsInstance(storage, resource.AsyncResource)
            self.assertEqual('/redfish/v1/Systems/1/Storage', storage.path)
            expected_path = (
                '/redfish/v1/Systems/1/Storage?$expand=.($levels=1)')
            self.mock_connector.get.assert_called_once_with(expected_path)

        asyncio.run(run_test())

    def test_link_without_expand(self):
        """Test following a link without $expand uses plain path."""
        data = {
            'Bios': {
                '@odata.id': '/redfish/v1/Systems/1/Bios'
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        bios_data = {'BootMode': 'Uefi'}
        self.mock_connector.get = mock.AsyncMock(return_value=bios_data)

        async def run_test():
            await res.link('Bios', expand=False)
            self.mock_connector.get.assert_called_once_with(
                '/redfish/v1/Systems/1/Bios')

        asyncio.run(run_test())

    def test_link_collection_with_expand(self):
        """Test following a collection link with $expand."""
        data = {
            'Links': {
                'Chassis': [
                    {'@odata.id': '/redfish/v1/Chassis/1'},
                    {'@odata.id': '/redfish/v1/Chassis/2'},
                ]
            }
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        async def run_test():
            chassis_collection = await res.link('Chassis', expand=True)

            self.assertIsInstance(
                chassis_collection, resource.AsyncResourceCollection)
            self.assertEqual(2, len(chassis_collection))
            expected_paths = [
                '/redfish/v1/Chassis/1?$expand=.($levels=1)',
                '/redfish/v1/Chassis/2?$expand=.($levels=1)',
            ]
            self.assertEqual(expected_paths, chassis_collection.paths)

        asyncio.run(run_test())

    def test_collection_with_expand(self):
        """Test getting a collection with $expand on member paths."""
        data = {
            'Members': [
                {'@odata.id': '/redfish/v1/Systems/1'},
                {'@odata.id': '/redfish/v1/Systems/2'}
            ]
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        collection = res.collection('Members', expand=True)
        expected_paths = [
            '/redfish/v1/Systems/1?$expand=.($levels=1)',
            '/redfish/v1/Systems/2?$expand=.($levels=1)',
        ]
        self.assertEqual(expected_paths, collection.paths)

    def test_collection_without_expand(self):
        """Test that collection without expand uses plain paths."""
        data = {
            'Members': [
                {'@odata.id': '/redfish/v1/Systems/1'},
                {'@odata.id': '/redfish/v1/Systems/2'}
            ]
        }
        res = resource.AsyncResource(self.mock_connector, self.path, data)

        collection = res.collection('Members', expand=False)
        expected_paths = [
            '/redfish/v1/Systems/1',
            '/redfish/v1/Systems/2',
        ]
        self.assertEqual(expected_paths, collection.paths)

    def test_repr(self):
        """Test string representation."""
        res = resource.AsyncResource(self.mock_connector, self.path)
        self.assertEqual(f"AsyncResource(path={self.path!r})", repr(res))


class TestAsyncResourceCollection(base.TestCase):
    """Test AsyncResourceCollection class."""

    def setUp(self):
        super().setUp()
        self.mock_connector = mock.AsyncMock()
        self.paths = [
            '/redfish/v1/Systems/1',
            '/redfish/v1/Systems/2',
            '/redfish/v1/Systems/3'
        ]

    def test_init(self):
        """Test initialization."""
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )

        self.assertEqual(3, len(collection))

    def test_get_all(self):
        """Test fetching all resources."""
        data1 = {'Manufacturer': 'Dell'}
        data2 = {'Manufacturer': 'HPE'}
        data3 = {'Manufacturer': 'Lenovo'}

        self.mock_connector.get = mock.AsyncMock(
            side_effect=[data1, data2, data3]
        )

        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )

        async def run_test():
            resources = await collection.get_all()

            self.assertEqual(3, len(resources))
            self.assertEqual(data1, resources[0].json)
            self.assertEqual(data2, resources[1].json)
            self.assertEqual(data3, resources[2].json)

        asyncio.run(run_test())

    def test_get_by_index(self):
        """Test fetching a single resource by index."""
        data = {'Manufacturer': 'HPE'}
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )

        async def run_test():
            resource_obj = await collection.get(1)

            self.assertEqual(data, resource_obj.json)
            self.assertEqual(self.paths[1], resource_obj.path)

        asyncio.run(run_test())

    def test_get_index_out_of_range(self):
        """Test getting resource with invalid index."""
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )

        async def run_test():
            try:
                await collection.get(10)
                return None  # Should not reach here
            except IndexError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, IndexError)

    def test_repr(self):
        """Test string representation."""
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )
        self.assertEqual('AsyncResourceCollection(count=3)', repr(collection))

    def test_one_success(self):
        """Test one() with exactly one resource."""
        data = {'Manufacturer': 'Dell', 'Model': 'PowerEdge R640'}
        self.mock_connector.get = mock.AsyncMock(return_value=data)

        single_path = ['/redfish/v1/Systems/1']
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            single_path
        )

        async def run_test():
            resource_obj = await collection.one()

            self.assertEqual(data, resource_obj.json)
            self.assertEqual(single_path[0], resource_obj.path)

        asyncio.run(run_test())

    def test_one_empty_collection(self):
        """Test one() with empty collection."""
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            []
        )

        async def run_test():
            try:
                await collection.one()
                return None  # Should not reach here
            except exceptions.UnknownDefaultError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.UnknownDefaultError)
        self.assertIn('found 0', str(exception))

    def test_one_multiple_resources(self):
        """Test one() with multiple resources."""
        collection = resource.AsyncResourceCollection(
            self.mock_connector,
            self.paths
        )

        async def run_test():
            try:
                await collection.one()
                return None  # Should not reach here
            except exceptions.UnknownDefaultError as e:
                return e

        exception = asyncio.run(run_test())
        self.assertIsNotNone(exception)
        self.assertIsInstance(exception, exceptions.UnknownDefaultError)
        self.assertIn('found 3', str(exception))
