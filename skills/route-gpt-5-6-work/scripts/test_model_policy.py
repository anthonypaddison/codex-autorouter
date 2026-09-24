import unittest

from model_policy import (
    ACTIVE_MODELS,
    POLICY_REVISION,
    RootSatisfaction,
    RouteProfile,
    TransitionKind,
    capability_key,
    classify_transition,
    root_profile_satisfaction,
    select_target,
)


class ModelPolicyTests(unittest.TestCase):
    def test_active_registry_contains_only_the_three_gpt6_models(self):
        self.assertEqual(
            set(ACTIVE_MODELS),
            {"gpt-6-luna", "gpt-6-sol", "gpt-6-astra"},
        )

    def test_luna_efforts_preserve_cheap_root_but_not_other_profiles(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.assertEqual(
                    root_profile_satisfaction("gpt-6-luna", effort, "cheap"),
                    RootSatisfaction.SATISFIED,
                )
                self.assertEqual(
                    root_profile_satisfaction("gpt-6-luna", effort, "balanced"),
                    RootSatisfaction.UNSATISFIED,
                )

    def test_sol_root_satisfaction_is_effort_and_profile_specific(self):
        expected = {
            "low": ("satisfied", "unsatisfied", "unsatisfied"),
            "medium": ("satisfied", "satisfied", "unsatisfied"),
            "high": ("satisfied", "satisfied", "satisfied"),
            "xhigh": ("satisfied", "satisfied", "satisfied"),
            "max": ("satisfied", "satisfied", "satisfied"),
            "ultra": ("satisfied", "satisfied", "satisfied"),
        }
        for effort, statuses in expected.items():
            with self.subTest(effort=effort):
                for profile, status in zip(("cheap", "balanced", "high"), statuses):
                    self.assertEqual(
                        root_profile_satisfaction("gpt-6-sol", effort, profile).value,
                        status,
                    )

    def test_unobservable_effort_does_not_prove_profile_or_trigger_target(self):
        self.assertEqual(
            root_profile_satisfaction("gpt-6-sol", None, "high"),
            RootSatisfaction.UNPROVEN,
        )
        selection = select_target(
            "high", root_model="gpt-6-sol", root_effort=None
        )
        self.assertEqual(selection.transition, TransitionKind.NONE)
        self.assertEqual(selection.target_model_id, "gpt-6-sol")
        self.assertEqual(selection.satisfaction, RootSatisfaction.UNPROVEN)

    def test_profile_up_is_not_a_model_route_up(self):
        self.assertEqual(
            classify_transition("gpt-6-sol", "low", "gpt-6-sol", "medium"),
            TransitionKind.PROFILE_UP,
        )
        self.assertEqual(
            classify_transition("gpt-6-sol", "medium", "gpt-6-sol", "high"),
            TransitionKind.PROFILE_UP,
        )
        self.assertEqual(
            classify_transition("gpt-6-luna", "low", "gpt-6-sol", "medium"),
            TransitionKind.MODEL_ROUTE_UP,
        )

    def test_active_target_selection_is_profile_and_discovery_gated(self):
        selection = select_target(
            "balanced",
            root_model="gpt-6-luna",
            root_effort="low",
            discovery_state="available",
        )
        self.assertEqual(selection.target_model_id, "gpt-6-sol")
        self.assertEqual(selection.target_effort, "medium")
        self.assertTrue(selection.approved)
        unavailable = select_target("balanced", discovery_state="discovery_unavailable")
        self.assertFalse(unavailable.approved)
        self.assertEqual(unavailable.target_model_id, "gpt-6-sol")
        unapproved = select_target(
            "balanced",
            requested_model_id="gpt-5.6-sol",
            discovery_state="available",
        )
        self.assertFalse(unapproved.approved)

    def test_sol_balanced_and_high_have_distinct_capability_identity(self):
        balanced = capability_key("gpt-6-sol", "balanced", "medium")
        high = capability_key("gpt-6-sol", "high", "high")
        self.assertNotEqual(balanced, high)
        self.assertIn(POLICY_REVISION, balanced)


if __name__ == "__main__":
    unittest.main(verbosity=2)
