import sys
import os
import streamlit as st
import pandas as pd
from langchain_core.messages import HumanMessage, AIMessage
from datetime import datetime

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent_setup import agent_executor
from src.tools import register_new_patient
from src.utils import DOCTORS_FILE_PATH

# --- Streamlit Page Configuration ---
st.set_page_config(page_title="RAGAAI Medical Scheduler", page_icon="🩺", layout="wide")

# --- Session State Initialization ---
if "page" not in st.session_state:
    st.session_state.page = "welcome"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "patient_details" not in st.session_state:
    st.session_state.patient_details = {}

def show_welcome_page():
    """Displays the interactive welcome page with a dynamic list of specialties."""
    st.image("https://storage.googleapis.com/agent-ux-rag-temp-public/healthcare_banner.png", use_column_width=True)
    st.title("Welcome to the RAGAAI AI Medical Scheduling Assistant")
    st.markdown("Your smart, simple, and secure way to book medical appointments.")

    try:
        doctors_df = pd.read_csv(DOCTORS_FILE_PATH)
        specialties = sorted(doctors_df['specialty'].unique())
        st.subheader("Our Medical Specialties")
        num_columns = 4
        cols = st.columns(num_columns)
        for i, specialty in enumerate(specialties):
            with cols[i % num_columns]:
                st.info(f"⚕️ {specialty}")
    except Exception as e:
        st.warning(f"Could not load specialties: {e}")

    st.markdown("---")
    if st.button("Start Scheduling Assistant", type="primary", use_container_width=True):
        st.session_state.page = "chat"
        st.session_state.chat_history = [
            AIMessage(content="Hello! I'm here to help you schedule your medical appointment. To start, what medical specialty are you looking for, and what date would you like to book?")
        ]
        st.rerun()

def show_registration_form():
    """Displays the new patient registration form."""
    st.title("📋 New Patient Registration")
    st.markdown("Please fill out the form below to register. All fields are required.")

    with st.form(key="registration_form"):
        st.subheader("Patient Information")
        name = st.session_state.patient_details.get("name", "")
        dob = st.session_state.patient_details.get("dob", "")
        c1, c2 = st.columns(2)
        with c1: name_input = st.text_input("Full Name", value=name)
        with c2: dob_input = st.text_input("Date of Birth (DD-MM-YYYY)", value=dob)
        c1, c2, c3 = st.columns(3)
        with c1: email_input = st.text_input("Email Address")
        with c2: phone_input = st.text_input("Phone Number")
        with c3: gender_input = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"])
        address_input = st.text_area("Full Street Address")
        st.subheader("Emergency Contact")
        c1, c2 = st.columns(2)
        with c1: emergency_name_input = st.text_input("Emergency Contact Full Name")
        with c2: emergency_phone_input = st.text_input("Emergency Contact Phone Number")

        submit_button = st.form_submit_button("Register Patient", type="primary", use_container_width=True)

        if submit_button:
            required_fields = [name_input, dob_input, email_input, phone_input, address_input, emergency_name_input, emergency_phone_input]
            if not all(required_fields):
                st.error("Please fill out all required fields.")
                return
            try:
                datetime.strptime(dob_input, '%d-%m-%Y')
            except ValueError:
                st.error("Invalid Date of Birth format. Please use DD-MM-YYYY.")
                return

            with st.spinner("Registering your details..."):
                result = register_new_patient.func(
                    name=name_input, dob=dob_input, email=email_input, phone=phone_input,
                    gender=gender_input, address=address_input,
                    emergency_contact_name=emergency_name_input, emergency_contact_phone=emergency_phone_input,
                )

            if result.get("status") == "success":
                st.success("Registration Successful!")
                st.balloons()
                patient_id = result.get("patient_id")
                confirmation_message = f"I have successfully registered the new patient. Their details are: Name: {name_input}, DOB: {dob_input}, Patient ID: {patient_id}. I should now proceed with booking their appointment. Their appointment duration is 60 minutes."
                st.session_state.chat_history.append(HumanMessage(content=confirmation_message))
                st.session_state.page = "chat"
                st.rerun()
            else:
                error_message = result.get('message', 'An unexpected error occurred. Please check the console for details.')
                st.error(f"Registration failed: {error_message}")

def show_chat_interface():
    """Displays the chatbot interface."""
    st.title("🩺 RAGAAI Scheduling Assistant")
    st.caption("Please describe your needs, and I'll guide you through the process.")

    for message in st.session_state.chat_history:
        if isinstance(message, AIMessage):
            with st.chat_message("AI"):
                st.write(message.content)
                if "please fill out our registration form" in message.content.lower():
                    if st.button("Open Registration Form", type="primary"):
                        st.session_state.page = "registration_form"
                        st.rerun()
        elif isinstance(message, HumanMessage):
            with st.chat_message("Human"): st.write(message.content)

    user_query = st.chat_input("Your message...")
    if user_query:
        st.session_state.chat_history.append(HumanMessage(content=user_query))
        with st.chat_message("Human"): st.write(user_query)
        with st.chat_message("AI"):
            with st.spinner("Thinking..."):
                if "my name is" in user_query.lower() and "dob is" in user_query.lower():
                     try:
                        name_part = user_query.lower().split("my name is")[1].split(" and my dob is")[0]
                        dob_part = user_query.lower().split("and my dob is")[1]
                        st.session_state.patient_details["name"] = name_part.strip().title()
                        st.session_state.patient_details["dob"] = dob_part.strip()
                     except Exception: pass
                response = agent_executor.invoke({"messages": st.session_state.chat_history})
                ai_response_content = response['messages'][-1].content
                st.write(ai_response_content)
        st.session_state.chat_history.append(AIMessage(content=ai_response_content))
        st.rerun()

# --- Main App Router ---
if st.session_state.page == "welcome":
    show_welcome_page()
elif st.session_state.page == "registration_form":
    show_registration_form()
else:
    show_chat_interface()
