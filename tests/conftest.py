print("CONFTES.PY LOADED")
print("About to define fixtures")
import pytest
import asyncio
import tempfile
import os
from app.core.config import Settings
import app.core.config as config_module

# Test if we can import our db module
try:
    from app.core.database import get_engine
    print("CONFTES: Successfully imported get_engine")
except Exception as e:
    print(f"CONFTES: Failed to import get_engine: {e}")


@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for the test session."""
    print(f"TEMP_DIR fixture called")
    td = tempfile.mkdtemp()
    print(f"Created temp dir: {td}")
    return td


@pytest.fixture(scope="session")
def database_file(temp_dir):
    """Create a database file path for the test session."""
    print(f"DATABASE_FILE fixture called with temp_dir: {temp_dir}")
    df = os.path.join(temp_dir, "test.db")
    print(f"Database file: {df}")
    return df


@pytest.fixture(scope="session", autouse=True)
def override_env_vars(temp_dir, database_file):
    """Override environment variables for testing."""
    print(f"OVERRIDE_ENV_VARS fixture called")
    # Set environment variables for test database
    os.environ["APP_ENV"] = "testing"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_file}"
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["STORAGE_LOCAL_PATH"] = os.path.join(temp_dir, "test_storage")
    print(f"Set DATABASE_URL to: {os.environ['DATABASE_URL']}")

    # Clear the settings cache to pick up new environment variables
    import app.core.config as config_module
    # Store original get_settings for cache clearing later
    original_get_settings = config_module.get_settings
    original_get_settings.cache_clear()
    print("Cleared settings cache")

    # Reset the database engine to pick up the new DATABASE_URL
    import app.core.database
    app.core.database.reset_engine()
    print("Reset database engine")

    yield

    # Clean up environment variables
    print("Cleaning up environment variables")
    os.environ.pop("APP_ENV", None)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("STORAGE_BACKEND", None)
    os.environ.pop("STORAGE_LOCAL_PATH", None)
    # Clear cache again using original function
    import app.core.config as config_module
    original_get_settings.cache_clear()
    # Reset engine again to clear the test engine (optional, but clean)
    import app.core.database
    app.core.database.reset_engine()


@pytest.fixture(scope="session", autouse=True)
def create_test_tables(temp_dir, database_file, override_env_vars):
    """Create test tables once for the test session."""
    print("CREATE_TEST_TABLES fixture called")
    print(f"Using database file: {database_file}")
    # Import after environment variables are set and engine is reset
    from app.core.database import Base, get_engine
    import app.models.document  # noqa: F401

    engine = get_engine()
    print(f"Engine URL: {engine.url}")

    # Create tables
    async def _create_tables():
        print("Creating tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Tables created")

    try:
        print("Running _create_tables...")
        asyncio.run(_create_tables())
        print("Tables created successfully")
    except RuntimeError as e:
        if "cannot close a running event loop" in str(e):
            print("Handling running event loop...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_create_tables())
            loop.close()
        else:
            raise

    yield
    print("CREATE_TEST_TABLES fixture yielding")

    # Drop tables at the end of session
    async def _drop_tables():
        print("Dropping tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        print("Tables dropped")

    try:
        print("Running _drop_tables...")
        asyncio.run(_drop_tables())
        print("Tables dropped successfully")
    except RuntimeError as e:
        if "cannot close a running event loop" in str(e):
            print("Handling running event loop...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_drop_tables())
            loop.close()
        else:
            raise


@pytest.fixture(autouse=True)
def clear_tables():
    """Clear all data from tables before each test."""
    print("=== CLEAR_TABLES fixture START ===")
    # Import after environment variables are set and reload to get correct engine
    import importlib
    import app.core.database as db_module
    importlib.reload(db_module)
    # After reload, get the engine
    engine = db_module.get_engine()
    print(f"CLEAR_TABLES: Engine URL: {engine.url}")
    # Import models from the correct location
    from app.models.document import Document, DocumentPage

    # Clear tables
    async def _clear_tables():
        print("CLEAR_TABLES: Deleting from document_pages and documents tables")
        async with engine.begin() as conn:
            result1 = await conn.execute(DocumentPage.__table__.delete())
            result2 = await conn.execute(Document.__table__.delete())
            print(f"CLEAR_TABLES: Deleted {result1.rowcount} rows from document_pages, {result2.rowcount} rows from documents")

    # Run the async function
    try:
        asyncio.run(_clear_tables())
        print("CLEAR_TABLES: Tables cleared successfully")
    except Exception as e:
        print(f"CLEAR_TABLES: Error clearing tables: {e}")
        raise

    print("=== CLEAR_TABLES fixture YIELD ===")
    yield
    print("=== CLEAR_TABLES fixture AFTER YIELD ===")
    # Clear tables after test (optional, since we clear before each test)
    try:
        asyncio.run(_clear_tables())
        print("CLEAR_TABLES: Tables cleared after test")
    except Exception as e:
        print(f"CLEAR_TABLES: Error clearing tables after test: {e}")
        raise