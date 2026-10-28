import pytest
from types import SimpleNamespace
from app.services.project_resolution_service import (
    match_project_in_message, match_project_reference, resolve_project,
)
from app.services.bank_details_project_resolver import (
    resolve_bank_details_project, BankDetailsProjectResolutionError,
)

PROJECTS = [
    'ASPIRZ BY DANUBE', 'GREENZ BY DANUBE', 'DIAMONDZ BY DANUBE',
    'ELEGANZ 2 BY DANUBE', 'ELEGANZ 5 BY DANUBE',
    'ELITZ 2 BY DANUBE', 'ELITZ 3 BY DANUBE',
    'TIMEZ BY DANUBE', 'BAYZ 102 BY DANUBE',
]

@pytest.mark.parametrize('question,expected', [
    ('Show bank details for Aspirs', 'ASPIRZ BY DANUBE'),
    ('Bank account of Greens', 'GREENZ BY DANUBE'),
    ('Show accounts of Greeenss', 'GREENZ BY DANUBE'),
    ('Bank details of Greeenz', 'GREENZ BY DANUBE'),
    ('Give me bank account of dIAMONds', 'DIAMONDZ BY DANUBE'),
    ('Bank details of Diamonds', 'DIAMONDZ BY DANUBE'),
    ('Bank details of Elegannz 2', 'ELEGANZ 2 BY DANUBE'),
    ('Bank details of Elegannz 5', 'ELEGANZ 5 BY DANUBE'),
    ('Bank details for Greenz by Danube', 'GREENZ BY DANUBE'),
])
def test_typos(question, expected):
    result = match_project_in_message(question, PROJECTS)
    assert result.status == 'matched'
    assert result.name == expected

@pytest.mark.parametrize('question', [
    'Bank details of Eleganz',
    'Bank details of Elitz',
])
def test_numbered_family_ambiguous(question):
    assert match_project_in_message(question, PROJECTS).status == 'ambiguous'

@pytest.mark.parametrize('question', [
    'Bank details for unit GRZ-TH-809',
    'Give account details for 1031001746692014',
    'Give me all bank details',
])
def test_bank_does_not_infer_project_from_identifier(question):
    snapshot = SimpleNamespace(projects=[
        SimpleNamespace(project_name=name, project_id=str(i))
        for i, name in enumerate(PROJECTS, start=1)
    ])
    with pytest.raises(BankDetailsProjectResolutionError):
        resolve_bank_details_project(message=question, snapshot=snapshot)

def test_bank_fuzzy_returns_catalog_project_id():
    snapshot = SimpleNamespace(projects=[
        SimpleNamespace(project_name=name, project_id=str(i))
        for i, name in enumerate(PROJECTS, start=1)
    ])
    result = resolve_bank_details_project(message='Bank account of Greens', snapshot=snapshot)
    assert result.project_name == 'GREENZ BY DANUBE'
    assert result.project_id == '2'

def test_llm_guess_not_accepted_for_bank():
    resolution = resolve_project(
        reference='GREENZ BY DANUBE', message='Bank details for unit GRZ-TH-809',
        projects=PROJECTS, require_message_mention=True,
    )
    assert resolution.status == 'not_found'

def test_catalog_scope():
    assert match_project_reference('Greens', ['ASPIRZ BY DANUBE']).status == 'not_found'
