# Superadmin Module Setup

## Overview
The superadmin module has been created by copying the staff_admin module and modifying it to work exclusively for users with the "Super Admin" role.

## Changes Made

### 1. Module Structure
- Copied entire `staff_admin` directory to `superadmin`
- Updated all internal references from `staff_admin` to `superadmin`

### 2. Role Restriction
- Changed `ADMIN_ROLE = "Admin"` to `ADMIN_ROLE = "Super Admin"` in views.py
- All views now require "Super Admin" role instead of "Admin" role

### 3. URL Configuration
- Updated `app_name` in urls.py to "superadmin"
- All URL redirects updated to use "superadmin:" namespace
- Added superadmin URLs to main barug/urls.py

### 4. Templates and Static Files
- Renamed template directory from `staff_admin` to `superadmin`
- Renamed static directory from `staff_admin` to `superadmin`
- Updated all template references in views.py

### 5. Django Settings
- Added "superadmin" to INSTALLED_APPS
- Added superadmin template directory to TEMPLATES
- Added superadmin context processor

### 6. App Configuration
- Updated apps.py to use SuperadminConfig class
- Updated app name to 'superadmin'

## Access Control
- Only users with role "Super Admin" can access superadmin pages
- All existing functionality from staff_admin is preserved
- Uses same models and database functions as staff_admin

## URL Structure
- Superadmin accessible at `/superadmin/` instead of `/admin/`
- All sub-URLs follow same pattern as staff_admin but under superadmin namespace

## Security
- Role-based access control enforced at view level
- Session login required for all views
- No cache headers applied to prevent sensitive data caching