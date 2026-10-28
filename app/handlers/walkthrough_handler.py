
import logging

from app.schemas.handler_result import HandlerResult
from app.services.walkthrough_access_service import WalkthroughEngine


logger = logging.getLogger(__name__)


class WalkthroughHandler:
    """
    Handles Excel-based Danube One feature walkthroughs.

    Uses deterministic RBAC permission checks.
    Does not use an LLM to generate walkthrough steps.
    """

    def __init__(
        self,
        engine: WalkthroughEngine,
        role: str,
        source: str,
        employee_type: str,
    ):
        self.engine = engine
        self.role = role
        self.source = source
        self.employee_type = employee_type

    async def handle(self, intent) -> HandlerResult:

        feature_name = getattr(intent, "feature_name", None)

        if not feature_name:
            return HandlerResult(
                intent="excel_walkthrough",
                messages=[
                    "Which Danube One feature would you like help with?"
                ],
            )

        result = self.engine.lookup(
            feature=feature_name,
            role=self.role,
            source=self.source,
            employee_type=self.employee_type,
        )

        if result["status"] != "ok":
            logger.info(
                "WALKTHROUGH_ACCESS_DENIED | "
                "feature=%s | reason=%s",
                feature_name,
                result.get("reason"),
            )

            return HandlerResult(
                intent="excel_walkthrough",
                messages=[
                    "This feature walkthrough is not available "
                    "for your account."
                ],
            )

        logger.info(
            "WALKTHROUGH_ACCESS_GRANTED | feature=%s",
            feature_name,
        )

        approved_steps = result["steps"]

        allowed_followup_features = []
        for guide in self.engine.guides.values():

            if guide.name == result["feature"]:
                continue

            allowed, _ = self.engine.permission(
                name=guide.name,
                role=self.role,
                source=self.source,
                employee_type=self.employee_type,
            )

            if allowed:
                allowed_followup_features.append(guide.name)

        return HandlerResult(
            intent="excel_walkthrough",
            generation_context={
                "service": "excel_walkthrough",
                "feature_name": result["feature"],
                "approved_steps": approved_steps,
                "allowed_followup_features": allowed_followup_features,
                "match_status": "exact",
            },
            messages=[],
            has_data=True,
        )