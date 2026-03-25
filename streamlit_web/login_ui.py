import streamlit as st

# Set the page configuration
st.set_page_config(page_title='Login', page_icon=':guardsman:', layout='centered', initial_sidebar_state='collapsed')

# Load logo
st.image('path/to/naturen_flow_logo.png', width=200)

# Style for dark theme
st.markdown('<style>body{background-color: #1d1d1d; color: #ffffff;} .stTextInput {background-color: #2a2a2a; color: #ffffff;} .stButton {background-color: #4caf50;}</style>', unsafe_allow_html=True)

st.title('Login to Naturen Flow')

# Username input
username = st.text_input('Username', '')

# Password input
password = st.text_input('Password', '', type='password')

# Authentication button
if st.button('Login'):
    # Here you would add the logic for authentication against the database and config.
    if authenticate(username, password):  # Assuming you have an authenticate function defined elsewhere
        st.success('Logged in successfully!')
        # Redirect or load user dashboard
    else:
        st.error('Invalid username or password')
