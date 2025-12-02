(() => {
    const fileInput = document.getElementById('faqFileInput');
    const previewBtn = document.getElementById('faqPreviewBtn');
    const uploadBtn = document.getElementById('faqUploadBtn');
    const previewContainer = document.getElementById('faqPreviewContainer');
    const msgEl = document.getElementById('faqMsg');
    
    let selectedFile = null;

    function showMsg(text, type = 'info') {
        msgEl.style.display = text ? 'block' : 'none';
        msgEl.innerText = text || '';
        msgEl.className = '';
        msgEl.classList.add('alert');
        if (type === 'success') msgEl.classList.add('alert-success');
        else if (type === 'danger') msgEl.classList.add('alert-danger');
        else msgEl.classList.add('alert-info');
    }

    fileInput.addEventListener('change', (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f) {
            selectedFile = null;
            previewBtn.disabled = true;
            uploadBtn.disabled = true;
            previewContainer.style.display = 'none';
            return;
        }
        const name = f.name.toLowerCase();
        if (!(name.endsWith('.xls') || name.endsWith('.xlsx'))) {
            showMsg('Invalid file type. Please select an .xls or .xlsx file.', 'danger');
            fileInput.value = '';
            selectedFile = null;
            previewBtn.disabled = true;
            uploadBtn.disabled = true;
            return;
        }
        selectedFile = f;
        showMsg('File ready for preview.', 'info');
        previewBtn.disabled = false;
        uploadBtn.disabled = false;
        // close any open preview when a new file is selected
        try {
            const controls = document.getElementById('faqPreviewControls');
            if (controls) controls.remove();
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';
            previewBtn.innerText = 'Preview File';
        } catch (_err) {
            // ignore
        }
    });

    // === Pagination-enabled preview ===
    const previewState = {
        headers: null,
        rows: null,      // full rows array (including header row at index 0)
        pageSize: 10,
        currentPage: 1,
    };

    function renderPreviewControls() {
        // create controls container if not present
        let controls = document.getElementById('faqPreviewControls');
        if (!controls) {
            controls = document.createElement('div');
            controls.id = 'faqPreviewControls';
            controls.className = 'd-flex align-items-center gap-2 mb-2';
            previewContainer.parentNode.insertBefore(controls, previewContainer);
        }
        controls.innerHTML = '';

        // page size selector
        const sizeSel = document.createElement('select');
        sizeSel.className = 'form-select form-select-sm';
        [10, 25, 50, 100].forEach(n => {
            const opt = document.createElement('option');
            opt.value = n;
            opt.innerText = `${n} / page`;
            if (n === previewState.pageSize) opt.selected = true;
            sizeSel.appendChild(opt);
        });
        sizeSel.addEventListener('change', () => {
            previewState.pageSize = parseInt(sizeSel.value, 10);
            previewState.currentPage = 1;
            renderCurrentPage();
        });
        controls.appendChild(sizeSel);

        // prev button
        const prev = document.createElement('button');
        prev.className = 'btn btn-sm btn-outline-secondary';
        prev.innerText = 'Prev';
        prev.addEventListener('click', () => {
            if (previewState.currentPage > 1) {
                previewState.currentPage -= 1;
                renderCurrentPage();
            }
        });
        controls.appendChild(prev);

        // page indicator and goto
        const pageSpan = document.createElement('div');
        pageSpan.id = 'faqPageIndicator';
        pageSpan.style.minWidth = '120px';
        pageSpan.className = 'text-muted small';
        controls.appendChild(pageSpan);

        // next button
        const next = document.createElement('button');
        next.className = 'btn btn-sm btn-outline-secondary';
        next.innerText = 'Next';
        next.addEventListener('click', () => {
            const totalPages = Math.max(1, Math.ceil((previewState.rows.length - 1) / previewState.pageSize));
            if (previewState.currentPage < totalPages) {
                previewState.currentPage += 1;
                renderCurrentPage();
            }
        });
        controls.appendChild(next);

        // goto input
        // const goto = document.createElement('input');
        // goto.type = 'number';
        // goto.className = 'form-control form-control-sm';
        // goto.style.width = '80px';
        // goto.placeholder = 'Go to';
        // goto.addEventListener('keydown', (e) => {
        //     if (e.key === 'Enter') {
        //         let v = Math.max(1, Math.floor(Number(goto.value) || 1));
        //         const totalPages = Math.max(1, Math.ceil((previewState.rows.length - 1) / previewState.pageSize));
        //         if (v > totalPages) v = totalPages;
        //         previewState.currentPage = v;
        //         renderCurrentPage();
        //     }
        // });
        // controls.appendChild(goto);

        // show total rows
        const totalInfo = document.createElement('div');
        // totalInfo.id = 'faqTotalInfo';
        totalInfo.className = 'ms-auto text-muted small';
        controls.appendChild(totalInfo);
    }

    function renderCurrentPage() {
        const rows = previewState.rows;
        const headers = previewState.headers;
        if (!rows || !headers) return;

        const totalRows = rows.length - 1; // excluding header row
        const totalPages = Math.max(1, Math.ceil(totalRows / previewState.pageSize));
        if (previewState.currentPage > totalPages) previewState.currentPage = totalPages;

        // slice rows for current page (skip header)
        const startIdx = 1 + (previewState.currentPage - 1) * previewState.pageSize;
        const endIdx = Math.min(rows.length, startIdx + previewState.pageSize);

        // build table
        previewContainer.innerHTML = '';
        const table = document.createElement('table');
        table.className = 'table table-sm table-bordered';
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headers.forEach(h => {
            const th = document.createElement('th');
            th.innerText = h || '';
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let r = startIdx; r < endIdx; r++) {
            const row = rows[r] || [];
            const tr = document.createElement('tr');
            for (let c = 0; c < headers.length; c++) {
                const td = document.createElement('td');
                td.innerText = (row && row[c] !== undefined && row[c] !== null) ? String(row[c]) : '';
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        previewContainer.appendChild(table);

        // update controls display
        const pageIndicator = document.getElementById('faqPageIndicator');
        if (pageIndicator) {
            pageIndicator.innerText = `Page ${previewState.currentPage} / ${totalPages}`;
        }
        // const totalInfo = document.getElementById('faqTotalInfo');
        // if (totalInfo) {
        //     totalInfo.innerText = `${totalRows} rows total`;
        // }

        // enable/disable Prev/Next
        const controls = document.getElementById('faqPreviewControls');
        if (controls) {
            const [_sizeSel, prevBtn, nextBtn] = controls.querySelectorAll('select, button');
            if (prevBtn) prevBtn.disabled = previewState.currentPage <= 1;
            if (nextBtn) nextBtn.disabled = previewState.currentPage >= totalPages;
        }
    }

    const ORIGINAL_PREVIEW_TEXT = previewBtn.innerText || 'Preview File';
    const CLOSE_PREVIEW_TEXT = 'Close Preview';

    function closePreview() {
        const controls = document.getElementById('faqPreviewControls');
        if (controls) controls.remove();
        previewContainer.style.display = 'none';
        previewContainer.innerHTML = '';
        previewState.headers = null;
        previewState.rows = null;
        previewState.currentPage = 1;
        previewBtn.innerText = ORIGINAL_PREVIEW_TEXT;
        showMsg('Preview closed.', 'info');
    }

    // Expose an explicit reset API so other modules can reset paginator state
    // This is used by faqs_api.js after a successful upload to fully clear UI
    function reset() {
        try {
            // clear DOM preview and controls
            const controls = document.getElementById('faqPreviewControls');
            if (controls) controls.remove();
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';

            // reset internal state
            previewState.headers = null;
            previewState.rows = null;
            previewState.currentPage = 1;
            previewState.pageSize = 10;

            // reset buttons
            try { previewBtn.innerText = ORIGINAL_PREVIEW_TEXT; } catch (_e) { /* ignore */ }
            try { previewBtn.disabled = true; } catch (_e) { /* ignore */ }
            try { uploadBtn.disabled = true; } catch (_e) { /* ignore */ }

            showMsg('', 'info');
        } catch (err) {
            console.debug('FAQ paginator reset failed', err);
        }
    }

    // make reset available globally for faqs_api.js to call
    try {
        if (!globalThis.FAQPaginator) globalThis.FAQPaginator = {};
        globalThis.FAQPaginator.reset = reset;
    } catch (_e) {
        // ignore if globalThis not writable
    }

    previewBtn.addEventListener('click', async () => {
        // If preview is currently visible, close it (toggle)
        if (previewContainer.style.display && previewContainer.style.display !== 'none') {
            closePreview();
            return;
        }

        if (!selectedFile) {
            showMsg('No file selected.', 'danger');
            return;
        }

        try {
            previewContainer.innerHTML = '';
            previewContainer.style.display = 'block';
            showMsg('Parsing file, building preview...', 'info');
            const ab = await selectedFile.arrayBuffer();
            const workbook = XLSX.read(ab, { type: 'array' });
            const firstSheetName = workbook.SheetNames[0];
            const sheet = workbook.Sheets[firstSheetName];
            const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });

            if (!rows || rows.length === 0) {
                previewContainer.innerHTML = '<div class="text-muted">No data found in the first sheet.</div>';
                showMsg('No data found to preview.', 'danger');
                return;
            }

            // store state
            previewState.headers = rows[0];
            previewState.rows = rows;
            previewState.pageSize = previewState.pageSize || 10;
            previewState.currentPage = 1;

            // render controls and first page
            renderPreviewControls();
            renderCurrentPage();

            previewBtn.innerText = CLOSE_PREVIEW_TEXT;
            showMsg(`Preview loaded from sheet: ${firstSheetName}`, 'success');
        } catch (err) {
            console.error(err);
            showMsg('Failed to parse Excel file for preview. Make sure the file is a valid Excel workbook.', 'danger');
            // ensure button text is reset
            previewBtn.innerText = ORIGINAL_PREVIEW_TEXT;
            previewContainer.style.display = 'none';
        }
    });

    

    // Upload logic moved to `faqs_api.js` to keep this module single-responsibility.
    // faqs_paginator.js handles previewing and pagination only.

})();