import sys
import os
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# Add the project root directory to the Python path
# This allows us to import from the 'src' module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent_setup import agent_executor

# --- Streamlit Page Configuration ---
st.set_page_config(page_title="RAGAAI Medical Scheduler", page_icon="🩺")

st.title("🩺 RAGAAI Medical Scheduling Agent")
st.caption("Your AI assistant for booking appointments efficiently.")


# --- Session State Initialization ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello! I'm here to help you schedule your medical appointment. To get started, could you please provide your full name and date of birth (YYYY-MM-DD)?")
    ]

# --- Display Chat History ---
for message in st.session_state.chat_history:
    if isinstance(message, AIMessage):
        with st.chat_message("AI"):
            st.write(message.content)
    elif isinstance(message, HumanMessage):
        with st.chat_message("Human"):
            st.write(message.content)

# --- Handle User Input ---
user_query = st.chat_input("Your message...")
if user_query is not None and user_query.strip() != "":
    st.session_state.chat_history.append(HumanMessage(content=user_query))
    
    with st.chat_message("Human"):
        st.write(user_query)

    with st.chat_message("AI"):
        with st.spinner("Thinking..."):
            # The input to the agent is a dictionary with the chat history
            response = agent_executor.invoke({"messages": st.session_state.chat_history})
            # The response is the final message from the agent
            ai_response_content = response['messages'][-1].content
            st.write(ai_response_content)
    
    # Append the AI's response to the chat history
    st.session_state.chat_history.append(AIMessage(content=ai_response_content))
