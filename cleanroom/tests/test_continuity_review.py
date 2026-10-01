"""Non-author check that navigation cannot silently replace a retained fact."""
import unittest

import test_continuity as author_fixture
from t2ag_next import service, continuity
from t2ag_next.model import DomainError


class ContinuityReview(unittest.TestCase):
    def test_redirect_cannot_shadow_an_existing_canonical_history_record(self):
        for locator in ('history/H1', 'H1'):
            with self.subTest(locator=locator):
                f = author_fixture.ContinuityJourneys()
                f.setUp(); self.addCleanup(f.doCleanups)
                f.history('H1'); f.history('H2')
                request = f.f.request('history.redirect.register', {
                    'id':'new-path', 'locator':locator, 'target_key':'history/H2',
                    'reason':'A relocation must not replace a different retained record.'})
                before = f.j.read_state()
                with self.assertRaises(DomainError):
                    service.execute(f.j.path, request)
                self.assertEqual(f.j.read_state(), before)
                self.assertEqual(continuity.resolve_history(before, locator)['id'], 'H1')


if __name__ == '__main__': unittest.main()
