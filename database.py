from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

# =========================
# Database Configuration
# =========================

# SQLite file (จะถูกสร้างอัตโนมัติ)
DATABASE_URL = "sqlite:///./election.db"

# create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # เปลี่ยนเป็น True ถ้าอยาก debug SQL
    connect_args={"check_same_thread": False}  # สำคัญสำหรับ SQLite + FastAPI
)

# =========================
# Create Tables Function
# =========================

def create_db_and_tables() -> None:
    """
    ใช้สร้าง tables จาก models
    ต้องถูกเรียกใน main.py ตอน start app
    """
    SQLModel.metadata.create_all(engine)

# =========================
# Session Dependency
# =========================

def get_session() -> Generator[Session, None, None]:
    """
    Dependency สำหรับ FastAPI
    ใช้ใน endpoint ด้วย Depends(get_session)
    """
    with Session(engine) as session:
        yield session