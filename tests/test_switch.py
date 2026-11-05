"""Regression tests for local direct-authorization switch semantics."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'custom_components/elli_charger_2/switch.py'
tree = ast.parse(SOURCE.read_text())
state_function = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == 'direct_authorization_state'
)
namespace = {}
exec(compile(ast.Module(body=[state_function], type_ignores=[]), str(SOURCE), 'exec'), namespace)


class SwitchStateTests(unittest.TestCase):
    def test_valid_states(self):
        decoder = namespace['direct_authorization_state']
        for value in ('allow', 'allowed'):
            self.assertIs(decoder({'charging_direct_authorization': {'value': value}}), True)
        for value in ('deny', 'denied'):
            self.assertIs(decoder({'charging_direct_authorization': {'value': value}}), False)

    def test_failed_or_malformed_get_is_unknown(self):
        decoder = namespace['direct_authorization_state']
        for response in (None, 'content malformed', {'error': 'content malformed'}, {}, {'value': 'Charging'}):
            self.assertIsNone(decoder({'charging_direct_authorization': response}))
