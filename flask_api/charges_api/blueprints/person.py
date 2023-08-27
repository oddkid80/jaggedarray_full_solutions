from flask import Blueprint, request
import pandas as pd
import sqlalchemy
import dotenv
import os

blueprint = Blueprint("Person Blueprint",__name__)

#load .env file
dotenv.load_dotenv()

#define sql alchemy connection and engine
connection_url = (
    sqlalchemy.URL.create(
            drivername='postgresql+psycopg2'
            ,username=os.environ.get("DBUSER")
            ,password=os.environ.get("DBPASSWORD")
            ,host=os.environ.get("DBHOST")
            ,database=os.environ.get("DBNAME")
            ,query={"sslmode":"require"}
        )
)
engine = sqlalchemy.create_engine(connection_url)  

@blueprint.route("/person",methods=["GET"])
def person():
    if request.method == "GET":
        
        request_parameters = request.args.to_dict()
        
        firstname = request_parameters.get("firstname",None)
        lastname = request_parameters.get("lastname",None)
        state = request_parameters.get("state",None)
        dob = request_parameters.get("dob",None)
        
        query = f"""
        select 
            id as personid, firstname, gender, middlename, lastname, dateofbirth, statename, stateabbreviation, zipcode, address1, address2
        from users.person
        where 1=1
            {f"and lower(firstname) = '{firstname.lower()}'" if firstname else ""}
            {f"and lower(lastname) = '{lastname.lower()}'" if lastname else ""}
            {f"and dateofbirth::date = '{dob}'" if dob else ""}
            {f"and (lower(stateabbreviation) = '{state.lower()}' or lower(statename) = '{state.lower()}')" if state else ""}
        limit 500
        """     
        engine = sqlalchemy.create_engine(connection_url)  
        with engine.connect() as con:
            persons = pd.read_sql(query,con)             
    
        return persons.to_json(orient='records'), 200