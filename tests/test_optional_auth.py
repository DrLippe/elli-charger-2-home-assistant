"""API and flow regressions using fake HTTP responses and HA flow plumbing."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / 'custom_components/elli_charger_2'


def load_module(filename, namespace):
    tree = ast.parse((COMPONENT / filename).read_text())
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or '').startswith('homeassistant')
        )
    ) and not (isinstance(node, ast.Import) and any(alias.name == 'voluptuous' for alias in node.names))]
    exec(compile(tree, str(COMPONENT / filename), 'exec'), namespace)
    return namespace


API = load_module('api.py', {
    'API_USER_SERVICE': 'technician', 'API_USER_STANDARD': 'standard',
    'USER_TYPE_SERVICE': 'service',
})


class Response:
    content_type = 'application/json'

    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise API['ClientError']('HTTP failure')

    async def json(self):
        await asyncio.sleep(0)
        return self.payload


class Session:
    def __init__(self):
        self.requests = []
        self.logins = []
        self.login_status = 200
        self.login_payload = None
        self.routes = {}

    def post(self, url, **kwargs):
        self.logins.append((url, kwargs))
        payload = self.login_payload if self.login_payload is not None else {'token': f'test-token-{len(self.logins)}'}
        return Response(self.login_status, payload)

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        path = url.split('wallbox', 1)[1]
        if path in self.routes:
            route = self.routes[path]
            if callable(route):
                return route(kwargs)
            return Response(*route)
        return Response(payload={'value': 'charging'} if path.endswith('/charging/state') else {})


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_password_fetches_only_public_endpoints(self):
        session = Session()
        api = API['ElliChargerApi'](session, 'wallbox')
        data = await api.async_get_data()
        self.assertFalse(api.authentication_enabled)
        self.assertEqual(len(session.requests), 5)
        self.assertEqual(session.logins, [])
        self.assertIsNone(data['ocpp'])
        self.assertIsNone(data['errors'])
        self.assertTrue(all(not call[2]['headers'] for call in session.requests))

    async def test_empty_password_never_logs_in(self):
        session = Session()
        api = API['ElliChargerApi'](session, 'wallbox', 'service', '')
        with self.assertRaises(API['ElliChargerAuthenticationError']):
            await api._request('GET', '/protected', auth=True)
        self.assertEqual(session.logins, [])
        self.assertEqual(session.requests, [])

    async def test_standard_and_service_user_login(self):
        for kind, name in [('standard', 'standard'), ('service', 'technician')]:
            session = Session()
            api = API['ElliChargerApi'](session, 'wallbox', kind, 'synthetic-password')
            data = await api.async_get_data()
            self.assertEqual(len(session.logins), 1)
            self.assertEqual(session.logins[0][1]['data'], {'user': name, 'pass': 'synthetic-password'})
            self.assertIsNotNone(data['ocpp'])
            protected = [r for r in session.requests if r[1].endswith('/connection/ocpp')][0]
            self.assertEqual(protected[2]['headers']['Authorization'], 'Bearer test-token-1')
            self.assertEqual(session.requests[0][2]['headers'], {})

    async def test_forbidden_endpoint_does_not_relogin_or_break_public_data(self):
        session = Session()
        session.routes['/api/v2/connection/ocpp'] = (403, None)
        api = API['ElliChargerApi'](session, 'wallbox', 'standard', 'synthetic-password')
        data = await api.async_get_data()
        self.assertEqual(len(session.logins), 1)
        self.assertIsNone(data['ocpp'])
        self.assertEqual(data['charging_state'], {'value': 'charging'})

    async def test_concurrent_401s_share_one_token_refresh(self):
        session = Session()
        for path in ('/protected-a', '/protected-b'):
            session.routes[path] = lambda kwargs: Response(401 if kwargs['headers']['Authorization'] == 'Bearer expired' else 200, {'ok': True})
        api = API['ElliChargerApi'](session, 'wallbox', 'service', 'synthetic-password')
        api._token = 'expired'
        result = await asyncio.gather(*(api._request('GET', path, auth=True) for path in ('/protected-a', '/protected-b')))
        self.assertEqual(result, [{'ok': True}, {'ok': True}])
        self.assertEqual(len(session.logins), 1)

    async def test_rejected_renewed_token_does_not_loop(self):
        session = Session()
        session.routes['/protected'] = (401, None)
        api = API['ElliChargerApi'](session, 'wallbox', 'standard', 'synthetic-password')
        api._token = 'expired'
        with self.assertRaises(API['ElliChargerAuthenticationError']):
            await api._request('GET', '/protected', auth=True)
        self.assertEqual(len(session.logins), 1)
        self.assertEqual(len(session.requests), 2)

    async def test_invalid_credentials_or_missing_token(self):
        for status, payload in [(401, {}), (403, {}), (200, {}), (200, None)]:
            session = Session()
            session.login_status = status
            session.login_payload = payload if payload is not None else []
            api = API['ElliChargerApi'](session, 'wallbox', 'standard', 'synthetic-password')
            with self.assertRaises(API['ElliChargerAuthenticationError']):
                await api.async_login()

    async def test_public_connectivity_failure_is_not_swallowed(self):
        session = Session()
        session.routes['/api/v2/charging/state'] = (503, None)
        api = API['ElliChargerApi'](session, 'wallbox')
        with self.assertRaises(API['ElliChargerConnectionError']):
            await api.async_get_data()

    async def test_optional_endpoint_failure_and_204_are_empty(self):
        session = Session()
        session.routes['/api/v2/vehicles/plugged'] = (204, None)
        session.routes['/api/v2/charging/lifetime-stats'] = (404, None)
        data = await API['ElliChargerApi'](session, 'wallbox').async_get_data()
        self.assertIsNone(data['plugged_vehicle'])
        self.assertIsNone(data['lifetime_stats'])


class Marker:
    def __init__(self, name, default=None):
        self.name, self.default = name, default


class Required(Marker):
    pass


class FlowBase:
    def __init_subclass__(cls, **kwargs):
        pass

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass

    def async_create_entry(self, **kwargs):
        return {'type': 'create_entry', **kwargs}

    def async_show_form(self, **kwargs):
        return {'type': 'form', **kwargs}

    def _get_reauth_entry(self):
        return self.config_entry

    def async_update_reload_and_abort(self, entry, **kwargs):
        return {'type': 'abort', **kwargs}


def flow_namespace():
    selector = lambda *args, **kwargs: kwargs
    return load_module('config_flow.py', {
        **API,
        'vol': SimpleNamespace(Optional=Marker, Required=Required, Schema=lambda schema: schema),
        'config_entries': SimpleNamespace(ConfigFlow=FlowBase, OptionsFlowWithReload=FlowBase),
        'CONF_HOST': 'host', 'CONF_PASSWORD': 'password', 'CONF_USER_TYPE': 'user_type',
        'DOMAIN': 'elli_charger_2', 'USER_TYPE_SERVICE': 'service', 'USER_TYPE_STANDARD': 'standard',
        'callback': lambda fn: fn,
        'async_get_clientsession': lambda hass: hass.session,
        'SelectSelector': selector, 'SelectSelectorConfig': selector,
        'SelectSelectorMode': SimpleNamespace(DROPDOWN='dropdown'),
        'TextSelector': selector, 'TextSelectorConfig': selector,
        'TextSelectorType': SimpleNamespace(PASSWORD='password', TEXT='text'),
    })


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = flow_namespace()
        self.session = Session()
        self.hass = SimpleNamespace(session=self.session)

    async def test_public_setup_without_password(self):
        flow = self.ns['ElliChargerConfigFlow']()
        flow.hass = self.hass
        result = await flow.async_step_user({'host': 'wallbox'})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(result['data'], {'host': 'https://wallbox'})
        self.assertEqual(self.session.logins, [])

    async def test_setup_with_credentials_and_invalid_auth(self):
        flow = self.ns['ElliChargerConfigFlow']()
        flow.hass = self.hass
        result = await flow.async_step_user({'host': 'wallbox', 'user_type': 'service', 'password': 'synthetic-password'})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(self.session.logins[0][1]['data']['user'], 'technician')
        self.session.login_status = 401
        result = await flow.async_step_user({'host': 'wallbox', 'password': 'wrong-synthetic-password'})
        self.assertEqual(result['errors'], {'base': 'invalid_auth'})

    async def test_password_is_optional_and_never_prefilled(self):
        schema = self.ns['_credential_schema']()
        password = next(marker for marker in schema if marker.name == 'password')
        self.assertNotIsInstance(password, Required)
        self.assertIsNone(password.default)

    async def test_options_can_add_and_disable_legacy_credentials(self):
        flow = self.ns['ElliChargerOptionsFlow']()
        flow.hass = self.hass
        flow.config_entry = SimpleNamespace(data={'host': 'https://wallbox', 'password': 'legacy-synthetic-password'}, options={})
        result = await flow.async_step_init({'user_type': 'service', 'password': 'synthetic-password'})
        self.assertEqual(result['data']['user_type'], 'service')
        self.session.logins.clear()
        result = await flow.async_step_init({})
        self.assertEqual(result['data']['password'], '')
        self.assertEqual(self.session.logins, [])

    async def test_reauth_can_disable_authentication(self):
        flow = self.ns['ElliChargerConfigFlow']()
        flow.hass = self.hass
        flow.config_entry = SimpleNamespace(data={'host': 'https://wallbox'}, options={'password': 'old-synthetic-password'})
        result = await flow.async_step_reauth_confirm({})
        self.assertEqual(result['type'], 'abort')
        self.assertEqual(result['options']['password'], '')
        self.assertEqual(self.session.logins, [])

    async def test_unreachable_host_shows_connection_error(self):
        flow = self.ns['ElliChargerConfigFlow']()
        flow.hass = self.hass
        self.session.routes['/api/v2/charging/state'] = (503, None)
        result = await flow.async_step_user({'host': 'wallbox'})
        self.assertEqual(result['errors'], {'base': 'cannot_connect'})


if __name__ == '__main__':
    unittest.main()
