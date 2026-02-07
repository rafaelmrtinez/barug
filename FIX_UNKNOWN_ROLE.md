# Fix for "Unknown" Role Issue

## Problem
The `staff_login2` function returns "Unknown" as the role name because it only checks the `staff_role_assignment` table, but your staff records still use the legacy `staff.role_id` column.

## Solution
Run the SQL script `fix_staff_login2.sql` in your database to update the function.

## How to Run
1. Open pgAdmin or your PostgreSQL client
2. Connect to your database (barug_db on 192.168.8.105)
3. Execute the contents of `fix_staff_login2.sql`

OR

Run this command in your terminal:
```bash
psql -h 192.168.8.105 -U postgres -d barug_db -f fix_staff_login2.sql
```

## What it does
The updated function will:
1. First check `staff_role_assignment` table for multi-role support
2. If empty, fall back to `staff.role_id` (legacy single role)
3. If still null, return "Unknown"

This ensures backward compatibility with existing staff records that haven't been migrated to the multi-role system yet.
