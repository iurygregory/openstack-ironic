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

"""Async Redfish client - main entry point."""


from oslo_log import log

from ironic.common.redfish import auth
from ironic.common.redfish import connector
from ironic.common.redfish import exceptions
from ironic.common.redfish import resource

LOG = log.getLogger(__name__)


class AsyncRedfishClient:
    """Async Redfish client.

    Main entry point for async Redfish BMC communication. Provides async
    methods to fetch and interact with Redfish resources.

    This client uses httpx for async HTTP operations and the lightweight
    AsyncResource class for dynamic resource access.

    Usage::

        async with AsyncRedfishClient(
            'https://bmc.example.com',
            username='admin',
            password='password',
            verify=True,
            auth_type='auto'
        ) as client:
            # Get a single system
            system = await client.get_system()
            print(system.field('Manufacturer'))
            print(system.field('PowerState'))

            # Get collections
            systems = await client.collection('Systems')
            for system in await systems.get_all():
                print(system.field('Name'))

            # Get resources by name
            update_service = await client.resource('UpdateService')
            session_service = await client.resource('SessionService')

            # Get resources by absolute path
            system = await client.resource('/redfish/v1/Systems/1')
            bios = await client.resource('/redfish/v1/Systems/1/Bios')
    """

    def __init__(self, base_url, username=None, password=None, verify=True,
                 auth_type='auto', root_prefix=None,
                 default_request_timeout=60, response_callback=None,
                 server_side_retries=3, server_side_retries_delay=2):
        """Initialize the async Redfish client.

        :param base_url: Base URL of the Redfish service
            (e.g., 'https://bmc.example.com').
        :param username: Username for authentication.
        :param password: Password for authentication.
        :param verify: Either a boolean to verify TLS certificates, or path
            to a CA certificate bundle. Defaults to True.
        :param auth_type: Authentication type - 'basic', 'session', or 'auto'.
            Defaults to 'auto' (try session, fallback to basic).
        :param root_prefix: Root prefix for Redfish API. Defaults to
            '/redfish/v1'.
        :param default_request_timeout: Default timeout in seconds for HTTP
            requests. Defaults to 60.
        :param response_callback: Optional callback function to invoke on
            every HTTP response. Takes response object as parameter.
        :param server_side_retries: Number of retries for server-side errors.
            Defaults to 3.
        :param server_side_retries_delay: Delay in seconds between server-side
            retries. Defaults to 2.
        :raises: ValueError if auth_type is invalid.
        """
        self._base_url = base_url
        self._root_prefix = root_prefix or '/redfish/v1'
        self._username = username
        self._password = password
        self._verify = verify
        self._default_request_timeout = default_request_timeout

        # Create connector
        self._connector = connector.AsyncConnector(
            url=base_url,
            verify=verify,
            default_request_timeout=default_request_timeout,
            response_callback=response_callback,
            server_side_retries=server_side_retries,
            server_side_retries_delay=server_side_retries_delay
        )

        # Create auth based on type
        auth_classes = {
            'basic': auth.AsyncBasicAuth,
            'session': auth.AsyncSessionAuth,
            'auto': auth.AsyncSessionOrBasicAuth,
        }

        if auth_type not in auth_classes:
            raise ValueError(
                f"Invalid auth_type '{auth_type}'. "
                f"Must be one of: {', '.join(auth_classes.keys())}")

        self._auth_type = auth_type
        self._auth = auth_classes[auth_type](
            username=username,
            password=password
        )

        # Track if we're initialized
        self._initialized = False

        # Cached root resource
        self._root = None

    async def __aenter__(self):
        """Async context manager entry.

        Initializes the HTTP connection and performs authentication.

        :returns: Self (AsyncRedfishClient instance).
        :raises: ConnectionError on connection failures.
        :raises: AccessError on authentication failures.
        """
        LOG.debug('Initializing async Redfish client for %(url)s',
                  {'url': self._base_url})

        # Initialize connector
        await self._connector.__aenter__()

        # Perform authentication
        await self._auth.set_context(self._connector)

        # Create root service resource
        try:
            self._root = resource.AsyncResource(
                self._connector,
                self._root_prefix
            )
            await self._root.refresh()
        except Exception as e:
            LOG.error('Failed to fetch Redfish root service at %(path)s: '
                      '%(error)s',
                      {'path': self._root_prefix, 'error': e})
            await self.close()
            raise

        self._initialized = True

        LOG.debug('Async Redfish client initialized successfully')

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit.

        Closes the authentication session and HTTP connection.
        """
        await self.close()

    async def close(self):
        """Close the client and clean up resources.

        Closes the authentication session and HTTP connection.
        """
        LOG.debug('Closing async Redfish client')

        if self._auth:
            try:
                await self._auth.close()
            except Exception as e:
                LOG.warning('Error closing auth session: %(error)s',
                            {'error': e})

        if self._connector:
            try:
                await self._connector.close()
            except Exception as e:
                LOG.warning('Error closing connector: %(error)s',
                            {'error': e})

        self._initialized = False

    def _ensure_initialized(self):
        """Ensure client is initialized.

        :raises: RuntimeError if client is not initialized.
        """
        if not self._initialized:
            raise RuntimeError(
                'AsyncRedfishClient not initialized. '
                'Use "async with AsyncRedfishClient(...) as client:"')

    async def collection(self, name):
        """Get a Redfish collection by name.

        :param name: Collection name (e.g., 'Systems', 'Managers', 'Chassis').
        :returns: AsyncResourceCollection with all members.
        :raises: ConnectionError on HTTP failures.
        :raises: ResourceNotFoundError if collection not found.
        """
        self._ensure_initialized()

        collection_path = self._root.field(f'{name}/@odata.id')

        if not collection_path:
            raise exceptions.ResourceNotFoundError(
                method='GET',
                url=f'{self._root_prefix}/{name}',
                response=None
            )

        collection_resource = resource.AsyncResource(
            self._connector,
            collection_path
        )
        await collection_resource.refresh()

        members = collection_resource.field('Members', default=[])
        paths = [m.get('@odata.id') for m in members
                 if isinstance(m, dict) and '@odata.id' in m]

        return resource.AsyncResourceCollection(self._connector, paths)

    async def resource(self, name):
        """Get a Redfish resource by name or path.

        :param name: Resource name (e.g., 'UpdateService', 'SessionService')
                     or absolute path (e.g., '/redfish/v1/Systems/1').
        :returns: AsyncResource for the requested resource.
        :raises: ResourceNotFoundError if resource not found.
        :raises: ConnectionError on HTTP failures.
        """
        self._ensure_initialized()

        # If name starts with '/', treat it as an absolute path
        if name.startswith('/'):
            resource_path = name
        else:
            # Look up the resource in the root service
            resource_path = self._root.field(f'{name}/@odata.id')

            if not resource_path:
                raise exceptions.ResourceNotFoundError(
                    method='GET',
                    url=f'{self._root_prefix}/{name}',
                    response=None
                )

        LOG.debug('Fetching resource at %(path)s', {'path': resource_path})

        res = resource.AsyncResource(self._connector, resource_path)
        await res.refresh()
        return res

    @property
    def root(self):
        """Get the root service resource.

        :returns: AsyncResource for the root service.
        :raises: RuntimeError if client is not initialized.
        """
        self._ensure_initialized()
        return self._root

    @property
    def redfish_version(self):
        """Get the Redfish version.

        :returns: Redfish version string.
        :raises: RuntimeError if client is not initialized.
        """
        self._ensure_initialized()
        return self._root.field('RedfishVersion')
