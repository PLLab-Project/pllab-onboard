import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from pllab_accounts import Account, Adopt, Conflict, Create, Lock, Reactivate, State, apply, plan  # noqa: E402

SYSTEM = {"root": 0, "daemon": 1}


class PlanTest(unittest.TestCase):
    def test_new_member_gets_lowercase_github_name(self):
        self.assertEqual(plan(State(), {1: "NewUser"}, SYSTEM, {}), [Create(1, "NewUser", "newuser")])

    def test_name_starting_with_digit_gets_prefix(self):
        self.assertEqual(plan(State(), {1: "1abc"}, SYSTEM, {}), [Create(1, "1abc", "gh-1abc")])

    def test_existing_linux_user_is_not_taken_over_without_override(self):
        actions = plan(State(), {1: "kdhoon"}, {**SYSTEM, "kdhoon": 1000}, {})
        self.assertIsInstance(actions[0], Conflict)

    def test_override_adopts_existing_human_account(self):
        actions = plan(State(), {1: "kdhoon723"}, {**SYSTEM, "kdhoon": 1000}, {"kdhoon723": "kdhoon"})
        self.assertEqual(actions, [Adopt(1, "kdhoon723", "kdhoon")])

    def test_override_never_adopts_system_account(self):
        actions = plan(State(), {1: "evil"}, SYSTEM, {"evil": "root"})
        self.assertIsInstance(actions[0], Conflict)

    def test_departed_member_is_locked(self):
        state = State({1: Account("gone", "gone", "active")})
        self.assertEqual(plan(state, {2: "other"}, {**SYSTEM, "gone": 1001}, {}), [Create(2, "other", "other"), Lock(1, "gone")])

    def test_returning_member_is_reactivated(self):
        state = State({1: Account("back", "back", "locked")})
        self.assertEqual(plan(state, {1: "back"}, {**SYSTEM, "back": 1001}, {}), [Reactivate(1, "back", "back")])

    def test_renamed_github_login_keeps_linux_name(self):
        state = State({1: Account("oldname", "oldname", "active")})
        members = {1: "NewName"}
        self.assertEqual(plan(state, members, {**SYSTEM, "oldname": 1001}, {}), [])
        self.assertEqual(apply(state, [], members).accounts[1], Account("oldname", "NewName", "active"))

    def test_locked_name_is_not_reused_by_someone_else(self):
        state = State({1: Account("same", "same", "locked")})
        actions = plan(state, {2: "same"}, {**SYSTEM, "same": 1001}, {})
        self.assertIsInstance(actions[0], Conflict)

    def test_steady_state_has_no_actions(self):
        state = State({1: Account("a", "a", "active")})
        self.assertEqual(plan(state, {1: "a"}, {**SYSTEM, "a": 1001}, {}), [])


if __name__ == "__main__":
    unittest.main()
