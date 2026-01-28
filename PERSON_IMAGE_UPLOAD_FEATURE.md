# Person Image Upload Feature

## Overview
Added the ability to upload and display person profile images in the resident profiling and resident list pages.

## Implementation Details

### Files Modified:

1. **`bhw/forms.py`** (MODIFIED)
   - Added `person_img` field to `ResidentPersonalInfoForm` as ImageField
   - Accepts image files (JPG, PNG, GIF)

2. **`lupon_mem/views_profiling.py`** (MODIFIED)
   - Updated `profile_personal_info` to handle file uploads
   - Converts uploaded image to base64 data URI format
   - Stores image data in session for review page
   - Passes `p_person_img` parameter to Supabase function

3. **`lupon_mem/views_residents.py`** (MODIFIED)
   - Updated `resident_list` to fetch `person_img` from database
   - Uses direct SQL query to include image data

4. **`lupon_mem/templates/lupon_mem/profiling/personal_info.html`** (MODIFIED)
   - Added file input for image upload
   - Added image preview functionality
   - Added `enctype="multipart/form-data"` to form

5. **`lupon_mem/templates/lupon_mem/resident_list.html`** (MODIFIED)
   - Added Photo column to table
   - Displays uploaded image or initials placeholder
   - Circular avatar style with brand colors

## Database Schema

The `person` table already has the `person_img` field:
```sql
person_img text null
```

This field stores the image as a base64-encoded data URI:
```
data:image/jpeg;base64,/9j/4AAQSkZJRg...
```

## Supabase Function Update Required

You need to update the `profile_resident_lupon` function in Supabase to accept the new parameter:

```sql
CREATE OR REPLACE FUNCTION profile_resident_lupon(
    p_performer_id integer,
    p_first_name text,
    p_middle_name text,
    p_last_name text,
    p_suffix text,
    p_birthdate date,
    p_sex_id integer,
    p_civil_status_id integer,
    p_nationality_id integer,
    p_religion_id integer,
    p_mobile_num text,
    p_email text,
    p_education_id integer,
    p_employment_status_id integer,
    p_residential_status_id integer,
    p_person_img text DEFAULT NULL  -- ADD THIS LINE
)
RETURNS void AS $$
BEGIN
    INSERT INTO person (
        first_name, middle_name, last_name, suffix, birthdate,
        sex_id, civil_status_id, nationality_id, religion_id,
        mobile_num, email, education_id, employment_status_id,
        residential_status_id, added_by_id, person_img  -- ADD person_img
    ) VALUES (
        p_first_name, p_middle_name, p_last_name, p_suffix, p_birthdate,
        p_sex_id, p_civil_status_id, p_nationality_id, p_religion_id,
        p_mobile_num, p_email, p_education_id, p_employment_status_id,
        p_residential_status_id, p_performer_id, p_person_img  -- ADD p_person_img
    );
END;
$$ LANGUAGE plpgsql;
```

## Features

### Upload Page (`/lupon_mem/profiling/personal-info/`)
- File input for image upload
- Live image preview before submission
- Accepts JPG, PNG, GIF formats
- Optional field (not required)

### Resident List (`/lupon_mem/resident-list/`)
- Photo column showing circular avatars
- Displays uploaded image if available
- Shows initials placeholder if no image
- Consistent styling with brand colors (#7C2D3E)

## Image Storage

Images are stored as base64-encoded data URIs in the database:
- **Pros**: No external file storage needed, simple implementation
- **Cons**: Increases database size, not ideal for very large images
- **Recommendation**: Consider adding file size validation (max 5MB)

## Usage

### To add a person with photo:
1. Navigate to `/lupon_mem/profiling/personal-info/`
2. Fill in personal information
3. Click "Choose File" under Profile Photo
4. Select an image file
5. Preview will appear below
6. Continue to review and submit

### Viewing residents with photos:
1. Navigate to `/lupon_mem/resident-list/`
2. Photo column shows circular avatars
3. If no photo: shows initials (e.g., "JD" for John Doe)
4. If photo exists: shows uploaded image

## Security Considerations

1. **File Type Validation**: Form only accepts image/* MIME types
2. **Size Limit**: Recommend adding max file size check (5MB)
3. **XSS Prevention**: Base64 encoding prevents script injection
4. **Access Control**: Only Lupon members can upload/view

## Future Enhancements

1. Add file size validation (client and server-side)
2. Image compression before upload
3. Crop/resize functionality
4. Store images in cloud storage (S3, Supabase Storage)
5. Lazy loading for image-heavy lists
6. Image optimization for faster loading

## Testing Checklist

- [ ] Upload JPG image
- [ ] Upload PNG image
- [ ] Upload GIF image
- [ ] Preview displays correctly
- [ ] Image saves to database
- [ ] Image displays in resident list
- [ ] Initials show when no image
- [ ] Form works without image (optional field)
- [ ] Large images are handled gracefully
- [ ] Invalid file types are rejected
