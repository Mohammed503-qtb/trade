#!/usr/bin/env python
"""validate-compose.py — تحقق بنيوي لمواصفة النشر (infra/docker-compose.yml).

الـsandbox لا يملك Docker (قرار D-01: تشغيل مزدوج — sandbox بـsupervisor
والهدف بـCompose)، لذا تُختبر مواصفة الخادم الهدف بنيويًا هنا فقط:
تفكيك YAML + فحوص آلية على الخدمات وشروطها وحدود النشر.
البناء الفعلي يحدث على الخادم الهدف لاحقًا.

تشغيل (من جذر engine/):
    unset VIRTUAL_ENV && uv run --no-sync python scripts/validate-compose.py

خروج: 0 = نجاح كامل · 1 = فشل أي فحص (مع رسالة عربية واضحة).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ENGINE_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_REL = Path("infra") / "docker-compose.yml"
COMPOSE_PATH = ENGINE_ROOT / COMPOSE_REL
ENV_FILE_REL = "../.env"  # نسبةً إلى ملف compose ⇒ engine/.env

# الخدمات الثماني المطلوبة في المواصفة (السبع التشغيلية + engine-replay ذات الـprofile)
EXPECTED_SERVICES = (
    "postgres",
    "nats",
    "minio",
    "storage-init",
    "migrate",
    "engine-worker",
    "engine-api",
    "engine-replay",
)
# خدمات المحرك التي تعلن env_file الاختياري ../.env
ENGINE_SERVICES = ("migrate", "engine-worker", "engine-api", "engine-replay")
# شروط الاعتماد الإلزامية لعمليات المحرك العاملة (worker/api/replay)
HARD_DEPS = {
    "postgres": "service_healthy",
    "nats": "service_healthy",
    "minio": "service_healthy",
    "migrate": "service_completed_successfully",
}
EXPECTED_API_PORTS = ["127.0.0.1:4001:4001"]


def _tokens(value: Any) -> list[str]:
    """توحيد أمر/فحص (قائمة أو سلسلة) إلى قائمة كلمات."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.split()
    return []


def _svc(doc: dict[str, Any], name: str) -> dict[str, Any]:
    service = (doc.get("services") or {}).get(name)
    return service if isinstance(service, dict) else {}


def _env_map(service: dict[str, Any]) -> dict[str, str]:
    environment = service.get("environment") or {}
    if isinstance(environment, dict):
        return {str(key): str(value) for key, value in environment.items()}
    return {}


def _depends(service: dict[str, Any]) -> dict[str, str]:
    """شروط depends_on كخريطة {خدمة: شرط} — الشرط فارغ إن كانت بصيغة مبسطة."""
    depends = service.get("depends_on")
    if isinstance(depends, dict):
        conditions: dict[str, str] = {}
        for target, spec in depends.items():
            if isinstance(spec, dict):
                conditions[str(target)] = str(spec.get("condition", ""))
            else:
                conditions[str(target)] = str(spec)
        return conditions
    if isinstance(depends, list):
        return {str(target): "" for target in depends}
    return {}


def _env_file_entries(service: dict[str, Any]) -> list[tuple[str, bool]]:
    """إدخالات env_file كقائمة (مسار، هل هو إلزامي؟)."""
    raw = service.get("env_file")
    if isinstance(raw, str):
        return [(raw, True)]
    if not isinstance(raw, list):
        return []
    entries: list[tuple[str, bool]] = []
    for item in raw:
        if isinstance(item, dict):
            entries.append((str(item.get("path", "")), bool(item.get("required", True))))
        else:
            entries.append((str(item), True))
    return entries


# ── الفحوص — كل دالة تستقبل المستند وتعيد (نجح؟، تفاصيل) ──────────────────────


def check_structure(doc: dict[str, Any]) -> tuple[bool, str]:
    services = doc.get("services")
    volumes = doc.get("volumes")
    networks = doc.get("networks")
    ok = (
        isinstance(services, dict)
        and bool(services)
        and isinstance(volumes, dict)
        and bool(volumes)
        and isinstance(networks, dict)
        and bool(networks)
    )
    detail = (
        f"services={len(services or {})} · volumes={len(volumes or {})} · "
        f"networks={len(networks or {})}"
    )
    return ok, detail


def check_services(doc: dict[str, Any]) -> tuple[bool, str]:
    services = doc.get("services") or {}
    missing = [name for name in EXPECTED_SERVICES if name not in services]
    ok = not missing
    if ok:
        detail = f"المطلوبة {len(EXPECTED_SERVICES)}/{len(EXPECTED_SERVICES)} مكتملة"
    else:
        detail = "ناقصة: " + "، ".join(missing)
    return ok, detail


def check_infra_health(doc: dict[str, Any]) -> tuple[bool, str]:
    lacking: list[str] = []
    for name in ("postgres", "nats", "minio"):
        healthcheck = _svc(doc, name).get("healthcheck")
        if not (isinstance(healthcheck, dict) and healthcheck.get("test")):
            lacking.append(name)
    ok = not lacking
    if ok:
        detail = "healthcheck.test معرّف للثلاثة (pg_isready · /healthz · mc ready)"
    else:
        detail = "بلا فحص صحة: " + "، ".join(lacking)
    return ok, detail


def check_loopback_only(doc: dict[str, Any]) -> tuple[bool, str]:
    services = doc.get("services") or {}
    publishers = sorted(
        name
        for name, service in services.items()
        if isinstance(service, dict) and service.get("ports")
    )
    api_ports = _svc(doc, "engine-api").get("ports")
    offenders = [name for name in publishers if name != "engine-api"]
    ok = not offenders and api_ports == EXPECTED_API_PORTS
    if offenders:
        detail = "خدمات تنشر خارجيًا خلافًا للمبدأ: " + "، ".join(offenders)
    elif api_ports != EXPECTED_API_PORTS:
        detail = f"نشر engine-api غير مطابق: {api_ports!r} (المطلوب {EXPECTED_API_PORTS!r})"
    else:
        detail = "النشر الخارجي الوحيد: engine-api → 127.0.0.1:4001:4001 (loopback)"
    return ok, detail


def check_worker_deps(doc: dict[str, Any]) -> tuple[bool, str]:
    deps = _depends(_svc(doc, "engine-worker"))
    broken = {
        target: condition
        for target, condition in HARD_DEPS.items()
        if deps.get(target) != condition
    }
    if not broken:
        return True, "worker → postgres+nats+minio healthy · migrate completed"
    detail = "شروط مفقودة/خاطئة: " + "، ".join(
        f"{target}={deps.get(target, 'غائب')!r} (المطلوب {condition})"
        for target, condition in broken.items()
    )
    return False, detail


def check_api_deps(doc: dict[str, Any]) -> tuple[bool, str]:
    deps = _depends(_svc(doc, "engine-api"))
    broken = {
        target: condition
        for target, condition in HARD_DEPS.items()
        if deps.get(target) != condition
    }
    if not broken:
        return True, "نفس شروط worker (depends_on مماثلة)"
    detail = "شروط مفقودة/خاطئة: " + "، ".join(
        f"{target}={deps.get(target, 'غائب')!r}" for target in broken
    )
    return False, detail


def check_jetstream(doc: dict[str, Any]) -> tuple[bool, str]:
    tokens = _tokens(_svc(doc, "nats").get("command"))
    ok = "-js" in tokens
    detail = "أمر nats: " + (" ".join(tokens) if tokens else "غائب")
    return ok, detail


def check_named_volumes(doc: dict[str, Any]) -> tuple[bool, str]:
    top_volumes = doc.get("volumes") or {}
    bad: list[str] = []
    used: set[str] = set()
    for name, service in (doc.get("services") or {}).items():
        if not isinstance(service, dict):
            continue
        for ref in service.get("volumes") or []:
            if isinstance(ref, dict):
                volume = ref.get("volume") or {}
                target = str(volume.get("name") or ref.get("source") or "")
                if ref.get("type") != "volume" or target not in top_volumes:
                    bad.append(f"{name}: إدخال غير مسمى")
                else:
                    used.add(target)
            else:
                target = str(ref).split(":")[0]
                if target.startswith(("/", "./", "~")) or target not in top_volumes:
                    bad.append(f"{name}: {ref}")
                else:
                    used.add(target)
    if not bad:
        return True, "المراجع كلها مسماة ومعرّفة أعلى الملف: " + "، ".join(sorted(used))
    return False, "مراجع غير مسماة/خارجية: " + "؛ ".join(bad)


def check_replay_profile(doc: dict[str, Any]) -> tuple[bool, str]:
    profiles = _svc(doc, "engine-replay").get("profiles")
    profile_list = profiles if isinstance(profiles, list) else []
    ok = "replay" in [str(item) for item in profile_list]
    detail = f"profiles={profile_list!r} — لا يقلع مع up الافتراضي"
    return ok, detail


def check_env_file(doc: dict[str, Any]) -> tuple[bool, str]:
    declarers = 0
    all_optional = True
    for name in ENGINE_SERVICES:
        entries = _env_file_entries(_svc(doc, name))
        if any(path == ENV_FILE_REL for path, _ in entries):
            declarers += 1
        if any(path == ENV_FILE_REL and required for path, required in entries):
            all_optional = False
    resolved = (COMPOSE_PATH.parent / ENV_FILE_REL).resolve()
    parent_exists = resolved.parent.is_dir()
    exists_now = "موجود" if resolved.is_file() else "غير موجود بعد (الافتراضيات تسد)"
    ok = declarers == len(ENGINE_SERVICES) and all_optional and parent_exists
    detail = (
        f"{declarers}/{len(ENGINE_SERVICES)} خدمات engine تعلن {ENV_FILE_REL} "
        f"بـrequired:false — الملف حاليًا: {exists_now}"
    )
    return ok, detail


def check_db_url_hosts(doc: dict[str, Any]) -> tuple[bool, str]:
    bad: list[str] = []
    for name in ("engine-worker", "engine-api", "migrate", "engine-replay"):
        url = _env_map(_svc(doc, name)).get("ENGINE_DATABASE_URL", "")
        if "@postgres:" not in url or "localhost" in url or "127.0.0.1" in url:
            bad.append(name)
    if not bad:
        return True, "ENGINE_DATABASE_URL يشير إلى خدمة postgres (لا localhost) في الجميع"
    return False, "روابط لا تشير لاسم الخدمة postgres: " + "، ".join(bad)


def check_pg_memory(doc: dict[str, Any]) -> tuple[bool, str]:
    tokens = _tokens(_svc(doc, "postgres").get("command"))
    ok = "shared_buffers=128MB" in tokens and "max_connections=25" in tokens
    detail = "أمر postgres: " + (" ".join(tokens) if tokens else "غائب")
    return ok, detail


def check_one_shots(doc: dict[str, Any]) -> tuple[bool, str]:
    migrate = _svc(doc, "migrate")
    storage = _svc(doc, "storage-init")
    ok = (
        migrate.get("restart") == "no"
        and storage.get("restart") == "no"
        and _depends(migrate).get("postgres") == "service_healthy"
        and _depends(storage).get("minio") == "service_healthy"
    )
    if ok:
        detail = "migrate/storage-init: restart=no · تنتظران صحة الاعتماد ثم تخرجان"
    else:
        detail = (
            f"migrate.restart={migrate.get('restart')!r} · "
            f"storage-init.restart={storage.get('restart')!r} · شروط الاعتماد ناقصة"
        )
    return ok, detail


def check_api_health(doc: dict[str, Any]) -> tuple[bool, str]:
    healthcheck = _svc(doc, "engine-api").get("healthcheck")
    test = healthcheck.get("test") if isinstance(healthcheck, dict) else None
    joined = " ".join(_tokens(test))
    ok = ("healthcheck.py" in joined) or ("healthz" in joined)
    if ok:
        return True, "فحص /healthz عبر healthcheck.py (stdlib — الصورة بلا curl/wget)"
    return False, f"فحص صحة engine-api غائب أو لا يضرب /healthz: {test!r}"


def check_worker_restart(doc: dict[str, Any]) -> tuple[bool, str]:
    restart = _svc(doc, "engine-worker").get("restart")
    ok = restart == "unless-stopped"
    return ok, f"engine-worker.restart={restart!r} (المطلوب unless-stopped)"


def check_network(doc: dict[str, Any]) -> tuple[bool, str]:
    engine_net = (doc.get("networks") or {}).get("engine-internal")
    ok_definition = isinstance(engine_net, dict) and engine_net.get("driver") == "bridge"
    unattached = [
        name
        for name, service in (doc.get("services") or {}).items()
        if isinstance(service, dict) and "engine-internal" not in (service.get("networks") or [])
    ]
    if ok_definition and not unattached:
        return True, "engine-internal (bridge) — كل الخدمات متصلة بها"
    problems: list[str] = []
    if not ok_definition:
        problems.append("تعريف engine-internal ناقص/ليس bridge")
    if unattached:
        problems.append("خارج الشبكة: " + "، ".join(unattached))
    return False, "؛ ".join(problems)


# ── التنفيذ والإخراج ───────────────────────────────────────────────────────────

CHECKS = (
    ("بنية YAML والأقسام الأساسية", check_structure),
    ("اكتمال الخدمات بأسمائها", check_services),
    ("فحوص صحة البنية التحتية", check_infra_health),
    ("النشر الخارجي loopback فقط", check_loopback_only),
    ("شروط اعتماد engine-worker", check_worker_deps),
    ("شروط اعتماد engine-api", check_api_deps),
    ("تفعيل JetStream في أمر nats", check_jetstream),
    ("volumes مسماة ومعرّفة", check_named_volumes),
    ("profile مستقل لـengine-replay", check_replay_profile),
    ("env_file اختياري ../.env", check_env_file),
    ("قاعدة البيانات باسم الخدمة", check_db_url_hosts),
    ("إعدادات postgres المحافظة", check_pg_memory),
    ("دلالات one-shot (migrate/storage-init)", check_one_shots),
    ("فحص صحة engine-api", check_api_health),
    ("استمرارية engine-worker", check_worker_restart),
    ("شبكة engine-internal للجميع", check_network),
)

WIDTH = 76


def _print_results(results: list[tuple[str, bool, str]]) -> None:
    print("─" * WIDTH)
    print(f"التحقق البنيوي لمواصفة الخادم الهدف — {COMPOSE_REL} (قرار D-01)")
    print("وضع sandbox بلا Docker: هذا فحص بنيوي فقط — البناء الفعلي على الخادم الهدف")
    print("─" * WIDTH)
    for index, (name, ok, detail) in enumerate(results, start=1):
        mark = "✓" if ok else "✗"
        print(f"  {mark} {index:02d} · {name}")
        print(f"      {detail}")
    print("─" * WIDTH)


def _print_summary_table(total: int) -> None:
    row = "├─────────────────────┼──────────────────────────────────────────────────┤"
    print()
    print(f"جدول الملخص — نجاح {total}/{total} فحصًا: المواصفة قانونية بنيويًا")
    print("┌─────────────────────┬──────────────────────────────────────────────────┐")
    print("│ البند               │ القيمة                                            │")
    print(row)
    print("│ الخدمات — تحتية     │ postgres · nats · minio · storage-init · migrate  │")
    print("│ الخدمات — محرك      │ engine-worker · engine-api · engine-replay        │")
    print("│ النشر الخارجي       │ engine-api فقط → 127.0.0.1:4001:4001 (loopback)   │")
    print("│ المنافذ الداخلية    │ PG 5543 · NATS 4222/8222 · MinIO 9100/9101        │")
    print("│ one-shot            │ migrate (alembic) · storage-init (حزمة engine-raw) │")
    print("│ engine-replay       │ profile=replay — لا يقلع مع up الافتراضي          │")
    print("│ الشبكة              │ engine-internal (bridge مسمى) — الجميع متصل        │")
    print("│ volumes مسماة (3)   │ postgres-data · nats-data · minio-data            │")
    print("│ البيئة              │ env_file ../.env اختياري + افتراضيات لكل المتغيرات │")
    print("└─────────────────────┴──────────────────────────────────────────────────┘")
    print()
    print("التشغيل القانوني على الخادم الهدف (من جذر engine/):")
    print("    docker compose -f infra/docker-compose.yml --env-file .env up -d")


def main() -> int:
    try:
        doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"✗ المواصفة غير موجودة: {COMPOSE_REL}")
        return 1
    except yaml.YAMLError as exc:
        print(f"✗ فشل تفكيك YAML في {COMPOSE_REL} — الصياغة غير سالمة:")
        print(f"  {exc}")
        return 1
    if not isinstance(doc, dict) or not isinstance(doc.get("services"), dict):
        print("✗ جذر المواصفة أو قسم services ليس خريطة (mapping) صالحة")
        return 1

    results: list[tuple[str, bool, str]] = []
    for name, check in CHECKS:
        try:
            ok, detail = check(doc)
        except Exception as exc:  # فحص متعثر = فشل بنيوي موثق، لا انهيار
            ok, detail = False, f"تعثر الفحص: {type(exc).__name__}: {exc}"
        results.append((name, ok, detail))

    _print_results(results)
    failed = [name for name, ok, _ in results if not ok]
    if failed:
        print(f"فشل {len(failed)}/{len(results)} فحصًا — المواصفة غير قانونية بعد:")
        for name in failed:
            print(f"  ✗ {name}")
        return 1

    _print_summary_table(len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
