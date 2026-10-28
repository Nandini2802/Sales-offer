"""Bank-only requirement: project name must be stated in the message
or already explicitly confirmed in this session. Never resolve using unit IDs.
"""
from dataclasses import dataclass
from app.services.project_resolution_service import (
    match_project_in_message,
    match_project_reference,
)

PROJECT_NAME_REQUIRED = (
    'Could you please tell me the project name '
    'so I can share the bank details?'
)

class BankDetailsProjectResolutionError(ValueError):
    pass

@dataclass(frozen=True)
class ResolvedBankDetailsProject:
    project_id: str
    project_name: str


def resolve_bank_details_project(
    *,
    message: str,
    snapshot,
    confirmed_project_name: str | None = None,
) -> ResolvedBankDetailsProject:
    projects = {
        p.project_name: str(p.project_id)
        for p in snapshot.projects
        if p.project_id and p.project_name
    }

    result = match_project_in_message(message, projects)
    if result.status == 'ambiguous':
        raise BankDetailsProjectResolutionError(
            'Multiple projects match your request. Please confirm the project name: '
            + ', '.join(result.candidates[:5])
        )

    # Only an explicitly confirmed project may be reused from context.
    # Never use the LLM-inferred project_name as confirmation.
    if result.status != 'matched' and confirmed_project_name:
        result = match_project_reference(confirmed_project_name, projects)
        if result.method != 'exact':
            result = match_project_in_message('', projects)

    if result.status != 'matched' or not result.name:
        raise BankDetailsProjectResolutionError(PROJECT_NAME_REQUIRED)

    return ResolvedBankDetailsProject(
        project_id=projects[result.name],
        project_name=result.name,
    )
