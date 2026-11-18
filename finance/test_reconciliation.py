# SPDX-License-Identifier: MPL-2.0
from copy import deepcopy
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, override_settings

from .reconciliation import ReconciliationInputError, compare_synthetic


def row(record, mapping, principal, interest=0, fees=0, unapplied=0):
    return {'record_id': record, 'match_id': mapping, 'principal_cents': principal,
            'interest_cents': interest, 'fees_cents': fees, 'unapplied_cents': unapplied}


@override_settings(DEBUG=True, DEMO_LEDGER_ENABLED=True, SYNTHETIC_RECONCILIATION_ENABLED=True)
class OfflineReconciliationTests(SimpleTestCase):
    def inputs(self):
        return {'source': [row('SYNTH-SRC-A', 'SYNTH-MAP-A', 100025, 2050, 0, 500),
                           row('SYNTH-SRC-B', 'SYNTH-MAP-B', 4200, 0, 100, 0)],
                'target': [row('SYNTH-TGT-A', 'SYNTH-MAP-A', 100000, 2050, 0, 500),
                           row('SYNTH-TGT-B', 'SYNTH-MAP-B', 4200, 0, 150, 0)],
                'source_provenance': 'SYNTH-PROV-SOURCE', 'target_provenance': 'SYNTH-PROV-TARGET',
                'as_of': '2026-11-10', 'synthetic_only': True}

    def test_independent_reference_case_and_stable_order(self):
        args = self.inputs()
        original = deepcopy(args)
        with patch('builtins.open', side_effect=AssertionError('No files')), \
             patch('socket.socket', side_effect=AssertionError('No network')):
            result = compare_synthetic(**args)
        self.assertEqual(args, original)
        self.assertFalse(result['reconciled'])
        self.assertTrue(result['comparison_complete'])
        self.assertEqual(result['source_role'], 'comparison_reference')
        self.assertEqual(result['target_role'], 'candidate')
        self.assertEqual(result['source_provenance'], 'SYNTH-PROV-SOURCE')
        self.assertEqual(result['target_provenance'], 'SYNTH-PROV-TARGET')
        self.assertEqual(result['aggregate'], {
            'source_cents': {'principal_cents': 104225, 'interest_cents': 2050, 'fees_cents': 100, 'unapplied_cents': 500},
            'target_cents': {'principal_cents': 104200, 'interest_cents': 2050, 'fees_cents': 150, 'unapplied_cents': 500},
            'target_minus_source_cents': {'principal_cents': -25, 'interest_cents': 0, 'fees_cents': 50, 'unapplied_cents': 0},
        })
        self.assertEqual(result['exceptions'], [
            {'kind': 'aggregate_mismatch', 'target_minus_source_cents': {'principal_cents': -25, 'interest_cents': 0, 'fees_cents': 50, 'unapplied_cents': 0}},
            {'kind': 'amount_mismatch', 'match_id': 'SYNTH-MAP-A', 'target_minus_source_cents': {'principal_cents': -25}},
            {'kind': 'amount_mismatch', 'match_id': 'SYNTH-MAP-B', 'target_minus_source_cents': {'fees_cents': 50}},
        ])
        self.assertEqual(result, compare_synthetic(**(args | {'source': list(reversed(args['source'])), 'target': list(reversed(args['target']))})))

    def test_equal_aggregates_cannot_hide_account_mismatches(self):
        args = self.inputs()
        args['source'] = [row('SYNTH-SRC-A', 'SYNTH-MAP-A', 100), row('SYNTH-SRC-B', 'SYNTH-MAP-B', 200)]
        args['target'] = [row('SYNTH-TGT-A', 'SYNTH-MAP-A', 200), row('SYNTH-TGT-B', 'SYNTH-MAP-B', 100)]
        result = compare_synthetic(**args)
        self.assertEqual(result['aggregate']['target_minus_source_cents']['principal_cents'], 0)
        self.assertEqual([e['kind'] for e in result['exceptions']], ['amount_mismatch', 'amount_mismatch'])
        self.assertFalse(result['reconciled'])

    def test_missing_both_sides_and_independent_aggregate(self):
        args = self.inputs()
        args['source'] = [row('SYNTH-SRC-A', 'SYNTH-MAP-A', 100)]
        args['target'] = [row('SYNTH-TGT-B', 'SYNTH-MAP-B', 200)]
        result = compare_synthetic(**args)
        self.assertEqual(result['exceptions'], [
            {'kind': 'aggregate_mismatch', 'target_minus_source_cents': {'principal_cents': 100, 'interest_cents': 0, 'fees_cents': 0, 'unapplied_cents': 0}},
            {'kind': 'missing_account', 'missing_side': 'source', 'match_id': 'SYNTH-MAP-B'},
            {'kind': 'missing_account', 'missing_side': 'target', 'match_id': 'SYNTH-MAP-A'},
        ])
        self.assertFalse(result['comparison_complete'])
        self.assertFalse(result['reconciled'])

    def test_duplicates_and_unresolved_mapping_never_guess_or_total(self):
        args = self.inputs()
        args['source'].append(row('SYNTH-SRC-A', 'SYNTH-MAP-C', 1))
        args['target'].append(row('SYNTH-TGT-C', 'SYNTH-MAP-B', 2))
        args['target'].append(row('SYNTH-TGT-D', None, 3))
        result = compare_synthetic(**args)
        self.assertIsNone(result['aggregate'])
        self.assertFalse(result['comparison_complete'])
        self.assertFalse(result['reconciled'])
        self.assertEqual(result['accounts'], [])
        self.assertEqual(result['exceptions'], [
            {'kind': 'aggregate_unavailable', 'reason': 'duplicate_or_unresolved_mapping'},
            {'kind': 'duplicate_mapping', 'side': 'target', 'match_id': 'SYNTH-MAP-B', 'record_ids': ['SYNTH-TGT-B', 'SYNTH-TGT-C']},
            {'kind': 'duplicate_record_id', 'side': 'source', 'record_id': 'SYNTH-SRC-A', 'count': 2},
            {'kind': 'unresolved_mapping', 'side': 'target', 'record_id': 'SYNTH-TGT-D'},
        ])
        self.assertEqual(result, compare_synthetic(**(args | {'source': list(reversed(args['source'])), 'target': list(reversed(args['target']))})))

    def test_valid_match_and_signed_cents(self):
        args = self.inputs()
        args['source'] = [row('SYNTH-SRC-A', 'SYNTH-MAP-A', -1)]
        args['target'] = [row('SYNTH-TGT-A', 'SYNTH-MAP-A', -1)]
        result = compare_synthetic(**args)
        self.assertTrue(result['reconciled'])
        self.assertTrue(result['comparison_complete'])
        self.assertEqual(result['exceptions'], [])
        self.assertEqual(result['accounts'][0]['status'], 'match')

    def test_invalid_input_fails_without_result_or_external_calls(self):
        args = self.inputs()
        invalid = [args | {'as_of': '20261110'}, args | {'as_of': '2026-02-30'},
                   args | {'source_provenance': 'real-file.csv'}, args | {'target_provenance': 'SYNTH-PROV-SOURCE'},
                   args | {'source': [], 'target': []}, args | {'source': tuple(args['source'])}]
        for bad in (True, 1.0, '1', 1000000000000):
            changed = deepcopy(args)
            changed['source'][0]['principal_cents'] = bad
            invalid.append(changed)
        for name, value in [('record_id', 'SYNTH-SRC-123'), ('match_id', 'account@example.invalid'), ('extra', 'private')]:
            changed = deepcopy(args)
            changed['source'][0][name] = value
            invalid.append(changed)
        invalid.append(args | {'source': [args['source'][0]] * 10001})
        with patch('builtins.open', side_effect=AssertionError('No files')), \
             patch('socket.socket', side_effect=AssertionError('No network')):
            for bad in invalid:
                with self.subTest(bad_type=type(bad).__name__), self.assertRaises(ReconciliationInputError):
                    compare_synthetic(**bad)

    def test_feature_and_explicit_synthetic_gates_fail_closed(self):
        args = self.inputs()
        for key in ('DEBUG', 'DEMO_LEDGER_ENABLED', 'SYNTHETIC_RECONCILIATION_ENABLED'):
            with self.subTest(gate=key), override_settings(**{key: False}), self.assertRaises(PermissionDenied):
                compare_synthetic(**args)
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value), self.assertRaises(PermissionDenied):
                compare_synthetic(**(args | {'synthetic_only': value}))

    def test_unknown_amounts_preserve_known_comparisons_and_never_match(self):
        args = self.inputs()
        args['source'][0]['principal_cents'] = None
        args['target'][1]['fees_cents'] = None
        args['target'][0]['interest_cents'] = 2000
        result = compare_synthetic(**args)
        self.assertFalse(result['reconciled'])
        self.assertFalse(result['comparison_complete'])
        self.assertEqual([a['status'] for a in result['accounts']], ['mismatch', 'incomplete'])
        self.assertEqual(result['aggregate']['source_cents']['principal_cents'], None)
        self.assertEqual(result['aggregate']['target_cents']['principal_cents'], 104200)
        self.assertEqual(result['aggregate']['target_minus_source_cents'],
                         {'principal_cents': None, 'interest_cents': -50, 'fees_cents': None, 'unapplied_cents': 0})
        self.assertEqual([e for e in result['exceptions'] if e['kind'] == 'unknown_amount'], [
            {'kind': 'unknown_amount', 'side': 'source', 'record_id': 'SYNTH-SRC-A', 'match_id': 'SYNTH-MAP-A', 'field': 'principal_cents'},
            {'kind': 'unknown_amount', 'side': 'target', 'record_id': 'SYNTH-TGT-B', 'match_id': 'SYNTH-MAP-B', 'field': 'fees_cents'},
        ])
        self.assertEqual(result, compare_synthetic(**(args | {'source': list(reversed(args['source'])), 'target': list(reversed(args['target']))})))

    def test_unknown_on_unmapped_and_missing_records_is_not_dropped(self):
        args = self.inputs()
        args['source'] = [row('SYNTH-SRC-A', None, None)]
        args['target'] = [row('SYNTH-TGT-B', 'SYNTH-MAP-B', None)]
        result = compare_synthetic(**args)
        self.assertIsNone(result['aggregate'])
        self.assertEqual([e['kind'] for e in result['exceptions']],
                         ['aggregate_unavailable', 'missing_account', 'unknown_amount', 'unknown_amount', 'unresolved_mapping'])
        self.assertFalse(result['reconciled'])
