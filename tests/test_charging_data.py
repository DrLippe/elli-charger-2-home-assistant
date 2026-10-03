"""Isolated regressions for charger data handling, without an HA installation.

Load the actual helpers/coordinator from their AST, omitting HA imports and
entity declarations. Only HA's coordinator plumbing and clock are stand-ins.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from typing import Any

COMPONENT = Path(__file__).resolve().parents[1] / 'custom_components/elli_charger_2'


def load_definitions(filename, namespace, names):
    tree = ast.parse((COMPONENT / filename).read_text())
    tree.body = [node for node in tree.body if (isinstance(node, ast.ImportFrom) and node.module == '__future__') or (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names)]
    namespace['Any'] = Any
    exec(compile(tree, str(COMPONENT / filename), 'exec'), namespace)
    return namespace


class CoordinatorBase:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, *args, **kwargs):
        self.data = None

    def async_set_updated_data(self, data):
        self.data = data

    async def async_request_refresh(self):
        self.data = await self._async_update_data()


class ChargingDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 1000
        self.api = SimpleNamespace(async_get_data=AsyncMock())
        self.ns = load_definitions('coordinator.py', {
            'DataUpdateCoordinator': CoordinatorBase,
            'ElliChargerError': RuntimeError,
            'UpdateFailed': RuntimeError,
            'timedelta': timedelta,
            'DEFAULT_SCAN_INTERVAL': 10,
            'DOMAIN': 'elli_charger_2',
            'CHARGING_CURVE_MAX_AGE': 150,
            'monotonic': lambda: self.now,
        }, {'ElliChargerCoordinator'})
        self.coordinator = self.ns['ElliChargerCoordinator'](None, self.api)
        self.session = {'startDateTime': '2026-10-02T12:00:00Z', 'chargingRate': 0}
        self.coordinator.data = {'last_session': self.session}
        self.point = {'powerL1': 2.3, 'powerL2': 2.3, 'powerL3': 2.3, 'timestamp': '2026-10-02T12:01:00Z'}
        self.helpers = load_definitions('sensor.py', {
            'dt_util': SimpleNamespace(
                parse_datetime=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')) if value != 'bad' else None,
                as_local=lambda value: value.astimezone(timezone(timedelta(hours=2))),
            ),
        }, {'_nested', '_parse_datetime', '_format_duration', '_last_session_date', '_latest_curve_point', '_charging_power'})

    async def sample(self):
        await self.coordinator.async_event_refresh('chargingCurvePointAppend', self.point)

    async def poll(self, session=None):
        self.api.async_get_data.return_value = {'last_session': self.session if session is None else session}
        data = await self.coordinator._async_update_data()
        self.coordinator.data = data
        return data

    async def test_multiple_polls_keep_power_between_minutely_events(self):
        await self.sample()
        for elapsed in (10, 30, 60, 100, 149):
            self.now = 1000 + elapsed
            data = await self.poll()
            self.assertEqual(self.helpers['_charging_power'](data), 6.9)
            self.assertEqual(data['charging_curve_point']['timestamp'], self.point['timestamp'])

    async def test_expired_sample_falls_back_to_rest(self):
        await self.sample()
        self.now += 150
        data = await self.poll()
        self.assertNotIn('charging_curve_point', data)
        self.assertEqual(self.helpers['_charging_power'](data), 0)

    async def test_new_event_renews_sample(self):
        await self.sample()
        self.now += 60
        self.point = dict(self.point, powerL1=1, powerL2=1, powerL3=1)
        await self.sample()
        self.now += 100
        self.assertEqual(self.helpers['_charging_power'](await self.poll()), 3)

    async def test_new_session_discards_old_power(self):
        await self.sample()
        data = await self.poll({'startDateTime': '2026-10-03T12:00:00Z', 'chargingRate': 0})
        self.assertNotIn('charging_curve_point', data)
        self.assertEqual(self.helpers['_charging_power'](data), 0)

    async def test_session_end_discards_old_power(self):
        await self.sample()
        data = await self.poll(dict(self.session, endDateTime='2026-10-02T12:30:00Z', chargingRate=6.9))
        self.assertNotIn('charging_curve_point', data)
        self.assertEqual(self.helpers['_charging_power'](data), 0)

    async def test_event_during_rest_poll_is_not_lost(self):
        async def fetch():
            await self.sample()
            return {'last_session': self.session}
        self.api.async_get_data.side_effect = fetch
        data = await self.coordinator._async_update_data()
        self.assertEqual(self.helpers['_charging_power'](data), 6.9)

    async def test_failed_poll_does_not_clear_cache(self):
        await self.sample()
        self.api.async_get_data.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            await self.coordinator._async_update_data()
        self.api.async_get_data.side_effect = None
        self.assertEqual(self.helpers['_charging_power'](await self.poll()), 6.9)

    async def test_optional_session_missing_still_keeps_recent_point(self):
        await self.sample()
        data = await self.poll(False)
        self.assertEqual(self.helpers['_charging_power'](data), 6.9)

    def test_power_fallback_and_missing_values(self):
        self.assertEqual(self.helpers['_charging_power']({'last_session': {'chargingRate': 4}}), 4)
        self.assertIsNone(self.helpers['_charging_power']({}))
        self.assertEqual(self.helpers['_charging_power']({'charging_curve_point': dict(self.point, powerL1=0, powerL2=0, powerL3=0)}), 0)

    def test_duration_days_hours_minutes(self):
        self.assertEqual(self.helpers['_format_duration'](2 * 86400 + 5 * 3600 + 12 * 60 + 59), '2 d 5 h 12 min')
        self.assertEqual(self.helpers['_format_duration'](3600), '1 h')
        self.assertEqual(self.helpers['_format_duration'](59), '0 min')
        self.assertEqual(self.helpers['_format_duration'](0), '0 min')
        for value in (None, -1, '123'):
            self.assertIsNone(self.helpers['_format_duration'](value))

    def test_last_session_date_respects_local_midnight(self):
        data = {'last_session': {'startDateTime': '2026-10-02T23:30:00Z'}}
        self.assertEqual(self.helpers['_last_session_date'](data).isoformat(), '2026-10-03')

    def test_missing_invalid_or_naive_session_timestamp(self):
        for value in (None, '', 'bad', '2026-10-02T12:00:00'):
            self.assertIsNone(self.helpers['_last_session_date']({'last_session': {'startDateTime': value}}))
        self.assertIsNone(self.helpers['_last_session_date']({}))


if __name__ == '__main__':
    unittest.main()
