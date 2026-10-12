import os
import shutil
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Nhiều test commit thẳng vào DB. Engine được tạo lúc import valuation.db.session,
# nên phải trỏ env sang bản copy TRƯỚC mọi import của package valuation.
if "DATABASE_URL_WRITE" not in os.environ:
    _src = os.path.join(ROOT_DIR, "vn100_full.db")
    if os.path.exists(_src):
        _dst = os.path.join(tempfile.mkdtemp(prefix="vn100_test_"), "vn100_full.db")
        shutil.copyfile(_src, _dst)
        os.environ["DATABASE_URL_WRITE"] = f"sqlite:///{_dst}"
        os.environ["DATABASE_URL_READONLY"] = f"sqlite:///{_dst}"
