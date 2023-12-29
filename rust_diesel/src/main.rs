mod models;
mod utils;

use diesel::prelude::*;
use diesel::dsl::{sql,sql_query};
use diesel::sql_types::Bool;

fn main() {
    let mut _con = utils::establish_connection();

    //Inserting New Record
    let mut new_person = models::NewPerson::new();
    new_person.firstname = Some("Jagged".to_string());
    new_person.lastname = Some("Array".to_string());
    new_person.address1 = Some("111 Super Rd.".to_string());
    new_person.zipcode = Some("00001".to_string());

    let inserted_record:models::Person = diesel::insert_into(models::person::table)
        //Pass struct as values
        .values(&new_person)
        //Return result (new record) as a Person struct
        .returning(models::Person::as_returning())
        //Get result utilizing the connection
        .get_result(&mut _con)
        .expect("Error");
    println!("{:?}",inserted_record);

    //Querying Records
    let persons:Vec<models::Person> = models::person::table
        //filter to where first name equals "jagged"
        .filter(models::person::firstname.eq("Jagged"))
        //limits output to 5 rows
        .limit(5)
        //put the results into the Person struct
        .select(models::Person::as_select())
        //utilize the connection object
        .load(&mut _con)
        .expect("Error");
    println!("{:?}",persons);

    //Custom Query utilizing diesel sql
    let persons_custom_filter:Vec<models::Person> = models::person::table
        //filter to where first name equals "jagged"
        .filter(
            sql::<Bool>("lower(firstname) = 'jagged'")
        )
        //limits output to 5 rows
        .limit(5)
        //put the results into the Person struct
        .select(models::Person::as_select())
        //utilize the connection object
        .load(&mut _con)
        .expect("Error");
    println!("{:?}",persons_custom_filter);

    //Custom Query utilizing hard coded SQL
    let custom_query = 
        "select id, firstname, lastname 
        from public.person 
        limit 5";
    let persons_custom_query:Vec<models::CustomPersonQuery> = sql_query(custom_query)
        .load::<models::CustomPersonQuery>(&mut _con)
        .unwrap();
        println!("{:?}",persons_custom_query);
}
