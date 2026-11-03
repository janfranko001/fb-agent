"""Long-running worker for hosting (e.g. Railway): runs `agent.run` Mon-Fri at 10:00 New York time."""
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import agent

TZ = ZoneInfo("America/New_York")


def next_run(now: datetime) -> datetime:
    run = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if run <= now:
        run += timedelta(days=1)
    while run.weekday() > 4:  # skip Saturday/Sunday
        run += timedelta(days=1)
    return run


def main() -> None:
    while True:
        now = datetime.now(TZ)
        run = next_run(now)
        print(f"შემდეგი პოსტი: {run:%Y-%m-%d %H:%M %Z}", flush=True)
        time.sleep(max(1, (run - now).total_seconds()))
        try:
            agent.run_once()
        except Exception as e:  # keep the worker alive; try again next scheduled day
            print(f"შეცდომა: {e}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
