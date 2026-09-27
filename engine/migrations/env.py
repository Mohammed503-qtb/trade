"""بيئة Alembic غير المتزامنة (asyncpg) — المهمة 0.6.

قالب الهجرة القياسي لغير المتزامن، مكيَّفًا على المحرك:
- لا URL ولا أسرار هنا ولا في alembic.ini إطلاقًا (§37.1): الرابط يُبنى
  برمجيًا من الإعدادات المركزية ``common.config.load_settings()`` التي تقرأ
  ``ENGINE_DATABASE_URL`` من البيئة أو ملف ``.env``.
- تمريرة صريحة تتجاوز الإعدادات عند الحاجة (اختبارات/بيئة مؤقتة):
  ``alembic -x sqlalchemy.url=postgresql://... upgrade head``
- دعم الوضعين: offline (إصدار SQL بلا اتصال) وonline (تنفيذ فعلي عبر
  محرك asyncpg) — خدمة migrate في supervisor وcompose تستخدم online.

يعمل الاستيراد المباشر ``from common.config import load_settings`` لأن حزم
workspace كلها مثبتة editable في البيئة الافتراضية للمحرك.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from common.config import load_settings

# ── MetaData لأجل autogenerate لاحقًا ──────────────────────────────────
# لا نماذج SQLAlchemy بعد (الجداول تُعرَّف يدويًا في الهجرات) — عند ظهورها
# تُجمَّع ميتاداتاها هنا. خريطة التسمية تضمن أسماء قيود حتمية للفروق المستقبلية.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

target_metadata = MetaData(naming_convention=NAMING_CONVENTION)

# كائن Config من alembic.ini — يمثل بيئة التشغيل الحالية للهجرة
config = context.config

# تسجيل السجلات من ملف ini إن وُجد (أقسام [logger_*] في alembic.ini)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    """مصدر رابط الاتصال بترتيب الأولوية: ‎-x sqlalchemy.url ثم الإعدادات المركزية."""
    x_args = context.get_x_argument(as_dictionary=True)
    if "sqlalchemy.url" in x_args:
        return str(x_args["sqlalchemy.url"])
    return str(load_settings().database_url)


def _async_database_url(raw_url: str) -> str:
    """إعادة كتابة الرابط إلى درايفر asyncpg.

    ``create_async_engine`` يرفض درايفر غير متزامن — والرابط الافتراضي من
    الإعدادات بصيغة ``postgresql://`` المجردة، لذا يُستبدل الدرايفر صراحةً
    بـ ``postgresql+asyncpg`` إن لم يكن متزامنًا أصلًا.

    تنبيه: ``str(url)`` يخفي كلمة المرور بـ ``***`` (سلوك URL الافتراضي)
    فيفشل الاتصال — لذا نصرّح بـ ``render_as_string(hide_password=False)``.
    """
    url = make_url(raw_url)
    if url.drivername in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        url = url.set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


def _apply_url() -> None:
    """تثبيت الرابط في كائن Config ليقرأه online وoffline معًا."""
    config.set_main_option("sqlalchemy.url", _async_database_url(_resolve_url()))


def run_migrations_offline() -> None:
    """وضع offline: يُصدر SQL إلى المخرجات بلا اتصال (``alembic upgrade --sql``)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """تهيئة سياق الهجرة داخل اتصال فعلي (يُستدعى عبر connection.run_sync)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """بناء محرك asyncpg من إعدادات ini المضبوطة برمجيًا وتشغيل الهجرات."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """وضع online: تنفيذ فعلي عبر محرك غير متزامن في حلقة أحداث مستقلة."""
    asyncio.run(run_async_migrations())


# الرابط يُحسم أولًا — الوضعان كلاهما يقرآه من كائن Config
_apply_url()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
