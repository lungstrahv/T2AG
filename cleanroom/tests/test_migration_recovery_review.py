"""Non-author recovery checks by metrics_contract, using actual temporary Journals."""
from copy import deepcopy
import unittest

import test_migration_recovery as author_fixture
from t2ag_next import migration_recovery as recovery, support
from t2ag_next.model import DomainError, put


class IndependentRecoveryReview(unittest.TestCase):
    def fixture(self):
        f = author_fixture.RecoveryJourneys()
        f.setUp(); self.addCleanup(f.tearDown)
        return f

    def test_origin_locator_does_not_match_another_question_prefix(self):
        for suffix in ('0', '(1)', '1'):
            with self.subTest(suffix=suffix):
                f = self.fixture(); f.mistake_fixture()
                target = f.i.data('mistake', 'M1')
                target['activity_id'] = None
                target['legacy_fields']['来源'] = 'Exercise UNIT1 / Q002'
                old = {'activity_id': f.aid, 'history_only': True,
                       'original_body': 'Original UNIT1-Q002' + suffix + ' answer.'}
                f.inject_legacy_fixture([put('mistake', 'M1', target), put('attempt', 'different-question', old)])
                p = f.payload('mistake', 'M1', ('legacy_fields', 'legacy_retest_rows', 'original_body'), mistake_id='M1')
                p['origin_evidence'] = {'kind': 'attempt', 'id': 'different-question', 'field': 'original_body',
                    'value_sha256': support.digest(old['original_body']), 'locator': 'UNIT1-Q002'}
                before = f.i.journal.read_state()
                with self.assertRaises(DomainError): f.call('migration.mistake.recover', p)
                self.assertEqual(f.i.journal.read_state(), before)

    def test_missing_expected_evidence_dependency_cannot_publish_recovery(self):
        f = self.fixture(); p = f.exercise_fixture()
        r = f.i.request('migration.exercise.recover', p)
        r['expected'].pop('attempt/old-answer')
        before = f.i.journal.read_state()
        with self.assertRaises(DomainError): f.i.journal.apply(r, recovery.plan)
        self.assertEqual(f.i.journal.read_state(), before)

    def test_recovery_keeps_unrelated_ambiguity_and_all_original_help_unknown(self):
        f = self.fixture(); f.exercise_fixture()
        target = f.i.data('exercise', f.aid)
        target['uncertainties'].append('another_unmapped_semantic_field')
        f.inject_legacy_fixture([put('exercise', f.aid, target)])
        p = f.payload('exercise', f.aid, ('legacy_fields', 'original_body', 'problems'), exercise_id=f.aid)
        f.call('migration.exercise.recover', p)
        result = f.i.data('exercise', f.aid)
        self.assertTrue(result['migration_requires_reconciliation'])
        self.assertEqual(result['uncertainties'], ['another_unmapped_semantic_field'])
        self.assertEqual({x['problem_id'] for x in result['assistance']}, set(target['problems']))
        self.assertTrue(all(x['level'] == 'legacy_unknown' for x in result['assistance']))
        self.assertEqual(result['original_body'], target['original_body'])

    def test_due_gate_ignores_other_course_and_corrected_dates(self):
        f = self.fixture()
        f.call('migration.mistake.recover', f.mistake_fixture(relative=True))
        f.call('course.create', {'id':'OTHER','title':'Other synthetic course','course_type':'mastery','learning_mode':'goal'}, 'Create the other course.')
        f.call('activity.create', {'id':'OTHER/E','course_id':'OTHER','activity_type':'exercise','title':'Other activity'})
        for n in (2,3,4):
            f.call('time.record', {'id':f'other-{n}','activity_id':'OTHER/E','quality':'exact','seconds':30,'started_at':f'2026-01-0{n}T12:00:00Z'})
        before = f.i.data('mistake', 'M1')
        with self.assertRaises(DomainError) as caught: f.i.retest(f.aid, settle=False)
        self.assertEqual(caught.exception.code, 'RETEST_RECOVERY_DUE')
        self.assertEqual(f.i.data('mistake','M1'), before)
        for n in (2,3,4):
            f.call('time.record', {'id':f'own-{n}','activity_id':f.aid,'quality':'exact','seconds':30,'started_at':f'2026-01-0{n}T12:00:00Z'})
        f.call('time.record', {'id':'correct-own-4','activity_id':f.aid,'quality':'unknown','corrects':'own-4'})
        before = f.i.journal.read_state()
        with self.assertRaises(DomainError) as caught: f.call('mistake.retest', f.i.last_retest)
        self.assertEqual(caught.exception.code, 'RETEST_RECOVERY_DUE')
        self.assertEqual(f.i.journal.read_state(), before)
        f.call('time.record', {'id':'confirmed-own-4','activity_id':f.aid,'quality':'exact','seconds':30,
                              'started_at':'2026-01-04T12:00:00Z','corrects':'correct-own-4'})
        f.call('mistake.retest', f.i.last_retest)
        f.call('session.close', {'session_id':f.i.last_retest['session_id']})
        self.assertEqual(f.i.data('mistake','M1')['cycle_successes'], 1)


if __name__ == '__main__': unittest.main()
