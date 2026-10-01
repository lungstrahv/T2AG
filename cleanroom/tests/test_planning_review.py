"""Non-author planning boundary tests, metrics_contract; real temporary Journals."""
import unittest
import test_planning as author_fixture
from t2ag_next.model import DomainError


class IndependentPlanningReview(unittest.TestCase):
    def fixture(self):
        f = author_fixture.PlanningJourneys()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.proposal(group=True)
        return f, f.present()

    def test_negative_confirmation_cannot_create_a_complete_plan(self):
        for text in ("我不能确认建立这个方案。", "I don't approve this plan.", "不可以建立。"):
            with self.subTest(statement=text):
                f, sha = self.fixture()
                prior = f.j.read_state()
                with self.assertRaises(DomainError):
                    f.call('planning.confirm', {'id': 'P', 'proposal_sha256': sha}, text)
                self.assertEqual(f.j.read_state(), prior)

    def test_one_unambiguous_plan_acceptance_creates_group_without_second_confirmation(self):
        f, sha = self.fixture()
        prior = f.j.read_state()['revision']
        f.call('planning.confirm', {'id': 'P', 'proposal_sha256': sha}, 'I approve this complete plan.')
        state = f.j.read_state()
        self.assertEqual(state['revision'], prior + 1)
        self.assertEqual(state['objects']['group/G']['data']['status'], 'active')
        self.assertEqual(state['objects']['course/C']['data']['current_activity_id'], 'C/L1')

    def test_presented_plan_identifies_the_teacher_it_will_bind(self):
        f = author_fixture.PlanningJourneys()
        f.setUp(); self.addCleanup(f.tearDown)
        for identity, name in [('T1', 'First distinct teacher'), ('T2', 'Second distinct teacher')]:
            f.call('teacher.register', {'id': identity, 'name': name, 'template': 'Actual teaching style.', 'overlay': {}})
        payload = f.proposal()
        payload['courses'][0]['teacher_id'] = 'T1'
        f.call('planning.revise', payload)
        first = f.data('learning_plan', 'P')['body']
        payload['courses'][0]['teacher_id'] = 'T2'
        f.call('planning.revise', payload)
        second = f.data('learning_plan', 'P')['body']
        self.assertNotEqual(first, second, 'Different actual teacher bindings must be visible in the displayed full plan.')


if __name__ == '__main__':
    unittest.main()
