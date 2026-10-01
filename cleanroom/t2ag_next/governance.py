"""Executable local governance contracts; attributed decisions are not host identity.

No shell commands, arbitrary code, or caller-supplied PASS receipts execute here.
Historical text remains in the journal; diagnostic suggestions never delete data.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re

from .model import DomainError, fields, get, key, put, require, require_student, version
from .support import _read, _new, _all, _provenance, digest

STRIKE_LIMIT = 2
PROTECTION = {'ordinary', 'core', 'meta'}
REASONS = {'checker_defect', 'not_applicable', 'env_waiver', 'known_debt', 'paused'}
HARD_FAILURES = {'data_integrity', 'stable_id', 'schema', 'route', 'authority', 'projection', 'candidate_binding'}
RELEASE_CHECKS = {'data_integrity', 'identity_schema_references', 'routes_authority', 'migration_history', 'distribution_parity', 'projection_parity', 'candidate_binding'}
LEVELS = {'V0': (None, None), 'V1': ('runtime', 'fast'), 'V2': ('runtime', 'deep'), 'V3': ('release', 'release_only')}
RELEASE_REASONS = {'formal_release', 'version_upgrade', 'full_review', 'real_migration', 'release_candidate'}
EVIDENCE_KINDS = {'governance_run', 'governance_verdict', 'version_qualification', 'independent_review'}
LEGACY_ACTIONS = {'issue.open', 'issue.recur', 'issue.resolve', 'rule.register', 'rule.retire', 'rule.use', 'history.record', 'campaign.create', 'campaign.observe'}
MAINTENANCE_ACTIONS = {'gov.campaign.observe', 'gov.campaign.renew', 'gov.verdict.record', 'gov.verdict.wake'}


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'GOVERNANCE_TEXT', f'Provide nonempty {name}.')


def _time(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(dt.tzinfo is not None, 'GOVERNANCE_TIME', 'Timezone is required.')
        return dt
    except (TypeError, AttributeError, ValueError) as exc:
        raise DomainError('GOVERNANCE_TIME', 'Use an ISO timestamp with timezone.') from exc


def _now(): return datetime.now(timezone.utc)


def _approval(r, subject):
    actor = require_student(r)
    text = actor['text'].strip().casefold()
    # The named action is the formal choice, interpreted from the original user
    # message by the calling agent/host. This finite contradiction check adds no
    # authentication and is deliberately not a positive-phrase NLP classifier.
    negative=r"不同意|不批准|拒绝|暂不|不能确认|不可以(?:执行|批准|退役|变更|创建|登记|发布|续期)|不要(?:执行|批准|退役|变更|创建|登记|发布|续期)|\b(?:do not|don't|cannot|can't|never)\s+(?:approve|accept|authorize|renew|retire|create|record|change|publish|confirm)\b|\bi (?:reject|decline)\b"
    require(re.search(negative,text) is None,'GOVERNANCE_APPROVAL_CONTRADICTION',f'The retained statement explicitly contradicts the requested {subject}. This is a limited guard, not speaker authentication.')
    return {**actor,'authorization_evidence_class':'agent_attributed','host_identity_authenticated':False}


def _refs(s, r, refs):
    require(isinstance(refs, list) and bool(refs), 'GOVERNANCE_EVIDENCE', 'Actual object references are required.')
    result=[]
    for ref in refs:
        require(isinstance(ref, dict) and set(ref)=={'kind','id'}, 'GOVERNANCE_REFERENCE', 'Use exact kind/id references.')
        _read(s,r,ref['kind'],ref['id'])
        result.append({**ref,'version':version(s,ref['kind'],ref['id'])})
    require(len({(x['kind'],x['id']) for x in result})==len(result), 'DUPLICATE_EVIDENCE', 'Repeated pointers are not independent evidence.')
    return result


def validator_fingerprint():
    from .service import _validator_fingerprint
    # Include this module even before a host updates its broader registry.
    from hashlib import sha256
    from pathlib import Path
    return digest({'service':_validator_fingerprint(), 'governance':sha256(Path(__file__).read_bytes()).hexdigest()})


def state_basis(s):
    """Evidence bookkeeping does not invalidate its own subject snapshot."""
    return digest({k:v for k,v in s['objects'].items() if v['kind'] not in EVIDENCE_KINDS})


def _validation_basis(state, level):
    if level != 'V0':
        return state_basis(state)
    # File-only checks should survive unrelated learning progress. Only the
    # applicable campaign envelopes affect whether this operation may execute.
    return digest({identity: data for identity, data in _all(state, 'campaign')
                   if _matches('governance.validation.executed', data.get('scope_actions', ['*']))})


def _negative(s,r,identity,implementation,code):
    proof=_read(s,r,'validation',identity)
    from .service import _validator_fingerprint, actions, CHECK_INPUTS
    known=isinstance(implementation,str) and ((implementation.startswith('action:') and implementation[7:] in actions()) or (implementation.startswith('check:') and implementation[6:] in CHECK_INPUTS))
    require(known, 'GOVERNANCE_IMPLEMENTATION', 'Implementation must resolve to an actual registered action/check.')
    require(proof.get('implementation_ref')==implementation and proof.get('expected_code')==code and proof.get('negative_result')=='expected_rejection' and proof.get('validator_sha256')==_validator_fingerprint(),
            'GOVERNANCE_NEGATIVE', 'Use actual current-validator negative execution evidence for this implementation and failure signal.')
    return {'id':identity,'version':version(s,'validation',identity),'implementation_ref':implementation,'expected_code':code}


def _matches(action, scopes):
    return any(scope=='*' or action==scope or (scope.endswith('.*') and action.startswith(scope[:-1])) for scope in scopes)


def validate_dispatch(s,r):
    """Host dispatch calls this for every public domain mutation, under its lock."""
    action=r.get('action')
    require(action not in LEGACY_ACTIONS, 'GOVERNANCE_ACTION_REQUIRED', 'Use the governed gov.* action; the legacy weak mutation is not public authority.')
    if action in MAINTENANCE_ACTIONS: return
    for identity,campaign in _all(s,'campaign'):
        scopes=campaign.get('scope_actions',['*'])
        if not _matches(action,scopes): continue
        # Constraint over the latest full set, not a user-selected stale object.
        require(campaign.get('status')=='active', 'STOPPED_BUDGET', f'Campaign {identity} is stopped; omitting campaign_id cannot bypass its scope.')
        if campaign.get('deadline'):
            require(_now() < _time(campaign['deadline']), 'STOPPED_BUDGET', f'Campaign {identity} reached its wall-clock deadline.')
        if r.get('campaign_id'):
            require(r['campaign_id']==identity, 'CAMPAIGN_SCOPE', 'Another campaign identifier cannot replace the applicable envelope.')


def _budget(p):
    fields(p,'tokens','repair_rounds','full_reviews','test_commands','attempts_per_round')
    require(set(p)=={'tokens','repair_rounds','full_reviews','test_commands','attempts_per_round'}, 'CAMPAIGN_BUDGET', 'Freeze every supported resource counter explicitly.')
    require(all(type(v) is int and v>0 for v in p.values()), 'CAMPAIGN_BUDGET', 'Budget limits are positive integer upper bounds.')
    return deepcopy(p)


def _history(s,r,identity,before):
    return _new(s,'governance_history',f'{identity}/r{s["revision"]+1}',{'subject':identity,'before':before,'actor':_provenance(r)})


def _issue_counts(d):
    return len(d.get('occurrences',[])), d.get('remedy_since')


def plan(s,r):
    action,p=r['action'],r['payload']; fields(p,'id'); identity=p['id']; actor={**_provenance(r),'authorization_evidence_class':'agent_attributed','host_identity_authenticated':False}
    if action=='gov.issue.open':
        fields(p,'problem','root_cause','scope','evidence_refs','category')
        require(p['category']=='system', 'ISSUE_CATEGORY', 'Knowledge errors and feelings belong to their learning/profile domains.')
        root=p['root_cause'].strip().casefold(); _text(root,'root cause')
        require(not any(d.get('root_cause','').strip().casefold()==root for _,d in _all(s,'issue')), 'ISSUE_ALREADY_EXISTS', 'Recur the existing root-cause identity, including resolved history.')
        refs=_refs(s,r,p['evidence_refs'])
        return [_new(s,'issue',identity,{'problem':p['problem'],'root_cause':p['root_cause'],'scope':p['scope'],'status':'open',
             'occurrences':[{'evidence_refs':refs,'actor':actor}],'reopen_count':0,'closure':'open','playbook_status':'pending'})]
    if action=='gov.issue.recur':
        d=_read(s,r,'issue',identity); refs=_refs(s,r,p.get('evidence_refs'))
        d['reopen_count']=d.get('reopen_count',0)+(d.get('status')=='resolved')
        d.setdefault('occurrences',[]).append({'evidence_refs':refs,'actor':actor}); d.update(status='open',closure='open')
        return [put('issue',identity,d)]
    if action=='gov.issue.resolve':
        d=_read(s,r,'issue',identity); fields(p,'resolution','enforcement','playbook_status','evidence_refs')
        require(d.get('status')=='open','ISSUE_STATE','Only an open issue can be resolved.')
        refs=_refs(s,r,p['evidence_refs']); count,baseline=_issue_counts(d)
        enforcement=p['enforcement']; require(enforcement in {'check','tool','context','prose'},'ENFORCEMENT','Unknown enforcement.')
        settlement=p['playbook_status']; require(isinstance(settlement,dict) and settlement.get('kind') in {'extracted','not_applicable'},'ISSUE_SETTLEMENT','Record extracted owner or a specific non-applicability reason.')
        if settlement['kind']=='extracted':
            rule=_read(s,r,'rule',settlement.get('rule_id')); require(rule.get('status')=='active','ISSUE_SETTLEMENT','Extraction must point to a live canonical rule.')
        else: _text(settlement.get('reason'),'why extraction is not applicable')
        if enforcement in {'prose','context'}:
            strikes=count-baseline if type(baseline) is int else 0
            require(strikes<STRIKE_LIMIT,'ISSUE_STRIKES','Two recurrences while a prose remedy existed require an actual check/tool landing.')
            fields(p,'accepted_risk'); _text(p['accepted_risk'],'accepted soft-enforcement risk')
            if baseline is None: d['remedy_since']=count
            proof=None
        else:
            fields(p,'implementation_ref','failure_signal','negative_validation_id')
            proof=_negative(s,r,p['negative_validation_id'],p['implementation_ref'],p['failure_signal'])
        d.update(status='resolved',resolution=p['resolution'],closure=enforcement,enforcement=enforcement,
                 playbook_status=deepcopy(settlement),verification=proof,evidence_refs=refs,accepted_risk=p.get('accepted_risk'),resolved_by=actor)
        return [put('issue',identity,d)]
    if action=='gov.rule.register':
        fields(p,'body','owner','protection','clauses','enforcement','consumer_refs','failure_signal',
               'enforcement_type','decision_owner','actual_executor','evidence','wake','stale','bypass')
        require(isinstance(p['enforcement_type'],list) and bool(p['enforcement_type']) and set(p['enforcement_type'])<={'language','gate','program'},'RULE_ENFORCEMENT_AXES','Language, gate and program are independent applicable axes, not an exclusive taxonomy.')
        require(isinstance(p['stale'],list) and {'object_change','validator_change'}<=set(p['stale']),'RULE_STALENESS','Declare object and validator changes as invalidation events.')
        for name in ('decision_owner','actual_executor','wake','bypass'): _text(p[name],name)
        evidence=_refs(s,r,p['evidence'])
        require(p['protection'] in PROTECTION,'RULE_PROTECTION','Use meta/core/ordinary protection.')
        require(isinstance(p['clauses'],dict) and bool(p['clauses']) and all(isinstance(k,str) and k and isinstance(v,str) and v.strip() for k,v in p['clauses'].items()),'RULE_CLAUSES','Keep each normative semantic clause under a stable ID.')
        require(not any(d.get('owner')==p['owner'] and d.get('body')==p['body'] for _,d in _all(s,'rule')),'RULE_DUPLICATE','One canonical rule owner; projections are references.')
        refs=_refs(s,r,p['consumer_refs']); enforcement=p['enforcement']
        require(enforcement in {'check','tool','context','prose'},'ENFORCEMENT','Unknown enforcement.')
        proof=None
        if enforcement in {'check','tool'}:
            fields(p,'implementation_ref','negative_validation_id')
            proof=_negative(s,r,p['negative_validation_id'],p['implementation_ref'],p['failure_signal'])
            require('program' in p['enforcement_type'] and p['actual_executor']==p['implementation_ref'],'RULE_EXECUTOR','A program claim must identify the verified implementation actually enforcing it.')
        elif 'program' in p['enforcement_type']:
            raise DomainError('RULE_FALSE_PROGRAM','A prose/context condition cannot claim program enforcement without verified implementation evidence.')
        else: fields(p,'accepted_risk')
        return [_new(s,'rule',identity,{**deepcopy(p),'status':'active','consumer_refs':refs,'negative_evidence':p.get('negative_validation_id'),
                     'verified_negative':proof,'provenance':actor,'uses':[],'evidence':evidence,'host_identity_authenticated':False})]
    if action=='gov.rule.use':
        d=_read(s,r,'rule',identity); fields(p,'use_ref','used_at'); _time(p['used_at'])
        require(d['status']=='active','RULE_RETIRED','Retired rules remain history, not live authority.')
        refs=_refs(s,r,[p['use_ref']]); token=refs[0]
        require(not any(x['reference']['kind']==token['kind'] and x['reference']['id']==token['id'] for x in d.get('dated_uses',[])),'DUPLICATE_USE','A use is counted once.')
        d.setdefault('dated_uses',[]).append({'reference':token,'used_at':p['used_at'],'actor':actor})
        return [put('rule',identity,d)]
    if action=='gov.rule.migrate':
        d=_read(s,r,'rule',identity); fields(p,'semantic_map','map_sha256','consumer_refs','reason','automatic')
        require(d.get('status')=='active' and d.get('clauses'),'RULE_MIGRATION','Map an active rule with explicit semantic clause identities.')
        require(type(p['automatic']) is bool and p['automatic'] is False,'RULE_AUTOMATIC_RETIRE','Rule migration is never automatic deletion or archiving.')
        _approval(r,'rule migration')
        mapping=p['semantic_map']; require(digest(mapping)==p['map_sha256'],'RULE_MIGRATION_BINDING','Bind the exact reviewed semantic map.')
        require(isinstance(mapping,list) and len(mapping)==len(d['clauses']) and {x.get('clause_id') for x in mapping}==set(d['clauses']),'RULE_MIGRATION_CLOSURE','Map every original clause exactly once.')
        for row in mapping:
            require(row.get('disposition') in {'keep','sink','retire'},'RULE_DISPOSITION','Unknown semantic destination.')
            if row['disposition']=='retire': _text(row.get('reason'),'explicit retired meaning and rationale')
            else:
                fields(row,'destination_id','destination_clause_id','semantic_explanation')
                require(row['destination_id']!=identity,'RULE_SELF_REPLACEMENT','A retired owner cannot replace itself.')
                target=_read(s,r,'rule',row['destination_id'])
                require(target.get('status')=='active' and row['destination_clause_id'] in target.get('clauses',{}),'RULE_DESTINATION','Destination must resolve to a live canonical semantic clause.')
        refs=_refs(s,r,p['consumer_refs'])
        if d.get('protection') in {'core','meta'}:
            fields(p,'changelog_id','negative_validation_id','implementation_ref','failure_signal')
            log=_read(s,r,'history',p['changelog_id']); require(log.get('category')=='changelog','RULE_PROTECTION','Protected changes need an actual changelog.')
            _negative(s,r,p['negative_validation_id'],p['implementation_ref'],p['failure_signal'])
        before=deepcopy(d); d.update(status='retired',migration={**deepcopy(p),'consumer_refs':refs,'approved_by':actor,'machine_semantic_equivalence':False})
        return [_history(s,r,'rule/'+identity,before),put('rule',identity,d)]
    if action=='gov.history.record':
        fields(p,'category','body'); require(p['category'] in {'journal','changelog'},'HISTORY_CATEGORY','Use separate decision lifecycle actions for ADR/Evolution.')
        if p['category']=='journal': require_student(r)
        return [_new(s,'history',identity,{'category':p['category'],'body':p['body'],'provenance':actor,'indexable':True})]
    if action=='gov.evolution.create':
        _approval(r,'evolution record'); fields(p,'body','decision_class')
        require(re.fullmatch(r'EV-[0-9]{4,}',identity) is not None,'EVOLUTION_ID','Use stable EV-NNNN identity.')
        require(p['decision_class'] in {'observation','architecture','implementation','policy'},'EVOLUTION_CLASS','Unknown decision class.')
        return [_new(s,'evolution',identity,{'body':p['body'],'decision_class':p['decision_class'],'status':'observing','adr_refs':[],'events':[{'to':'observing','actor':actor}]})]
    if action=='gov.evolution.transition':
        d=_read(s,r,'evolution',identity); fields(p,'status','reason'); _approval(r,'evolution transition')
        allowed={'observing':{'discussing'},'discussing':{'decided','observing'},'decided':{'archived'},'archived':set()}
        require(p['status'] in allowed.get(d['status'],set()),'EVOLUTION_STATE','Follow observing/discussing/decided/archived lifecycle.')
        if p['status']=='decided' and d['decision_class']=='architecture' and not d.get('adr_refs'):
            fields(p,'adr_exception'); _text(p['adr_exception'],'why no portable ADR is applicable'); d['adr_exception']=p['adr_exception']
        if p['status']=='archived':
            fields(p,'changelog_id','implementation_refs','month_index_id')
            log=_read(s,r,'history',p['changelog_id']); month=_read(s,r,'history',p['month_index_id'])
            require(log.get('category')=='changelog' and month.get('category')=='journal','EVOLUTION_ARCHIVE','Archive needs changelog and monthly index history.')
            refs=_refs(s,r,p['implementation_refs']); d['landing']={'changelog_id':p['changelog_id'],'month_index_id':p['month_index_id'],'implementation_refs':refs}
        d['events'].append({'from':d['status'],'to':p['status'],'reason':p['reason'],'actor':actor,'at':_now().isoformat()}); d['status']=p['status']
        return [put('evolution',identity,d)]
    if action=='gov.adr.create':
        fields(p,'body','portable_key','source_evolution','supersedes')
        require(re.fullmatch(r'ADR-[0-9]{4,}',identity) is not None,'ADR_ID','Use stable ADR-NNNN identity.')
        require(not any(d.get('portable_key')==p['portable_key'] for _,d in _all(s,'adr')),'ADR_PORTABLE_KEY','Portable semantic keys are unique.')
        require(isinstance(p['source_evolution'],list) and bool(p['source_evolution']) and len(set(p['source_evolution']))==len(p['source_evolution']),'ADR_SOURCE','ADR needs unique actual local Evolution records.')
        rows=[]
        for ev in p['source_evolution']:
            e=_read(s,r,'evolution',ev); require(e['decision_class']=='architecture' and e['status'] in {'discussing','decided','archived'},'ADR_SOURCE','Proposed ADR binds architecture discussion or later decision.')
            require(e['status']!='archived','EVOLUTION_ARCHIVED','Do not alter archived EV linkage; establish it before archive.')
            e['adr_refs'].append(identity); rows.append(put('evolution',ev,e))
        require(isinstance(p['supersedes'],list) and len(set(p['supersedes']))==len(p['supersedes']),'ADR_SUPERSEDES','Use distinct existing predecessors.')
        for prior in p['supersedes']:
            require(prior!=identity,'ADR_CYCLE','An ADR cannot supersede itself.'); _read(s,r,'adr',prior)
        return rows+[_new(s,'adr',identity,{**deepcopy(p),'status':'proposed','provenance':actor})]
    if action=='gov.adr.accept':
        d=_read(s,r,'adr',identity); _approval(r,'architecture decision')
        require(d['status']=='proposed','ADR_STATE','Only proposed decisions become accepted.')
        evolutions=[_read(s,r,'evolution',ev) for ev in d['source_evolution']]
        require(any(e['status'] in {'decided','archived'} and e['decision_class']=='architecture' for e in evolutions),'ADR_SOURCE','Accepted ADR needs an actual decided architecture EV.')
        require(all(identity in e['adr_refs'] for e in evolutions),'ADR_LINKAGE','ADR and EV links must be bidirectional.')
        rows=[]
        for prior in d['supersedes']:
            e=_read(s,r,'adr',prior); require(e['status']=='accepted','ADR_STATE','Only an accepted predecessor can be superseded.')
            e.update(status='superseded',superseded_by=identity); rows.append(put('adr',prior,e))
        d.update(status='accepted',approved_by=actor,implementation_complete=False)
        return rows+[put('adr',identity,d)]
    if action=='gov.campaign.create':
        fields(p,'scope_actions','objective_key','acceptance_contract','completion_definition','limits','deadline')
        _approval(r,'campaign envelope'); limits=_budget(p['limits']); require(_time(p['deadline'])>_now(),'CAMPAIGN_DEADLINE','A new envelope needs a future deadline.')
        scopes = p['scope_actions']
        valid_scope = lambda value: isinstance(value, str) and (value == '*' or
            ('.' in value and re.fullmatch(r'[a-z_]+(?:\.[a-z_]+)*(?:\.\*)?', value)))
        require(isinstance(scopes, list) and bool(scopes) and all(valid_scope(x) for x in scopes),
                'CAMPAIGN_SCOPE', 'Freeze explicit actions, namespace.* or global *.')
        require(not any(d.get('objective_key')==p['objective_key'] for _,d in _all(s,'campaign')),'CAMPAIGN_RENUMBER','Renew the original objective envelope; renumbering cannot reset its history.')
        return [_new(s,'campaign',identity,{**deepcopy(p),'limits':limits,'counters':{k:0 for k in limits},'status':'active','envelopes':[],'observations':[],'approved_by':actor})]
    if action=='gov.campaign.observe':
        d=_read(s,r,'campaign',identity); fields(p,'counters','measurement_source','evidence_ref')
        require('limits' in d,'CAMPAIGN_LEGACY','Legacy incomplete envelope needs explicit renewal before measurement.')
        counters=p['counters']; require(isinstance(counters,dict) and set(counters)==set(d['limits']) and all(type(v) is int and v>=d['counters'][k] for k,v in counters.items()),'CAMPAIGN_COUNTER','Cumulative counters cannot decrease or change meaning.')
        d['counters']=deepcopy(counters); d['observations'].append({'counters':deepcopy(counters),'source':p['measurement_source'],'evidence_ref':p['evidence_ref'],'actor':actor})
        if any(counters[k]>=v for k,v in d['limits'].items()) or _now()>=_time(d['deadline']): d['status']='stopped_budget'
        return [put('campaign',identity,d)]
    if action=='gov.campaign.renew':
        d=_read(s,r,'campaign',identity); fields(p,'limits','deadline','reason','previous_envelope_sha256')
        _approval(r,'campaign renewal')
        require(digest(d)==p['previous_envelope_sha256'],'CAMPAIGN_BINDING','Renew exactly the exhausted envelope inspected by the requester.')
        require(d.get('status')=='stopped_budget' or (d.get('deadline') and _now()>=_time(d['deadline'])),'CAMPAIGN_STATE','Renew only an exhausted envelope.')
        limits=_budget(p['limits']); require(_time(p['deadline'])>_now(),'CAMPAIGN_DEADLINE','New bounded envelope needs a future deadline.')
        require(all(limits[k]>d.get('counters',{}).get(k,0) for k in limits),'CAMPAIGN_BUDGET','New absolute limits must exceed retained cumulative counters; no reset.')
        d.setdefault('envelopes',[]).append({'before':{k:deepcopy(v) for k,v in d.items() if k!='envelopes'},'renewal':actor,'reason':p['reason']})
        d.update(limits=limits,deadline=p['deadline'],status='active'); return [put('campaign',identity,d)]
    if action=='gov.verdict.record':
        fields(p,'run_id','finding_sha256','act')
        run=_read(s,r,'governance_run',p['run_id']); _current_run(s,run)
        finding=next((x for x in run['findings'] if digest(x)==p['finding_sha256']),None)
        require(finding is not None,'VERDICT_FINDING','Bind a real exact finding from this current validation run.')
        require(p['act'] in {'yes','no'},'VERDICT_ACT','Disposition is yes/no, separate from its reason.')
        if p['act']=='yes': require(p.get('reason') is None,'VERDICT_REASON','act=yes has no no-action reason.')
        else:
            require(p.get('reason') in REASONS,'VERDICT_REASON','Choose an explicit no-action reason.')
            fields(p,'evidence_refs','explanation'); _refs(s,r,p['evidence_refs'])
            if p['reason']=='paused': fields(p,'wake_ref')
            if p['reason']=='env_waiver':
                require(finding.get('category')=='external_environment' and not finding.get('hard_failure'), 'WAIVER_FORBIDDEN','Only external environment failures without repository correctness impact are waivable.')
                fields(p,'risk','responsible','approved_at','expires_at','unfixable_locally')
                _approval(r,'environment waiver')
                require(_time(p['approved_at'])<=_now()<_time(p['expires_at']),'WAIVER_EXPIRY','Waiver approval and expiry must bracket the current time.')
        wake=None
        if p.get('wake_ref'): wake=_refs(s,r,[p['wake_ref']])[0]
        return [_new(s,'governance_verdict',identity,{**deepcopy(p),'finding':deepcopy(finding),'state_basis':run['state_basis'],
                     'validator_sha256':run['validator_sha256'],'validation_level':run['plan']['level'],
                     'wake_ref':wake,'woken':False,'actor':actor,'fact_status_unchanged':True})]
    if action=='gov.verdict.wake':
        d=_read(s,r,'governance_verdict',identity); fields(p,'reason'); d.update(woken=True,wake_reason=p['reason'],wake_actor=actor)
        return [put('governance_verdict',identity,d)]
    if action=='gov.case_matrix.freeze':
        fields(p,'candidate_sha256','cases'); _approval(r,'case matrix')
        require(isinstance(p['cases'],list) and bool(p['cases']),'CASE_MATRIX','Freeze a nonempty explicit required scenario inventory.')
        require(len({x.get('id') for x in p['cases']})==len(p['cases']),'CASE_MATRIX','Case IDs must be unique.')
        for case in p['cases']:
            fields(case,'id','contract','applicable','condition','evidence_kind')
            require(type(case['applicable']) is bool and case['evidence_kind'] in {'program','independent_review'},'CASE_MATRIX','Explicit applicability and evidence type are required.')
            _text(case['condition'],'applicability reason')
            if not case['applicable']:
                require(case.get('feature')=='offline_cloud' and not any(d.get('independent_exchange_enabled') for _,d in _all(s,'bridge')),
                        'CASE_NOT_APPLICABLE','This exclusion is only for an explicitly disabled offline-cloud compatibility path; local/remote use is the same instance.')
        return [_new(s,'case_matrix',identity,{**deepcopy(p),'matrix_sha256':digest(p),'status':'frozen','approved_by':actor})]
    if action=='gov.version.record':
        fields(p,'candidate_sha256','matrix_id','implementation_status')
        require(p['implementation_status'] in {'partial','complete'},'VERSION_IMPLEMENTATION','Implementation state is independent of review/release qualification.')
        matrix=_read(s,r,'case_matrix',p['matrix_id'])
        require(matrix['candidate_sha256']==p['candidate_sha256'],'VERSION_BINDING','Candidate and scenario inventory must match.')
        return [_new(s,'version_record',identity,{**deepcopy(p),'candidate_review':'not_run','release_qualification':'not_claimed','actor':actor})]
    if action=='gov.version.qualify':
        version_record=_read(s,r,'version_record',identity); fields(p,'run_id','review_refs')
        run=_read(s,r,'governance_run',p['run_id']); _current_run(s,run)
        require(run['plan']['level']=='V3' and run.get('package_sha256')==version_record['candidate_sha256'],'VERSION_BINDING','Release qualification binds the exact actual checked candidate.')
        matrix=_read(s,r,'case_matrix',version_record['matrix_id'])
        require(run['plan'].get('case_matrix_id')==version_record['matrix_id'],'VERSION_BINDING','Validation must consume this complete frozen scenario inventory.')
        reviews=_refs(s,r,p['review_refs'])
        require(all(x['kind']=='independent_review' for x in reviews),'VERSION_REVIEW','Use actual imported independent report records, not arbitrary object references.')
        for ref in reviews:
            report=_read(s,r,'independent_review',ref['id'])
            require(report['candidate_sha256']==version_record['candidate_sha256'] and report['verdict']=='passed' and report['scope'] in {'full_candidate','finalization_delta'},'VERSION_REVIEW','Review must bind this candidate and a complete or finalization review scope.')
        require(any(_read(s,r,'independent_review',ref['id'])['scope']=='full_candidate' for ref in reviews),'VERSION_REVIEW','A delta report cannot replace the full candidate review.')
        require(version_record['implementation_status']=='complete','VERSION_IMPLEMENTATION','Partial implementation is not releasable.')
        require(run['release_qualification']=='mechanical_checks_passed','VERSION_CHECKS','Missing/failed/review-required matrix evidence prevents release qualification.')
        # This records the evidence dependency, not authenticated reviewer identity
        # or permission to publish. The host must independently adjudicate those.
        return [_new(s,'version_qualification',identity,{'version_id':identity,'run_id':p['run_id'],'candidate_sha256':version_record['candidate_sha256'],
                     'review_refs':reviews,'state_basis':run['state_basis'],'validator_sha256':run['validator_sha256'],
                     'implementation_status':'complete','candidate_review':'external_review_referenced_not_authenticated',
                     'release_qualification':'mechanical_checks_passed_pending_host_approval','released':False,'actor':actor})]
    raise DomainError('UNKNOWN_ACTION',action)


def rule_usage(rule, now=None):
    """Read-only report: silent reads are unobservable and never inferred absent."""
    now=now or _now()
    if rule.get('protection') in {'core','meta'} or rule.get('managed_by') or rule.get('usage_exempt'):
        return {'status':'INFO','classification':'protected_or_exempt','automatic_action':False}
    uses=rule.get('dated_uses',[])
    if not uses: return {'status':'INFO','classification':'unobserved','automatic_action':False}
    age=(now-max(_time(x['used_at']) for x in uses)).total_seconds()/86400
    return {'status':'WARN' if age>=14 else 'PASS','classification':'archive_candidate' if age>=40 else 'cold' if age>=14 else 'observed_recently','days_since_observed_use':age,'automatic_action':False}


def _current_run(s,run):
    basis = _validation_basis(s, run.get('plan', {}).get('level'))
    require(run.get('validator_sha256') == validator_fingerprint() and run.get('state_basis') == basis,
            'STALE_GOVERNANCE_RUN', 'Applicable state or validator changed after validation; run evidence is historical.')


def verdict_state(s, verdict, now=None):
    reason=None
    if verdict.get('state_basis')!=_validation_basis(s, verdict.get('validation_level')): reason='object_state_changed'
    elif verdict.get('validator_sha256')!=validator_fingerprint(): reason='validator_changed'
    elif verdict.get('woken'): reason='wake_triggered'
    elif verdict.get('wake_ref'):
        ref=verdict['wake_ref']
        if version(s,ref['kind'],ref['id'])!=ref['version']: reason='wake_dependency_changed'
    if verdict.get('reason')=='env_waiver' and (now or _now())>=_time(verdict['expires_at']): reason='waiver_expired'
    return {'valid':reason is None,'invalidated_by':reason,'display_status':'WAIVED' if reason is None and verdict.get('reason')=='env_waiver' else verdict['finding']['status'],
            'original_status':verdict['finding']['status'],'fact_status_unchanged':True}


def build_validation_plan(s, *, level='V1', changed_kinds=None, changed_files=None, release_reason=None, package=None, case_matrix_id=None):
    from . import service
    from pathlib import Path
    from hashlib import sha256
    require(level in LEVELS,'VALIDATION_LEVEL','Use explicit V0, V1, V2 or V3.')
    profile,tier=LEVELS[level]
    files={}
    if level=='V0':
        require(isinstance(changed_files,list) and bool(changed_files),'V0_FILES','V0 checks only the explicitly changed files.')
        for name in changed_files:
            path=Path(name); require(path.is_file() and not path.is_symlink(),'V0_FILES','Each named changed file must be a regular readable file.')
            files[str(path.absolute())]=sha256(path.read_bytes()).hexdigest()
        domain=None
    else: domain=service.check_plan(s,changed_kinds,full=level=='V3')
    if level=='V3': require(release_reason in RELEASE_REASONS,'RELEASE_REASON','Release execution is explicit and never selected by ordinary checks.')
    body={'level':level,'profile':profile,'max_test_tier':tier,'changed_kinds':sorted(changed_kinds or []),'files':files,
          'domain_plan':domain,'release_reason':release_reason,'case_matrix_id':case_matrix_id,
          'package':str(Path(package).absolute()) if package is not None else None,
          'package_sha256':sha256(Path(package).read_bytes()).hexdigest() if package is not None else None,
          'validator_sha256':validator_fingerprint(),'state_basis':_validation_basis(s, level),'ordinary_test_command_limit':3,
          'tests_executed':False,'test_execution_scope':'Doctor and storage/package checks only; test runners require their separately frozen test plans.'}
    body['plan_sha256']=digest(body); return body


def run_validation(instance, run_id, plan_body, execute_plan_sha):
    """Actual read-only checks followed by one bound evidence transaction.

    The API does not accept a caller-supplied check status. Case reports are only
    accepted from earlier actual governance runs or explicit review artifacts;
    incomplete review evidence remains REVIEW instead of becoming release PASS.
    """
    from . import service, distribution
    from .journal import Journal
    from pathlib import Path
    from hashlib import sha256
    import io
    store=Journal(instance)
    previous=store.lookup('gov-validation/'+run_id)
    if previous:
        old=get(store.read_state(),'governance_run',run_id)
        require(old['plan']==plan_body and old['plan']['plan_sha256']==execute_plan_sha,'VALIDATION_ID_REUSED','Validation ID binds its original plan.')
        return previous
    state=store.read_state()
    operation = {'action': 'governance.validation.executed'}
    validate_dispatch(state, operation)
    rebuilt=build_validation_plan(state,level=plan_body.get('level'),changed_kinds=plan_body.get('changed_kinds'),changed_files=list(plan_body.get('files',{})),
          release_reason=plan_body.get('release_reason'),package=plan_body.get('package'),case_matrix_id=plan_body.get('case_matrix_id'))
    require(rebuilt==plan_body and plan_body['plan_sha256']==execute_plan_sha,'STALE_CHECK_PLAN','Execute the complete unchanged state/code/file-bound plan.')
    findings=[]; actual={}; started=_now().isoformat(); profile=plan_body['profile']
    if plan_body['level']!='V0':
        report=service.doctor(instance,plan=plan_body['domain_plan'])
        findings=[{**x,'category':_finding_category(x['code']),'hard_failure':_finding_category(x['code']) in HARD_FAILURES} for x in report['findings']]
        actual['runtime']=report
    if plan_body['level'] in {'V2','V3'}: actual['data_integrity']=store.validate()
    package_sha=None; qualification='not_requested'
    if profile=='release':
        require(plan_body.get('package') and plan_body.get('case_matrix_id'),'RELEASE_INPUTS','Release checks require the actual candidate and frozen case matrix.')
        frozen=Path(plan_body['package']).read_bytes(); package_sha=sha256(frozen).hexdigest()
        require(package_sha==plan_body['package_sha256'],'CANDIDATE_CHANGED','Candidate bytes changed after plan generation.')
        actual['distribution_manifest']=distribution.verify_distribution(io.BytesIO(frozen))
        matrix=get(state,'case_matrix',plan_body['case_matrix_id'])
        require(matrix['candidate_sha256']==package_sha,'CANDIDATE_BINDING','Frozen case matrix binds another candidate.')
        case_results=[]
        for case in matrix['cases']:
            if not case['applicable']:
                status='NOT_APPLICABLE'
            else:
                # A real frozen independent report is evidence, not machine proof
                # of model behavior or reviewer identity. Keep it REVIEW pending
                # host adjudication; never infer all-feature PASS from a unit test.
                check=case.get('check_id')
                proof=get(state,'independent_review',case.get('review_id'),False) if case.get('review_id') else None
                if case['evidence_kind']=='program':
                    require(check in {'runtime','data_integrity','distribution_manifest'},'RELEASE_CHECK','A case must name an actually executed registered check; arbitrary scenario labels are not program results.')
                    measured=actual[check]
                    status='PASS' if check=='distribution_manifest' or (measured.get('ok') and not measured.get('review_required')) else 'FAIL'
                else:
                    status='REPORTED_PASS' if proof and proof['candidate_sha256']==package_sha and proof['cases'].get(case['id'])=='PASS' and proof['verdict']=='passed' else 'REVIEW'
            case_results.append({'case_id':case['id'],'status':status,'condition':case['condition'],'evidence_kind':case['evidence_kind']})
        actual['case_matrix']=case_results
        for row in case_results:
            if row['status']=='REVIEW': findings.append({'code':'release.case_evidence','status':'REVIEW','message':'Required case has no applicable executed evidence or needs independent human adjudication.','object':row['case_id'],'category':'review','hard_failure':False})
        qualification='mechanical_checks_passed' if all(x['status'] in {'PASS','REPORTED_PASS','NOT_APPLICABLE'} for x in case_results) and not any(x['status'] in {'FAIL','REVIEW'} for x in findings) else 'pending'
    current = store.read_state()
    validate_dispatch(current, operation)
    require(_validation_basis(current, plan_body['level']) == plan_body['state_basis'] and
            validator_fingerprint() == plan_body['validator_sha256'],
            'STALE_CHECK_PLAN', 'Applicable state or validator changed while checks ran.')
    record={'plan':deepcopy(plan_body),'state_basis':plan_body['state_basis'],'validator_sha256':plan_body['validator_sha256'],
            'findings':findings,'actual_checks':actual,'package_sha256':package_sha,'release_qualification':qualification,
            'started_at':started,'finished_at':_now().isoformat(),'scope':'actual local code checks; no host/user/reviewer identity authentication'}
    request={'request_id':'gov-validation/'+run_id,'action':'governance.validation.executed','payload':{'record_sha256':digest(record)},
             'actor':{'role':'system','source':'governance.run_validation','text':'Persist actual bound local validation outcomes.'},'expected':{}}
    def publish(current,_):
        validate_dispatch(current, operation)
        require(_validation_basis(current, plan_body['level']) == plan_body['state_basis'] and
                validator_fingerprint() == plan_body['validator_sha256'],
                'STALE_CHECK_PLAN', 'Validation basis changed before evidence publication.')
        return [_new(current,'governance_run',run_id,record)]
    return store.apply(request,publish)


def import_review(instance, review_id, blob_sha256):
    """Consume actual frozen report bytes; do not authenticate report authors."""
    from .journal import Journal
    from .model import parse_json
    store=Journal(instance); raw=store.read_blob(blob_sha256); report=parse_json(raw)
    fields(report,'candidate_sha256','author','reviewer','scope','verdict','cases')
    _text(report['author'], 'report author')
    _text(report['reviewer'], 'report reviewer')
    require(report['author'].strip() != report['reviewer'].strip(), 'REVIEW_AUTHOR',
            'Non-author review must name a different attributed reviewer.')
    require(report['verdict'] in {'passed','failed','review_required'} and isinstance(report['cases'],dict) and bool(report['cases']) and all(v in {'PASS','FAIL','REVIEW','WARN'} for v in report['cases'].values()),'REVIEW_REPORT','Keep explicit per-case findings, not only a generic pass label.')
    require(report['verdict'] != 'passed' or not {'FAIL', 'REVIEW'}.intersection(report['cases'].values()),
            'REVIEW_REPORT', 'An overall pass cannot contradict an unresolved or failed case in the same report.')
    record={k:deepcopy(report[k]) for k in ('candidate_sha256','author','reviewer','scope','verdict','cases')}
    record.update(blob_refs=[{'sha256':blob_sha256,'bytes':len(raw)}],authority='external_reported_findings',host_identity_authenticated=False)
    request={'request_id':'gov-review/'+review_id,'action':'governance.review.import','payload':{'blob_sha256':blob_sha256},
             'actor':{'role':'system','source':'governance.import_review','text':'Preserve actual frozen review artifact; no identity authentication inferred.'},'expected':{}}
    def publish(state, request):
        validate_dispatch(state, request)
        return [_new(state, 'independent_review', review_id, record)]
    return store.apply(request, publish)


def _finding_category(code):
    if code.startswith(('route.','cursor.orphan')): return 'route'
    if code.startswith(('alias.','source.missing','teacher.missing','activity.orphan')): return 'stable_id'
    if code.startswith('projection.'): return 'projection'
    if code.startswith('environment.'): return 'external_environment'
    if code.startswith(('review.','teaching.','authorization.')): return 'data_integrity'
    return 'review'


def doctor_findings(s):
    findings=[]
    for identity,d in _all(s,'issue'):
        count,baseline=_issue_counts(d)
        if count>=2 and d.get('playbook_status') in (None,'pending'):
            findings.append({'code':'issue.extraction_due','status':'WARN','message':'Repeated root cause needs an explicit extraction or non-applicability decision.','object':identity})
        if d.get('closure') in {'prose','context'} and type(baseline) is int and count-baseline>=STRIKE_LIMIT:
            findings.append({'code':'issue.failed_soft_remedy','status':'FAIL','message':'Two recurrences after the prose remedy require a program landing.','object':identity})
    for identity,d in _all(s,'rule'):
        if d.get('status')=='active':
            usage=rule_usage(d)
            if usage['status']!='PASS': findings.append({'code':'rule.usage','status':usage['status'],'message':usage['classification'],'object':identity})
    for identity,d in _all(s,'governance_verdict'):
        result=verdict_state(s,d)
        findings.append({'code':'verdict.current' if result['valid'] else 'verdict.stale','status':result['display_status'] if result['valid'] else 'REVIEW','message':result.get('invalidated_by') or 'Original finding fact retained with disposition.','object':identity})
    for identity,d in _all(s,'campaign'):
        if d.get('status')=='stopped_budget' or (d.get('deadline') and _now()>=_time(d['deadline'])):
            findings.append({'code':'campaign.stopped_budget','status':'WARN','message':'Applicable writes are blocked. Elapsed deadline is effective even before the next counter observation records the stopped state.','object':identity})
    return findings


ACTIONS={'gov.issue.open','gov.issue.recur','gov.issue.resolve','gov.rule.register','gov.rule.use','gov.rule.migrate','gov.history.record',
         'gov.evolution.create','gov.evolution.transition','gov.adr.create','gov.adr.accept','gov.campaign.create','gov.campaign.observe','gov.campaign.renew',
         'gov.verdict.record','gov.verdict.wake','gov.case_matrix.freeze','gov.version.record','gov.version.qualify'}
ENTITY_KINDS={'issue','rule','history','governance_history','evolution','adr','campaign','case_matrix','version_record',*EVIDENCE_KINDS}
