import os
import shutil
import unittest
from datetime import datetime, timedelta
import pandas as pd

# Import all the tools that need testing, and the utils for path overrides
from src.tools import (
    find_doctors_by_specialty_and_date,
    lookup_patient,
    register_new_patient,
    find_available_slots,
    book_appointment,
    finalize_booking_and_notify,
)
from src import utils

class TestTools(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up a temporary, isolated test environment."""
        cls.test_data_dir = "test_data_temp"
        os.makedirs(cls.test_data_dir, exist_ok=True)

        # --- Override file paths to use our temporary test data ---
        cls.original_paths = {
            'patients': utils.PATIENTS_FILE_PATH,
            'schedules': utils.SCHEDULES_FILE_PATH,
            'doctors': utils.DOCTORS_FILE_PATH,
            'insurance': utils.INSURANCE_FILE_PATH,
            'admin_report': utils.ADMIN_REPORT_FILE_PATH
        }
        utils.PATIENTS_FILE_PATH = os.path.join(cls.test_data_dir, "patients.csv")
        utils.SCHEDULES_FILE_PATH = os.path.join(cls.test_data_dir, "schedules.xlsx")
        utils.DOCTORS_FILE_PATH = os.path.join(cls.test_data_dir, "doctors.csv")
        utils.INSURANCE_FILE_PATH = os.path.join(cls.test_data_dir, "insurance.json")
        utils.ADMIN_REPORT_FILE_PATH = os.path.join(cls.test_data_dir, "admin_report.xlsx")

        # --- Create Mock Data ---
        # Mock Doctors Data
        mock_doctors = pd.DataFrame([
            {"doctor_id": "D101", "doctor_name": "Dr. Alice Test", "specialty": "Cardiology", "years_experience": 15},
            {"doctor_id": "D102", "doctor_name": "Dr. Bob Case", "specialty": "Cardiology", "years_experience": 22},
            {"doctor_id": "D103", "doctor_name": "Dr. Carol Mock", "specialty": "Dermatology", "years_experience": 10}
        ])
        mock_doctors.to_csv(utils.DOCTORS_FILE_PATH, index=False)

        # Mock Patient Data (using DD-MM-YYYY format)
        mock_patients = pd.DataFrame([
            {"patient_id": "PAT-EXISTING", "name": "John Doe", "dob": "15-05-1990", "phone": "123", "email": "jd@test.com", "gender": "Male", "address": "123 Test St", "emergency_contact_name": "Jane Doe", "emergency_contact_phone": "111"}
        ])
        mock_patients.to_csv(utils.PATIENTS_FILE_PATH, index=False)

        # Mock Schedule Data
        with pd.ExcelWriter(utils.SCHEDULES_FILE_PATH, engine='openpyxl') as writer:
            cls.test_date = (datetime.now() + timedelta(days=2)).date()
            start_time = datetime.combine(cls.test_date, datetime.min.time()).replace(hour=10)
            
            schedule_data = []
            for i in range(16): # 4 hours of 15-min slots
                slot_time = start_time + timedelta(minutes=15 * i)
                schedule_data.append({'slot_iso': slot_time.isoformat(), 'status': 'Available', 'booked_by': ''})
            
            # Block out a few slots to test logic
            schedule_data[2]['status'] = 'Blocked' # 10:30
            schedule_data[5]['status'] = 'Booked'  # 11:15

            df_schedule = pd.DataFrame(schedule_data)
            df_schedule.to_excel(writer, sheet_name="Dr. Alice Test", index=False)
            # Create a blank schedule for another doctor
            pd.DataFrame(columns=['slot_iso', 'status', 'booked_by']).to_excel(writer, sheet_name="Dr. Bob Case", index=False)

    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment and restore original paths."""
        shutil.rmtree(cls.test_data_dir)
        utils.PATIENTS_FILE_PATH = cls.original_paths['patients']
        utils.SCHEDULES_FILE_PATH = cls.original_paths['schedules']
        utils.DOCTORS_FILE_PATH = cls.original_paths['doctors']
        utils.INSURANCE_FILE_PATH = cls.original_paths['insurance']
        utils.ADMIN_REPORT_FILE_PATH = cls.original_paths['admin_report']

    def test_find_doctors_by_specialty_success(self):
        """Test finding available doctors for a specialty on a given date."""
        test_date_str = self.test_date.strftime("%d-%m-%Y")
        result = find_doctors_by_specialty_and_date.func("Cardiology", test_date_str)
        
        self.assertEqual(result["status"], "success")
        self.assertIsInstance(result["available_doctors"], list)
        self.assertEqual(len(result["available_doctors"]), 1)
        self.assertEqual(result["available_doctors"][0]["name"], "Dr. Alice Test")
        self.assertEqual(result["available_doctors"][0]["experience"], 15)

    def test_find_doctors_by_specialty_none_available(self):
        """Test when doctors of a specialty exist but have no slots on the date."""
        test_date_str = self.test_date.strftime("%d-%m-%Y")
        # Dr. Bob Case has a schedule but it's empty
        result = find_doctors_by_specialty_and_date.func("Cardiology", test_date_str)
        # Check that only Dr. Alice Test is returned
        self.assertEqual(len(result["available_doctors"]), 1)
        
    def test_lookup_patient_returning(self):
        """Test finding an existing patient with DD-MM-YYYY format."""
        result = lookup_patient.func("John Doe", "15-05-1990")
        self.assertEqual(result["status"], "returning")
        self.assertEqual(result["patient_id"], "PAT-EXISTING")

    def test_register_new_patient_success(self):
        """Test successfully registering a new patient."""
        result = register_new_patient.func(
            name="Jane Smith", dob="20-11-1985", email="js@test.com", phone="456",
            gender="Female", address="456 Mock Ave", emergency_contact_name="John Smith",
            emergency_contact_phone="222"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("PAT-", result["patient_id"])
        self.assertEqual(result["data"]["name"], "Jane Smith")
        # Verify it was written to the file
        df = pd.read_csv(utils.PATIENTS_FILE_PATH)
        self.assertEqual(len(df), 2)

    def test_find_available_slots_60min(self):
        """Test finding a 60-minute (4 consecutive slots) appointment."""
        test_date_str = self.test_date.strftime("%d-%m-%Y")
        result = find_available_slots.func("Dr. Alice Test", test_date_str, 60)
        self.assertEqual(result["status"], "success")
        # Expecting 10:45 (after a booked slot) and 11:30 onwards
        self.assertEqual(len(result["slots"]), 3)
        self.assertIn("10:45", result["slots"][0])

    def test_book_appointment_and_finalize(self):
        """Test the full booking and finalization flow."""
        test_date_str = self.test_date.strftime("%d-%m-%Y")
        slots_result = find_available_slots.func("Dr. Alice Test", test_date_str, 30)
        first_slot = slots_result["slots"][0] # Should be 10:00

        # 1. Book the appointment
        booking_result = book_appointment.func(first_slot, "Dr. Alice Test", "PAT-EXISTING", "John Doe")
        self.assertEqual(booking_result["status"], "success")
        appointment_id = booking_result["appointment_id"]
        self.assertIn("APP-", appointment_id)

        # 2. Try to book the same slot again, expecting failure
        fail_booking_result = book_appointment.func(first_slot, "Dr. Alice Test", "PAT-NEW", "Jane Smith")
        self.assertEqual(fail_booking_result["status"], "error")

        # 3. Finalize the successful booking
        finalize_result = finalize_booking_and_notify.func(
            appointment_id=appointment_id, patient_id="PAT-EXISTING", patient_name="John Doe",
            patient_dob="15-05-1990", patient_email="jd@test.com", patient_phone="123",
            doctor_name="Dr. Alice Test", slot_iso=first_slot, is_new_patient=False,
            insurance_company="Test Health", insurance_member_id="T123", insurance_group_number="G456"
        )
        self.assertEqual(finalize_result["status"], "success")

        # Verify that the finalization steps created files
        self.assertTrue(os.path.exists(utils.INSURANCE_FILE_PATH))
        self.assertTrue(os.path.exists(utils.ADMIN_REPORT_FILE_PATH))

if __name__ == "__main__":
    unittest.main()

