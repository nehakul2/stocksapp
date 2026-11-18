import os
import tempfile

# Must run before db.py is imported: tests use a throwaway database file.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
