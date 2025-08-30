import streamlit as st

pages = {
    "Databricks App Demo": [
        st.Page("./query_page.py",title="Query Page")
        , st.Page("./upload_page.py",title="Upload Page")
    ]
}

pg = st.navigation(pages)
pg.run()