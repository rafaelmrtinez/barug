# Upload Final Copy Feature - Implementation Guide

## Summary
This guide shows you how to add an "Upload Final Copy" button to your case detail page at http://127.0.0.1:8000/lupon_mem/cases/25/

## What You Need to Do

### 1. Database Setup
Run the SQL file I created to add the `case_document` table:
```bash
psql -U your_username -d your_database -f "d:\CAPSTONE 2\cloned_repo\barug\sql\case_documents_table.sql"
```

### 2. Views are Already Added
I've already added these functions to your `views.py`:
- `case_document_upload` - Handles file uploads
- `case_document_download` - Handles downloads
- `case_document_delete` - Handles deletions

### 3. URLs are Already Added
I've already added these routes to your `urls.py`:
- `/cases/<case_id>/documents/upload/` - Upload endpoint
- `/documents/<document_id>/download/` - Download endpoint
- `/documents/<document_id>/delete/` - Delete endpoint

### 4. Update case_detail.html Template

Add this section AFTER the "ATTACHED FORMS" section (around line 230):

```html
  <!-- ======= CASE DOCUMENTS (Final Copy, etc.) ======= -->
  <div class="d-flex align-items-center justify-content-between mb-2 mt-4 flex-wrap gap-2">
    <h6 class="text-uppercase text-muted fw-bold mb-0 d-flex align-items-center">
      {% bs_icon_cached 'file-earmark-arrow-up' extra_classes='me-1' %} Case Documents
    </h6>
  </div>

  <div class="toolbar d-flex align-items-center flex-wrap mb-2">
    {% if request.session.auth.role_name|lower != 'barangay secretary' %}
    <button class="btn btn-outline-brand" data-bs-toggle="modal" data-bs-target="#uploadDocumentModal">
      {% bs_icon_cached 'cloud-upload' extra_classes='me-1' %} Upload Final Copy
    </button>
    {% endif %}
  </div>

  <div class="table-wrap">
    <div class="table-responsive">
      <table class="table mb-0 align-middle">
        <thead>
          <tr>
            <th>{% bs_icon_cached 'file-earmark' extra_classes='me-1' %} Document</th>
            <th style="width:150px;">Type</th>
            <th style="width:180px;">Uploaded</th>
            <th class="text-end" style="width:120px;">Actions</th>
          </tr>
        </thead>
        <tbody>
        {% if case_documents %}
          {% for doc in case_documents %}
          <tr>
            <td class="fw-semibold">{{ doc.file_name }}</td>
            <td><span class="badge bg-primary">{{ doc.document_type }}</span></td>
            <td class="text-muted small">
              {{ doc.uploaded_at|date:"M d, Y" }}<br>
              <small>{{ doc.uploaded_at|time:"h:i A" }}</small>
            </td>
            <td class="text-end">
              <div class="d-flex gap-1 justify-content-end">
                <a href="{% url 'lupon_mem:case_document_download' doc.case_document_id %}" 
                   class="btn btn-outline-brand btn-sm" 
                   target="_blank"
                   title="Download">
                  {% bs_icon_cached 'download' %}
                </a>
                {% if request.session.auth.role_name|lower != 'barangay secretary' %}
                <form method="post" action="{% url 'lupon_mem:case_document_delete' doc.case_document_id %}" style="display:inline;">
                  {% csrf_token %}
                  <button type="submit" 
                          class="btn btn-outline-danger btn-sm" 
                          onclick="return confirm('Delete this document?')"
                          title="Delete">
                    {% bs_icon_cached 'trash' %}
                  </button>
                </form>
                {% endif %}
              </div>
            </td>
          </tr>
          {% endfor %}
        {% else %}
          <tr>
            <td colspan="4" class="text-center text-muted py-4">
              {% bs_icon_cached 'inbox' extra_classes='me-2' %} No documents uploaded yet.
            </td>
          </tr>
        {% endif %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Upload Document Modal -->
  <div class="modal fade" id="uploadDocumentModal" tabindex="-1" aria-labelledby="uploadDocumentLabel" aria-hidden="true">
    <div class="modal-dialog">
      <div class="modal-content" style="border-radius:12px;">
        <div class="modal-header" style="border-bottom:1px solid var(--line);">
          <h5 class="modal-title d-flex align-items-center gap-2" id="uploadDocumentLabel">
            {% bs_icon_cached 'cloud-upload' %} Upload Case Document
          </h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <form method="post" action="{% url 'lupon_mem:case_document_upload' case_id %}" enctype="multipart/form-data">
          {% csrf_token %}
          <div class="modal-body" style="padding:1.25rem;">
            <div class="mb-3">
              <label for="documentType" class="form-label">Document Type</label>
              <select class="form-select" name="document_type" id="documentType" required>
                <option value="FINAL_COPY">Final Copy</option>
                <option value="SETTLEMENT_COPY">Settlement Copy</option>
                <option value="SUPPORTING_DOC">Supporting Document</option>
                <option value="OTHER">Other</option>
              </select>
            </div>
            <div class="mb-3">
              <label for="documentFiles" class="form-label">Select Files</label>
              <input type="file" class="form-control" name="documents[]" id="documentFiles" multiple accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" required>
              <small class="text-muted">Accepted: PDF, Word, Images. You can select multiple files.</small>
            </div>
            <div class="mb-3">
              <label for="documentDescription" class="form-label">Description (Optional)</label>
              <textarea class="form-control" name="description" id="documentDescription" rows="2" placeholder="Add notes about this document..."></textarea>
            </div>
          </div>
          <div class="modal-footer" style="border-top:1px solid var(--line);">
            <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-brand btn-sm">
              {% bs_icon_cached 'cloud-upload' extra_classes='me-1' %} Upload
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
```

### 5. Update views_cases.py to Pass Documents to Template

Find the `case_detail` function in `views_cases.py` and add this code to fetch documents:

```python
# Add this near the end of the function, before the return render() statement:

# Get case documents
with connection.cursor() as cur:
    cur.execute("""
        SELECT case_document_id, document_type, file_name, file_path, 
               uploaded_at, description
        FROM case_document
        WHERE blotter_case_id = %s AND is_deleted = FALSE
        ORDER BY uploaded_at DESC
    """, [case_id])
    case_documents = []
    for row in cur.fetchall():
        case_documents.append({
            'case_document_id': row[0],
            'document_type': row[1],
            'file_name': row[2],
            'file_path': row[3],
            'uploaded_at': row[4],
            'description': row[5]
        })

# Then add 'case_documents': case_documents to the context dictionary in the return statement
```

## How It Works

1. **Upload Button**: Click "Upload Final Copy" button on case detail page
2. **Modal Opens**: A modal appears where you can:
   - Select document type (Final Copy, Settlement Copy, etc.)
   - Choose one or more files
   - Add optional description
3. **Upload**: Files are uploaded to Supabase Storage
4. **Database**: File metadata is stored in `case_document` table
5. **Display**: Documents appear in a table below the forms section
6. **Download**: Click download icon to view/download documents
7. **Delete**: Click trash icon to soft-delete documents

## File Storage

Files are stored in Supabase Storage at:
```
blotter/{case_id}/documents/{unique_filename}
```

## Security

- Only Lupon members and treasurers can upload/delete
- Barangay secretaries can only view
- Files are stored with unique UUIDs to prevent conflicts
- Soft delete (is_deleted flag) preserves audit trail

## Testing

1. Run the SQL migration
2. Restart your Django server
3. Go to http://127.0.0.1:8000/lupon_mem/cases/25/
4. Click "Upload Final Copy"
5. Select a PDF file
6. Upload and verify it appears in the table

## Troubleshooting

If you get errors:
- Check that the `case_document` table exists in your database
- Verify Supabase credentials are configured in settings.py
- Check that the URL routes are properly added
- Ensure the view functions are imported correctly
