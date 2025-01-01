from flask import Flask
from flask import request, session, redirect

import dotenv
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_auth_requests

app = Flask(__name__)
app.secret_key = os.urandom(24) 
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
dotenv.load_dotenv()

@app.route("/")
def app_root():
    return """  
        <button onclick="window.location.href='/google_login'">
            Login with Google
        </button>
    """, 200

@app.route("/google_login")
def google_login():
    #creates google login flow object
    flow = Flow.from_client_config(
        client_config={
            "web":
            {
                "client_id":os.environ.get("GOOGLE_CLIENT_ID")
                ,"client_secret":os.environ.get("GOOGLE_CLIENT_SECRET")
                ,"auth_uri":"https://accounts.google.com/o/oauth2/v2/auth"
                ,"token_uri":"https://oauth2.googleapis.com/token"
            }
        }
        ,scopes=[
            "https://www.googleapis.com/auth/userinfo.email"
            ,"https://www.googleapis.com/auth/userinfo.profile"
            ,"openid"
        ]      
    )      
    
    #redirect uri for the google callback (i.e., the route in our api that handles everything AFTER google auth)
    flow.redirect_uri = "http://localhost:10000/google_login/oauth2callback"
    
    #pulling authorization url (google login), and state to store in Flask session
    authorization_url, state = (
        flow.authorization_url(
            access_type="offline"
            ,prompt="select_account"
            ,include_granted_scopes="true"
        )
    )
    
    #connecting/storing state and final redirect AFTER login in the Flask API
    session['state'] = state
    session['final_redirect'] = "http://localhost:10000/logged_in"
    
    #redirecting to the authorization URL
    return redirect(authorization_url)

@app.route("/google_login/oauth2callback")
def auth_login_google_oauth2callback():
    #pull the state from the session
    session_state = session['state']
    redirect_uri = request.base_url
    #pull the authorization response
    authorization_response = request.url  
    #create our flow object similar to our initial login with the added "state" information
    flow = flow = Flow.from_client_config(
        client_config={
            "web":
            {
                "client_id":os.environ.get("GOOGLE_CLIENT_ID")
                ,"client_secret":os.environ.get("GOOGLE_CLIENT_SECRET")
                ,"auth_uri":"https://accounts.google.com/o/oauth2/v2/auth"
                ,"token_uri":"https://oauth2.googleapis.com/token"
            }
        }
        ,scopes=[
            "https://www.googleapis.com/auth/userinfo.email"
            ,"https://www.googleapis.com/auth/userinfo.profile"
            ,"openid"
        ]  
        ,state=session_state    
    )  
    
    flow.redirect_uri = redirect_uri  
    #fetch token
    flow.fetch_token(authorization_response=authorization_response)
    #get credentials
    credentials = flow.credentials
    #verify token, while also retrieving information about the user
    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token
        ,request=google_auth_requests.Request()
        ,audience=os.environ.get("GOOGLE_CLIENT_ID")
    )    
    #setting the user information to an element of the session
    #you'll generally want to do something else with this (login, store in JWT, etc)
    session["id_info"] = id_info
    
    #redirecting to the final redirect (i.e., logged in page)
    redirect_response = redirect(session['final_redirect'])   
        
    return redirect_response

@app.route("/logged_in")
def logged_in():
    #retrieve the users picture
    picture = session["id_info"]["picture"]
    #retrieve the users email
    email = session["id_info"]["email"]
    
    #render the email/picture
    return f"""
    <h1>Logged In</h1>
    <p>Email: {email}</p>
    <img src="{picture}" />
    """, 200

if __name__ == '__main__':    
    app.run(
        port=10000,
        debug=True,
    )