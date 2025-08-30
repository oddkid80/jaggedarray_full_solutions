import streamlit as st

st.header("Upload Page")
st.write("This is the page where users can upload data.")

import polars as pl

#uploader
file = st.file_uploader("Upload a file",type=["csv"],accept_multiple_files=False)
#if someone passed in a file, read it and render it
if file:
    df = pl.read_csv(file)
    st.data_editor(df)

import os
import dotenv
#loading the .env file
dotenv.load_dotenv()

#import tempfile to manage writing the table from the app to databricks
import tempfile
#importing required modules to query data and upload to volumes
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

#creating configuration for authentication to databricks
config = Config()
#create workspace client for uploading file to volumes
workspace_client = WorkspaceClient()
#pulling our required variables - host, warehouse, and creating http_path
host = os.getenv("DATABRICKS_HOST")
warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"

#if a file has been uploaded
if file:
    #if the submit button has been clicked
    if st.button("Submit"):
        #will show a spinner while the rest of the code is executed
        with st.spinner("Uploading file and creating table..."):
            #creating a temporary file for the data to be stored before it's written to databricks
            with tempfile.NamedTemporaryFile(delete=True,suffix=".parquet") as tmp_file:
                file_path = tmp_file.name
                file_name = file_path.split("/")[-1]

                #creating destination volume path for the file
                destination_volume_file = f"/Volumes/apps/my_app/tmp/{file_name}"
                
                #writing the parquet file out
                df.write_parquet(file_path,compression="gzip")
                
                #uploading the file to the databricks volume
                with open(file_path,"rb") as f:
                    workspace_client.files.upload(file_path=destination_volume_file,contents=f.read(),overwrite=True)
                
            with sql.connect(
                server_hostname=host,
                http_path=http_path,
                credentials_provider=lambda: config.authenticate,
            ) as con:
                #create your cursor
                cursor = con.cursor()
                #creating sql to create a databricks table utilizing the parquet
                create_table_sql = f"""
                    create or replace table apps.my_app.a1c_data as
                        select *
                        from parquet.`{destination_volume_file}`
                """
                #trying to create the table
                exception = None
                try:
                    cursor.execute(create_table_sql)
                except Exception as ex:
                    exception = ex
                finally:
                    workspace_client.files.delete(destination_volume_file)
                    if exception: raise exception
        #creating success message
        st.success("File uploaded and table created successfully!")