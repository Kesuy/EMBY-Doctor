from __future__ import annotations

import copy
import json
import re
import unicodedata
import urllib.parse
from typing import Any


def normalize_person_name(value: Any) -> str:
    """Normalize a Person name for conservative duplicate detection."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    # Ignore common visual separators and whitespace, but keep letters/numbers intact.
    return re.sub(r"[\s\u3000·・._\-]+", "", text)


def person_provider_ids(person: dict[str, Any]) -> dict[str, str]:
    raw = person.get("ProviderIds") or {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        provider = str(key or "").strip()
        provider_id = str(value or "").strip()
        if provider and provider_id:
            result[provider] = provider_id
    return result



def _identity_name_candidates(value: Any) -> list[str]:
    """Extract a stable display identity from provider-supplied actor names."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
    if len(parts) > 1:
        cjk_parts = [
            part
            for part in parts
            if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", part)
        ]
        return [cjk_parts[-1] if cjk_parts else parts[-1]]
    return [text]


def identity_name_matches(left: Any, right: Any) -> bool:
    """Return True when two identity labels are the same or one contains the other."""
    left_key = normalize_person_name(left)
    right_key = normalize_person_name(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if min(len(left_key), len(right_key)) < 3:
        return False
    return left_key in right_key or right_key in left_key


def provider_identity_hints(person: dict[str, Any]) -> list[dict[str, str]]:
    """Extract human-readable identity hints embedded by common AV metadata providers.

    These hints are deliberately limited to provider values that carry a name
    directly. Numeric IDs such as TMDB/FANZA are not resolved over the network.
    """
    hints: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(source: str, identity: Any, evidence: str) -> None:
        for candidate in _identity_name_candidates(identity):
            key = (source.casefold(), normalize_person_name(candidate))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            hints.append(
                {
                    "Source": source,
                    "Identity": candidate,
                    "Evidence": evidence,
                }
            )

    for provider, raw_value in person_provider_ids(person).items():
        key = provider.casefold()
        value = str(raw_value or "").strip()
        if not value:
            continue

        if "javscraper-actress-json" in key:
            try:
                payload = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and payload.get("Name"):
                add(provider, payload.get("Name"), value)

        if value.casefold().startswith("gfriends:"):
            add(provider, urllib.parse.unquote(value.split(":", 1)[1]), value)

        if "minnano" in key and "?" in value:
            add(provider, urllib.parse.unquote(value.rsplit("?", 1)[1]), value)

        if "javscraper-actress" in key and "raw.githubusercontent.com" in value:
            path = urllib.parse.urlparse(value).path
            filename = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            if "." in filename:
                filename = filename.rsplit(".", 1)[0]
            filename = re.sub(r"^AI-Fix[-_]", "", filename, flags=re.IGNORECASE)
            add(provider, filename, value)

    return hints


def find_person_identity_anomalies(persons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find a single Person whose embedded provider name hints disagree with its name."""
    anomalies: list[dict[str, Any]] = []
    for person in persons:
        person_id = str(person.get("Id") or "").strip()
        person_name = str(person.get("Name") or "").strip()
        if not person_id or not person_name:
            continue

        hints = provider_identity_hints(person)
        mismatched = [
            hint
            for hint in hints
            if not identity_name_matches(person_name, hint.get("Identity"))
        ]
        if not mismatched:
            continue

        groups: dict[str, dict[str, Any]] = {}
        for hint in mismatched:
            identity = str(hint.get("Identity") or "").strip()
            identity_key = normalize_person_name(identity)
            if not identity_key:
                continue
            group = groups.setdefault(
                identity_key,
                {"Identity": identity, "Sources": []},
            )
            source = str(hint.get("Source") or "").strip()
            if source and source not in group["Sources"]:
                group["Sources"].append(source)

        if not groups:
            continue

        source_count = sum(len(group["Sources"]) for group in groups.values())
        risk = "高" if len(groups) >= 2 or source_count >= 2 else "中"
        summary = " / ".join(
            f"{group['Identity']}（{'、'.join(group['Sources'])}）"
            for group in groups.values()
        )
        anomalies.append(
            {
                "Id": person_id,
                "Name": person_name,
                "Person": person,
                "Hints": hints,
                "MismatchedHints": mismatched,
                "Risk": risk,
                "Summary": summary,
            }
        )

    anomalies.sort(
        key=lambda item: (
            0 if item["Risk"] == "高" else 1,
            normalize_person_name(item["Name"]),
            item["Id"],
        )
    )
    return anomalies


def provider_conflicts(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    left_ids = person_provider_ids(left)
    right_ids = person_provider_ids(right)
    right_by_key = {key.casefold(): (key, value) for key, value in right_ids.items()}
    conflicts: list[str] = []
    for key, value in left_ids.items():
        other = right_by_key.get(key.casefold())
        if other and other[1].casefold() != value.casefold():
            conflicts.append(key)
    return sorted(conflicts, key=str.casefold)


def person_completeness(person: dict[str, Any], association_count: int = 0) -> int:
    """Return a deterministic 0-100 profile completeness score."""
    score = 0
    providers = person_provider_ids(person)
    score += min(35, len(providers) * 7)
    if person.get("PrimaryImageTag") or (person.get("ImageTags") or {}).get("Primary"):
        score += 20
    if str(person.get("Overview") or "").strip():
        score += 15
    if person.get("PremiereDate") or person.get("ProductionYear"):
        score += 10
    locations = person.get("ProductionLocations") or []
    if locations:
        score += 5
    if str(person.get("SortName") or "").strip():
        score += 5
    score += min(10, max(0, int(association_count)))
    return min(100, score)


def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))


def build_duplicate_candidates(
    persons: list[dict[str, Any]],
    association_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Build conservative duplicate Person candidates.

    Highest confidence is shared provider identity; otherwise normalized exact
    name matches are included for manual review. Nothing is modified here.
    """
    association_counts = association_counts or {}
    people = {
        str(person.get("Id") or "").strip(): person
        for person in persons
        if str(person.get("Id") or "").strip()
    }
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    def add_pair(a_id: str, b_id: str, confidence: int, reason: str) -> None:
        if not a_id or not b_id or a_id == b_id:
            return
        key = _pair_key(a_id, b_id)
        existing = candidates.get(key)
        if existing and int(existing["Confidence"]) >= confidence:
            return
        a = people[a_id]
        b = people[b_id]
        a_score = person_completeness(a, association_counts.get(a_id, 0))
        b_score = person_completeness(b, association_counts.get(b_id, 0))
        if (b_score, association_counts.get(b_id, 0), b_id) > (
            a_score,
            association_counts.get(a_id, 0),
            a_id,
        ):
            left, right = b, a
            left_score, right_score = b_score, a_score
        else:
            left, right = a, b
            left_score, right_score = a_score, b_score
        candidates[key] = {
            "Left": left,
            "Right": right,
            "Confidence": confidence,
            "Reason": reason,
            "Conflicts": provider_conflicts(a, b),
            "LeftScore": left_score,
            "RightScore": right_score,
        }

    # Same provider + same provider id is the strongest identity signal.
    provider_index: dict[tuple[str, str], list[str]] = {}
    for person_id, person in people.items():
        for provider, provider_id in person_provider_ids(person).items():
            provider_index.setdefault(
                (provider.casefold(), provider_id.casefold()), []
            ).append(person_id)
    for ids in provider_index.values():
        unique_ids = list(dict.fromkeys(ids))
        if len(unique_ids) < 2:
            continue
        anchor = max(
            unique_ids,
            key=lambda pid: (
                person_completeness(people[pid], association_counts.get(pid, 0)),
                association_counts.get(pid, 0),
                pid,
            ),
        )
        for other in unique_ids:
            if other != anchor:
                add_pair(anchor, other, 100, "Provider ID 一致")

    # Exact normalized name match is useful but still requires manual review.
    name_index: dict[str, list[str]] = {}
    for person_id, person in people.items():
        name_key = normalize_person_name(person.get("Name"))
        if name_key:
            name_index.setdefault(name_key, []).append(person_id)
    for ids in name_index.values():
        unique_ids = list(dict.fromkeys(ids))
        if len(unique_ids) < 2:
            continue
        anchor = max(
            unique_ids,
            key=lambda pid: (
                person_completeness(people[pid], association_counts.get(pid, 0)),
                association_counts.get(pid, 0),
                pid,
            ),
        )
        for other in unique_ids:
            if other != anchor:
                add_pair(anchor, other, 90, "姓名完全一致")

    result = list(candidates.values())
    result.sort(
        key=lambda item: (
            -int(item["Confidence"]),
            normalize_person_name(item["Left"].get("Name")),
            str(item["Left"].get("Id") or ""),
            str(item["Right"].get("Id") or ""),
        )
    )
    return result


def replace_person_reference(
    item: dict[str, Any],
    old_person: dict[str, Any],
    keep_person: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Replace references to one Person with another in an item People list.

    The Person entity itself is never deleted. Existing identical references
    to the keep Person are de-duplicated by (Id, Type, Role).
    """
    old_id = str(old_person.get("Id") or "").strip()
    keep_id = str(keep_person.get("Id") or "").strip()
    keep_name = str(keep_person.get("Name") or "").strip()
    if not old_id or not keep_id:
        return copy.deepcopy(item), 0

    result = copy.deepcopy(item)
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    replaced = 0

    for raw_person in result.get("People") or []:
        person = dict(raw_person)
        if str(person.get("Id") or "").strip() == old_id:
            person["Id"] = keep_id
            if keep_name:
                person["Name"] = keep_name
            replaced += 1

        identity = (
            str(person.get("Id") or "").strip(),
            str(person.get("Type") or "").strip().casefold(),
            str(person.get("Role") or "").strip().casefold(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        output.append(person)

    result["People"] = output
    # UserData is playback state and should not be posted as editable metadata.
    result.pop("UserData", None)
    return result, replaced
