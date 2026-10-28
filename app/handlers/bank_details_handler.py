import logging

from app.schemas.handler_result import HandlerResult
from app.services.template_service import TemplateService
from app.services.bank_details_service import BankDetailsService
from app.services.bank_details_project_resolver import (
    resolve_bank_details_project,
    BankDetailsProjectResolutionError,
)
from app.retrieval.bank_details_connector import BankDetailsAPIError


logger = logging.getLogger(__name__)


class BankDetailsHandler:

    def __init__(
        self,
        inventory_snapshot,
        access_token: str,
        user_id: str,
        message: str = "",
        confirmed_project_name: str | None = None,
    ):
        self.inventory_snapshot = inventory_snapshot
        self.access_token = access_token
        self.user_id = user_id
        self.message = message
        self.confirmed_project_name = confirmed_project_name

        self.service = BankDetailsService()
        self.templates = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(intent="bank_details")

        try:

            resolved = resolve_bank_details_project(
                message=self.message,
                snapshot=self.inventory_snapshot,
                confirmed_project_name=self.confirmed_project_name,
            )

            project_id = resolved.project_id
            project_name = resolved.project_name

            logger.info(
                "BANK_DETAILS_PROJECT_RESOLVED",
                extra={
                    "project_id": project_id,
                    "user_id": self.user_id,
                },
            )

            accounts = await self.service.get_accounts(
                project_id=project_id,
                access_token=self.access_token,
                user_id=self.user_id,
                account_types=getattr(
                    intent,
                    "bank_account_types",
                    None,
                ),
                bank_id=getattr(
                    intent,
                    "bank_id",
                    None,
                ),
                bank_name=getattr(
                    intent,
                    "bank_name",
                    None,
                ),
                account_number=getattr(
                    intent,
                    "bank_account_number",
                    None,
                ),
                account_index=getattr(
                    intent,
                    "bank_account_index",
                    None,
                ),
            )

            if not accounts:
                result.messages.append(
                    "No matching bank accounts were found "
                    f"for {project_name}."
                )

                result.generation_context = {
                    "service": "bank_details",
                    "project": project_name,
                    "accounts_found": False,
                    "account_count": 0,
                }

                return result

            display_accounts = []

            for account in accounts:
                account_data = account.model_dump()

                account_data["displayBankType"] = (
                    self.service.format_account_type(
                        account.bankType
                    )
                )

                account_data["projectName"] = project_name

                display_accounts.append(account_data)

            if len(display_accounts) == 1:

                html = self.templates.render(
                    "bank_details_single.html.j2",
                    project=project_name,
                    account=display_accounts[0],
                )

            else:

                html = self.templates.render(
                    "bank_details.html.j2",
                    project=project_name,
                    accounts=display_accounts,
                )
            result.html_blocks.append(
                {
                    "card_type": "bank_details",
                    "html": html,
                }
            )

            result.generation_context = {
                "service": "bank_details",
                "project": project_name,
                "accounts_found": True,
                "account_count": len(accounts),
                "account_types": [
                    self.service.format_account_type(
                        account.bankType
                    )
                    for account in accounts
                ],
                "bank_names": list(
                    {
                        account.bankName
                        for account in accounts
                    }
                ),
            }

            result.has_data = True

            logger.info(
                "BANK_DETAILS_COMPLETED",
                extra={
                    "project_id": project_id,
                    "account_count": len(accounts),
                },
            )

            return result

        except BankDetailsProjectResolutionError as exc:

            logger.info(
                "BANK_DETAILS_PROJECT_NAME_REQUIRED",
                extra={
                    "user_id": self.user_id,
                },
            )

            result.messages.append(str(exc))

            result.generation_context = {
                "service": "bank_details",
                "project_required": True,
                "accounts_found": False,
                "account_count": 0,
            }

            return result

        except BankDetailsAPIError:

            logger.exception(
                "BANK_DETAILS_FAILED"
            )

            result.messages.append(
                "Bank details are temporarily unavailable. "
                "Please try again."
            )

            return result
