"""Author contract tests on real temporary journals; not agent-quality metrics."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from t2ag_next import governance as g, support, service, distribution
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError, get, put


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.j=Journal(self.root/'instance'); self.j.initialize({'language':'en'})
        self.n=0

    def call(self,action,payload,text=None,role=None):
        self.n+=1; s=self.j.read_state()
        r={'request_id':f'gov-test-{self.n}','action':action,'payload':payload,
           'actor':{'role':role or ('student' if text else 'teacher'),'source':f'fixture-{self.n}','text':text or 'Attributed synthetic governance observation.'},
           'expected':{k:v['version'] for k,v in s['objects'].items()}}
        def dispatch(current,request):
            g.validate_dispatch(current,request)
            return g.plan(current,request) if action in g.ACTIONS else support.plan(current,request)
        return self.j.apply(r,dispatch)

    def data(self,kind,identity): return get(self.j.read_state(),kind,identity)

    def seed(self,kind,identity,data):
        """Explicit synthetic internal fixture, never a public governance action."""
        self.n+=1
        r={'request_id':f'internal-{self.n}','action':'internal.fixture','payload':{},'actor':{'role':'system','source':'test-fixture','text':'Synthetic internal fixture.'},'expected':{}}
        return self.j.apply(r,lambda s,r:[put(kind,identity,data)])

    def evidence(self): return [{'kind':'student','id':'current'}]

    def issue(self):
        return self.call('gov.issue.open',{'id':'P-0001','problem':'A repeatable synthetic defect.','root_cause':'missing-boundary','scope':'fixture','category':'system','evidence_refs':self.evidence()})

    def soft_resolution(self):
        return {'id':'P-0001','resolution':'Retain an explicit reminder.','enforcement':'prose','playbook_status':{'kind':'not_applicable','reason':'Temporary local fixture.'},'evidence_refs':self.evidence(),'accepted_risk':'A reminder is a soft guarantee.'}

    def negative(self):
        state=self.j.read_state()
        request={'request_id':'negative-candidate','action':'student.update','payload':{'id':'current','declarations':{'language':'zh'}},'actor':{'role':'teacher','source':'fixture','text':'Not student permission.'},'expected':{'student/current':state['objects']['student/current']['version']}}
        service.validate_negative(self.j.path,'NEG',request,'STUDENT_DECISION_REQUIRED')

    def rule(self,identity='R1',protection='ordinary',program=False):
        p={'id':identity,'body':'Preserve exact confirmation boundary.','owner':identity+'-owner','protection':protection,
           'clauses':{'permission':'Teacher attribution cannot authorize student changes.'},'enforcement':'tool' if program else 'prose',
           'consumer_refs':self.evidence(),'failure_signal':'STUDENT_DECISION_REQUIRED','enforcement_type':['gate','program'] if program else ['language','gate'],
           'decision_owner':'student','actual_executor':'action:student.update' if program else 'agent following prose',
           'evidence':self.evidence(),'wake':'Actual object or validator changes.','stale':['object_change','validator_change'],
           'bypass':'Same-privilege shell can replace code/storage; API does not authenticate human identity.','accepted_risk':'Agent compliance only.'}
        if program: p.update(implementation_ref='action:student.update',negative_validation_id='NEG')
        return self.call('gov.rule.register',p)

    def test_strikes_are_recurrences_after_first_remedy_not_occurrences(self):
        self.issue()
        self.call('gov.issue.recur',{'id':'P-0001','evidence_refs':self.evidence()})
        self.call('gov.issue.resolve',self.soft_resolution())
        self.assertEqual(self.data('issue','P-0001')['remedy_since'],2)
        self.call('gov.issue.recur',{'id':'P-0001','evidence_refs':self.evidence()})
        self.call('gov.issue.resolve',self.soft_resolution())
        self.assertEqual(self.data('issue','P-0001')['remedy_since'],2)
        self.call('gov.issue.recur',{'id':'P-0001','evidence_refs':self.evidence()})
        before=self.j.read_state()
        with self.assertRaisesRegex(DomainError,'Two recurrences'): self.call('gov.issue.resolve',self.soft_resolution())
        self.assertEqual(before,self.j.read_state())
        self.assertEqual(self.data('issue','P-0001')['reopen_count'],2)

    def test_issue_program_closure_requires_executed_negative_not_string(self):
        self.issue(); p=self.soft_resolution();p.update(enforcement='tool',implementation_ref='action:student.update',failure_signal='STUDENT_DECISION_REQUIRED',negative_validation_id='NEG')
        with self.assertRaises(DomainError): self.call('gov.issue.resolve',p)
        self.negative(); self.call('gov.issue.resolve',p)
        self.assertEqual(self.data('issue','P-0001')['verification']['id'],'NEG')

    def test_issue_identity_category_and_weak_legacy_path_rejected(self):
        self.issue()
        with self.assertRaises(DomainError): self.issue()
        with self.assertRaisesRegex(DomainError,'governed'): self.call('issue.resolve',{'id':'P-0001'})
        with self.assertRaises(DomainError): self.call('gov.issue.open',{'id':'P2','problem':'Math error','root_cause':'wrong-answer','scope':'fixture','category':'knowledge','evidence_refs':self.evidence()})

    def test_rule_language_gate_program_are_independent_truthful_axes(self):
        self.rule(); self.negative(); self.rule('R2',program=True)
        self.assertEqual(self.data('rule','R2')['enforcement_type'],['gate','program'])
        self.assertFalse(self.data('rule','R2')['host_identity_authenticated'])

    def test_rule_retirement_maps_all_original_semantics_and_never_deletes(self):
        self.rule(); self.rule('R2')
        mapping=[{'clause_id':'permission','disposition':'sink','destination_id':'R2','destination_clause_id':'permission','semantic_explanation':'Same explicit decision boundary at its new owner.'}]
        p={'id':'R1','semantic_map':mapping,'map_sha256':g.digest(mapping),'consumer_refs':self.evidence(),'reason':'One canonical replacement.','automatic':True}
        with self.assertRaises(DomainError): self.call('gov.rule.migrate',p,'I approve this rule migration.')
        p['automatic']=False;self.call('gov.rule.migrate',p,'I approve this rule migration.')
        self.assertEqual(self.data('rule','R1')['status'],'retired')
        self.assertIn('permission',self.data('rule','R1')['clauses'])
        with self.assertRaises(DomainError): self.call('gov.rule.use',{'id':'R1','use_ref':self.evidence()[0],'used_at':'2026-09-30T00:00:00Z'})

    def test_protected_rule_requires_changelog_and_real_negative(self):
        self.rule(protection='core'); self.rule('R2')
        mapping=[{'clause_id':'permission','disposition':'retire','reason':'Explicit documented changed requirement.'}]
        p={'id':'R1','semantic_map':mapping,'map_sha256':g.digest(mapping),'consumer_refs':self.evidence(),'reason':'Explicit protected change.','automatic':False}
        with self.assertRaises(DomainError): self.call('gov.rule.migrate',p,'I approve this rule migration.')
        self.negative();self.call('gov.history.record',{'id':'CH','category':'changelog','body':'Actual protected change retained.'})
        p.update(changelog_id='CH',negative_validation_id='NEG',implementation_ref='action:student.update',failure_signal='STUDENT_DECISION_REQUIRED')
        self.call('gov.rule.migrate',p,'I approve this rule migration.')

    def test_usage_unknown_is_not_cold_and_core_is_exempt(self):
        now=datetime(2026,9,30,tzinfo=timezone.utc)
        self.assertEqual(g.rule_usage({'protection':'ordinary'},now)['classification'],'unobserved')
        d={'protection':'ordinary','dated_uses':[{'used_at':'2026-08-01T00:00:00Z'}]}
        self.assertEqual(g.rule_usage(d,now)['classification'],'archive_candidate')
        d['protection']='core';self.assertEqual(g.rule_usage(d,now)['classification'],'protected_or_exempt')
        self.assertFalse(g.rule_usage(d,now)['automatic_action'])

    def test_evolution_adr_bidirectional_state_machine_and_archive_landing(self):
        self.call('gov.evolution.create',{'id':'EV-0001','body':'Original architecture observation.','decision_class':'architecture'},'I approve this evolution record.')
        with self.assertRaises(DomainError): self.call('gov.evolution.transition',{'id':'EV-0001','status':'archived','reason':'skip'},'I approve this evolution transition.')
        self.call('gov.evolution.transition',{'id':'EV-0001','status':'discussing','reason':'Discuss actual tradeoff.'},'I approve this evolution transition.')
        self.call('gov.adr.create',{'id':'ADR-0001','body':'Portable decision body.','portable_key':'first','source_evolution':['EV-0001'],'supersedes':[]})
        with self.assertRaises(DomainError): self.call('gov.adr.accept',{'id':'ADR-0001'},'I approve this architecture decision.')
        self.call('gov.evolution.transition',{'id':'EV-0001','status':'decided','reason':'Decision approved.'},'I approve this evolution transition.')
        self.call('gov.adr.accept',{'id':'ADR-0001'},'I approve this architecture decision.')
        self.assertFalse(self.data('adr','ADR-0001')['implementation_complete'])
        self.call('gov.history.record',{'id':'CH','category':'changelog','body':'Implementation actually landed.'})
        self.call('gov.history.record',{'id':'MONTH','category':'journal','body':'EV-0001 decided to archived; see CH.'},'Save this monthly index record.')
        self.call('gov.evolution.transition',{'id':'EV-0001','status':'archived','reason':'Landed.','changelog_id':'CH','month_index_id':'MONTH','implementation_refs':self.evidence()},'I approve this evolution transition.')
        self.assertEqual(self.data('evolution','EV-0001')['body'],'Original architecture observation.')
        with self.assertRaises(DomainError): self.call('gov.evolution.transition',{'id':'EV-0001','status':'discussing','reason':'resurrect'},'I approve this evolution transition.')

    def campaign(self,scope='*'):
        limits={'tokens':100,'repair_rounds':2,'full_reviews':2,'test_commands':3,'attempts_per_round':3}
        p={'id':'CAMP','scope_actions':[scope],'objective_key':'same-root-objective','acceptance_contract':'frozen-contract-v1','completion_definition':'All named findings settled.','limits':limits,'deadline':(_now()+timedelta(hours=1)).isoformat()}
        self.call('gov.campaign.create',p,'I approve this campaign envelope.');return limits

    def test_campaign_omitted_id_renumber_and_exact_limit_cannot_bypass(self):
        limits=self.campaign(); counters={k:0 for k in limits};counters['tokens']=100
        self.call('gov.campaign.observe',{'id':'CAMP','counters':counters,'measurement_source':'actual fixture counter','evidence_ref':'fixture-meter-1'})
        self.assertEqual(self.data('campaign','CAMP')['status'],'stopped_budget')
        with self.assertRaisesRegex(DomainError,'omitting'): self.call('course.create',{'id':'C','title':'No','course_type':'praxis'},'Create course.')
        with self.assertRaises(DomainError): self.campaign()
        d=self.data('campaign','CAMP');limits={k:v+101 for k,v in limits.items()}
        self.call('gov.campaign.renew',{'id':'CAMP','limits':limits,'deadline':(_now()+timedelta(hours=2)).isoformat(),'reason':'New bounded allowance.','previous_envelope_sha256':g.digest(d)},'I approve this campaign renewal.')
        self.assertEqual(self.data('campaign','CAMP')['counters']['tokens'],100)
        self.call('course.create',{'id':'C','title':'Now allowed','course_type':'praxis'},'Create course.')

    def test_campaign_named_scope_does_not_block_unrelated_learning(self):
        limits=self.campaign('gov.rule.*'); counters={k:0 for k in limits};counters['test_commands']=3
        self.call('gov.campaign.observe',{'id':'CAMP','counters':counters,'measurement_source':'fixture','evidence_ref':'trace'})
        self.call('course.create',{'id':'C','title':'Unrelated teaching','course_type':'praxis'},'Create course.')
        with self.assertRaises(DomainError): self.rule()

    def test_formal_choice_preserves_natural_acceptance_and_rejects_known_contradiction(self):
        p={'id':'EV-0001','body':'Keep an observation.','decision_class':'observation'}
        before=self.j.read_state()
        for text in ("I don't approve this evolution record.",'我不同意创建这条记录。','不能确认这项变更。'):
            with self.subTest(text=text):
                with self.assertRaises(DomainError):self.call('gov.evolution.create',p,text)
                self.assertEqual(self.j.read_state(),before)
        original='这条很重要，先记进演化观察里，具体实施以后再议。'
        self.call('gov.evolution.create',p,original)
        event=self.data('evolution','EV-0001')['events'][0]
        self.assertEqual(event['actor']['text'],original)
        self.assertEqual(event['actor']['authorization_evidence_class'],'agent_attributed')
        self.assertFalse(event['actor']['host_identity_authenticated'])

    def test_actual_validation_plan_stale_sha_and_v0_no_domain_expansion(self):
        f=self.root/'changed.md';f.write_text('first','utf-8')
        plan=g.build_validation_plan(self.j.read_state(),level='V0',changed_files=[str(f)])
        self.assertIsNone(plan['domain_plan']); self.assertIsNone(plan['max_test_tier'])
        f.write_text('changed','utf-8')
        with self.assertRaises(DomainError):g.run_validation(self.j.path,'stale',plan,plan['plan_sha256'])
        plan=g.build_validation_plan(self.j.read_state(),level='V1',changed_kinds=['course'])
        with self.assertRaises(DomainError):g.run_validation(self.j.path,'bad-sha',plan,'0'*64)
        g.run_validation(self.j.path,'runtime',plan,plan['plan_sha256'])
        run=self.data('governance_run','runtime');self.assertEqual(run['plan']['profile'],'runtime')
        self.assertIn('runtime',run['actual_checks']);self.assertEqual(run['release_qualification'],'not_requested')
        self.assertTrue(g.run_validation(self.j.path,'runtime',plan,plan['plan_sha256'])['replayed'])

    def test_v0_file_plan_survives_unrelated_learning_progress_without_doctor(self):
        changed = self.root / 'changed.md'
        changed.write_text('The explicitly checked file.', encoding='utf-8')
        plan = g.build_validation_plan(self.j.read_state(), level='V0', changed_files=[str(changed)])
        self.call('course.create', {'id':'C','title':'Independent learning progress','course_type':'praxis'}, 'Create this course.')
        with patch.object(service, 'doctor', side_effect=AssertionError('V0 must not expand to Doctor')):
            result = g.run_validation(self.j.path, 'file-only', plan, plan['plan_sha256'])
        self.assertTrue(result['ok'])
        self.assertEqual(self.data('governance_run','file-only')['actual_checks'], {})

    def test_verdict_waiver_expiry_wake_state_and_hard_fact_preservation(self):
        s=self.j.read_state(); environment={'code':'environment.optional_pdf','status':'WARN','category':'external_environment','hard_failure':False,'object':None,'message':'Optional backend absent.'}
        hard={'code':'route.invalid','status':'FAIL','category':'route','hard_failure':True,'object':None,'message':'Dangling current activity.'}
        self.seed('governance_run','synthetic-run',{'plan':{'level':'V1'},'findings':[environment,hard],'state_basis':g.state_basis(s),'validator_sha256':g.validator_fingerprint()})
        p={'id':'WAIVE','run_id':'synthetic-run','finding_sha256':g.digest(environment),'act':'no','reason':'env_waiver','evidence_refs':self.evidence(),
           'explanation':'External optional capability only.','risk':'PDF rendering unavailable.','responsible':'fixture operator','approved_at':(_now()-timedelta(minutes=1)).isoformat(),'expires_at':(_now()+timedelta(hours=1)).isoformat(),'unfixable_locally':'No installed optional dependency.'}
        self.call('gov.verdict.record',p,'I approve this environment waiver.')
        d=self.data('governance_verdict','WAIVE'); self.assertEqual(g.verdict_state(self.j.read_state(),d)['display_status'],'WAIVED')
        self.assertEqual(g.verdict_state(self.j.read_state(),d,_now()+timedelta(hours=2))['invalidated_by'],'waiver_expired')
        p['id']='HARD';p['finding_sha256']=g.digest(hard)
        with self.assertRaises(DomainError):self.call('gov.verdict.record',p,'I approve this environment waiver.')
        self.call('gov.verdict.wake',{'id':'WAIVE','reason':'Environment changed.'})
        self.assertEqual(g.verdict_state(self.j.read_state(),self.data('governance_verdict','WAIVE'))['invalidated_by'],'wake_triggered')

    def test_verdict_and_plan_invalidate_on_changed_state_and_checker(self):
        s=self.j.read_state()
        verdict={'state_basis':g.state_basis(s),'validator_sha256':g.validator_fingerprint(),'finding':{'status':'WARN'},'reason':'known_debt','woken':False}
        self.assertTrue(g.verdict_state(s,verdict)['valid'])
        with patch.object(g,'validator_fingerprint',return_value='changed'):
            self.assertEqual(g.verdict_state(s,verdict)['invalidated_by'],'validator_changed')
        plan=g.build_validation_plan(s,level='V1',changed_kinds=['course'])
        self.call('course.create',{'id':'C','title':'Changes the actual basis','course_type':'praxis'},'Create course.')
        self.assertEqual(g.verdict_state(self.j.read_state(),verdict)['invalidated_by'],'object_state_changed')
        with self.assertRaises(DomainError):g.run_validation(self.j.path,'old',plan,plan['plan_sha256'])

    def test_deadline_blocks_without_a_submitted_campaign_id_or_observation(self):
        self.campaign('course.*')
        with patch.object(g,'_now',return_value=_now()+timedelta(hours=2)):
            with self.assertRaisesRegex(DomainError,'deadline'):self.call('course.create',{'id':'C','title':'Stop','course_type':'praxis'},'Create course.')
            self.assertTrue(any(x['code']=='campaign.stopped_budget' for x in g.doctor_findings(self.j.read_state())))

    def test_actual_review_bytes_qualified_candidate_remains_unreleased(self):
        package=self.root/'candidate.zip';distribution.build_distribution(Path(__file__).resolve().parents[1],package)
        candidate=hashlib.sha256(package.read_bytes()).hexdigest()
        report={'candidate_sha256':candidate,'author':'fixture author','reviewer':'fixture non-author','scope':'full_candidate','verdict':'passed','cases':{'human-case':'PASS'}}
        blob=self.j.put_blob(json.dumps(report).encode())
        g.import_review(self.j.path,'REVIEW',blob['sha256'])
        self.assertTrue(g.import_review(self.j.path,'REVIEW',blob['sha256'])['replayed'])
        self.call('gov.case_matrix.freeze',{'id':'M','candidate_sha256':candidate,'cases':[
            {'id':'manifest','contract':'Actual package bytes','applicable':True,'condition':'Always','evidence_kind':'program','check_id':'distribution_manifest'},
            {'id':'human-case','contract':'External judgment','applicable':True,'condition':'Frozen required review','evidence_kind':'independent_review','review_id':'REVIEW'}]},'I approve this case matrix.')
        self.call('gov.version.record',{'id':'0.3.0','candidate_sha256':candidate,'matrix_id':'M','implementation_status':'complete'})
        plan=g.build_validation_plan(self.j.read_state(),level='V3',release_reason='release_candidate',package=package,case_matrix_id='M')
        g.run_validation(self.j.path,'release',plan,plan['plan_sha256'])
        self.call('gov.version.qualify',{'id':'0.3.0','run_id':'release','review_refs':[{'kind':'independent_review','id':'REVIEW'}]})
        q=self.data('version_qualification','0.3.0');self.assertFalse(q['released'])
        self.assertEqual(q['release_qualification'],'mechanical_checks_passed_pending_host_approval')
        self.assertFalse(self.data('independent_review','REVIEW')['host_identity_authenticated'])

    def test_release_requires_explicit_reason_actual_package_and_required_cases(self):
        with self.assertRaises(DomainError):g.build_validation_plan(self.j.read_state(),level='V3')
        package=self.root/'runtime.zip';distribution.build_distribution(Path(__file__).resolve().parents[1],package)
        candidate=hashlib.sha256(package.read_bytes()).hexdigest()
        self.call('gov.case_matrix.freeze',{'id':'M','candidate_sha256':candidate,'cases':[
            {'id':'storage','contract':'Actual journal integrity','applicable':True,'condition':'Always','evidence_kind':'program','check_id':'data_integrity'},
            {'id':'agent-journey','contract':'Independent agent journey','applicable':True,'condition':'Required by this matrix','evidence_kind':'independent_review'},
            {'id':'offline','contract':'Optional offline compatibility','feature':'offline_cloud','applicable':False,'condition':'Offline mode disabled; remote uses same instance.','evidence_kind':'program'}]},'I approve this case matrix.')
        plan=g.build_validation_plan(self.j.read_state(),level='V3',release_reason='release_candidate',package=package,case_matrix_id='M')
        g.run_validation(self.j.path,'release',plan,plan['plan_sha256'])
        run=self.data('governance_run','release');self.assertEqual(run['release_qualification'],'pending')
        self.assertEqual([x['status'] for x in run['actual_checks']['case_matrix']],['PASS','REVIEW','NOT_APPLICABLE'])


def _now(): return datetime.now(timezone.utc)


if __name__=='__main__':unittest.main()
