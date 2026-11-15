# SPDX-License-Identifier: MPL-2.0
from django.test import SimpleTestCase
from .form_registry import REFERENCES, REGISTRY_VERSION, research_inventory


class ResearchInventoryTests(SimpleTestCase):
    def snapshot(self, deal_type):
        return {'deal_type': deal_type, 'buyer': {'name': 'Synthetic Buyer', 'address_lines': []},
                'vehicle': {'facts': {'VIN': 'Not recorded', 'Title brand as recorded': 'Not verified', 'Odometer reading': '0'}},
                'trade': None, 'proposal': None}

    def test_registry_keys_are_unique_and_research_is_versioned(self):
        self.assertEqual(len({item.key for item in REFERENCES}), len(REFERENCES))
        self.assertTrue(REGISTRY_VERSION)
        self.assertTrue(all(item.source.startswith('https://') and item.rights and item.revision for item in REFERENCES))

    def test_buyers_guide_is_a_research_topic_for_all_deal_types(self):
        self.assertEqual(REGISTRY_VERSION, 'fl-research-2026-11-10-v6')
        for deal_type in ('Cash', 'Buy here, pay here', 'Not chosen', 'Outside financing'):
            with self.subTest(deal_type=deal_type):
                entries = {item['reference'].key: item for item in research_inventory(self.snapshot(deal_type))}
                reference = entries['buyers-guide']['reference']
                self.assertIn('November 2016', reference.revision)
                self.assertIn('no automatic determination', reference.applicability)
                self.assertIn('Spanish', reference.review)
                self.assertIn('VIN', entries['buyers-guide']['missing'])

    def test_title_research_does_not_treat_unknown_facts_as_ready(self):
        for deal_type in ('Cash', 'Buy here, pay here', 'Not chosen'):
            with self.subTest(deal_type=deal_type):
                entry = next(item for item in research_inventory(self.snapshot(deal_type))
                             if item['reference'].key == 'title')
                self.assertIn('current revision remains unconfirmed', entry['reference'].revision)
                self.assertIn('reproduction', entry['reference'].rights)
                self.assertIn('no automatic determination', entry['reference'].applicability)
                self.assertIn('Title brand verification', entry['missing'])
                self.assertIn('VIN', entry['missing'])

    def test_cash_and_bhph_do_not_confuse_financing(self):
        names = lambda s: {item['reference'].key for item in research_inventory(s)}
        self.assertNotIn('retail-installment', names(self.snapshot('Cash')))
        self.assertIn('retail-installment', names(self.snapshot('Buy here, pay here')))
        self.assertIn('retail-installment', names(self.snapshot('Not chosen')))
        self.assertIn('retail-installment', names(self.snapshot('Outside financing')))

    def test_credit_research_distinguishes_terms_without_deciding_coverage(self):
        entry = next(item for item in research_inventory(self.snapshot('Buy here, pay here'))
                     if item['reference'].key == 'retail-installment')
        reference = entry['reference']
        for term in ('APR as annual credit cost rate', 'amount financed as net credit',
                     'finance charge as dollar credit cost', 'total of payments as scheduled payments'):
            self.assertIn(term, reference.review)
        self.assertIn('no automatic determination', reference.applicability)
        self.assertIn('effective dates remain unverified', reference.revision)
        self.assertIn('Financing proposal', entry['missing'])

    def test_unverified_brand_and_missing_facts_are_not_treated_as_known(self):
        entries = {item['reference'].key: item for item in research_inventory(self.snapshot('Cash'))}
        self.assertIn('Title brand verification', entries['title']['missing'])
        self.assertIn('VIN', entries['title']['missing'])
        self.assertIn('Buyer address', entries['title']['missing'])
        self.assertNotIn('Odometer reading', entries['odometer']['missing'])

    def test_recorded_trade_shows_trade_research(self):
        snapshot = self.snapshot('Cash')
        self.assertNotIn('trade', {x['reference'].key for x in research_inventory(snapshot)})
        snapshot['trade'] = {'record_id': 1}
        self.assertIn('trade', {x['reference'].key for x in research_inventory(snapshot)})

    def test_old_or_incomplete_snapshot_fails_to_unknown(self):
        entries = {item['reference'].key: item for item in research_inventory({})}
        self.assertIn('retail-installment', entries)
        self.assertIn('VIN', entries['title']['missing'])
        self.assertIn('Title brand verification', entries['title']['missing'])

    def test_odometer_secure_and_reassignment_topics_are_research_not_applicability(self):
        for deal_type in ('Cash', 'Buy here, pay here', 'Not chosen', 'Outside financing'):
            with self.subTest(deal_type=deal_type):
                entries = {item['reference'].key: item for item in research_inventory(self.snapshot(deal_type))}
                for key in ('odometer', 'dealer-reassignment', 'secure-odometer-poa'):
                    self.assertIn('no automatic determination', entries[key]['reference'].applicability)
                    self.assertIn('VIN', entries[key]['missing'])
                    self.assertNotIn('Odometer reading', entries[key]['missing'])
                self.assertIn('secure stock', entries['dealer-reassignment']['reference'].rights)
                self.assertIn('Part C', entries['secure-odometer-poa']['reference'].review)
                for key in ('odometer', 'dealer-reassignment', 'secure-odometer-poa'):
                    self.assertIn('indexed', entries[key]['reference'].revision.lower())
                    self.assertIn('blocked', entries[key]['reference'].revision.lower())
        entries = {item['reference'].key: item for item in research_inventory({})}
        for key in ('odometer', 'dealer-reassignment', 'secure-odometer-poa'):
            self.assertIn('Odometer reading', entries[key]['missing'])
