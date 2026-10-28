"""Catalog-scoped project name matching; does not grant data access.

Resolution order: exact full/short name, unique alias, guarded fuzzy match,
then ambiguity/unknown. Bank details independently verifies a name in the
current message rather than trusting an LLM-provided project name.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Collection


@dataclass(frozen=True)
class ProjectResolution:
    status: str  # matched | ambiguous | not_found
    name: str | None = None
    method: str | None = None
    candidates: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _short(value: str | None) -> str:
    return re.sub(r"\s+by\s+danube$", "", _norm(value)).strip()


def _numbers(value: str | None) -> tuple[str, ...]:
    return tuple(re.findall(r"\b\d+\b", _norm(value)))


def _names(projects: Collection[str]) -> list[str]:
    return sorted({str(p).strip() for p in projects if p and str(p).strip()})


def _aliases(name: str) -> set[str]:
    return {alias for alias in (_norm(name), _short(name)) if alias}


def _score(left: str, right: str) -> float:
    def canonical(value: str) -> str:
        return " ".join(
            w[:-1] + "z" if len(w) > 3 and w.endswith("s") else w
            for w in value.split()
        )
    return max(
        SequenceMatcher(None, left, right).ratio(),
        SequenceMatcher(None, canonical(left), canonical(right)).ratio(),
    )


def _exact(phrase: str, names: list[str], method: str) -> ProjectResolution | None:
    normalized = _norm(phrase)
    if not normalized:
        return None
    # Full canonical name is always authoritative over near fuzzy matches.
    full = [name for name in names if _norm(name) == normalized]
    if len(full) == 1:
        return ProjectResolution("matched", full[0], method)
    if len(full) > 1:
        return ProjectResolution("ambiguous", candidates=tuple(full))
    short = [name for name in names if _short(name) == normalized]
    if len(short) == 1:
        return ProjectResolution("matched", short[0], method)
    if len(short) > 1:
        return ProjectResolution("ambiguous", candidates=tuple(short))
    return None


def _rank(phrase: str, names: list[str]) -> list[tuple[float, str]]:
    query = _short(phrase)
    if len(query) < 4 or not re.search(r"[a-z]{3,}", query):
        return []
    nums = _numbers(query)
    results = []
    for name in names:
        if _numbers(_short(name)) != nums:
            continue  # Never substitute a different numbered project.
        results.append((_score(query, _short(name)), name))
    return sorted(results, key=lambda item: (-item[0], item[1]))


def _select(phrase: str, names: list[str], *, threshold: float, method: str) -> ProjectResolution:
    exact = _exact(phrase, names, "message_exact" if method == "message_fuzzy" else "exact")
    if exact:
        return exact
    ranked = _rank(phrase, names)
    if not ranked or ranked[0][0] < threshold:
        return ProjectResolution("not_found")
    score, best = ranked[0]
    if len(ranked) > 1 and score - ranked[1][0] < 0.09:
        return ProjectResolution("ambiguous", candidates=tuple(n for _, n in ranked[:3]))
    return ProjectResolution("matched", best, method)


def match_project_reference(reference: str | None, projects: Collection[str]) -> ProjectResolution:
    """Match a project reference extracted by LLM; never use as bank proof."""
    return _select(reference or "", _names(projects), threshold=0.70, method="fuzzy")


def _message_phrases(message: str) -> list[str]:
    """Extract project-like spans, excluding generic bank request wording."""
    text = _norm(message)
    # Common bank request prefixes. These are language patterns, not project mappings.
    prefixes = (
        r"^(?:please\s+)?(?:show|give|share|provide|fetch|find|tell|get)\s+(?:me\s+)?",
        r"^(?:what\s+(?:are|is)\s+)?",
        r"^(?:bank\s+(?:account|details|information|info|accounts)|account\s+details)\s+(?:number\s+)?(?:of|for|from|in)\s+",
    )
    for _ in range(3):
        old = text
        for prefix in prefixes:
            text = re.sub(prefix, "", text).strip()
        if text == old:
            break
    text = re.sub(r"\s+(?:bank\s+(?:details|account|information)|account\s+details)$", "", text)
    text = re.sub(r"^(?:of|for|from|in|the|project)\s+", "", text)
    text = re.sub(r"\s+(?:please|thanks|thank you)$", "", text)
    if not text:
        return []
    words = text.split()
    phrases = [text]
    # Restrict fuzzy windows to meaningful project-bearing spans; don't score
    # 'bank details' or 'account of' as candidate project names.
    for size in range(1, min(4, len(words)) + 1):
        for i in range(len(words) - size + 1):
            span = " ".join(words[i:i + size])
            if span not in phrases and re.search(r"[a-z]{4,}", span):
                phrases.append(span)
    return phrases


def match_project_in_message(message: str, projects: Collection[str]) -> ProjectResolution:
    """Verify a project mention in raw text, allowing safe spelling corrections."""
    names = _names(projects)
    text = _norm(message)
    if not text or not names:
        return ProjectResolution("not_found")

    # Whole-word exact aliases take precedence over every fuzzy match.
    found = [name for name in names if any(
        re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text)
        for alias in _aliases(name)
    )]
    if found:
        longest = max(len(_short(name).split()) for name in found)
        selected = [name for name in found if len(_short(name).split()) == longest]
        if len(selected) == 1:
            return ProjectResolution("matched", selected[0], "message_exact")
        return ProjectResolution("ambiguous", candidates=tuple(selected))

    phrases = _message_phrases(message)
    if not phrases:
        return ProjectResolution("not_found")

    # A family-only request such as 'Eleganz' must not select Eleganz 2/5.
    # Also handles misspelled family names when there is no exact unnumbered
    # project, without silently inventing a variant number.
    for phrase in phrases[:1]:
        if _numbers(phrase):
            break
        family_groups: dict[str, list[str]] = {}
        for name in names:
            short = _short(name)
            base = re.sub(r"\s+\d+$", "", short)
            if base != short:
                family_groups.setdefault(base, []).append(name)
        for base, members in family_groups.items():
            if len(members) > 1 and _score(phrase, base) >= 0.82:
                # If the catalog has an exact unnumbered project, the exact
                # match wins (e.g. ELITZ BY DANUBE vs ELITZ 2).
                exact = _exact(phrase, names, "message_exact")
                if exact:
                    return exact
                return ProjectResolution("ambiguous", candidates=tuple(sorted(members)))

    # Prefer full extracted phrase; a single token is not enough if a
    # numbered project was explicitly requested.
    per_name: dict[str, float] = {}
    requested_numbers = _numbers(phrases[0])
    for phrase in phrases:
        if _numbers(phrase) != requested_numbers:
            continue
        ranked = _rank(phrase, names)
        for score, name in ranked:
            if score >= 0.78:
                per_name[name] = max(per_name.get(name, 0.0), score)
    ranked = sorted(((score, name) for name, score in per_name.items()), key=lambda x: (-x[0], x[1]))
    if not ranked:
        return ProjectResolution("not_found")
    score, name = ranked[0]
    if len(ranked) > 1 and score - ranked[1][0] < 0.09:
        return ProjectResolution("ambiguous", candidates=tuple(n for _, n in ranked[:3]))
    return ProjectResolution("matched", name, "message_fuzzy")


def resolve_project(
    *,
    reference: str | None,
    message: str,
    projects: Collection[str],
    require_message_mention: bool = False,
) -> ProjectResolution:
    """Shared resolution; caller supplies the authorized, intent-specific catalog."""
    stated = match_project_in_message(message, projects)
    if require_message_mention:
        return stated
    if stated.status in {"matched", "ambiguous"}:
        return stated
    return match_project_reference(reference, projects) if reference else ProjectResolution("not_found")
