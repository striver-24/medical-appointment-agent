import logging
from contextlib import contextmanager
from filelock import FileLock, Timeout
from typing import Generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define file paths
SCHEDULES_FILE_PATH = "data/schedules.xlsx"
PATIENTS_FILE_PATH = "data/patients.csv"
INSURANCE_FILE_PATH = "data/insurance.json"
ADMIN_REPORT_FILE_PATH = "data/admin_report.xlsx"

@contextmanager
def acquire_lock(lock_file_path: str, timeout: int = 10) -> Generator[None, None, None]:
    """
    A context manager to acquire a file lock in a thread-safe and process-safe manner.

    Args:
        lock_file_path (str): The path to the lock file.
        timeout (int): The maximum time in seconds to wait for the lock.

    Yields:
        None: Yields control back to the context block once the lock is acquired.

    Raises:
        TimeoutError: If the lock cannot be acquired within the specified timeout.
    """
    lock = FileLock(lock_file_path)
    try:
        logging.info(f"Attempting to acquire lock on {lock_file_path}...")
        lock.acquire(timeout=timeout)
        logging.info(f"Lock acquired on {lock_file_path}.")
        yield
    except Timeout:
        logging.error(f"Could not acquire lock on {lock_file_path} within {timeout} seconds.")
        raise TimeoutError(f"Could not acquire lock for {lock_file_path}")
    finally:
        if lock.is_locked:
            lock.release()
            logging.info(f"Lock released on {lock_file_path}.")
