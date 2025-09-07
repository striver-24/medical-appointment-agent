#!/bin/bash
echo " RAGAAI Medical Scheduling Agent Demo Setup "
echo "----------------------------------------------"

# --- IMPORTANT PRE-REQUISITE ---
echo "Please ensure you have downloaded the 'doctors.csv' file from the"
echo "Kaggle dataset and placed it inside the 'data/' directory before running this script."
echo "----------------------------------------------------------------------------------"
sleep 3 # Give user time to read the message

# Create necessary directories
echo "[1/5] Creating directories..."
mkdir -p src data forms tests

# Create empty __init__.py files
touch src/__init__.py
touch tests/__init__.py

# Install dependencies
echo "[2/5] Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# --- START OF CHANGES ---
# Process the downloaded doctors.csv file to match the application's required format.
echo "[3/5] Processing doctors data from data/doctors.csv..."
python -c "
import pandas as pd
import sys

doctors_file_path = 'data/doctors.csv'

try:
    doctors_df = pd.read_csv(doctors_file_path)
    print(' -> Original columns found:', doctors_df.columns.tolist())

    # 1. Combine name columns
    if 'first_name' in doctors_df.columns and 'last_name' in doctors_df.columns:
        doctors_df['doctor_name'] = 'Dr. ' + doctors_df['first_name'] + ' ' + doctors_df['last_name']
    elif 'Doctor_Name' in doctors_df.columns:
        doctors_df.rename(columns={'Doctor_Name': 'doctor_name'}, inplace=True)
    
    # 2. Rename specialty column
    if 'specialization' in doctors_df.columns:
        doctors_df.rename(columns={'specialization': 'specialty'}, inplace=True)
    elif 'Specialization' in doctors_df.columns:
        doctors_df.rename(columns={'Specialization': 'specialty'}, inplace=True)

    # 3. Rename ID column
    if 'Doctor_ID' in doctors_df.columns:
        doctors_df.rename(columns={'Doctor_ID': 'doctor_id'}, inplace=True)

    # 4. Select and reorder columns, now including years_experience
    final_columns = ['doctor_id', 'doctor_name', 'specialty', 'years_experience']
    if all(col in doctors_df.columns for col in final_columns):
        processed_df = doctors_df[final_columns]
        
        # Save the processed file, overwriting the original
        processed_df.to_csv(doctors_file_path, index=False)
        print(f' -> Successfully processed and standardized {doctors_file_path}.')
    else:
        print(f'ERROR: Could not create all required columns: {final_columns}')
        print('Please ensure your CSV contains doctor_id, first_name, last_name, specialty, and years_experience.')
        sys.exit(1)

except FileNotFoundError:
    print(f'ERROR: The file {doctors_file_path} was not found.')
    print('Please download it from the Kaggle dataset and place it in the data/ directory.')
    sys.exit(1)
except Exception as e:
    print(f'An error occurred during data processing: {e}')
    sys.exit(1)
"
# Check if the python script failed
if [ $? -ne 0 ]; then
    echo "Exiting due to an error in the data processing step."
    exit 1
fi
# --- END OF CHANGES ---


echo "[4/5] Generating synthetic patient and schedule data..."
python -c "
import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta

fake = Faker()

# Generate Patients
print(' -> Generating data/patients.csv...')
patient_columns = ['patient_id', 'name', 'dob', 'phone', 'email', 'gender', 'address', 'emergency_contact_name', 'emergency_contact_phone']
patients = []
for i in range(50):
    patients.append({'patient_id': f'PAT{1000 + i}', 'name': fake.name(), 'dob': fake.date_of_birth(minimum_age=18, maximum_age=90).strftime('%d-%m-%Y'), 'phone': fake.phone_number(), 'email': f'patient{1000+i}@notreal.com', 'gender': random.choice(['Male', 'Female', 'Other']), 'address': fake.address().replace('\n', ', '), 'emergency_contact_name': fake.name(), 'emergency_contact_phone': fake.phone_number()})
try: pd.read_csv('data/patients.csv')
except FileNotFoundError: pd.DataFrame(columns=patient_columns).to_csv('data/patients.csv', index=False)
pd.DataFrame(patients).to_csv('data/patients.csv', mode='a', header=False, index=False)


# Generate Schedules for all doctors from the processed CSV
print(' -> Generating data/schedules.xlsx...')
doctors_df = pd.read_csv('data/doctors.csv')
writer = pd.ExcelWriter('data/schedules.xlsx', engine='openpyxl')
start_date = datetime.now().date() + timedelta(days=1)

for index, doc in doctors_df.iterrows():
    doctor_name = doc['doctor_name']
    schedule_data = []
    for day in range(14):
        current_date = start_date + timedelta(days=day)
        for hour in range(8, 18):
            for minute in [0, 15, 30, 45]:
                slot_time = datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute)
                if 12 <= hour < 13: status = 'Blocked'
                elif random.choice([True, False, False, False]): status = 'Blocked'
                else: status = 'Available'
                schedule_data.append({'slot_iso': slot_time.isoformat(), 'status': status, 'booked_by': ''})
    df_schedule = pd.DataFrame(schedule_data)
    df_schedule.to_excel(writer, sheet_name=doctor_name, index=False)
writer.close()
print(' -> Data generation complete.')
"

# Acknowledge form path requirement
echo "[5/5] Acknowledging form path requirement..."
echo "NOTE: The application is configured to look for the intake form at '/mnt/data/New Patient Intake Form (1).pdf'."

# Run Streamlit app
echo "Starting the Streamlit application..."
streamlit run src/main.py
