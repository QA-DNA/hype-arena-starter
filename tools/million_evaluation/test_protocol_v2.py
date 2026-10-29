import unittest
from protocol import ProtocolError, kleene, leaves
from protocol_v2 import ProtocolV2


class SurfaceCompatibility(unittest.TestCase):
    def setUp(self):
        self.p = ProtocolV2({'subjects': [
            {'name': 'Atlas', 'attributes': ['price', 'staff', 'desks', 'customers', 'version', 'api_version']},
            {'name': 'Boreal', 'attributes': ['customers']},
        ]}, {'attributes': {'customers': 'customer count'}})

    def inp(self, text, context=()):
        return {'text': text, 'context': list(context), 'evidence_policy': 'provided_notes_only'}

    def test_flat_sentences_and_decimal_versions(self):
        tree = self.p.parse(self.inp('According to the 2 March 2026 note, Atlas costs €12 per month. From the note dated 3 March 2026: Atlas is on version 2.1. My tea has gone cold.'))
        self.assertEqual(tree['type'], 'all')
        self.assertEqual([n['reference']['attribute'] for n in leaves(tree)], ['price', 'version'])
        self.assertIn('version 2.1', tree['children'][1]['literal'])

    def test_specific_staff_pattern_wins_over_generic_has(self):
        tree = self.p.parse(self.inp('The 2 March 2026 note says Atlas has 26 employees on staff.'))
        self.assertEqual(tree['reference']['attribute'], 'staff')
        self.assertEqual(tree['value_text'], '26 employees')

    def test_negation_scope_and_mixed_unknown_logic(self):
        text = 'Not all of these hold: (customer count in note one: 4 customers); ((customer count in note one: 5 customers) or (customer count in note two: 3 customers)).'
        context = [
            {'id': 'binding-p-a', 'role': 'discourse', 'text': 'Note one concerns Atlas: customer count, dated 2 March 2026.'},
            {'id': 'binding-p-b', 'role': 'discourse', 'text': 'Note two concerns Boreal: customer count, dated 3 March 2026.'},
        ]
        tree = self.p.parse(self.inp(text, context))
        self.assertEqual(tree['type'], 'not')
        self.assertEqual(tree['child']['children'][1]['type'], 'any')
        self.assertEqual(kleene(tree, lambda leaf: 'false' if leaf['value_text'].startswith('4 ') else 'unsure'), 'true')

    def test_comparison_keeps_dates_and_strictness(self):
        tree = self.p.parse(self.inp('The customer count for Atlas reported on 2 March 2026 is no higher than the customer count for Boreal reported on 3 March 2026.'))
        self.assertEqual(tree['type'], 'compare')
        self.assertEqual(tree['op'], 'le')
        self.assertEqual(tree['left']['date'], '2026-03-02')
        self.assertEqual(tree['right']['subject'], 'Boreal')

    def test_missing_binding_and_unrecognized_text_fail_closed(self):
        with self.assertRaises(ProtocolError):
            self.p.parse(self.inp('Customer count in note one: 5 customers.'))
        with self.assertRaises(ProtocolError):
            self.p.parse(self.inp('Atlas probably has the best price.'))

    def test_v1_interface_delegates_without_changing_output(self):
        from protocol import Protocol
        base = Protocol({'subjects': [{'name': 'Atlas', 'attributes': ['customers']}]}, {})
        text = "Using only the supplied notes, all of these statements are true: (the entry for Atlas's customers in the note of 2 March 2026 reads 5 customers)."
        self.assertEqual(self.p.parse(self.inp(text)), base.parse(self.inp(text)))


if __name__ == '__main__':
    unittest.main()
