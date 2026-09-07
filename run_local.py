"""Windows 로컬 개발 실행 스크립트.

psycopg의 비동기 모드는 Windows 기본 이벤트루프(ProactorEventLoop)를 지원하지 않는다.
uvicorn이 이벤트루프를 생성하기 전에(=이 스크립트 최상단에서) 정책을 바꿔야 실제로 적용된다 —
`app/main.py` 안에서 바꾸면 이미 루프가 만들어진 뒤라 늦는다.
배포 환경(Linux/Railway)에서는 이 이슈가 없으므로 그냥 `uvicorn app.main:app`을 쓰면 된다.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
