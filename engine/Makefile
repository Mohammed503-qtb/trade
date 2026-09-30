# ══════════════════════════════════════════════════════════════════
# AI Market Reasoning Engine — Makefile (build_plan §D)
# القاعدة الذهبية: كل مهمة لها أمر تحقق ميكانيكي.
# ══════════════════════════════════════════════════════════════════
SHELL := /bin/bash
UV    := uv
ENGINE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.DEFAULT_GOAL := help
.PHONY: help doctor gate lint format typecheck imports test schemas \
	infra-provision infra-up infra-down infra-status infra-health \
	migrate migrate-down verify-phase1 verify-phase2 verify-phase3 verify-phase4 verify-phase5 verify-phase6 ablation-dryrun db-test clean

help: ## عرض الأوامر المتاحة
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─────────────────────────── الفحص والتشخيص ───────────────────────────

doctor: ## فحص البيئة: بايثون، uv، التبعيات، الثنائيات، الإعدادات
	@bash $(ENGINE_DIR)/scripts/doctor.sh

sync: ## تثبيت/مزامنة كل تبعيات workspace
	$(UV) sync --all-packages

# ─────────────────────────── بوابة الجودة ───────────────────────────

gate: lint typecheck imports test ## البوابة الكاملة: ruff + mypy strict + import-linter + pytest

lint: ## ruff فحص + تنسيق
	$(UV) run --no-sync ruff format --check .
	$(UV) run --no-sync ruff check .

format: ## ruff تنسيق تلقائي
	$(UV) run --no-sync ruff format .
	$(UV) run --no-sync ruff check --fix .

typecheck: ## mypy strict
	$(UV) run --no-sync mypy

imports: ## عقود حدود الطبقات (import-linter)
	$(UV) run --no-sync lint-imports

test: ## pytest (unit + property)
	$(UV) run --no-sync pytest

test-integration: ## pytest مع علامة integration (تتطلب بنية حية)
	$(UV) run --no-sync pytest -m integration

# ─────────────────────────── المخططات ───────────────────────────

schemas: ## إعادة توليد JSON Schema + التحقق من عدم انحرافها (idempotent)
	$(UV) run --no-sync python -m schemas.export check

schemas-write: ## إعادة توليد JSON Schema (كتابة الفعلية عند تغير النماذج)
	$(UV) run --no-sync python -m schemas.export write

# ─────────────────────────── البنية التحتية المحلية ───────────────────────────

infra-provision: ## تنزيل ثنائيات nats/minio/postgres إلى infra/local/bin
	@bash $(ENGINE_DIR)/infra/local/provision.sh

infra-up: ## إقلاع البنية تحتية عبر supervisor (خلفية)
	$(UV) run --no-sync python infra/local/supervisor.py start

infra-down: ## إيقاف كل خدمات supervisor
	$(UV) run --no-sync python infra/local/supervisor.py shutdown

infra-status: ## حالة كل الخدمات
	$(UV) run --no-sync python infra/local/supervisor.py status

infra-health: ## فحوص الصحة (PG/NATS/MinIO/worker/api)
	$(UV) run --no-sync python infra/local/supervisor.py health

# ─────────────────────────── الهجرات ───────────────────────────

migrate: ## alembic upgrade head
	$(UV) run --no-sync alembic upgrade head

migrate-down: ## alembic downgrade -1
	$(UV) run --no-sync alembic downgrade -1

# ─────────────────────────── بوابات المراحل ───────────────────────────

verify-phase1: ## بوابة المرحلة 1: حتمية الإعادة + الذهبية + الخلود (يتطلب بنية حية)
	$(UV) run --no-sync python scripts/verify_phase1.py

verify-phase2: ## بوابة المرحلة 2: حتمية السياق + عتبات تطبيعية + بث وتخزين حي (يتطلب بنية حية)
	$(UV) run --no-sync python scripts/verify_phase2.py

verify-phase3: ## بوابة المرحلة 3: كواشف SMC حتمية + لا-نظرة-مستقبلية + تحجيم + بث وتخزين حي (يتطلب بنية حية)
	$(UV) run --no-sync python scripts/verify_phase3.py

verify-phase4: ## بوابة المرحلة 4: فوتبرنت حتمي + مطابقة إحصائية ضد مرجع البورصة + كواشف تدفق + بث وتخزين حي (يتطلب بنية حية)
	$(UV) run --no-sync python scripts/verify_phase4.py

verify-phase5: ## بوابة المرحلة 5a: الأنماط + الاستئصال §46-5 — مقيّم حقيقي وسجل ترقية وبث وتخزين حي (يتطلب بنية حية)
	$(UV) run --no-sync python scripts/verify_phase5.py

verify-phase6: ## بوابة المرحلة 6: دمج الدليل §19 — سجل ولقطات وسلسلة باستعلام واحد (يتطلب بنية حية عند 0006)
	$(UV) run --no-sync python scripts/verify_phase6.py

ablation-dryrun: ## تشغيل استئصال تجريبي على عينة المرحلة 1 (تقرير placeholder موثق)
	$(UV) run --no-sync python scripts/run_ablation.py --dataset phase1

# ─────────────────────────── تنظيف ───────────────────────────

clean: ## إزالة مخلفات الأدوات
	rm -rf .pytest_cache .mypy_cache .ruff_cache .ruff
	find . -type d -name __pycache__ -not -path "./.venv/*" -not -path "./data/*" -exec rm -rf {} + 2>/dev/null || true
