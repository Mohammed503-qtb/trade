#!/usr/bin/env python3
"""supervisor — مدير عمليات البنية التحتية المحلي (build_plan A.2، قرار D-01).

يدير إقلاعًا متدرجًا: postgres → nats → seaweedfs → migrate → worker،
مع إعادة تشغيل مؤجلرة عند الفشل، وفحوص صحة حقيقية، وسجلات لكل خدمة.

الأوامر:
    run              التشغيل الأمامي (يستخدمه غلاف mini-service)
    start            تشغيل خفي (double-fork — النمط الوحيد الذي ينجو في sandbox)
    stop / shutdown  إيقاف نظيف بترتيب عكسي
    restart <svc>    إعادة تشغيل خدمة واحدة
    status           جدول الحالة
    health           فحوص صحة نشطة (exit 0 = البنية الحرجة سليمة)

قرار ADR-007: engine-api ليس تحت إدارة هذا المدير — يعمل غلافه الخاص
(mini-services/engine-api) لضمان استقلالية إعادة التشغيل.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import yaml

ENGINE_ROOT = Path(__file__).resolve().parents[2]
LOCAL_DIR = ENGINE_ROOT / "infra" / "local"
BIN_DIR = LOCAL_DIR / "bin"
DATA_DIR = ENGINE_ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"
RUN_DIR = DATA_DIR / "run"
SERVICES_YAML = LOCAL_DIR / "services.yaml"
PID_FILE = RUN_DIR / "supervisor.pid"
STATE_FILE = RUN_DIR / "supervisor-state.json"
LOCK_FILE = RUN_DIR / "supervisor.lock"

# سياسة إعادة التشغيل (§49: الفشل يُعالج بأمان لا بتجاهل)
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0
BACKOFF_RESET_AFTER_S = 300.0
MAX_CONSECUTIVE_FAILURES = 5
FAILURE_WINDOW_S = 180.0
HEALTH_TIMEOUT_S = 30.0
TERM_WAIT_S = 5.0

# علم إيقاف عام (يُضبط من معالج الإشارات)
shutting_down = False


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log(msg: str, *, error: bool = False) -> None:
    line = f"{_now()} [{'E' if error else 'I'}] {msg}"
    print(line, file=sys.stderr if error else sys.stdout, flush=True)
    # سجل موحد عندما نعمل خفيين (stdout قد يكون مغلقاً بعد الانفصال)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with (LOGS_DIR / "supervisor.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ─────────────────────────── الإعدادات والسياق ───────────────────────────


def load_env_context() -> dict[str, str]:
    """دمج .env (إن وُجد) فوق بيئة العملية — قيم .env لا تطغى على البيئة."""
    merged = dict(os.environ)
    env_file = ENGINE_ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            merged.setdefault(key, value)
    # الافتراضيات الحاسمة (تتطابق مع .env.example)
    defaults = {
        "POSTGRES_PORT": "5543",
        "POSTGRES_USER": "engine",
        "POSTGRES_PASSWORD": "engine",
        "POSTGRES_DB": "engine",
        "S3_BUCKET": "engine-raw",
        "S3_ACCESS_KEY": "engine",
        "S3_SECRET_KEY": "engine-secret",
    }
    for key, value in defaults.items():
        merged.setdefault(key, value)
    return merged


def build_substitution_context(env: dict[str, str]) -> dict[str, Any]:
    return {
        "engine": str(ENGINE_ROOT),
        "bin": str(BIN_DIR),
        "data": str(DATA_DIR),
        "run": str(RUN_DIR),
        "logs": str(LOGS_DIR),
        "python": sys.executable,
        "env": env,
    }


def substitute(value: Any, ctx: dict[str, Any]) -> Any:
    """استبدال العناصر {engine} و{env.NAME} في السلاسل والقوائم والقواميس."""
    if isinstance(value, str):
        return value.format(**ctx)
    if isinstance(value, list):
        return [substitute(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, ctx) for k, v in value.items()}
    return value


# ─────────────────────────── تعريف الخدمة ───────────────────────────


@dataclass
class ServiceSpec:
    name: str
    kind: str  # process | oneshot
    priority: int
    cmd: list[str]
    health: dict[str, Any]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    depends: list[str] = field(default_factory=list)
    critical: bool = False
    first_run: str | None = None
    post_healthy: str | None = None
    skip_if_missing: str | None = None


def load_services(env: dict[str, str]) -> list[ServiceSpec]:
    raw = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    ctx = build_substitution_context(env)
    specs: list[ServiceSpec] = []
    for name, cfg in raw["services"].items():
        specs.append(
            ServiceSpec(
                name=name,
                kind=cfg["kind"],
                priority=int(cfg["priority"]),
                cmd=substitute(cfg["cmd"], ctx),
                health=substitute(cfg.get("health", {"type": "process"}), ctx),
                cwd=Path(substitute(cfg.get("cwd", "{engine}"), ctx)),
                env=substitute(cfg.get("env", {}), ctx),
                depends=list(cfg.get("depends", [])),
                critical=bool(cfg.get("critical", False)),
                first_run=cfg.get("first_run"),
                post_healthy=cfg.get("post_healthy"),
                skip_if_missing=cfg.get("skip_if_missing"),
            )
        )
    specs.sort(key=lambda s: s.priority)
    return specs


# ─────────────────────────── حالة العملية ───────────────────────────


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


class ServiceState:
    def __init__(self, spec: ServiceSpec) -> None:
        self.spec = spec
        self.proc: subprocess.Popen[bytes] | None = None
        self.restarts = 0
        self.consecutive_failures = 0
        self.first_failure_at: float | None = None
        self.started_at: float | None = None
        self.exit_code: int | None = None
        self.state = "STOPPED"  # STOPPED|STARTING|RUNNING|HEALTHY|FAILED|EXITED_OK|SKIPPED
        self.next_restart_at: float | None = None
        self.backoff_s = BACKOFF_BASE_S

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "state": self.state,
            "pid": self.pid,
            "alive": self.alive,
            "restarts": self.restarts,
            "exit_code": self.exit_code,
            "critical": self.spec.critical,
            "kind": self.spec.kind,
        }


# ─────────────────────────── فحوص الصحة ───────────────────────────


def probe_health(spec: ServiceSpec, env: dict[str, str] | None = None) -> tuple[bool, str]:
    env = env or dict(os.environ)
    h = spec.health
    htype = h.get("type", "process")
    if htype == "http":
        try:
            with urlopen(h["url"], timeout=5) as resp:  # noqa: S310 — داخلي موثوق
                code = resp.status
            return (code == int(h.get("expect", 200)), f"http {code}")
        except Exception as exc:
            return (False, f"http err: {type(exc).__name__}")
    if htype == "tcp":
        try:
            with socket.create_connection((h["host"], int(h["port"])), timeout=3):
                return (True, "tcp ok")
        except OSError as exc:
            return (False, f"tcp err: {exc.__class__.__name__}")
    if htype == "pg_sql":
        # توزيعة Zonky بلا pg_isready — الفحص عبر asyncpg (أصدق: يثبت مسار الاستعلام)
        import asyncio

        db_name = str(h.get("database", "engine"))
        conn_kw: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": int(env.get("POSTGRES_PORT", "5543")),
            "user": env.get("POSTGRES_USER", "engine"),
            "password": env.get("POSTGRES_PASSWORD", "engine"),
        }

        async def _probe() -> None:
            import asyncpg

            conn = await asyncio.wait_for(
                asyncpg.connect(database=db_name, timeout=3, **conn_kw),
                timeout=4,
            )
            try:
                await conn.fetchval("SELECT 1")
            finally:
                await conn.close()

        async def _ensure_db() -> None:
            """تئام ذاتي: Zonky بلا createdb — أنشئ قاعدة الهدف إن غابت.

            يحل حلقة «بيضة-ودجاجة»: خطاف post_healthy لا يعمل إلا بعد نجاح
            الفحص، والفحص ذاته يحتاج القاعدة موجودة أصلًا.
            """
            import asyncpg

            conn = await asyncpg.connect(database="postgres", **conn_kw)
            try:
                exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
                if not exists:
                    await conn.execute(f'CREATE DATABASE "{db_name}"')
                    log(f"pg_sql: أُنشئت قاعدة البيانات {db_name} (تئام ذاتي)")
            finally:
                await conn.close()

        try:
            try:
                asyncio.run(_probe())
                return (True, "pg SELECT 1 ok")
            except Exception as exc:
                # InvalidCatalogNameError: القاعدة لم تُنشأ بعد — أنشئها ثم أعد المحاولة
                if type(exc).__name__ == "InvalidCatalogNameError":
                    asyncio.run(_ensure_db())
                    asyncio.run(_probe())
                    return (True, "pg SELECT 1 ok (db ensured)")
                raise
        except Exception as exc:
            return (False, f"pg err: {type(exc).__name__}")
    if htype == "exec":
        try:
            result = subprocess.run(  # noqa: S603 — أمر من services.yaml الموثوقة
                h["cmd"], capture_output=True, timeout=10, check=False
            )
            return (result.returncode == 0, f"rc={result.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return (False, f"exec err: {exc.__class__.__name__}")
    return (False, f"نوع فحص غير معروف: {htype}")


# ─────────────────────────── خطافات التهيئة الأولى ───────────────────────────


def hook_postgres_initdb(env: dict[str, str]) -> None:
    pg_data = DATA_DIR / "pg"
    if (pg_data / "PG_VERSION").exists():
        return
    log(f"postgres: تهيئة عنقود جديد في {pg_data}")
    pg_data.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pw_file = RUN_DIR / "pg-pwfile"
    pw_file.write_text(env["POSTGRES_PASSWORD"], encoding="utf-8")
    pw_file.chmod(0o600)
    try:
        subprocess.run(  # noqa: S603 — مسار ثابت من infra/local/bin
            [
                str(BIN_DIR / "pg" / "bin" / "initdb"),
                "-D",
                str(pg_data),
                "-U",
                env["POSTGRES_USER"],
                "--auth-local=trust",
                "--auth-host=scram-sha-256",
                "--pwfile",
                str(pw_file),
                "-E",
                "UTF8",
                "--locale=C",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        pw_file.unlink(missing_ok=True)


def hook_postgres_ensure_db(env: dict[str, str]) -> None:
    """إنشاء قاعدة البيانات إن لم تكن موجودة (asyncpg — توزيعة Zonky بلا createdb)."""
    import asyncio

    async def _ensure() -> None:
        import asyncpg

        conn = await asyncpg.connect(
            host="127.0.0.1",
            port=int(env["POSTGRES_PORT"]),
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
            database="postgres",
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname=$1", env["POSTGRES_DB"]
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{env["POSTGRES_DB"]}"')
                log(f"postgres: أُنشئت قاعدة البيانات {env['POSTGRES_DB']}")
        finally:
            await conn.close()

    asyncio.run(_ensure())


def hook_seaweedfs_s3config(env: dict[str, str]) -> None:
    """كتابة هويات S3 (قرار ADR-006: SeaweedFS بواجهة minio-py)."""
    cfg_path = DATA_DIR / "seaweed" / "s3-config.json"
    if cfg_path.exists():
        return
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "identities": [
            {
                "name": "engine-admin",
                "credentials": [
                    {
                        "accessKey": env["S3_ACCESS_KEY"],
                        "secretKey": env["S3_SECRET_KEY"],
                    }
                ],
                "actions": ["Admin", "Read", "Write", "List", "Tagging"],
                "isAdmin": True,
            }
        ]
    }
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    cfg_path.chmod(0o600)
    log(f"seaweedfs: كُتبت هوية S3 في {cfg_path}")


FIRST_RUN_HOOKS: dict[str, Any] = {
    "postgres_initdb": hook_postgres_initdb,
    "postgres_ensure_db": hook_postgres_ensure_db,
    "seaweedfs_s3config": hook_seaweedfs_s3config,
}


# ─────────────────────────── المشرف ───────────────────────────


class Supervisor:
    def __init__(self) -> None:
        self.env = load_env_context()
        self.specs = load_services(self.env)
        self.states: dict[str, ServiceState] = {s.name: ServiceState(s) for s in self.specs}
        self.should_run = True

    # ── بدء الخدمات (متدرج بالأولوية مع انتظار الصحة) ──
    def start_all(self) -> None:
        for state in self.states.values():
            spec = state.spec
            if spec.skip_if_missing and not (ENGINE_ROOT / spec.skip_if_missing).exists():
                state.state = "SKIPPED"
                log(f"{spec.name}: متخطى — {spec.skip_if_missing} غير موجود بعد")
                self.persist_state()
                continue
            if spec.first_run:
                hook = FIRST_RUN_HOOKS.get(spec.first_run)
                if hook:
                    try:
                        hook(self.env)
                    except Exception:
                        log(f"{spec.name}: فشل خطاف {spec.first_run}", error=True)
                        state.state = "FAILED"
                        self.persist_state()
                        continue
            self.spawn(state)
            if spec.kind == "process":
                self.wait_healthy(state)
                if state.state != "HEALTHY":
                    self.persist_state()
                    continue  # السجل وثّق؛ الرقابة ستعيد المحاولة
                if spec.post_healthy:
                    hook = FIRST_RUN_HOOKS.get(spec.post_healthy)
                    if hook:
                        try:
                            hook(self.env)
                        except Exception:
                            log(f"{spec.name}: فشل خطاف {spec.post_healthy}", error=True)
            else:  # oneshot — انتظر الخروج
                assert state.proc is not None
                rc = state.proc.wait()
                state.exit_code = rc
                state.state = "EXITED_OK" if rc == 0 else "FAILED"
                log(f"{spec.name}: oneshot خرج rc={rc} → {state.state}")
            # حفظ تدريجي — لا ينتظر اكتمال الإقلاع كله (status يبقى صادقًا أثناء الإقلاع)
            self.persist_state()

    def spawn(self, state: ServiceState) -> bool:
        spec = state.spec
        binary = Path(spec.cmd[0])
        if not binary.exists():
            log(
                f"{spec.name}: الثنائية غير موجودة: {binary} — شغّل make infra-provision",
                error=True,
            )
            state.state = "FAILED"
            return False
        log_path = LOGS_DIR / f"{spec.name}.log"
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("ab")
        child_env = {**self.env, **spec.env}
        try:
            state.proc = subprocess.Popen(  # noqa: S603 — أوامر موثقة من services.yaml
                spec.cmd,
                cwd=str(spec.cwd),
                env=child_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            log(f"{spec.name}: فشل الإقلاع: {exc}", error=True)
            state.state = "FAILED"
            return False
        state.started_at = time.monotonic()
        state.state = "STARTING"
        state.exit_code = None
        (RUN_DIR / f"{spec.name}.pid").write_text(str(state.proc.pid))
        log(f"{spec.name}: أُقلع pid={state.proc.pid}")
        return True

    def wait_healthy(self, state: ServiceState) -> None:
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while time.monotonic() < deadline and self.should_run:
            if not state.alive:
                log(f"{state.spec.name}: مات أثناء الإقلاع", error=True)
                state.state = "FAILED"
                return
            # صحة نوع process: البقاء نفسه هو الدليل — لا فحص خارجي مطلوب
            # (probe_health لا يعرف هذا النوع؛ هو خاصية دورة الحياة لا فحص شبكة)
            if state.spec.health.get("type", "process") == "process":
                state.state = "HEALTHY"
                state.consecutive_failures = 0
                state.first_failure_at = None
                log(f"{state.spec.name}: صحي (process alive)")
                return
            healthy, detail = probe_health(state.spec, self.env)
            if healthy:
                state.state = "HEALTHY"
                state.consecutive_failures = 0
                state.first_failure_at = None
                log(f"{state.spec.name}: صحي ({detail})")
                return
            time.sleep(0.5)
        if state.alive:
            log(f"{state.spec.name}: مهلة صحة انتهت — يعمل بلا صحة مؤكدة", error=True)
            state.state = "RUNNING"
        else:
            state.state = "FAILED"

    # ── حلقة الرقابة ──
    def monitor_loop(self) -> None:
        while self.should_run:
            for state in self.states.values():
                self.check_service(state)
            self.persist_state()
            time.sleep(1.0)

    def check_service(self, state: ServiceState) -> None:
        spec = state.spec
        if spec.kind == "oneshot" or state.state == "SKIPPED":
            return
        if state.alive:
            if state.state == "STARTING":
                # نوع process: البقاء دليل الصحة (probe_health لا يعرفه)
                if spec.health.get("type", "process") == "process":
                    state.state = "HEALTHY"
                else:
                    healthy, _ = probe_health(spec, self.env)
                    if healthy:
                        state.state = "HEALTHY"
            return
        # مات — سجل وقرر
        assert state.proc is not None
        rc = state.proc.returncode
        state.exit_code = rc
        now = time.monotonic()
        if state.first_failure_at is None:
            state.first_failure_at = now
        if now - state.first_failure_at > FAILURE_WINDOW_S:
            state.first_failure_at = now
            state.consecutive_failures = 0
        state.consecutive_failures += 1
        if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            log(
                f"{spec.name}: تخليت عن إعادة التشغيل بعد "
                f"{state.consecutive_failures} إخفاقات متتالية",
                error=True,
            )
            state.state = "FAILED"
            return
        state.restarts += 1
        wait = state.backoff_s
        state.backoff_s = min(state.backoff_s * 2, BACKOFF_MAX_S)
        # إعادة تعيين التراجع بعد استقرار كافٍ
        if state.started_at and now - state.started_at > BACKOFF_RESET_AFTER_S:
            state.backoff_s = BACKOFF_BASE_S
        log(
            f"{spec.name}: خرج rc={rc} — إعادة بعد {wait:.1f}s (محاولة {state.restarts})",
            error=True,
        )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and self.should_run:
            time.sleep(0.25)
        if not self.should_run:
            return
        self.spawn(state)
        if spec.kind == "process" and state.state == "STARTING":
            self.wait_healthy(state)

    # ── إيقاف متدرج عكسي ──
    def stop_all(self) -> None:
        log("supervisor: إيقاف نظيف بترتيب عكسي")
        for state in sorted(self.states.values(), key=lambda s: s.spec.priority, reverse=True):
            if state.spec.kind == "oneshot" or not state.alive:
                continue
            assert state.proc is not None
            try:
                os.killpg(state.proc.pid, signal.SIGTERM)
            except OSError:
                continue
        deadline = time.monotonic() + TERM_WAIT_S
        alive_states = [s for s in self.states.values() if s.alive]
        while time.monotonic() < deadline and any(s.alive for s in alive_states):
            time.sleep(0.2)
        for state in alive_states:
            if state.alive and state.proc is not None:
                with contextlib.suppress(OSError):
                    os.killpg(state.proc.pid, signal.SIGKILL)
            state.state = "STOPPED"
            log(f"{state.spec.name}: أُوقف")
        self.persist_state()

    def persist_state(self) -> None:
        try:
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            services_snapshot = [s.snapshot() for s in self.states.values()]
            STATE_FILE.write_text(
                json.dumps(
                    {"updated_at": _now(), "services": services_snapshot},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def run_forever(self) -> None:
        self.install_signal_handlers()
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        log("supervisor: يعمل — الخدمات: " + ", ".join(self.states))
        try:
            self.start_all()
            self.monitor_loop()
        finally:
            self.stop_all()
            PID_FILE.unlink(missing_ok=True)

    def install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: Any) -> None:
            global shutting_down
            shutting_down = True
            log(f"supervisor: استقبل إشارة {signum} — بدء الإيقاف")
            self.should_run = False

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)


# ─────────────────────────── الأوامر ───────────────────────────


def acquire_lock() -> bool:
    """قفل حالة-واحدة — يمنع مشرفَين معًا (pidfile + فحص حياة)."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    old_pid = read_pid(PID_FILE)
    if old_pid and pid_alive(old_pid):
        log(f"supervisor: يعمل أصلًا (pid={old_pid}) — لا إقلاع مزدوج", error=True)
        return False
    PID_FILE.unlink(missing_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        old = read_pid(LOCK_FILE)
        if old and pid_alive(old):
            return False
        LOCK_FILE.unlink(missing_ok=True)
        return acquire_lock()
    return True


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def cmd_run() -> int:
    if not acquire_lock():
        return 1
    try:
        Supervisor().run_forever()
    finally:
        release_lock()
    return 0


def cmd_start() -> int:
    """تشغيل خفي بنمط double-fork (ADR-002: النمط الوحيد الناجي في sandbox)."""
    if not acquire_lock():
        return 1
    pid = os.fork()
    if pid > 0:
        # الأب الأول: يحرر القفل ويعود فورًا (الابن ورثه)
        time.sleep(0.4)  # مهلة قصيرة كي يقلع الابن ويستلم القفل بنفسه
        release_lock()
        log("supervisor: أُطلق خفيًا (double-fork)")
        return 0
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)
    # الابن الثاني: يفصل نفسه عن الطرفيات ويكتب pidfile بنفسه
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        daemon_log_fd = os.open(
            LOGS_DIR / "daemon.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
        )
        devnull_fd = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull_fd, sys.stdin.fileno())
        os.dup2(daemon_log_fd, sys.stdout.fileno())
        os.dup2(daemon_log_fd, sys.stderr.fileno())
        os.close(devnull_fd)
        os.close(daemon_log_fd)
    except OSError:
        pass
    try:
        Supervisor().run_forever()
    finally:
        release_lock()
    os._exit(0)


def cmd_stop() -> int:
    pid = read_pid(PID_FILE)
    if not pid or not pid_alive(pid):
        log("supervisor: غير مشغل")
        PID_FILE.unlink(missing_ok=True)
        release_lock()
        return 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + TERM_WAIT_S + 3
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            log("supervisor: أُوقف نظيفًا")
            return 0
        time.sleep(0.3)
    log("supervisor: لم يستجب — قتل قسري", error=True)
    os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    release_lock()
    return 0


def cmd_status() -> int:
    pid = read_pid(PID_FILE)
    alive = pid is not None and pid_alive(pid)
    print(f"supervisor: {'يعمل' if alive else 'متوقف'}" + (f" (pid={pid})" if pid else ""))
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        print(f"آخر تحديث حالة: {data['updated_at']}")
        for svc in data["services"]:
            mark = {"HEALTHY": "✓", "EXITED_OK": "✓", "SKIPPED": "-"}.get(svc["state"], "✗")
            extra = f" pid={svc['pid']}" if svc.get("pid") else ""
            extra += f" restarts={svc['restarts']}" if svc["restarts"] else ""
            extra += f" exit={svc['exit_code']}" if svc.get("exit_code") is not None else ""
            print(f"  {mark} {svc['name']:12s} {svc['state']:10s}{extra}")
    else:
        print("لا ملف حالة — supervisor لم يعمل بعد")
    return 0


def cmd_health() -> int:
    env = load_env_context()
    specs = load_services(env)
    all_ok = True
    print("فحوص الصحة النشطة:")
    for spec in specs:
        if spec.skip_if_missing and not (ENGINE_ROOT / spec.skip_if_missing).exists():
            print(f"  - {spec.name:12s} SKIPPED ({spec.skip_if_missing} غير موجود)")
            continue
        if spec.health.get("type") == "exit_zero":
            # oneshot: صحته آخر حالة خروج مسجلة
            state = _state_for(spec.name)
            ok = state in ("EXITED_OK",)
            print(f"  {'✓' if ok else '✗'} {spec.name:12s} {state or 'غير معروف'}")
            all_ok = all_ok and ok
            continue
        if spec.health.get("type") == "process":
            state = _state_for(spec.name)
            ok = state in ("HEALTHY", "RUNNING", "STARTING")
            print(f"  {'✓' if ok else '✗'} {spec.name:12s} {state or 'متوقف'}")
            all_ok = all_ok and ok
            continue
        ok, detail = probe_health(spec, env)
        print(f"  {'✓' if ok else '✗'} {spec.name:12s} {detail}")
        all_ok = all_ok and ok
    print("النتيجة:", "سليم" if all_ok else "خلل في خدمة حرجة")
    return 0 if all_ok else 1


def _state_for(name: str) -> str | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for svc in data["services"]:
            if svc["name"] == name:
                return str(svc["state"])
    except (OSError, json.JSONDecodeError):
        return None
    return None


def cmd_restart(name: str) -> int:
    pid = read_pid(PID_FILE)
    if not pid or not pid_alive(pid):
        log("supervisor: غير مشغل — لا إعادة لخدمة فردية", error=True)
        return 1
    svc_pid = read_pid(RUN_DIR / f"{name}.pid")
    if svc_pid and pid_alive(svc_pid):
        os.kill(svc_pid, signal.SIGTERM)  # الرقابة ستعيده تلقائيًا
        log(f"{name}: أُرسلت إشارة إعادة — الرقابة ستنهض به")
        return 0
    log(f"{name}: لا عملية حية بها")
    return 1


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    command, rest = args[0], args[1:]
    if command == "run":
        return cmd_run()
    if command == "start":
        return cmd_start()
    if command in {"stop", "shutdown"}:
        return cmd_stop()
    if command == "status":
        return cmd_status()
    if command == "health":
        return cmd_health()
    if command == "restart" and rest:
        return cmd_restart(rest[0])
    print(f"أمر غير معروف: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
