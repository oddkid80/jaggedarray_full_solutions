from flask import Flask
from blueprints.person import blueprint as person_blueprint
from blueprints.charges import blueprint as charges_blueprint


app = Flask(__name__)
app.register_blueprint(person_blueprint)
app.register_blueprint(charges_blueprint)

@app.route("/")
def app_root():
    return "API is running", 200

if __name__ == '__main__':    
    app.run()