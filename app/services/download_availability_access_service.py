from app.core.config import get_settings
from app.services.walkthrough_access_service import (
    WalkthroughEngine,
)


DOWNLOAD_AVAILABILITY_FEATURE = (
    "Project Details Page – Download Availability"
)


class DownloadAvailabilityAccessService:

    def __init__(self, engine: WalkthroughEngine):
        self.engine = engine

    def check(
        self,
        *,
        role: str,
        source: str,
        employee_type: str,
    ) -> tuple[bool, str]:

        settings = get_settings()

        if not settings.download_availability_rbac_enabled:
            return True, "feature_rbac_disabled"

        return self.engine.permission(
            name=DOWNLOAD_AVAILABILITY_FEATURE,
            role=role,
            source=source,
            employee_type=employee_type,
        )