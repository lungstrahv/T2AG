"""Small bilingual task guides, not an executor or an authority source.

The single catalog fixes meaningful order and return points. An agent selects
only applicable steps using actual state and existing authorization; reading a
guide neither mutates an instance nor mandates a number of tool calls.
"""
from .model import DomainError


def _text(zh, en):
    return {"zh": zh, "en": en}


_WORKFLOWS = (
    {
        "name": "first-plan", "title": _text("首次学习方案", "First learning plan"),
        "entry": "entry.teach", "lane": "teach",
        "start": _text("尚无已确认方案，或学生明确要重做方案。", "No confirmed plan, or the learner asks to revise it."),
        "steps": [
            {"id": "conditions", "text": _text("沿用已知语言和目标；只收学生愿意提供的条件，未知留空。", "Reuse the known language and goal; collect optional conditions without guessing."), "actions": ["planning.conditions.record"], "commands": []},
            {"id": "proposal", "text": _text("展示完整可改方案及假设；有修改就更新并展示当前版。", "Present the complete editable plan and assumptions; revise and show the current version."), "actions": ["planning.propose", "planning.revise", "planning.present"], "commands": []},
            {"id": "decision", "text": _text("用针对当前方案的清楚决定确认一次；已有决定不再问。按真实结果说明课程状态。", "Consume the clear decision on this plan once; do not ask again. Report the resulting course state."), "actions": ["planning.confirm"], "commands": []},
        ],
        "done": _text("完整方案与原决定已保存，课程引用和状态可读。", "The complete plan and original decision are saved; course references and states are readable."),
        "on_failure": [
            {"when": "plan_changed", "return_to": "proposal", "text": _text("回到当前方案，不把旧同意套给新内容。", "Return to the current plan; old consent does not cover changed content.")},
            {"when": "result_unknown", "return_to": "decision", "text": _text("先 lookup 原请求；必要时原样重试。", "Look up the original request before an identical retry.")},
        ],
        "stop": _text("确认成功即结束方案回路；未确认就停在方案，不擅自开课。", "End after confirmation; otherwise leave the proposal pending, without starting teaching."),
        "checks": _text("核当前方案及引用即可；不为制订方案跑全量检查。", "Check this plan and its references, not the entire instance."),
    },
    {
        "name": "resume-source", "title": _text("恢复与读源", "Resume and read sources"),
        "entry": "entry.teach", "lane": "teach",
        "start": _text("进入或恢复指定课程；跨会话不继承旧扫描和旧票。", "Enter or resume a named course; a new conversation does not inherit scans or tickets."),
        "steps": [
            {"id": "context", "text": _text("读同一实例的当前停点和等待项；只展开缺的证据，沿用已读且未变的教师/皮肤。", "Read the same instance's cursor and waiting state; expand missing evidence and reuse unchanged presentation settings."), "actions": [], "commands": ["context", "inspect"]},
            {"id": "source", "text": _text("启动本次会话；textbook 真读当前 Scope 页后记 scan，准备过期才重建，布局页看整页图。", "Start this session. For textbook work, actually read current Scope pages before recording a scan; rebuild stale preparation and view whole layout-critical pages."), "actions": ["session.start", "scope.create", "lessonmap.create", "preparation.create", "scan.record"], "commands": ["evidence", "assets prewarm"]},
            {"id": "resume", "text": _text("按 waiting_for 接回原互动；需新正文时沿用一次明确许可。旧迁移正文有冲突才消歧重呈现。", "Resume the waiting interaction. Use one clear permission for a new body; reconcile migrated saved-body conflicts only when present."), "actions": ["session.opening", "ticket.issue", "block.present", "migration.cursor.recover"], "commands": []},
        ],
        "done": _text("停点、原文和本次会话对应，下一步由实际等待项决定。", "Cursor, source and current session agree; actual waiting state determines the next step."),
        "on_failure": [
            {"when": "source_missing_or_changed", "return_to": "source", "text": _text("补当前来源证据；摘要或历史哈希不能替代读源。", "Obtain current source evidence; summaries and historical hashes do not replace reading.")},
            {"when": "cursor_conflict", "return_to": "context", "text": _text("保留冲突与原正文，先查清停点，不猜进度。", "Retain the conflict and original body; resolve the cursor instead of guessing progress.")},
        ],
        "stop": _text("本次读源未证成或前门未闭，就停在该等待项。", "Stop at the pending item if current reading or an earlier gate remains incomplete."),
        "checks": _text("只核当前来源闭包；普通恢复不跑全量 doctor。", "Check the current source closure; ordinary resume needs no full doctor."),
    },
    {
        "name": "feedback-save", "title": _text("理解反馈与保存", "Understanding feedback and save"),
        "entry": "entry.teach", "lane": "teach",
        "start": _text("学生刚回答当前小节，已有冻结判据。", "The learner answered the current block and its criterion is frozen."),
        "steps": [
            {"id": "judge", "text": _text("对实际原答作判断，证据清楚就直接反馈；不因后台保存延迟把正确说成待判断。", "Judge the actual answer and give clear feedback promptly; saving delay does not change a known judgment."), "actions": [], "commands": []},
            {"id": "persist", "text": _text("一次 assess 保存原答、判据、教师判断和停点；异步评分才分 submit/record。", "Use one assess to save answer, criterion, judgment and cursor; split submit/record only for asynchronous review."), "actions": ["comprehension.assess", "comprehension.submit", "comprehension.record"], "commands": []},
            {"id": "waiting", "text": _text("告知实际保存结果和 waiting_for；感受与疑问照实处理，正确不等于许可下一段。", "Report persistence and waiting_for; handle feelings/questions without treating correctness as next-block permission."), "actions": ["feeling.record", "question.open"], "commands": []},
        ],
        "done": _text("判断与保存状态清楚，原答和当前等待项可恢复。", "Judgment and persistence are clear; the original answer and waiting state are recoverable."),
        "on_failure": [
            {"when": "result_unknown", "return_to": "persist", "text": _text("lookup 原 request_id，再决定原样重试；不新造一次确认。", "Look up the original request_id, then retry identically if needed; do not invent a second confirmation.")},
            {"when": "criterion_or_cursor_changed", "return_to": "judge", "text": _text("重读相关对象，保留原答，重新核对适用判断。", "Reread the relevant objects, retain the answer and reconcile the applicable judgment.")},
        ],
        "stop": _text("反馈和保存结果交代清楚即结束；等待学生实际回应。", "End once feedback and save status are clear; wait for the learner's actual response."),
        "checks": _text("依赖版本和事务检查已在动作内；每题不跑全量检查。", "The action checks dependencies and persistence; no full check per answer."),
    },
    {
        "name": "practice-hint", "title": _text("练习与提示", "Practice and hints"),
        "entry": "entry.teach", "lane": "teach",
        "start": _text("已进入练习；题目、来源和当前会话可用。", "An exercise is active, with available problems, sources and current session."),
        "steps": [
            {"id": "criterion", "text": _text("按教材原题序建题并在作答前冻结判据；学生请求的加练单独记。", "Keep source question order and freeze criteria before answers; record requested supplements separately."), "actions": ["exercise.configure", "problem.add", "criterion.create"], "commands": []},
            {"id": "help", "text": _text("先回应实际问题；方向/资料/完整解答按请求等级一次授权并记帮助，不能偷偷升级。", "Answer the actual question; authorize direction/reference/solution once at the requested level and record help without upgrading it."), "actions": ["hint.authorize", "hint.record"], "commands": []},
            {"id": "review", "text": _text("保留原答后按冻结判据评分；帮助与污染随结果保留，有效错误才入错题。", "Preserve the answer, review against its frozen criterion, retain help/pollution and record only eligible mistake evidence."), "actions": ["attempt.submit", "review.record", "mistake.record"], "commands": []},
        ],
        "done": _text("原答、判断和帮助记录可追溯；没有把受助正确当独立掌握。", "Answer, judgment and help are traceable; assisted correctness is not independent mastery."),
        "on_failure": [
            {"when": "source_or_criterion_missing", "return_to": "criterion", "text": _text("先补来源或判据，不给历史作答补造先验标准。", "Supply source or criterion first; do not invent a prior rubric for historical answers.")},
            {"when": "help_scope_mismatch", "return_to": "help", "text": _text("回到实际请求的帮助范围，不扩大授权。", "Return to the requested help scope without expanding authorization.")},
        ],
        "stop": _text("当次反馈完成就停；加练、下一题与考试另按实际意图进入。", "Stop after this feedback; extra practice, the next question and exams follow actual intent."),
        "checks": _text("只核本题和援助证据；不开全库检查。", "Check this problem and help evidence, not the entire bank."),
    },
    {
        "name": "save-close", "title": _text("手动保存与收课", "Manual save and close"),
        "entry": "entry.teach", "lane": "teach",
        "start": _text("学生要保存、暂离，或结束当前学习活动。", "The learner asks to save, leave the session or close the current activity."),
        "steps": [
            {"id": "save", "text": _text("保存尚未记录的课堂要点/待续正文；已提交事实直接确认。保存不移动停点或教学门。", "Save unrecorded notes/pending text; acknowledge already committed facts. Saving changes neither cursor nor teaching gates."), "actions": ["activity.save"], "commands": ["lookup"]},
            {"id": "choose-end", "text": _text("仅暂离则关闭 session 即结束；确实要收活动才核对覆盖/原题序并展示完整结课正文。", "For a break, close the session and stop. Only an activity-close request needs coverage/source-order reconciliation and the complete closing body."), "actions": ["session.close", "activity.close.propose"], "commands": []},
            {"id": "close", "text": _text("用已针对当前结课正文的清楚决定确认一次；完成或未完成如实记，不替学生补同意。", "Consume one clear decision bound to the current closing body; record completed or incomplete honestly without inventing consent."), "actions": ["activity.close.confirm", "activity.close.withdraw"], "commands": []},
        ],
        "done": _text("所请求的保存/暂离/结课已落盘；未完事项和真实停点保留。", "The requested save/break/close is persisted; unfinished work and the real cursor remain."),
        "on_failure": [
            {"when": "result_unknown", "return_to": "save", "text": _text("查原请求，再原样重试；不要把未知说成已保存。", "Look up the original request before an identical retry; unknown is not saved.")},
            {"when": "close_body_or_coverage_changed", "return_to": "choose-end", "text": _text("回到当前正文和覆盖对账；未完成可保留，不强行判完成。", "Return to the current body and coverage; preserve incomplete work rather than forcing completion.")},
        ],
        "stop": _text("只要求保存就到保存为止；关闭 session 不等于完成活动或课程。", "A save-only request ends at saving; session close does not complete an activity or course."),
        "checks": _text("常规保存不重读皮肤、不跑全量 doctor。", "An ordinary save needs no skin reload or full doctor."),
    },
    {
        "name": "repair", "title": _text("维护修复", "Maintenance repair"),
        "entry": "entry.maintain", "lane": "maintain",
        "start": _text("已有具体故障或获授权的改动；不自动恢复教学。", "A concrete fault or authorized change exists; do not automatically restore teaching."),
        "steps": [
            {"id": "reproduce", "text": _text("读取相关状态，复现最小问题；已有根因用同一 issue 记复发。", "Read relevant state and reproduce the smallest failure; record recurrence against the same root-cause issue."), "actions": ["gov.issue.open", "gov.issue.recur"], "commands": ["context", "inspect"]},
            {"id": "repair", "text": _text("优先修结构性错误，做范围内可回退的小改动；小的可恢复问题不扩成新机制。", "Fix structural faults first with a small recoverable change; do not turn minor recoverable issues into new mechanisms."), "actions": [], "commands": []},
            {"id": "verify", "text": _text("重跑复现和受影响检查，记录真实结果；需要独立复审时交实际产物。", "Rerun the reproduction and affected checks, retain actual results and hand over artifacts when independent review is required."), "actions": ["gov.issue.resolve"], "commands": ["governance-plan", "governance-run", "doctor --changed"]},
        ],
        "done": _text("原问题已验证修复，或明确保留未决项及继续所需输入。", "The original fault is verified fixed, or remaining uncertainty and required input are explicit."),
        "on_failure": [
            {"when": "new_evidence", "return_to": "reproduce", "text": _text("携新证据回到复现，调整方法。", "Return to reproduction with new evidence and adjust the approach.")},
            {"when": "same_failure_no_new_evidence", "return_to": "stop", "text": _text("停止重复和扩大改动，报告具体阻点；预算/权限边界照常生效。", "Stop repeating or widening changes; report the concrete blocker and respect budget/authority limits.")},
        ],
        "stop": _text("相关验证通过即结束；同一核心失败无新证据时停止扩大。", "End after relevant checks pass; stop expanding after repeated core failure without new evidence."),
        "checks": _text("按改动选检查；全量检查只用于真实迁移、完整性调查或发行门。", "Select checks by change; full validation belongs to real migration, integrity investigation or release gates."),
    },
)


def _language(language):
    if language not in ("zh", "en"):
        raise DomainError("WORKFLOW_LANGUAGE", "Choose zh or en for the workflow guide.")


def _localized(value, language):
    if isinstance(value, dict):
        if set(value) == {"zh", "en"}:
            return value[language]
        return {key: _localized(item, language) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_localized(item, language) for item in value]
    return value


def list_workflows(language):
    """Return small discovery rows without reading an instance or executing work."""
    _language(language)
    return [{field: _localized(workflow[field], language) for field in ("name", "title", "entry", "lane")} for workflow in _WORKFLOWS]


def get_workflow(name, language):
    """Return an independent localized copy; actual state decides applicable steps."""
    _language(language)
    for workflow in _WORKFLOWS:
        if workflow["name"] == name:
            return {"language": language, **_localized(workflow, language)}
    raise DomainError("WORKFLOW_NOT_FOUND", f"Unknown workflow: {name}")
