"""محرك التدفق والفوتبرنت (§12): بناء الفوتبرنت من aggTrades بتصنيف
الطرف المتسبب، ومقاييس الشريط، وعناقيد الاختلال، والامتصاص والإنهاك،
ومصفوفة الجهد مقابل النتيجة — عبر كواشف على نمط البنية/السيولة.

كل المقاييس التدفقية موسومة بالمصدر والمنهجية (§12.7): تصنيف الشراء/
البيع هنا **مبني على علم ``buyer_is_maker`` من aggTrades** — ليس «كل
مشتريي السوق مقابل كل بائعيه»؛ ``source_feed`` و``methodology``
إلزاميان في كل ``FootprintBar``.

العتبات السعرية (امتداد/استجابة) من ``VolatilityState.threshold`` حصرًا
(§16) — مفاتيح ``ABSORPTION_EXTENSION_MAX`` و``FLOW_RESPONSE_MIN``؛
والنسب عديمة الأبعاد (حصص الدلتا، نسب الاختلال الصفّي) قياسات صرفة.
"""

__version__ = "0.1.0"

from orderflow.events import EmittedEvent
from orderflow.rows import (
    IMBALANCE_RATIO,
    METHODOLOGY_AGGTRADE_TAKER,
    BarRows,
    FootprintRow,
    row_imbalance_side,
    row_ratio,
)

__all__ = [
    "IMBALANCE_RATIO",
    "METHODOLOGY_AGGTRADE_TAKER",
    "BarRows",
    "EmittedEvent",
    "FootprintRow",
    "row_imbalance_side",
    "row_ratio",
]
