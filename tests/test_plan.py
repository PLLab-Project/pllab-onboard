import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from pllab_accounts import (  # noqa: E402
    Account, Adopt, Conflict, Create, Host, LinuxUser, Lock, Reactivate, State, apply, plan, too_many_locks, with_logins,
)


def host(users=None, groups=()):
    base = {"root": LinuxUser(0, "root"), "nobody": LinuxUser(65534, "nobody")}
    return Host({**base, **(users or {})}, frozenset(groups))


class PlanTest(unittest.TestCase):
    def test_new_member_gets_lowercase_github_name(self):
        self.assertEqual(plan(State(), {1: "NewUser"}, host(), {}), [Create(1, "NewUser", "newuser")])

    def test_name_starting_with_digit_gets_prefix(self):
        self.assertEqual(plan(State(), {1: "1abc"}, host(), {}), [Create(1, "1abc", "gh-1abc")])

    def test_existing_linux_user_is_not_taken_over_without_override(self):
        actions = plan(State(), {1: "kdhoon"}, host({"kdhoon": LinuxUser(1000, "")}), {})
        self.assertIsInstance(actions[0], Conflict)

    def test_override_adopts_existing_human_account(self):
        actions = plan(State(), {1: "kdhoon723"}, host({"kdhoon": LinuxUser(1000, "")}), {"kdhoon723": "kdhoon"})
        self.assertEqual(actions, [Adopt(1, "kdhoon723", "kdhoon")])

    def test_override_never_adopts_system_account(self):
        for target in ("root", "nobody"):
            actions = plan(State(), {1: "evil"}, host(), {"evil": target})
            self.assertIsInstance(actions[0], Conflict, target)

    def test_group_name_collision_is_reported(self):
        actions = plan(State(), {1: "docker"}, host(groups={"docker"}), {})
        self.assertIsInstance(actions[0], Conflict)

    def test_account_created_before_a_crash_is_picked_up(self):
        actions = plan(State(), {1: "Ann"}, host({"ann": LinuxUser(1001, "GitHub Ann")}), {})
        self.assertEqual(actions, [Adopt(1, "Ann", "ann")])

    def test_departed_member_is_locked(self):
        state = State({1: Account("gone", "gone", "active")})
        actions = plan(state, {2: "other"}, host({"gone": LinuxUser(1001, "")}), {})
        self.assertEqual(actions, [Create(2, "other", "other"), Lock(1, "gone")])

    def test_returning_member_is_reactivated(self):
        state = State({1: Account("back", "back", "locked")})
        self.assertEqual(plan(state, {1: "back"}, host({"back": LinuxUser(1001, "")}), {}), [Reactivate(1, "back", "back")])

    def test_mapped_name_taken_by_system_account_is_not_reactivated(self):
        state = State({1: Account("svc", "svc", "active")})
        actions = plan(state, {1: "svc"}, host({"svc": LinuxUser(998, "")}), {})
        self.assertIsInstance(actions[0], Conflict)

    def test_renamed_github_login_keeps_linux_name(self):
        state = State({1: Account("oldname", "oldname", "active")})
        members = {1: "NewName"}
        self.assertEqual(plan(state, members, host({"oldname": LinuxUser(1001, "")}), {}), [])
        self.assertEqual(with_logins(state, members).accounts[1], Account("oldname", "NewName", "active"))

    def test_locked_name_is_not_reused_by_someone_else(self):
        state = State({1: Account("same", "same", "locked")})
        actions = plan(state, {2: "same"}, host({"same": LinuxUser(1001, "")}), {})
        self.assertIsInstance(actions[0], Conflict)

    def test_steady_state_has_no_actions(self):
        state = State({1: Account("a", "a", "active")})
        self.assertEqual(plan(state, {1: "a"}, host({"a": LinuxUser(1001, "")}), {}), [])

    def test_locking_most_accounts_at_once_is_flagged(self):
        state = State({i: Account(f"u{i}", f"u{i}", "active") for i in range(1, 8)})
        locks = [Lock(i, f"u{i}") for i in range(1, 6)]
        self.assertTrue(too_many_locks(state, locks))
        self.assertFalse(too_many_locks(state, locks[:2]))

    def test_apply_records_lock(self):
        state = apply(State({1: Account("a", "a", "active")}), Lock(1, "a"))
        self.assertEqual(state.accounts[1].status, "locked")


if __name__ == "__main__":
    unittest.main()
