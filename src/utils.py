import logging
from contextlib import contextmanager
from filelock import FileLock, Timeout
from typing import Generator, Optional
from datetime import datetime
from dateutil.parser import parse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- File Paths ---
SCHEDULES_FILE_PATH = "data/schedules.xlsx"
PATIENTS_FILE_PATH = "data/patients.csv"
INSURANCE_FILE_PATH = "data/insurance.json"
ADMIN_REPORT_FILE_PATH = "data/admin_report.xlsx"
DOCTORS_FILE_PATH = "data/doctors.csv"


@contextmanager
def acquire_lock(lock_file_path: str, timeout: int = 10) -> Generator[None, None, None]:
    """A context manager to acquire a file lock in a thread-safe and process-safe manner."""
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

def robust_date_parser(date_string: str) -> Optional[datetime.date]:
    """
    Parses a variety of date formats (e.g., '9th september 2025', '09-09-2025', 'tomorrow')
    into a standardized date object.
    """
    try:
        # The 'dayfirst=True' argument helps resolve ambiguity for formats like DD/MM/YYYY
        dt_object = parse(date_string, dayfirst=True)
        return dt_object.date()
    except (ValueError, TypeError):
        logging.error(f"Could not parse date string: {date_string}")
        return None

