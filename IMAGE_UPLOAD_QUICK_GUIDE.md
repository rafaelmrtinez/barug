# Quick Setup Guide: Person Image Upload

## ✅ What Was Added

1. **Image upload field** in resident profiling form
2. **Live image preview** before submission
3. **Photo display** in resident list with circular avatars
4. **Initials placeholder** when no photo exists

## 🚀 Setup Steps

### Step 1: Update Supabase Function
Run this SQL in your Supabase SQL Editor:

```sql
-- File: sql/update_profile_resident_lupon_with_image.sql
```

This adds the `p_person_img` parameter to the `profile_resident_lupon` function.

### Step 2: Test the Feature

1. **Upload a photo:**
   - Go to: `http://127.0.0.1:8000/lupon_mem/profiling/personal-info/`
   - Fill in the form
   - Click "Choose File" under Profile Photo
   - Select an image (JPG, PNG, or GIF)
   - See the preview appear
   - Click "Continue" and submit

2. **View photos:**
   - Go to: `http://127.0.0.1:8000/lupon_mem/resident-list/`
   - See circular avatars in the Photo column
   - Residents with photos show their image
   - Residents without photos show initials (e.g., "JD")

## 📁 Files Changed

- ✅ `bhw/forms.py` - Added image field
- ✅ `lupon_mem/views_profiling.py` - Handle image upload
- ✅ `lupon_mem/views_residents.py` - Fetch images from DB
- ✅ `lupon_mem/templates/lupon_mem/profiling/personal_info.html` - Upload UI
- ✅ `lupon_mem/templates/lupon_mem/resident_list.html` - Display images

## 🎨 UI Features

### Profiling Form
- File input with "Choose File" button
- Live preview shows selected image
- Optional field (can skip)
- Accepts: JPG, PNG, GIF

### Resident List
- New "Photo" column (first column)
- Circular avatars (40x40px)
- Brand color border (#7C2D3E)
- Initials fallback for no image

## 💾 How Images Are Stored

Images are converted to base64 data URIs and stored in the `person_img` text field:

```
data:image/jpeg;base64,/9j/4AAQSkZJRg...
```

**Pros:**
- No external file storage needed
- Simple implementation
- Works immediately

**Cons:**
- Increases database size
- Not ideal for very large images

## ⚠️ Important Notes

1. **Image Size**: Recommend keeping images under 5MB
2. **Format**: Only image files accepted (JPG, PNG, GIF)
3. **Optional**: Photo upload is not required
4. **Database**: Images stored as base64 text in `person.person_img`

## 🧪 Testing Checklist

- [ ] Upload JPG image ✓
- [ ] Upload PNG image ✓
- [ ] Upload GIF image ✓
- [ ] Preview shows correctly ✓
- [ ] Submit without image (optional) ✓
- [ ] Image appears in resident list ✓
- [ ] Initials show when no image ✓
- [ ] Supabase function updated ✓

## 🔧 Troubleshooting

**Image not saving?**
- Check if Supabase function was updated
- Verify `person_img` column exists in database
- Check browser console for errors

**Image not displaying?**
- Verify image data is in database
- Check if base64 string is complete
- Ensure image column is fetched in query

**Preview not working?**
- Check browser console for JavaScript errors
- Verify file input has correct name attribute
- Ensure FileReader API is supported

## 📝 Example Usage

```python
# In views_profiling.py
if 'person_img' in request.FILES:
    import base64
    img_file = request.FILES['person_img']
    img_data = base64.b64encode(img_file.read()).decode('utf-8')
    data['person_img'] = f"data:{img_file.content_type};base64,{img_data}"
```

```html
<!-- In resident_list.html -->
{% if r.person_img %}
    <img src="{{ r.person_img }}" style="width:40px;height:40px;border-radius:50%;">
{% else %}
    <div style="...">{{ r.first_name.0 }}{{ r.last_name.0 }}</div>
{% endif %}
```

---

**Need more details?** See `PERSON_IMAGE_UPLOAD_FEATURE.md`
