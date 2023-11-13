from flask import Blueprint, request
import pandas as pd
import sqlalchemy
import dotenv
import os

blueprint = Blueprint("Charges Blueprint",__name__)

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

@blueprint.route("/charges/<personid>",methods=["GET"])
def charges(personid:int):
    if request.method == "GET":
        query = f"""
            select *
            from users.charges
            where 1=1
                and personid = {personid}
            order by chargedate desc, chargecategory asc, chargeamount asc
            limit 500                    
        """
        with engine.connect() as con:
            result = pd.read_sql(query,con)
        
        return result.to_json(orient="records",date_format='iso'), 200

@blueprint.route("/charges/<personid>/summary",methods=["GET"])
def charges_summary(personid:int):
    if request.method == "GET":
        query = f"""
        select 
            sum(chargeamount) as amount_owed
            , max(case when chargecategory = 'Payment' then chargedate else null end) as last_payment
        from users.charges
        where 1=1
            and personid = {personid}
        """
        with engine.connect() as con:
            result = pd.read_sql(query,con)
        
        return result.to_json(orient="records",date_format='iso'), 200