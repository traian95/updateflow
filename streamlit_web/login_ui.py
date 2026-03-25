import streamlit as st

# Function to create login UI

def login_ui():
    st.title("Welcome to UpdateFlow")
    st.markdown("## Please log in to continue")

    # Centered card
    with st.container():
        st.write("")  # Empty line for padding
        card = st.container()
        with card:
            # Logo at the top
            st.image("path_to_your_logo.png", width=200)
            st.text_input("Username", placeholder="Enter your username", key='username')
            st.text_input("Password", placeholder="Enter your password", type='password', key='password')
            st.button("Login", key='login_button', style="background-color: #4CAF50; color: white; padding: 10px; border: none; cursor: pointer;")

# Main function
if __name__ == '__main__':
    login_ui()