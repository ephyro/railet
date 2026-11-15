# SPDX-License-Identifier: MPL-2.0
from dataclasses import FrozenInstanceError, replace
from django.test import SimpleTestCase
from .hold_rehearsal import Event, Hold, State, assess, place, transition


class HoldRehearsalTests(SimpleTestCase):
    def place(self, name, records=('synthetic:record',), unknown=False):
        return place('synthetic:' + name, 'synthetic:staff', records, scope_unknown=unknown, enabled=True)

    def move(self, hold, action, actor='synthetic:reviewer'):
        return transition(hold, action, actor, enabled=True)

    def test_overlapping_release_and_reactivation(self):
        first=self.place('one'); second=self.place('two')
        self.assertEqual(assess('synthetic:record',[second,first],enabled=True).blocked_by,('synthetic:one','synthetic:two'))
        first=self.move(self.move(first,'request_release'),'approve_release','synthetic:approver')
        self.assertEqual(assess('synthetic:record',[first,second],enabled=True).blocked_by,('synthetic:two',))
        second=self.move(self.move(second,'confirm'),'request_release')
        second=self.move(second,'approve_release','synthetic:approver')
        self.assertTrue(assess('synthetic:record',[first,second],enabled=True).hold_clear_for_review)
        revived=self.move(first,'reactivate')
        self.assertEqual(revived.state,State.PROVISIONAL)
        self.assertEqual(revived.events[-1].prior_release_event,2)
        self.assertFalse(assess('synthetic:record',[revived,second],enabled=True).hold_clear_for_review)
        self.assertEqual(first.state,State.RELEASED)
        with self.assertRaises(FrozenInstanceError):revived.events[-1].actor='synthetic:changed'

    def test_unknown_scope_blocks_any_candidate_until_released(self):
        hold=self.place('unknown',(),True)
        result=assess('synthetic:unlisted',[hold],enabled=True)
        self.assertEqual(result.unknown_scope,('synthetic:unknown',))
        self.assertFalse(result.hold_clear_for_review)
        hold=self.move(self.move(hold,'request_release'),'approve_release','synthetic:other')
        self.assertTrue(assess('synthetic:unlisted',[hold],enabled=True).hold_clear_for_review)

    def test_invalid_transitions_self_approval_and_gate(self):
        hold=self.place('hold')
        with self.assertRaises(ValueError):self.move(hold,'approve_release')
        pending=self.move(hold,'request_release')
        with self.assertRaises(ValueError):self.move(pending,'approve_release')
        with self.assertRaises(ValueError):self.move(pending,'confirm')
        with self.assertRaises(PermissionError):assess('synthetic:record',[hold])
        with self.assertRaises(ValueError):self.place('invalid',('real-record',))
        with self.assertRaises(ValueError):assess('synthetic:record',[hold,hold],enabled=True)
        self.assertEqual(len(hold.events),1)

    def test_rejects_manual_state_scope_and_mutable_history_forgery(self):
        hold = self.place('one')
        forged = (
            Hold('synthetic:one', State.RELEASED, hold.records, False, ()),
            replace(hold, state=State.RELEASED),
            replace(hold, state='released'),
            replace(hold, records={'synthetic:record'}),
            replace(hold, events=list(hold.events)),
            replace(hold, scope_unknown=0),
            replace(hold, identifier='non-synthetic'),
            replace(hold, records=frozenset({'non-synthetic'})),
            replace(hold, events=('not-an-event',)),
        )
        for invalid in forged:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    assess('synthetic:record', [invalid], enabled=True)
                with self.assertRaises(ValueError):
                    self.move(invalid, 'request_release')

    def test_rejects_forged_release_and_reactivation_history(self):
        hold = self.place('one')
        request = Event('request_release', 'synthetic:reviewer', State.PROVISIONAL, State.RELEASE_REQUESTED)
        approval = Event('approve_release', 'synthetic:approver', State.RELEASE_REQUESTED,
                         State.RELEASED, requester='synthetic:reviewer')
        # Structural replay cannot prove that a consistent, hand-built history
        # represents authorized actors or an actual decision.
        release = replace(hold, state=State.RELEASED, events=hold.events + (request, approval))
        self.assertTrue(assess('synthetic:record', [release], enabled=True).hold_clear_for_review)
        invalid = (
            replace(release, events=hold.events + (approval,)),
            replace(release, events=hold.events + (request, replace(approval, actor='synthetic:reviewer'))),
            replace(release, events=hold.events + (request, replace(approval, requester='synthetic:wrong'))),
            replace(release, events=hold.events + (request, replace(approval, after=State.CONFIRMED))),
            replace(release, events=(replace(hold.events[0], requester='synthetic:reviewer'), request, approval)),
            replace(release, events=hold.events + (replace(request, prior_release_event=0), approval)),
            replace(release, state=State.PROVISIONAL, events=release.events + (
                Event('reactivate', 'synthetic:reviewer', State.RELEASED, State.PROVISIONAL,
                      prior_release_event=1),)),
            replace(release, state=State.PROVISIONAL, events=release.events + (
                Event('reactivate', 'synthetic:reviewer', State.RELEASED, State.PROVISIONAL,
                      prior_release_event=True),)),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                assess('synthetic:record', [candidate], enabled=True)
