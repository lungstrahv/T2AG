"""Non-author governance boundary checks; no production code mutations."""
import json
import unittest

from t2ag_next import governance as g
from t2ag_next.model import DomainError
import test_governance as author_fixture


class GovernanceIndependentReview(unittest.TestCase):
    def fixture(self):
        f=author_fixture.GovernanceTests();f.setUp();self.addCleanup(f.doCleanups)
        return f

    def test_gov_r1_validation_host_entry_respects_global_stopped_campaign(self):
        f=self.fixture();limits=f.campaign()
        counters={k:0 for k in limits};counters['tokens']=limits['tokens']
        f.call('gov.campaign.observe',{'id':'CAMP','counters':counters,'measurement_source':'synthetic exact counter','evidence_ref':'counter-receipt'})
        file=f.root/'changed.txt';file.write_text('Actual local check input.',encoding='utf8')
        plan=g.build_validation_plan(f.j.read_state(),level='V0',changed_files=[str(file)])
        before=f.j.read_state()
        with self.assertRaises(DomainError) as caught:g.run_validation(f.j.path,'should-not-run',plan,plan['plan_sha256'])
        self.assertEqual(caught.exception.code,'STOPPED_BUDGET')
        self.assertEqual(before,f.j.read_state())

    def test_gov_r2_malformed_scope_cannot_silently_disable_campaign_guard(self):
        f=self.fixture()
        with self.assertRaises(DomainError):f.campaign('course.*.create')

    def test_gov_r3_full_candidate_pass_cannot_hide_its_own_failed_case(self):
        f=self.fixture()
        report={'candidate_sha256':'a'*64,'author':'actual synthetic author','reviewer':'different synthetic reviewer','scope':'full_candidate',
            'verdict':'passed','cases':{'chosen-case':'PASS','unselected-blocker':'FAIL'}}
        blob=f.j.put_blob(json.dumps(report).encode('utf8'))
        with self.assertRaises(DomainError):g.import_review(f.j.path,'contradictory-report',blob['sha256'])

    def test_gov_r4_report_attribution_cannot_be_different_whitespace(self):
        f=self.fixture()
        report={'candidate_sha256':'a'*64,'author':' ','reviewer':'\n','scope':'full_candidate','verdict':'passed','cases':{'case':'PASS'}}
        blob=f.j.put_blob(json.dumps(report).encode('utf8'))
        with self.assertRaises(DomainError):g.import_review(f.j.path,'empty-attribution',blob['sha256'])


if __name__=='__main__':unittest.main()
