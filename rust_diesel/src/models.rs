use diesel::prelude::*;

//Diesel person table
diesel::table! {
    person (id) {
        id -> Bigint,
        firstname -> Nullable<Varchar>,
        lastname -> Nullable<Varchar>,
        address1 -> Nullable<Varchar>,
        address2 -> Nullable<Varchar>,
        zipcode -> Nullable<Varchar>,
    }
}

//Person Struct
#[derive(Queryable,Selectable,Debug)]
#[diesel(table_name=person)]
pub struct Person {
    pub id: i64,
    pub firstname: Option<String>,
    pub lastname: Option<String>,
    pub address1: Option<String>,
    pub address2: Option<String>,
    pub zipcode: Option<String>,
}

//New Person Struct for inserting
#[derive(Insertable,Debug)]
#[diesel(table_name=person)]
pub struct NewPerson {
    pub firstname: Option<String>,
    pub lastname: Option<String>,
    pub address1: Option<String>,
    pub address2: Option<String>,
    pub zipcode: Option<String>,
}
impl NewPerson {
    pub fn new() -> NewPerson {
        NewPerson {
            firstname: None,
            lastname: None,
            address1: None,
            address2: None,
            zipcode: None,
        }
    }
}

//Custom Person Query diesel table
diesel::table! {
    custom_person_query (id) {
        id -> Bigint,
        firstname -> Nullable<Varchar>,
        lastname -> Nullable<Varchar>,
    }
}
#[derive(QueryableByName,Debug)]
#[diesel(table_name=custom_person_query)]
//Custom Person Query Struct
pub struct CustomPersonQuery {
    pub id: i64,
    pub firstname: Option<String>,
    pub lastname: Option<String>,
}