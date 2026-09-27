"""فحص صحة engine-api داخل الحاوية — stdlib فقط (صورة slim بلا curl/wget).

يقرأ ENGINE_API_PORT من بيئة التشغيل ويضرب /healthz على loopback الداخلي.
خروج 0 = صحيح؛ أي شيء آخر = فشل (يستهلكه docker healthcheck لخدمة engine-api).
"""

from __future__ import annotations

import http.client
import os
import sys


def main() -> int:
    port = int(os.environ.get("ENGINE_API_PORT", "4001"))
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        return 0 if response.status == 200 else 1
    except OSError:
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
