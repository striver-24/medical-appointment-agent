import os
import shutil
import unittest
from datetime import datetime, timedelta

import pandas as pd

from src.tools import lookup_patient, find_available_slots, book_appointment

class TestTools(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up a temporary test environment."""
        cls.test_data_dir = "test_data_temp"
        os.makedirs(cls.test_data_dir, exist_ok=True)
        
        # Override file paths for testing
        from src import utils
        cls.original_patients_path = utils.PATIENTS_FILE_PATH
        cls.original_schedules_path = utils.SCHEDULES_FILE_PATH
        utils.PATIENTS_FILE_PATH = os.path.join(cls.test_data_dir, "patients.csv")
        utils.SCHEDULES_FILE_PATH = os.path.join(cls.test_data_dir, "schedules.xlsx")

        # Create mock patient data
        mock_patients = pd.DataFrame([
            {"patient_id": 101, "name": "John Doe", "dob": "1990-05-15", "phone": "123", "email": "jd@test.com"},
            {"patient_id": 102, "name": "Jane Smith", "dob": "1985-11-20", "phone": "456", "email": "js@test.com"}
        ])
        mock_patients.to_csv(utils.PATIENTS_FILE_PATH, index=False)

        # Create mock schedule data
        writer = pd.ExcelWriter(utils.SCHEDULES_FILE_PATH, engine='openpyxl')
        start_time = datetime.now() + timedelta(days=1)
        start_time = start_time.replace(hour=10, minute=0, second=0, microsecond=0)
        
        schedule_data = []
        for i in range(16): # 4 hours of slots
            slot_time = start_time + timedelta(minutes=15 * i)
            schedule_data.append({
                'slot_iso': slot_time.isoformat(), 
                'status': 'Available', 
                'booked_by': ''
            })
        
        # Make one slot booked
        schedule_data[4]['status'] = 'Booked'
        
        df_schedule = pd.DataFrame(schedule_data)
        df_schedule.to_excel(writer, sheet_name="Dr. Test", index=False)
        writer.close()

    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment."""
        shutil.rmtree(cls.test_data_dir)
        # Restore original paths
        from src import utils
        utils.PATIENTS_FILE_PATH = cls.original_patients_path
        utils.SCHEDULES_FILE_PATH = cls.original_schedules_path

    def test_lookup_patient_returning(self):
        """Test finding an existing patient."""
        result = lookup_patient("John Doe", "1990-05-15")
        self.assertEqual(result["status"], "returning")
        self.assertEqual(result["patient_id"], 101)
        self.assertEqual(result["data"]["name"], "John Doe")

    def test_lookup_patient_new(self):
        """Test lookup for a new patient."""
        result = lookup_patient("New Person", "2000-01-01")
        self.assertEqual(result["status"], "new")

    def test_find_available_slots_30min(self):
        """Test finding a 30-minute (2 consecutive slots) appointment."""
        result = find_available_slots("Dr. Test", 30)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["slots"]), 3)
        # The first available should be the start of our mock schedule
        expected_first_slot = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        self.assertEqual(result["slots"][0], expected_first_slot.isoformat())

    def test_find_available_slots_60min(self):
        """Test finding a 60-minute (4 consecutive slots) appointment."""
        result = find_available_slots("Dr. Test", 60)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["slots"]), 3)
        # We should not find the slot that was pre-booked
        self.assertNotIn((datetime.now() + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0).isoformat(), result["slots"])

    def test_book_appointment_success_and_fail(self):
        """Test booking an available slot and then trying to book it again."""
        slots_result = find_available_slots("Dr. Test", 30)
        first_slot = slots_result["slots"][0]

        # First booking should succeed
        booking_result = book_appointment(first_slot, "Dr. Test", 101, "John Doe")
        self.assertEqual(booking_result["status"], "success")
        self.assertIn("BKNG-101", booking_result["booking_id"])

        # Second booking of the same slot should fail
        booking_result_fail = book_appointment(first_slot, "Dr. Test", 102, "Jane Smith")
        self.assertEqual(booking_result_fail["status"], "error")
        self.assertEqual(booking_result_fail["message"], "Slot is no longer available.")

if __name__ == "__main__":
    unittest.main()
