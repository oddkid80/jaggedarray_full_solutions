import requests #generally included in python standard packages, but might have to install
import os #standard python package
import datetime #standard python package
import dotenv #(optional) - but utilize this to import environmental files python-dotenv
import polars as pl #polars - utilizing for transforming/writing data

#async modules that are already installed
from concurrent.futures import ThreadPoolExecutor #we'll utilize this for pooling our tasks
import asyncio #standard asyncio package

dotenv.load_dotenv()
api_url = "https://api.nasa.gov/neo/rest/v1/feed"
api_key = os.environ.get("API_KEY")

start_date = datetime.date(2020, 1, 1)
end_date = datetime.date.today()

date_list = []
current_date = start_date
while current_date <= end_date:
    date_list.append(
        {
            "start_date":current_date.strftime("%Y-%m-%d"),
            "end_date":(current_date + datetime.timedelta(days=6)).strftime("%Y-%m-%d")
        }
    )
    current_date += datetime.timedelta(days=7)
    
def pull_api(start_date:str,end_date:str):
    print(f"Pulling data for {start_date} to {end_date}")
    try:
        #set our request url
        request_url = api_url
        #set our request parameters
        request_params = {
            "start_date": start_date,
            "end_date": end_date,
            "api_key": api_key,
        }
        #make our api call
        response = requests.get(request_url,params=request_params)
        #raise an error if we get a bad response
        response.raise_for_status()
        #parse the response json
        neos = []
        for neo in response.json()["near_earth_objects"].values():
            neos+=neo
        #check if the output path exists - it not, create it
        if not os.path.exists("./data"): os.mkdir("./data")
        
        #create dataframe from our neos list
        df = pl.DataFrame(neos)
        #write dataframe out as parquet
        df.write_parquet(f"./data/neos_part_{start_date}_{end_date}.parquet")  
        
        return {"start_date":start_date,"end_date":end_date,"result":"success","exception":None}
        
    except Exception as ex:
        return {"start_date":start_date,"end_date":end_date,"result":"error","exception":str(ex)}
    

async def pull_api_async(dates:list,max_workers:int=4):
    
    #create our thread pool executor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        #create our event loop
        loop = asyncio.get_event_loop()
        #create the tasks to be executed
        tasks = [
            loop.run_in_executor(
                executor,
                pull_api,
                *(
                    d["start_date"], #start_date argument of our pull_api function
                    d["end_date"], #end_date argument of our pull_api function
                )
            )
            for d in dates
        ]
        #create a list to store the results of our execution
        results = []
        #gather the results of our tasks
        for r in await asyncio.gather(*tasks,return_exceptions=True):
            results.append(r)
    
    #return the results
    return results

#create a loop
loop = asyncio.get_event_loop()
#get "futures" of our tasks
future = asyncio.ensure_future(
    pull_api_async(
        dates=date_list,
        max_workers=4,
    )
)
#pull the results from our loop when it finishes executing
results = loop.run_until_complete(future)