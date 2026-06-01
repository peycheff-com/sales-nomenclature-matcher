from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _exists(relative_path: str) -> Check:
    path = ROOT / relative_path
    return Check(relative_path, path.exists(), "present" if path.exists() else "missing")


def _contains(relative_path: str, expected: list[str]) -> Check:
    path = ROOT / relative_path
    if not path.exists():
        return Check(relative_path, False, "missing")
    text = _read(path)
    missing = [item for item in expected if item not in text]
    return Check(
        relative_path,
        not missing,
        "contains required text" if not missing else f"missing: {', '.join(missing)}",
    )


def check_required_files() -> list[Check]:
    return [
        _exists("LICENSE"),
        _exists("README.md"),
        _exists("CONTRIBUTING.md"),
        _exists("SECURITY.md"),
        _exists("CODE_OF_CONDUCT.md"),
        _exists(".env.production.example"),
        _exists("docker-compose.prod.yml"),
        _exists("docs/open-source.md"),
        _exists("docs/testing.md"),
        _exists("docs/production-checklist.md"),
        _exists("docs/backup-restore-drill.md"),
        _exists("docs/deploy_runbook.md"),
        _exists("docs/openapi_v1.yaml"),
    ]


def check_bilingual_docs() -> list[Check]:
    docs = [
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "docs/open-source.md",
        "docs/testing.md",
        "docs/production-checklist.md",
        "docs/backup-restore-drill.md",
        "docs/deploy_runbook.md",
        "docs/provider_matrix.md",
        "docs/quality_gates.md",
        "docs/release.md",
        "docs/scoring_v1.md",
        "docs/ssl-architecture.md",
    ]
    return [
        _contains(relative_path, ["English", "Русский"])
        for relative_path in docs
    ]


def check_restore_drill_docs() -> list[Check]:
    return [
        _contains(
            "docs/backup-restore-drill.md",
            [
                "pg_dump",
                "matcher-restore-drill",
                "catalog_products count",
                "match_requests count",
                "operations log",
            ],
        )
    ]


def check_free_local_defaults() -> list[Check]:
    env = ROOT / ".env.production.example"
    if not env.exists():
        return [Check(".env.production.example", False, "missing")]
    text = _read(env)
    expected = [
        "EMBEDDING_PROVIDER=local",
        "LLM_PROVIDER=local",
        "RERANK_PROVIDER=local",
        "EMBEDDING_DIMENSIONS=384",
    ]
    missing = [item for item in expected if item not in text]
    return [
        Check(
            ".env.production.example local defaults",
            not missing,
            "free local defaults configured" if not missing else f"missing: {', '.join(missing)}",
        )
    ]


def check_prod_compose() -> list[Check]:
    compose_path = ROOT / "docker-compose.prod.yml"
    if not compose_path.exists():
        return [Check("docker-compose.prod.yml", False, "missing")]

    data = yaml.safe_load(_read(compose_path))
    services = data.get("services", {})
    required_services = {
        "nginx",
        "api",
        "worker-match",
        "worker-catalog",
        "db",
        "redis",
        "backup",
        "alerter",
    }
    missing_services = sorted(required_services - set(services))
    checks = [
        Check(
            "production services",
            not missing_services,
            "all required services present"
            if not missing_services
            else f"missing: {', '.join(missing_services)}",
        )
    ]

    for name in sorted(required_services & set(services)):
        service = services[name]
        checks.append(
            Check(
                f"{name} restart policy",
                service.get("restart") == "unless-stopped",
                "restart=unless-stopped"
                if service.get("restart") == "unless-stopped"
                else "missing restart=unless-stopped",
            )
        )

    for name in ["nginx", "api", "worker-match", "worker-catalog", "db", "redis"]:
        service = services.get(name, {})
        checks.append(
            Check(
                f"{name} healthcheck",
                "healthcheck" in service,
                "healthcheck present" if "healthcheck" in service else "healthcheck missing",
            )
        )

    return checks


def run_checks() -> list[Check]:
    return [
        *check_required_files(),
        *check_bilingual_docs(),
        *check_restore_drill_docs(),
        *check_free_local_defaults(),
        *check_prod_compose(),
    ]


def main() -> int:
    checks = run_checks()
    failures = [check for check in checks if not check.ok]
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"{status}: {check.name} - {check.detail}")
    if failures:
        print(f"\n{len(failures)} production-readiness check(s) failed.")
        return 1
    print("\nAll production-readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
