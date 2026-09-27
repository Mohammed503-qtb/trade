"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

قاعدة المشروع: معرّف المراجعة صيغته ``NNNN_وصف_إنجليزي`` (مثل 0001_reference_tables)
لتكون سجل الهجرة مقروءًا ترتيبيًا في ``alembic current/history``. الأعمدة والجداول
تطابق الخطة الأم (docs/Master Plan.md §31) حرفيًا — أي انحراف عنها يحتاج ADR موثقًا
في docs/architecture/decisions.md قبل كتابة الهجرة.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# معرفات المراجعة — يقرؤها alembic فقط ولا تُلمس يدويًا
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """الصعود إلى هذه المراجعة."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """الهبوط منها (كل ما يهدمه يمكن إعادة بنائه بالصعود ثانيةً)."""
    ${downgrades if downgrades else "pass"}
