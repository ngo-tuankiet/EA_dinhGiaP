import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from valuation.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

def _create_safe_engine(url: str, is_readonly: bool = False):
    kwargs = dict(pool_pre_ping=True)
    if "sqlite" in url:
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(dict(
            pool_size=5,
            max_overflow=10,
            connect_args={"connect_timeout": 1},
        ))
        if is_readonly:
            kwargs["isolation_level"] = "AUTOCOMMIT"
            
    try:
        engine = create_engine(url, **kwargs)
        with engine.connect() as conn:
            pass
        return engine
    except Exception as e:
        logger.warning(f"Không thể kết nối DB tại {url}: {e}. Tự động chuyển sang SQLite (sqlite:///vn100_full.db).")
        sqlite_url = "sqlite:///vn100_full.db"
        sqlite_kwargs = {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
        return create_engine(sqlite_url, **sqlite_kwargs)

# Engine dùng cho ghi dữ liệu (cần quyền write)
engine_write = _create_safe_engine(settings.database_url_write, is_readonly=False)
SessionLocalWrite = sessionmaker(autocommit=False, autoflush=False, bind=engine_write)

# Engine dùng cho đọc dữ liệu (readonly)
engine_read = _create_safe_engine(settings.database_url_readonly, is_readonly=True)
SessionLocalRead = sessionmaker(autocommit=False, autoflush=False, bind=engine_read)


def init_db(engine=None):
    """Khởi tạo schema cho SQLite nếu chưa có."""
    target_engine = engine or engine_write
    if "sqlite" in str(target_engine.url):
        try:
            import valuation.db.models  # noqa: F401
            Base.metadata.create_all(bind=target_engine)
        except Exception as exc:
            logger.warning(f"Không thể tự động tạo schema SQLite: {exc}")


# Tự động đảm bảo schema SQLite khi load session
if "sqlite" in str(engine_write.url):
    init_db(engine_write)


def get_write_db():
    db = SessionLocalWrite()
    try:
        yield db
    finally:
        db.close()


def get_read_db():
    db = SessionLocalRead()
    try:
        yield db
    finally:
        db.close()
