from app.domain.contracts.readiness_check_contract import ReadinessCheckContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.enums.readiness_status import ReadinessStatus
from app.domain.errors.domain_errors import ServiceUnavailableError


class CheckReadinessParams(InputData):
    pass


class DependencyStatus(InputData):
    name: str
    status: ReadinessStatus


class CheckReadinessResponse(InputData):
    status: ReadinessStatus
    dependencies: list[DependencyStatus]


class CheckReadinessUsecase(Usecase[CheckReadinessParams, CheckReadinessResponse]):
    def __init__(self, checks: list[ReadinessCheckContract]):
        self.checks = checks

    def execute(self, params: CheckReadinessParams) -> CheckReadinessResponse:
        dependencies = [
            DependencyStatus(
                name=check.name,
                status=ReadinessStatus.READY if check.is_ready() else ReadinessStatus.NOT_READY,
            )
            for check in self.checks
        ]
        failed = [item.name for item in dependencies if item.status == ReadinessStatus.NOT_READY]
        if failed:
            raise ServiceUnavailableError(f"Dependencies not ready: {', '.join(failed)}")
        return CheckReadinessResponse(status=ReadinessStatus.READY, dependencies=dependencies)
