"""Simple test to verify emotion_detection_page works"""
import streamlit as st

st.title("Test Page")

st.write("Testing emotion_detection_page import...")

try:
    import emotion_detection_page
    st.write("Import successful!")
    st.write("Calling main()...")
    emotion_detection_page.main()
    st.write("Done!")
except Exception as e:
    st.error(f"Error: {e}")
    import traceback
    st.code(traceback.format_exc())
