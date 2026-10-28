import pytest
from app.services.walkthrough_access_service import WalkthroughEngine

@pytest.fixture(scope='module')
def engine():
    return WalkthroughEngine(directory='app/data/walkthrough')

@pytest.mark.parametrize('role,employee_type', [('HOS','direct'),('HOS','indirect'),('DOS','direct'),('DOS','indirect'),('RM','direct'),('RM','indirect')])
def test_team_role_resolution(engine,role,employee_type):
    allowed,reason=engine.permission('Unit Details Page',role,'mobile_app',employee_type)
    assert reason=='permission_checked'
    assert isinstance(allowed,bool)

@pytest.mark.parametrize('role', ['BROKER_AGENT','UNKNOWN','', 'Partner/Owner'])
def test_unknown_or_unmapped_role(engine,role):
    assert engine.lookup('Create Lead',role,'mobile_app','')['status']=='denied'

def test_team_empty_employee_type_denied(engine):
    assert engine.lookup('Create Lead','HOS','mobile_app','')['status']=='denied'

def test_known_agent_feature(engine):
    result=engine.lookup('Create Lead','Agent','mobile_app','')
    assert result['status']=='ok'
    assert result['steps']

def test_unmapped_feature(engine):
    assert engine.lookup('3D Tour / Virtual Tour','Agent','mobile_app','')['status']=='denied'

def test_unknown_feature(engine):
    assert engine.lookup('Secret Feature','Agent','mobile_app','')['status']=='denied'
