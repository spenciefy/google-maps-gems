import streamlit as st

pg = st.navigation({"Google Maps Gems ": [st.Page("main.py", title="Main")]})
pg.run()