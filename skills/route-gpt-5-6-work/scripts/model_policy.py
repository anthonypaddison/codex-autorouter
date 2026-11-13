"""Pure, deterministic GPT-6 route-profile policy."""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

POLICY_SCHEMA_VERSION = 1
POLICY_REVISION = "gpt6-profiles-2026-09-22.1"


class RootSatisfaction(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNPROVEN = "unproven"


class TransitionKind(str, Enum):
    NONE = "none"
    MODEL_ROUTE_UP = "model_route_up"
    PROFILE_UP = "profile_up"
    DOWNWARD = "downward"


class DiscoveryState(str, Enum):
    AVAILABLE = "available"
    ABSENT = "absent"
    HIDDEN = "hidden_nonselectable"
    UNAVAILABLE = "discovery_unavailable"


class PolicyOutcome(str, Enum):
    APPROVED = "approved"
    POLICY_UNAPPROVED = "policy_unapproved"
    PROFILE_UNAPPROVED = "profile_unapproved"
    EFFORT_UNAPPROVED = "effort_unapproved"
    AVAILABILITY_UNPROVEN = "availability_unproven"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ModelPolicy:
    canonical_id: str
    display_label: str
    automatic_target: bool
    child_target_allowed: bool
    explicit_root_allowed: bool
    explicit_child_efforts: tuple[str, ...]
    root_ownership: str


@dataclass(frozen=True)
class RouteProfile:
    profile_id: str
    target_model_id: str
    automatic_effort: str
    allowed_automatic_efforts: tuple[str, ...]
    ordinal: int


@dataclass(frozen=True)
class TargetSelection:
    profile_id: str
    target_model_id: str
    target_effort: str
    approved: bool
    outcome: PolicyOutcome
    transition: TransitionKind
    satisfaction: RootSatisfaction


ACTIVE_MODELS: Mapping[str, ModelPolicy] = MappingProxyType({
    "gpt-6-luna": ModelPolicy("gpt-6-luna", "GPT-6 Luna", True, False, True, (), "preserve"),
    "gpt-6-sol": ModelPolicy("gpt-6-sol", "GPT-6 Sol", True, True, True, ("medium", "high", "xhigh"), "preserve"),
    "gpt-6.1-sol": ModelPolicy("gpt-6.1-sol", "GPT-6.1 Sol", True, True, True, ("medium", "high", "xhigh"), "preserve"),
    "gpt-6.1-terra": ModelPolicy("gpt-6.1-terra", "GPT-6.1 Terra", True, True, True, ("medium", "high", "xhigh"), "preserve"),
    "gpt-6-astra": ModelPolicy("gpt-6-astra", "GPT-6 Astra", True, True, True, ("medium", "high", "xhigh", "max"), "preserve"),
})

WORKHORSE_MODELS = frozenset({"gpt-6-sol", "gpt-6.1-sol", "gpt-6.1-terra"})

ROUTE_PROFILES: Mapping[str, RouteProfile] = MappingProxyType({
    "cheap": RouteProfile("cheap", "gpt-6-luna", "low", (), 0),
    "balanced": RouteProfile("balanced", "gpt-6-sol", "medium", ("medium",), 1),
    "high": RouteProfile("high", "gpt-6-sol", "high", ("high", "xhigh"), 2),
    "frontier": RouteProfile("frontier", "gpt-6-astra", "medium", ("medium",), 3),
})

ROOT_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
_EFFORT_ORDINAL = {name: index for index, name in enumerate(("low", "medium", "high", "xhigh", "max", "ultra"))}


def root_profile_satisfaction(root_model: str | None, root_effort: str | None, profile_id: str) -> RootSatisfaction:
    """Assess a root against a requested profile without changing root ownership."""
    profile = ROUTE_PROFILES.get(profile_id)
    if profile is None or root_model not in ACTIVE_MODELS:
        return RootSatisfaction.UNPROVEN
    effort = root_effort.lower() if isinstance(root_effort, str) else None
    if effort not in ROOT_EFFORTS:
        return RootSatisfaction.UNPROVEN
    if root_model == "gpt-6-luna":
        return RootSatisfaction.SATISFIED if profile_id == "cheap" else RootSatisfaction.UNSATISFIED
    if root_model in WORKHORSE_MODELS:
        if profile_id == "cheap":
            return RootSatisfaction.SATISFIED
        required = {"balanced": "medium", "high": "high"}.get(profile_id)
        if required is None:
            return RootSatisfaction.UNSATISFIED
        return RootSatisfaction.SATISFIED if _EFFORT_ORDINAL[effort] >= _EFFORT_ORDINAL[required] else RootSatisfaction.UNSATISFIED
    # Astra remains the owner and never routes down; supported observed effort
    # is sufficient to retain it for any lower/equal request.
    return RootSatisfaction.SATISFIED


def classify_transition(source_model: str | None, source_effort: str | None, target_model: str, target_effort: str) -> TransitionKind:
    """Classify model changes separately from same-model effort increases."""
    if source_model == target_model:
        old = _EFFORT_ORDINAL.get((source_effort or "").lower())
        new = _EFFORT_ORDINAL.get(target_effort.lower())
        if old is None or new is None:
            return TransitionKind.NONE
        if new > old:
            return TransitionKind.PROFILE_UP
        if new < old:
            return TransitionKind.DOWNWARD
        return TransitionKind.NONE
    if source_model in WORKHORSE_MODELS and target_model == "gpt-6-astra":
        return TransitionKind.MODEL_ROUTE_UP
    if (source_model, target_model) in {
        ("gpt-6-luna", "gpt-6-sol"),
        ("gpt-6-sol", "gpt-6-astra"),
    }:
        return TransitionKind.MODEL_ROUTE_UP
    if (source_model, target_model) in {
        ("gpt-6-sol", "gpt-6-luna"),
        ("gpt-6-astra", "gpt-6-sol"),
        ("gpt-6-astra", "gpt-6-luna"),
    }:
        return TransitionKind.DOWNWARD
    return TransitionKind.NONE


def select_target(profile_id: str, *, root_model: str | None = None, root_effort: str | None = None, discovery_state: str | DiscoveryState = DiscoveryState.AVAILABLE, requested_model_id: str | None = None, requested_effort: str | None = None, deep_high: bool = False) -> TargetSelection:
    """Select only the exact profile target after independent policy and discovery checks."""
    profile = ROUTE_PROFILES.get(profile_id)
    if profile is None:
        return TargetSelection(profile_id, root_model or "", root_effort or "", False, PolicyOutcome.PROFILE_UNAPPROVED, TransitionKind.NONE, RootSatisfaction.UNPROVEN)
    satisfaction = root_profile_satisfaction(root_model, root_effort, profile_id)
    target_model = root_model if root_model in WORKHORSE_MODELS and profile_id in {"balanced", "high"} else profile.target_model_id
    target_effort = profile.automatic_effort
    if profile_id == "high" and deep_high:
        target_effort = "xhigh"
    if requested_model_id is not None and requested_model_id != target_model:
        return TargetSelection(profile_id, target_model, target_effort, False, PolicyOutcome.POLICY_UNAPPROVED, TransitionKind.NONE, satisfaction)
    if requested_effort is not None and requested_effort not in profile.allowed_automatic_efforts:
        return TargetSelection(profile_id, target_model, target_effort, False, PolicyOutcome.EFFORT_UNAPPROVED, TransitionKind.NONE, satisfaction)
    if satisfaction in {RootSatisfaction.SATISFIED, RootSatisfaction.UNPROVEN}:
        return TargetSelection(profile_id, root_model or target_model, root_effort or target_effort, False, PolicyOutcome.PROFILE_UNAPPROVED if satisfaction == RootSatisfaction.UNPROVEN else PolicyOutcome.APPROVED, TransitionKind.NONE, satisfaction)
    try:
        discovery = discovery_state if isinstance(discovery_state, DiscoveryState) else DiscoveryState(discovery_state)
    except ValueError:
        discovery = DiscoveryState.UNAVAILABLE
    if discovery != DiscoveryState.AVAILABLE:
        outcome = PolicyOutcome.AVAILABILITY_UNPROVEN if discovery == DiscoveryState.UNAVAILABLE else PolicyOutcome.UNAVAILABLE
        return TargetSelection(profile_id, root_model or "", root_effort or "", False, outcome, TransitionKind.NONE, satisfaction)
    transition = classify_transition(root_model, root_effort, target_model, target_effort)
    if transition in {TransitionKind.DOWNWARD, TransitionKind.NONE}:
        return TargetSelection(profile_id, root_model or "", root_effort or "", False, PolicyOutcome.PROFILE_UNAPPROVED, transition, satisfaction)
    return TargetSelection(profile_id, target_model, target_effort, True, PolicyOutcome.APPROVED, transition, satisfaction)


def capability_key(model_id: str, profile_id: str, effort: str) -> str:
    """Return the receipt key bound to exact model, profile, effort and policy revision."""
    if model_id not in ACTIVE_MODELS or profile_id not in ROUTE_PROFILES or not effort:
        raise ValueError("unknown capability identity")
    return f"{model_id}|{profile_id}|{effort.lower()}|{POLICY_REVISION}"


def capability_specs() -> dict[str, tuple[str, str, str]]:
    """Share exact receipt identities between the writer and readiness checker."""
    specs = [(model, profile, effort) for model in sorted(WORKHORSE_MODELS)
             for profile, effort in (("balanced", "medium"), ("high", "high"), ("high", "xhigh"))]
    specs.append(("gpt-6-astra", "frontier", "medium"))
    return {capability_key(*spec): spec for spec in specs}


def validate_registry() -> None:
    if set(ACTIVE_MODELS) != {"gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-astra"}:
        raise ValueError("active model registry must contain only approved GPT-6 models")
    for key, profile in ROUTE_PROFILES.items():
        if key != profile.profile_id or profile.target_model_id not in ACTIVE_MODELS:
            raise ValueError("invalid route profile reference")
        if profile.profile_id == "cheap" and profile.target_model_id != "gpt-6-luna":
            raise ValueError("cheap profile must target GPT-6 Luna")
        if profile.profile_id in {"balanced", "high"} and profile.target_model_id != "gpt-6-sol":
            raise ValueError("balanced/high profiles must target GPT-6 Sol")
        if profile.profile_id == "frontier" and profile.target_model_id != "gpt-6-astra":
            raise ValueError("frontier profile must target GPT-6 Astra")


validate_registry()
