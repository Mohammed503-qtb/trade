#!/usr/bin/env python3
"""مُطلق double-fork — النمط الوحيد الذي ينجو بين أوامر الأدوات (ADR-002).

الاستخدام: python3 launch-daemon.py <label> <logfile> <cmd> [args...]
يفصل العملية عن الجلسة والطرفية ثم exec الأمر — تصبح يتيمة تتبنى PID 1.
"""
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: launch-daemon.py <label> <logfile> <cmd> [args...]", file=sys.stderr)
        return 2
    label, logfile, cmd, *args = sys.argv[1:]
    log_path = Path(logfile)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    pid = os.fork()
    if pid > 0:
        # الأب الأول يعود فورًا
        print(f"[launch-daemon] {label}: أُطلق (ابن أولي pid={pid})")
        return 0

    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    # الابن الثاني — يتيمة تحت PID 1
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(fd, sys.stdout.fileno())
        os.dup2(fd, sys.stderr.fileno())
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, sys.stdin.fileno())
    except OSError:
        pass

    os.execvp(cmd, [cmd, *args])
    return 1  # لن يُبلغ إليه عمليًا


if __name__ == "__main__":
    raise SystemExit(main())
