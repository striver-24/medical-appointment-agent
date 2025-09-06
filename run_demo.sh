#!/bin/bash
echo " RAGAAI Medical Scheduling Agent Demo Setup "
echo "----------------------------------------------"

# Create necessary directories
echo "[1/5] Creating directories..."
mkdir -p src data forms tests

# Create empty __init__.py files to make packages
touch src/__init__.py
touch tests/__init__.py

# Check if pip is available
if ! command -v pip &> /dev/null
then
    echo "ERROR: pip could not be found. Please install Python and pip."
    exit 1
fi

# Install dependencies
echo "[2/5] Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Generate synthetic data
echo "[3/5] Generating synthetic patient and schedule data..."
python -c "
import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta

fake = Faker()
# Generate Patients
print(' -> Generating data/patients.csv...')
patients = []
for i in range(50):
    patients.append({
        'patient_id': 1000 + i,
        'name': fake.name(),
        'dob': fake.date_of_birth(minimum_age=18, maximum_age=90).strftime('%Y-%m-%d'),
        'phone': fake.phone_number(),
        'email': f'patient{1000+i}@notreal.com'
    })
# Create the file with headers if it doesn't exist
try:
    pd.read_csv('data/patients.csv')
except FileNotFoundError:
    pd.DataFrame(columns=['patient_id', 'name', 'dob', 'phone', 'email']).to_csv('data/patients.csv', index=False)

# Append new data
pd.DataFrame(patients).to_csv('data/patients.csv', mode='a', header=False, index=False)


# Generate Schedules
print(' -> Generating data/schedules.xlsx...')
writer = pd.ExcelWriter('data/schedules.xlsx', engine='openpyxl')
doctors = ['Dr. Emily Carter', 'Dr. Ben Adams', 'Dr. Olivia Chen', 'Dr. Marcus Rodriguez']
start_date = datetime.now().date() + timedelta(days=1)

for doctor in doctors:
    schedule_data = []
    for day in range(7): # 7-day schedule
        current_date = start_date + timedelta(days=day)
        # Expanded working hours 8 AM to 6 PM
        for hour in range(8, 18):
            for minute in [0, 15, 30, 45]:
                slot_time = datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute)
                # Block out lunch from 12 PM to 1 PM
                if 12 <= hour < 13:
                    status = 'Blocked'
                # Randomly block some other slots
                elif random.choice([True, False, False, False, False]):
                     status = 'Blocked'
                else:
                    status = 'Available'
                schedule_data.append({'slot_iso': slot_time.isoformat(), 'status': status, 'booked_by': ''})
    df_schedule = pd.DataFrame(schedule_data)
    df_schedule.to_excel(writer, sheet_name=doctor, index=False)
writer.close()
print(' -> Data generation complete.')
"

# Acknowledge form path requirement
echo "[4/5] Acknowledging form path requirement..."
echo "NOTE: The application is configured to look for the intake form at '/mnt/data/New Patient Intake Form (1).pdf' as per requirements."
echo "Please ensure a file exists at this path or update it in 'src/tools.py'."

# Run Streamlit app
echo "[5/5] Starting the Streamlit application..."
echo "Please open your browser to the URL provided by Streamlit."
streamlit run src/main.py
