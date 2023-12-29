create table public.person
	(
	id bigserial primary key
    , FirstName varchar(200)
    , LastName varchar(200)
    , Address1 varchar(500)
    , Address2 varchar(200)
    , ZipCode varchar(100)
	)
;