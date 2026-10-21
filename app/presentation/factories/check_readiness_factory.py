from app.domain.contracts.readiness_check_contract import ReadinessCheckContract
from app.domain.usecases.health.check_readiness_usecase import CheckReadinessUsecase


def check_readiness_factory() -> CheckReadinessUsecase:
    checks: list[ReadinessCheckContract] = []
    return CheckReadinessUsecase(checks=checks)
