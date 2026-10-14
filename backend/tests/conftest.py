"""测试环境：禁用真实密钥（全部走高仿真回退数据），独立临时数据库。"""
import os
import tempfile

os.environ["FUYAO_API_KEY"] = ""
os.environ["IFIND_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["JEV_API_KEY"] = ""
os.environ["ENABLE_HIGH_FIDELITY_FALLBACK"] = "true"

_tmpdir = tempfile.mkdtemp(prefix="radar_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test_radar.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_if_empty(db)
    db.close()
    yield


@pytest.fixture(scope="session")
def client():
    """整个测试会话共享一个 TestClient（多次 lifespan 会在轮换的事件循环间交叉报错）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()
