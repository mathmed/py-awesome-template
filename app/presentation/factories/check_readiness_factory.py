from app.domain.contracts.readiness_check_contract import ReadinessCheckContract
from app.domain.usecases.health.check_readiness_usecase import CheckReadinessUsecase


def check_readiness_factory() -> CheckReadinessUsecase:
    # Register one check per real dependency (database, cache, broker...) implemented in app/infra/,
    # e.g. checks = [PostgresReadinessCheck(get_settings().database_url)]
    checks: list[ReadinessCheckContract] = []
    return CheckReadinessUsecase(checks=checks)
