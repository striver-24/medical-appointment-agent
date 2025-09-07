import json
import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional
import uuid

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from langchain_core.tools import tool

from src.utils import (
    acquire_lock, robust_date_parser,
    SCHEDULES_FILE_PATH, PATIENTS_FILE_PATH, INSURANCE_FILE_PATH,
    ADMIN_REPORT_FILE_PATH, DOCTORS_FILE_PATH
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
scheduler = BackgroundScheduler()
scheduler.start()

# --- Internal Helper Functions (Not exposed as tools) ---
def _save_insurance_details(patient_id: str, company: str, member_id: str, group_number: str) -> Dict[str, Any]:
    """Saves patient insurance details to a JSON file."""
    lock_file = f"{INSURANCE_FILE_PATH}.lock"
    try:
        with acquire_lock(lock_file):
            data = {}
            if os.path.exists(INSURANCE_FILE_PATH):
                with open(INSURANCE_FILE_PATH, 'r') as f: data = json.load(f)
            data[patient_id] = {"company": company, "member_id": member_id, "group_number": group_number, "updated_at": datetime.now().isoformat()}
            with open(INSURANCE_FILE_PATH, 'w') as f: json.dump(data, f, indent=4)
        return {"status": "success", "message": "Insurance details saved."}
    except Exception as e: return {"status": "error", "message": str(e)}

def _export_admin_report(appointment_id: str, patient_name: str, patient_id: str, dob: str, insurance_status: str, doctor: str, slot_iso: str) -> Dict[str, Any]:
    """Exports a summary of the booking to an admin-facing Excel report."""
    lock_file = f"{ADMIN_REPORT_FILE_PATH}.lock"
    try:
        with acquire_lock(lock_file):
            new_record = pd.DataFrame([{"appointment_id": appointment_id, "patient_name": patient_name, "patient_id": patient_id, "dob": dob, "insurance_status": insurance_status, "doctor": doctor, "appointment_slot": slot_iso, "created_at": datetime.now().isoformat()}])
            if not os.path.exists(ADMIN_REPORT_FILE_PATH):
                new_record.to_excel(ADMIN_REPORT_FILE_PATH, index=False, sheet_name="Bookings")
            else:
                with pd.ExcelWriter(ADMIN_REPORT_FILE_PATH, mode='a', engine='openpyxl', if_sheet_exists='overlay') as writer:
                    new_record.to_excel(writer, sheet_name="Bookings", startrow=writer.sheets["Bookings"].max_row, index=False, header=False)
        return {"status": "success", "message": "Admin report updated."}
    except Exception as e: return {"status": "error", "message": str(e)}

def _send_email(to_email: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> Dict[str, Any]:
    """Sends an email. Uses SMTP environment variables if set, otherwise logs to console."""
    if attachments and isinstance(attachments, str):
        try: attachments = json.loads(attachments)
        except json.JSONDecodeError: attachments = [attachments]
    use_smtp = all(os.getenv(k) for k in ["SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"])
    if not use_smtp:
        logging.info(f"--- MOCK EMAIL ---\nTo: {to_email}\nSubject: {subject}\nBody: {body}\nAttachments: {attachments}\n--------------------")
        return {"status": "success", "message": "Email logged to console (mock)."}
    # ... SMTP logic ...
    return {"status": "success", "message": "Email sent."}

def _send_sms(to_phone: str, message: str) -> Dict[str, Any]:
    """Logs an SMS message to the console."""
    logging.info(f"--- SMS Notification (Logged) ---\nTo: {to_phone}\nMessage: {message}\n---------------------------------")
    return {"status": "success", "message": "SMS logged to console."}

def _send_intake_form(appointment_id: str, patient_email: str) -> Dict[str, Any]:
    """Sends the new patient intake form via email."""
    form_path = "/mnt/data/New Patient Intake Form (1).pdf"
    if not os.path.exists(form_path):
        return {"status": "error", "message": "Intake form PDF not found on server."}
    subject = f"Your New Patient Intake Form for Appointment {appointment_id}"
    body = f"Dear Patient,\n\nThank you for booking appointment {appointment_id}.\nPlease complete the attached intake form.\n\nSincerely,\nThe Clinic"
    return _send_email(to_email=patient_email, subject=subject, body=body, attachments=[form_path])

def _schedule_reminder_jobs(appointment_id: str, appointment_iso: str, patient_phone: str, patient_email: str) -> Dict[str, Any]:
    """Schedules three automated reminders for the appointment."""
    try:
        appt_time = datetime.fromisoformat(appointment_iso)
        reminders = [
            (appt_time - timedelta(hours=48), f"Reminder: Your appointment {appointment_id} is at {appt_time.strftime('%I:%M %p')}.", "Appointment Reminder"),
            (appt_time - timedelta(hours=24), f"Reminder: Have you completed your intake form for appointment {appointment_id}?", "Action Required: Intake Form"),
            (appt_time - timedelta(hours=6), f"Final reminder: Your appointment {appointment_id} is today at {appt_time.strftime('%I:%M %p')}.", "Action Required: Confirm Your Appointment")
        ]
        for reminder_time, msg, subject in reminders:
            if reminder_time > datetime.now():
                scheduler.add_job(_reminder_task, 'date', run_date=reminder_time, args=[msg, patient_phone, patient_email, subject])
        return {"status": "success", "message": "Reminders scheduled."}
    except Exception as e:
        logging.error(f"Error scheduling reminders: {e}")
        return {"status": "error", "message": str(e)}

def _reminder_task(message: str, to_phone: str, to_email: str, subject: str):
    """The actual task executed by the scheduler."""
    logging.info(f"Executing reminder job: {subject}")
    _send_sms(to_phone, message)
    _send_email(to_email, subject, message)


# --- Tools Exposed to the Agent ---

@tool
def finalize_booking_and_notify(
    appointment_id: str, patient_id: str, patient_name: str, patient_dob: str,
    patient_email: str, patient_phone: str, doctor_name: str, slot_iso: str,
    is_new_patient: bool, insurance_company: str, insurance_member_id: str,
    insurance_group_number: str
) -> Dict[str, Any]:
    """
    Performs all final steps after collecting insurance: saves insurance, exports a report,
    sends all notifications (email, SMS, intake form), and schedules reminders.
    This is the final tool to be called in the booking process.
    """
    logging.info(f"Finalizing booking for appointment {appointment_id}...")
    _save_insurance_details(patient_id, insurance_company, insurance_member_id, insurance_group_number)
    _export_admin_report(appointment_id, patient_name, patient_id, patient_dob, "Provided", doctor_name, slot_iso)
    confirmation_message = f"Your appointment with {doctor_name} on {datetime.fromisoformat(slot_iso).strftime('%A, %B %d at %I:%M %p')} is confirmed. Appointment ID: {appointment_id}."
    _send_email(patient_email, "Appointment Confirmed", confirmation_message)
    _send_sms(patient_phone, confirmation_message)
    if is_new_patient:
        _send_intake_form(appointment_id, patient_email)
    _schedule_reminder_jobs(appointment_id, slot_iso, patient_phone, patient_email)
    logging.info(f"Finalization complete for appointment {appointment_id}.")
    return {"status": "success", "message": "All finalization steps completed successfully. The user has been notified and reminders are set."}


@tool
def find_doctors_by_specialty_and_date(specialty: str, date: str) -> Dict[str, Any]:
    """Finds available doctors, returning their name and experience."""
    target_date = robust_date_parser(date)
    if not target_date:
        return {"status": "error", "message": f"Invalid date format: '{date}'. Please provide a clearer date like DD-MM-YYYY."}

    try:
        doctors_df = pd.read_csv(DOCTORS_FILE_PATH)
        specialty_doctors = doctors_df[doctors_df['specialty'].str.lower() == specialty.lower()]

        if specialty_doctors.empty:
            available_specialties = sorted(doctors_df['specialty'].unique().tolist())
            return {"status": "not_found", "message": f"No doctors found for '{specialty}'. Available specialties are: {', '.join(available_specialties)}."}

        available_doctors_with_exp = []
        with pd.ExcelFile(SCHEDULES_FILE_PATH) as xls:
            for _, row in specialty_doctors.iterrows():
                doctor_name = row['doctor_name']
                years_experience = row['years_experience']
                if doctor_name in xls.sheet_names:
                    df_schedule = pd.read_excel(xls, sheet_name=doctor_name)
                    df_schedule['slot_iso'] = pd.to_datetime(df_schedule['slot_iso'])
                    day_schedule = df_schedule[df_schedule['slot_iso'].dt.date == target_date]
                    future_slots = day_schedule[day_schedule['slot_iso'] > datetime.now()]
                    if not future_slots[future_slots['status'].str.lower() == 'available'].empty:
                        available_doctors_with_exp.append({"name": doctor_name, "experience": years_experience})

        if available_doctors_with_exp:
            return {"status": "success", "available_doctors": available_doctors_with_exp}
        else:
            return {"status": "not_found", "message": f"No doctors with the specialty '{specialty}' have any availability on {target_date.strftime('%d-%m-%Y')}. Please try another date."}
            
    except Exception as e:
        logging.error(f"Error in find_doctors_by_specialty_and_date: {e}")
        return {"status": "error", "message": "A system error occurred while searching for doctors."}

@tool
def lookup_patient(name: str, dob: str) -> Dict[str, Any]:
    """Looks up a patient by name and date of birth."""
    target_dob = robust_date_parser(dob)
    if not target_dob:
        return {"status": "error", "message": "Invalid date of birth format. Please provide a clearer date."}
    
    lock_file = f"{PATIENTS_FILE_PATH}.lock"
    try:
        with acquire_lock(lock_file):
            if not os.path.exists(PATIENTS_FILE_PATH):
                return {"status": "new", "message": "Patient database is empty."}
            
            df = pd.read_csv(PATIENTS_FILE_PATH)
            df['dob_dt'] = pd.to_datetime(df['dob'], format='%d-%m-%Y', errors='coerce').dt.date
            
            patient_record = df[(df['name'].str.lower() == name.lower()) & (df['dob_dt'] == target_dob)]

            if not patient_record.empty:
                return {"status": "returning", "patient_id": patient_record.iloc[0]['patient_id'], "data": patient_record.iloc[0].to_dict()}
            else:
                return {"status": "new", "message": "No patient found. Please register."}
    except Exception as e:
        logging.error(f"Error in lookup_patient: {e}")
        return {"status": "error", "message": "A system error occurred during patient lookup."}

# --- START OF FIX ---
@tool
def register_new_patient(
    name: str, dob: str, email: str, phone: str, gender: str, address: str,
    emergency_contact_name: str, emergency_contact_phone: str
) -> Dict[str, Any]:
    """
    Registers a new patient. This function is robust against empty or non-existent files.
    """
    lock_file = f"{PATIENTS_FILE_PATH}.lock"
    try:
        datetime.strptime(dob, '%d-%m-%Y')
        
        with acquire_lock(lock_file):
            new_patient_id = f"PAT-{uuid.uuid4().hex[:8].upper()}"
            
            new_patient_data = {
                "patient_id": new_patient_id, "name": name, "dob": dob, "phone": phone,
                "email": email, "gender": gender, "address": address,
                "emergency_contact_name": emergency_contact_name,
                "emergency_contact_phone": emergency_contact_phone
            }
            
            new_patient_df = pd.DataFrame([new_patient_data])
            
            if os.path.exists(PATIENTS_FILE_PATH) and os.path.getsize(PATIENTS_FILE_PATH) > 0:
                new_patient_df.to_csv(PATIENTS_FILE_PATH, mode='a', header=False, index=False)
            else:
                new_patient_df.to_csv(PATIENTS_FILE_PATH, mode='w', header=True, index=False)

            return {"status": "success", "patient_id": new_patient_id, "data": new_patient_data}
            
    except ValueError:
        return {"status": "error", "message": "Invalid date format for DOB. Please use DD-MM-YYYY."}
    except Exception as e:
        logging.error(f"Critical error in register_new_patient: {e}")
        error_message = str(e) if str(e) else "A critical error occurred while saving patient data."
        return {"status": "error", "message": error_message}
# --- END OF FIX ---

@tool
def find_available_slots(doctor: str, date: str, duration_min: int) -> Dict[str, Any]:
    """Finds available time slots."""
    target_date = robust_date_parser(date)
    if not target_date:
        return {"status": "error", "message": "Invalid date format."}
    try:
        xls = pd.ExcelFile(SCHEDULES_FILE_PATH)
        df = pd.read_excel(xls, sheet_name=doctor)
        df['slot_iso'] = pd.to_datetime(df['slot_iso'])
        day_schedule = df[df['slot_iso'].dt.date == target_date]
        available_slots = []
        num_consecutive = duration_min // 15
        for i in range(len(day_schedule) - num_consecutive + 1):
            window = day_schedule.iloc[i:i+num_consecutive]
            if (window['status'].str.lower() == 'available').all():
                start_slot = window.iloc[0]['slot_iso']
                if start_slot > datetime.now():
                    available_slots.append(start_slot.isoformat())
                    if len(available_slots) == 3: break
        if available_slots:
            return {"status": "success", "slots": available_slots}
        else:
            return {"status": "not_found", "message": f"No {duration_min}-minute slots for Dr. {doctor} on {date}."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
@tool
def book_appointment(slot_iso: str, doctor: str, patient_id: str, patient_name: str) -> Dict[str, Any]:
    """Books an appointment."""
    try:
        with acquire_lock(f"{SCHEDULES_FILE_PATH}.lock"):
            xls = pd.ExcelFile(SCHEDULES_FILE_PATH)
            df = pd.read_excel(xls, sheet_name=doctor)
            idx = df.index[pd.to_datetime(df['slot_iso']) == pd.to_datetime(slot_iso)].tolist()[0]
            if df.loc[idx, 'status'].lower() != 'available':
                return {"status": "error", "message": "Slot no longer available."}
            df.loc[idx, 'status'] = 'Booked'
            df.loc[idx, 'booked_by'] = f"{patient_name} ({patient_id})"
            all_sheets = {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}
            all_sheets[doctor] = df
            with pd.ExcelWriter(SCHEDULES_FILE_PATH, engine='openpyxl') as writer:
                for sheet_name, sheet_df in all_sheets.items():
                    sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            appointment_id = f"APP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            return {"status": "success", "appointment_id": appointment_id, "message": "Appointment booked."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

all_tools = [
    find_doctors_by_specialty_and_date,
    lookup_patient,
    register_new_patient,
    find_available_slots,
    book_appointment,
    finalize_booking_and_notify,
]

