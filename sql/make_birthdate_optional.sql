-- Make birthdate optional in person table
ALTER TABLE person ALTER COLUMN birthdate DROP NOT NULL;
