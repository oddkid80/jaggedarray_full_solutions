import streamlit as st
st.header("Page for querying data")
st.write("This is the page where users can query data.")

import os
import dotenv
#loading the .env file
dotenv.load_dotenv()

#importing required modules to query and read data
import polars as pl
from databricks import sql
from databricks.sdk.config import Config

#creating configuration for authentication to databricks
config = Config()
#pulling our required variables - host, warehouse, and creating http_path
host = os.getenv("DATABRICKS_HOST")
warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"

#connecting to our databricks warehouse
with sql.connect(
    server_hostname=host,
    http_path=http_path,
    credentials_provider=lambda: config.authenticate,
) as con:
    #creating cursor objection
    cursor = con.cursor()
    #executing our query
    cursor.execute("select * from samples.nyctaxi.trips")
    #returning our result as pyarrow data
    arrow_results = cursor.fetchall_arrow()
    #creating a dataframe from our pyarrow data
    df = pl.from_arrow(arrow_results)

#rendering the data
st.data_editor(df)