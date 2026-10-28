"""Live integration smoke tests for Danube Inventory Milestone 1.

Run from repository root:
  python -m pip install python-dotenv
  python tests/test_inventory_milestone1.py

Required .env values:
  INVENTORY_TEST_TOKEN, INVENTORY_TEST_USER_ID
  FOUNDRY_OPENAI_BASE_URL, FOUNDRY_OPENAI_API_KEY
  FOUNDRY_OPENAI_MODEL (or Settings default)
  INVENTORY_PROJECT_API_URL, INVENTORY_UNITS_API_URL (used by existing client)

This script calls real UAT APIs and a real Foundry LLM. Do not commit secrets.
"""
import asyncio
import inspect
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')

from openai import AsyncOpenAI
from app.core.config import get_settings
from app.retrieval.salesforce_client import SalesforceClient
from app.retrieval.inventory_connector import InventoryConnector
from app.services.inventory_catalog_service import InventoryCatalogService
from app.services.router_service import RouterService


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def catalog_names(snapshot):
    catalogs = InventoryCatalogService.build(snapshot)
    active = catalogs.active_projects
    visible = catalogs.unit_projects
    check(isinstance(active, list) and isinstance(visible, list), 'Catalogs must be lists')
    check(all(isinstance(n, str) and n.strip() for n in active + visible), 'Invalid catalog names')
    check(len(active) == len(set(active)), 'Duplicate active project names')
    check(len(visible) == len(set(visible)), 'Duplicate visible unit project names')
    return active, visible


async def run_case(router, title, message, marketing, active, visible, expected_intent,
                   expected_project=None, clarification=None, scope=None):
    result = await router.classify(
        message=message,
        history=[],
        available_projects=marketing,
        inventory_active_projects=active,
        inventory_unit_projects=visible,
    )
    matching = [i for i in result.intents if i.intent == expected_intent]
    check(matching, f'{title}: expected {expected_intent}, got {[i.intent for i in result.intents]}')
    intent = matching[0]
    if expected_project is not None:
        check(intent.project_name == expected_project,
              f'{title}: expected {expected_project!r}, got {intent.project_name!r}')
    if clarification is not None:
        check(intent.requires_clarification is clarification,
              f'{title}: expected clarification={clarification}, got {intent.requires_clarification}')
    if scope is not None:
        check(getattr(intent, 'inventory_scope', None) == scope,
              f'{title}: expected scope={scope}, got {getattr(intent, "inventory_scope", None)}')
    print(f'  PASS {title}: intent={intent.intent}; project={intent.project_name}; '
          f'scope={getattr(intent, "inventory_scope", None)}; clarify={intent.requires_clarification}')
    return result


async def main():
    token = os.getenv('INVENTORY_TEST_TOKEN', '').strip()
    user_id = os.getenv('INVENTORY_TEST_USER_ID', '').strip()
    base_url = os.getenv('FOUNDRY_OPENAI_BASE_URL', '').strip()
    api_key = os.getenv('FOUNDRY_OPENAI_API_KEY', '').strip()
    settings = get_settings()
    model = os.getenv('FOUNDRY_OPENAI_MODEL', '').strip() or settings.foundry_openai_model
    missing = [k for k, v in {
        'INVENTORY_TEST_TOKEN': token, 'INVENTORY_TEST_USER_ID': user_id,
        'FOUNDRY_OPENAI_BASE_URL': base_url, 'FOUNDRY_OPENAI_API_KEY': api_key,
    }.items() if not v]
    check(not missing, 'Missing .env values: ' + ', '.join(missing))
    check('inventory_active_projects' in inspect.signature(RouterService.classify).parameters,
          'RouterService.classify must accept inventory_active_projects')
    check('inventory_unit_projects' in inspect.signature(RouterService.classify).parameters,
          'RouterService.classify must accept inventory_unit_projects')
    from app.schemas.routing import RoutingIntent
    check('inventory_scope' in RoutingIntent.model_fields,
          'RoutingIntent needs inventory_scope field')

    print('\n[1] Checking real Inventory APIs')
    api = SalesforceClient()
    try:
        # Independent checks make it clear which upstream endpoint failed.
        projects_raw = await api.get_active_projects(token=token)
        check(isinstance(projects_raw, list), 'Active Projects API should return a list')
        print(f'  PASS Active Projects API: {len(projects_raw)} records')
        units_raw = await api.get_visible_units(token=token, user_id=user_id)
        check(isinstance(units_raw, list), 'Visible Units API should return a list')
        print(f'  PASS Visible Units API: {len(units_raw)} records')

        print('\n[2] Checking normalization and catalog separation')
        connector = InventoryConnector(salesforce_client=api)
        snapshot = await connector.fetch_inventory(token=token, user_id=user_id)
        active, visible = catalog_names(snapshot)
        check(active, 'Active Projects catalog is empty; cannot test project resolution')
        print(f'  PASS Active catalog: {len(active)} unique projects')
        print(f'  PASS Visible-unit catalog: {len(visible)} unique projects')
        print('  Note: Visible-unit catalog can legitimately be empty for a user.')
        print('  Active-only examples:', (sorted(set(active) - set(visible)))[:5])

        print('\n[3] Checking real Foundry LLM and semantic project resolution')
        # Use deliberately separate marketing catalog to prove intent-specific routing.
        # This is a synthetic marketing catalog for a focused test, NOT live Marketing API data.
        marketing = ['GREENZ MARKETING DEMO', 'BROCHURE TEST PROJECT']
        async with AsyncOpenAI(base_url=base_url, api_key=api_key,
                               timeout=settings.foundry_openai_timeout_seconds) as foundry:
            router = RouterService(client=foundry, model=model)
            await run_case(router, 'General unit search', 'Show all available units',
                           marketing, active, visible, 'inventory',
                           clarification=False, scope='units')

            if 'GREENZ BY DANUBE' in set(active) | set(visible):
                await run_case(router, 'Misspelling Greenz', 'Show available units in grenz',
                               marketing, active, visible, 'inventory',
                               expected_project='GREENZ BY DANUBE', clarification=False, scope='units')
            else:
                print('  SKIP Greenz spelling test: project not in live inventory catalogs')

            if 'ASPIRZ BY DANUBE' in set(active) | set(visible):
                await run_case(router, 'Shortened Aspirz', 'Show units in Aspirz',
                               marketing, active, visible, 'inventory',
                               expected_project='ASPIRZ BY DANUBE', clarification=False, scope='units')
            else:
                print('  SKIP Aspirz test: project not in live inventory catalogs')

            eleganz = [n for n in set(active) | set(visible) if n.startswith('ELEGANZ ')]
            if len(eleganz) >= 2:
                result = await run_case(router, 'Ambiguous Eleganz', 'Show available units in Eleganz',
                                        marketing, active, visible, 'inventory',
                                        clarification=True, scope='units')
                check(next(i for i in result.intents if i.intent == 'inventory').project_name is None,
                      'Ambiguous Eleganz should have project_name=None')
            else:
                print('  SKIP ambiguity test: fewer than two Eleganz projects in live catalogs')

            active_only = sorted(set(active) - set(visible))
            if active_only:
                name = active_only[0]
                await run_case(router, 'Active-only project recognized',
                               f'Show available units in {name}', marketing, active, visible,
                               'inventory', expected_project=name, clarification=False, scope='units')
            else:
                print('  SKIP active-only test: all active projects appear in unit catalog')

            await run_case(router, 'Marketing catalog isolation',
                           'Give me brochure for BROCHURE TEST PROJECT', marketing, active, visible,
                           'marketing', expected_project='BROCHURE TEST PROJECT', clarification=False)

        print('\nSUCCESS: All executed Milestone 1 smoke tests passed.')
        print('Note: This does not test APIM, chat SSE, RBAC authorization, or InventoryHandler rendering.')
    finally:
        # Some client implementations own an httpx.AsyncClient, others create one per request.
        http_client = getattr(api, 'http_client', None)
        if http_client is not None and not http_client.is_closed:
            await http_client.aclose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f'\nFAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
