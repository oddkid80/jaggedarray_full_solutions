use std::env;
use dotenvy::dotenv;
use diesel::pg::PgConnection;
use diesel::prelude::*;

pub fn establish_connection() -> PgConnection {
    //Load .env file
    dotenv().ok();
    //Create db_url from the DATABASE_URL environmental variable
    let db_url = env::var("DATABASE_URL").expect("Need DATABASE_URL");
    //Create our connection
    let conn = PgConnection::establish(&db_url).unwrap();
    //Return the connection
    conn
}