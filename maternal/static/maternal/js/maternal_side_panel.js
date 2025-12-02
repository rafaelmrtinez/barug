(function () {
    'use strict';

    // Expose fetchSidePanel globally so it can be called from row clicks
    window.fetchMaternalSidePanel = async function(mhrId) {
        await fetchSidePanel(mhrId);
    };

    async function fetchSidePanel(mhrId) {
        if (!mhrId) return;
        try {
            const resp = await fetch(`/maternal/api/v1/mhr/side-panel/?mhr_id=${encodeURIComponent(mhrId)}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json' }
            });

            let data = null;
            try { data = await resp.json(); } catch (_e) { /* ignore */ }

            if (!resp.ok) {
                const msg = data && data.message ? data.message : `Server returned ${resp.status}`;
                if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') globalThis.MHRToast.show(msg, false);
                return;
            }

            const result = data && data.result ? data.result : {};
            const visit_schedules = data && data.visit_schedules ? data.visit_schedules : [];
            const postpartum_visit_schedules = data && data.postpartum_visit_schedules ? data.postpartum_visit_schedules : [];
            const maternal_anc_visits = data && data.maternal_anc_visit_history ? data.maternal_anc_visit_history : [];
            const latest_union = data && data.latest_scheduled_visit ? data.latest_scheduled_visit : null;

            // Debug logging
            console.log('Side panel data received:', data);
            console.log('Maternal ANC visits:', maternal_anc_visits);
            console.log('Postpartum visit schedules:', postpartum_visit_schedules);

            // latest schedule is the first element (API returns ordered DESC)
            const latest_schedule = Array.isArray(visit_schedules) && visit_schedules.length ? visit_schedules[0] : null;
            
            // Find latest PENDING postpartum schedule (status_id = 1)
            const latest_pending_postpartum = Array.isArray(postpartum_visit_schedules) && postpartum_visit_schedules.length
                ? postpartum_visit_schedules.find(s => s.status_id === 1)
                : null;

            // populate fields (fall back to empty strings)
            const setText = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val != null && String(val) !== '' ? String(val) : '-';
            };
            // If the API returns the ANC trimester tracker directly, it'll contain
            // keys like 'trimester_no' or 'trimester_label'. Support both shapes
            // for backwards-compatibility.
            const isTrackerShape = result && (('trimester_no' in result) || ('trimester_label' in result));

            if (Array.isArray(result) && result.length) {
                // Expect an array of trimester tracker objects. Render exactly three cards.
                const container = document.getElementById('lmhr_cards');
                if (container) {
                    // clear existing content
                    container.innerHTML = '';
                    // render each tracker as a small card-like row
                    result.forEach(function (tracker) {
                        const card = document.createElement('div');
                        card.className = 'card p-2 mb-2';

                        const title = document.createElement('div');
                        title.className = 'card-title small fw-semibold mb-1';
                        title.textContent = tracker.trimester_label || ('Trimester ' + (tracker.trimester_no || '?'));
                        card.appendChild(title);

                        const body = document.createElement('div');
                        body.className = 'small';

                        const makeRow = function (label, value) {
                            const row = document.createElement('div');
                            row.className = 'kpi';
                            const spanL = document.createElement('span');
                            spanL.textContent = label;
                            const spanV = document.createElement('span');
                            spanV.style.float = 'right';
                            spanV.textContent = value != null && String(value) !== '' ? String(value) : '-';
                            row.appendChild(spanL);
                            row.appendChild(spanV);
                            return row;
                        };

                        body.appendChild(makeRow('Min required', tracker.min_required));
                        body.appendChild(makeRow('Visits', tracker.visit_count));
                        body.appendChild(makeRow('Met', typeof tracker.is_met === 'boolean' ? (tracker.is_met ? 'Yes' : 'No') : '-'));
                        body.appendChild(makeRow('Remaining', tracker.remaining));

                        card.appendChild(body);
                        container.appendChild(card);
                    });
                }
                // also set a simple trim label in lv_trimester if present
                if (result[0] && result[0].trimester_label) setText('lv_trimester', result[0].trimester_label);
            } else if (isTrackerShape) {
                // single tracker object - render it into the lmhr_cards as single card
                const tracker = result;
                const container = document.getElementById('lmhr_cards');
                if (container) {
                    container.innerHTML = '';
                    const card = document.createElement('div');
                    card.className = 'card p-2 mb-2';
                    const title = document.createElement('div');
                    title.className = 'card-title small fw-semibold mb-1';
                    title.textContent = tracker.trimester_label || ('Trimester ' + (tracker.trimester_no || '?'));
                    card.appendChild(title);
                    const body = document.createElement('div');
                    body.className = 'small';
                    const makeRow = function (label, value) {
                        const row = document.createElement('div');
                        row.className = 'kpi';
                        const spanL = document.createElement('span');
                        spanL.textContent = label;
                        const spanV = document.createElement('span');
                        spanV.style.float = 'right';
                        spanV.textContent = value != null && String(value) !== '' ? String(value) : '-';
                        row.appendChild(spanL);
                        row.appendChild(spanV);
                        return row;
                    };
                    body.appendChild(makeRow('Min required', tracker.min_required));
                    body.appendChild(makeRow('Visits', tracker.visit_count));
                    body.appendChild(makeRow('Met', typeof tracker.is_met === 'boolean' ? (tracker.is_met ? 'Yes' : 'No') : '-'));
                    body.appendChild(makeRow('Remaining', tracker.remaining));
                    card.appendChild(body);
                    container.appendChild(card);
                }
                setText('lv_trimester', tracker.trimester_label || '-');
            } else {
                setText('ep_delivery_plan', result.delivery_plan || '-');
                setText('ep_nbs_plan', result.nbs_plan || '-');
                setText('h-val', result.height_cm ? result.height_cm + ' cm' : '-');
                setText('w-val', result.weight_kg ? result.weight_kg + ' kg' : '-');
                setText('lv_date', result.last_visit_date || '-');
                setText('lv_weight', result.weight_kg ? result.weight_kg + ' KG' : '-');
                setText('last_danger', result.last_danger || '-');
            }

            // Populate latest schedule card
            const scheduleCard = document.getElementById('visit_schedule_card');
            const scheduleDateEl = document.getElementById('visit_sched_date');
            const scheduleTimeEl = document.getElementById('visit_sched_time');
            const schedulePurposeEl = document.getElementById('visit_sched_purpose');
            const scheduleNotesEl = document.getElementById('visit_sched_notes');
            const scheduleCreatorEl = document.getElementById('visit_sched_creator');

            if (scheduleCard && latest_schedule) {
                const statusId = typeof latest_schedule.status_id !== 'undefined' && latest_schedule.status_id !== null ? Number(latest_schedule.status_id) : null;
                
                if (scheduleDateEl) {
                    scheduleDateEl.textContent = latest_schedule.scheduled_date_str || latest_schedule.scheduled_date || '-';
                }
                if (scheduleTimeEl) {
                    scheduleTimeEl.textContent = latest_schedule.scheduled_time_hm || latest_schedule.scheduled_time || '-';
                }
                if (schedulePurposeEl) {
                    schedulePurposeEl.textContent = latest_schedule.visit_purpose || '-';
                }
                if (scheduleNotesEl) {
                    scheduleNotesEl.textContent = latest_schedule.notes || '-';
                }
                if (scheduleCreatorEl) {
                    scheduleCreatorEl.textContent = latest_schedule.created_by_name || '-';
                }
                
                scheduleCard.style.display = '';
            } else if (scheduleCard) {
                scheduleCard.style.display = 'none';
            }

            // Populate latest PENDING postpartum schedule card
            const postpartumCard = document.getElementById('postpartum_schedule_card');
            const postpartumDateEl = document.getElementById('postpartum_sched_date');
            const postpartumTimeEl = document.getElementById('postpartum_sched_time');
            const postpartumPurposeEl = document.getElementById('postpartum_sched_purpose');
            const postpartumNotesEl = document.getElementById('postpartum_sched_notes');
            const postpartumCreatorEl = document.getElementById('postpartum_sched_creator');

            if (postpartumCard && latest_pending_postpartum) {
                if (postpartumDateEl) {
                    postpartumDateEl.textContent = latest_pending_postpartum.scheduled_date_str || latest_pending_postpartum.scheduled_date || '-';
                }
                if (postpartumTimeEl) {
                    postpartumTimeEl.textContent = latest_pending_postpartum.scheduled_time_hm || latest_pending_postpartum.scheduled_time || '-';
                }
                if (postpartumPurposeEl) {
                    postpartumPurposeEl.textContent = latest_pending_postpartum.visit_purpose || '-';
                }
                if (postpartumNotesEl) {
                    postpartumNotesEl.textContent = latest_pending_postpartum.notes || '-';
                }
                if (postpartumCreatorEl) {
                    postpartumCreatorEl.textContent = latest_pending_postpartum.created_by_name || '-';
                }
                
                postpartumCard.style.display = '';
            } else if (postpartumCard) {
                postpartumCard.style.display = 'none';
            }

            // Populate schedule history table
            const fillScheduleHistoryTable = (tbodyId, rows) => {
                const tbody = document.getElementById(tbodyId);
                if (!tbody) return;
                tbody.innerHTML = '';
                
                const paginationNav = document.getElementById('schedule_pagination_nav');
                
                if (!Array.isArray(rows) || rows.length === 0) {
                    const tr = document.createElement('tr');
                    const td = document.createElement('td');
                    td.setAttribute('colspan', '6');
                    td.className = 'text-center small text-muted';
                    td.textContent = 'No scheduled visits.';
                    tr.appendChild(td);
                    tbody.appendChild(tr);
                    if (paginationNav) paginationNav.style.display = 'none';
                    return;
                }

                // Pagination setup
                const itemsPerPage = 5;
                let currentPage = 1;
                const totalPages = Math.ceil(rows.length / itemsPerPage);

                const renderPage = (page) => {
                    tbody.innerHTML = '';
                    const start = (page - 1) * itemsPerPage;
                    const end = start + itemsPerPage;
                    const pageRows = rows.slice(start, end);

                    pageRows.forEach(function (r) {
                        const tr = document.createElement('tr');
                        const scheduledDate = r.scheduled_date_str || r.scheduled_date || '-';
                        const scheduledTime = r.scheduled_time_hm || (r.scheduled_time ? (String(r.scheduled_time).slice(0,5)) : '-');
                        const purpose = r.visit_purpose || '-';
                        const notes = r.notes || '-';
                        const creator = r.created_by_name || '-';
                        const status = r.status_name || '-';
                        const statusId = typeof r.status_id !== 'undefined' && r.status_id !== null ? Number(r.status_id) : null;

                        const makeTd = (txt) => { 
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.textContent = txt;
                            td.title = txt;
                            return td;
                        };

                        const makeClickableTd = (txt, title) => {
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.style.cursor = 'pointer';
                            td.style.color = '#6d2932';
                            td.style.textDecoration = 'underline';
                            td.textContent = txt;
                            td.title = 'Click to view full ' + title;
                            td.onclick = () => {
                                const modal = new bootstrap.Modal(document.getElementById('scheduleTextDetailModal'));
                                document.getElementById('scheduleTextDetailModalLabel').textContent = title;
                                document.getElementById('scheduleTextDetailContent').textContent = txt;
                                modal.show();
                            };
                            return td;
                        };

                        tr.appendChild(makeTd(scheduledDate));
                        tr.appendChild(makeTd(scheduledTime));
                        tr.appendChild(makeClickableTd(purpose, 'Purpose'));
                        tr.appendChild(makeClickableTd(notes, 'Notes'));
                        tr.appendChild(makeTd(creator));
                        
                        // status badge
                        const tdStatus = document.createElement('td');
                        tdStatus.style.overflow = 'hidden';
                        tdStatus.style.textOverflow = 'ellipsis';
                        tdStatus.style.whiteSpace = 'nowrap';
                        const span = document.createElement('span');
                        span.className = 'badge';
                        if (statusId === 1) { span.className += ' bg-warning text-dark'; }
                        else if (statusId === 2) { span.className += ' bg-success'; }
                        else if (statusId === 3) { span.className += ' bg-info text-dark'; }
                        else if (statusId === 4) { span.className += ' bg-secondary'; }
                        else if (statusId === 5) { span.className += ' bg-danger'; }
                        else { span.className += ' bg-light text-dark'; }
                        span.textContent = status;
                        tdStatus.appendChild(span);
                        tr.appendChild(tdStatus);
                        
                        tbody.appendChild(tr);
                    });
                };

                const renderPagination = () => {
                    if (!paginationNav) return;
                    const paginationList = paginationNav.querySelector('.pagination');
                    if (!paginationList) return;
                    
                    paginationList.innerHTML = '';

                    // Previous button
                    const prevLi = document.createElement('li');
                    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
                    const prevLink = document.createElement('a');
                    prevLink.className = 'page-link';
                    prevLink.href = '#';
                    prevLink.textContent = 'Previous';
                    prevLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage > 1) {
                            currentPage--;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    prevLi.appendChild(prevLink);
                    paginationList.appendChild(prevLi);

                    // Page numbers
                    for (let i = 1; i <= totalPages; i++) {
                        const li = document.createElement('li');
                        li.className = `page-item ${i === currentPage ? 'active' : ''}`;
                        const link = document.createElement('a');
                        link.className = 'page-link';
                        link.href = '#';
                        link.textContent = i;
                        link.onclick = (e) => {
                            e.preventDefault();
                            currentPage = i;
                            renderPage(currentPage);
                            renderPagination();
                        };
                        li.appendChild(link);
                        paginationList.appendChild(li);
                    }

                    // Next button
                    const nextLi = document.createElement('li');
                    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
                    const nextLink = document.createElement('a');
                    nextLink.className = 'page-link';
                    nextLink.href = '#';
                    nextLink.textContent = 'Next';
                    nextLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage < totalPages) {
                            currentPage++;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    nextLi.appendChild(nextLink);
                    paginationList.appendChild(nextLi);
                };

                // Initial render
                renderPage(currentPage);
                if (totalPages > 1) {
                    renderPagination();
                    if (paginationNav) paginationNav.style.display = '';
                } else {
                    if (paginationNav) paginationNav.style.display = 'none';
                }
            };

            // Populate postpartum visit schedule history table
            const fillPostpartumScheduleHistoryTable = (tbodyId, rows) => {
                const tbody = document.getElementById(tbodyId);
                if (!tbody) return;
                tbody.innerHTML = '';
                
                const paginationNav = document.getElementById('postpartum_pagination_nav');
                
                if (!Array.isArray(rows) || rows.length === 0) {
                    const tr = document.createElement('tr');
                    const td = document.createElement('td');
                    td.setAttribute('colspan', '6');
                    td.className = 'text-center small text-muted';
                    td.textContent = 'No postpartum visit schedules.';
                    tr.appendChild(td);
                    tbody.appendChild(tr);
                    if (paginationNav) paginationNav.style.display = 'none';
                    return;
                }

                // Pagination setup
                const itemsPerPage = 5;
                let currentPage = 1;
                const totalPages = Math.ceil(rows.length / itemsPerPage);

                const renderPage = (page) => {
                    tbody.innerHTML = '';
                    const start = (page - 1) * itemsPerPage;
                    const end = start + itemsPerPage;
                    const pageRows = rows.slice(start, end);

                    pageRows.forEach(function (r) {
                        const tr = document.createElement('tr');
                        const scheduledDate = r.scheduled_date_str || r.scheduled_date || '-';
                        const scheduledTime = r.scheduled_time_hm || (r.scheduled_time ? (String(r.scheduled_time).slice(0,5)) : '-');
                        const purpose = r.visit_purpose || '-';
                        const notes = r.notes || '-';
                        const creator = r.created_by_name || '-';
                        const status = r.status_name || '-';
                        const statusId = typeof r.status_id !== 'undefined' && r.status_id !== null ? Number(r.status_id) : null;

                        const makeTd = (txt) => { 
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.textContent = txt;
                            td.title = txt;
                            return td;
                        };

                        const makeClickableTd = (txt, title) => {
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.style.cursor = 'pointer';
                            td.style.color = '#6d2932';
                            td.style.textDecoration = 'underline';
                            td.textContent = txt;
                            td.title = 'Click to view full ' + title;
                            td.onclick = () => {
                                const modal = new bootstrap.Modal(document.getElementById('postpartumTextDetailModal'));
                                document.getElementById('postpartumTextDetailModalLabel').textContent = title;
                                document.getElementById('postpartumTextDetailContent').textContent = txt;
                                modal.show();
                            };
                            return td;
                        };

                        tr.appendChild(makeTd(scheduledDate));
                        tr.appendChild(makeTd(scheduledTime));
                        tr.appendChild(makeClickableTd(purpose, 'Purpose'));
                        tr.appendChild(makeClickableTd(notes, 'Notes'));
                        tr.appendChild(makeTd(creator));
                        
                        // status badge
                        const tdStatus = document.createElement('td');
                        tdStatus.style.overflow = 'hidden';
                        tdStatus.style.textOverflow = 'ellipsis';
                        tdStatus.style.whiteSpace = 'nowrap';
                        const span = document.createElement('span');
                        span.className = 'badge';
                        if (statusId === 1) { span.className += ' bg-warning text-dark'; }
                        else if (statusId === 2) { span.className += ' bg-success'; }
                        else if (statusId === 3) { span.className += ' bg-info text-dark'; }
                        else if (statusId === 4) { span.className += ' bg-secondary'; }
                        else if (statusId === 5) { span.className += ' bg-danger'; }
                        else { span.className += ' bg-light text-dark'; }
                        span.textContent = status;
                        tdStatus.appendChild(span);
                        tr.appendChild(tdStatus);
                        
                        tbody.appendChild(tr);
                    });
                };

                const renderPagination = () => {
                    if (!paginationNav) return;
                    const paginationList = paginationNav.querySelector('.pagination');
                    if (!paginationList) return;
                    
                    paginationList.innerHTML = '';

                    // Previous button
                    const prevLi = document.createElement('li');
                    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
                    const prevLink = document.createElement('a');
                    prevLink.className = 'page-link';
                    prevLink.href = '#';
                    prevLink.textContent = 'Previous';
                    prevLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage > 1) {
                            currentPage--;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    prevLi.appendChild(prevLink);
                    paginationList.appendChild(prevLi);

                    // Page numbers
                    for (let i = 1; i <= totalPages; i++) {
                        const li = document.createElement('li');
                        li.className = `page-item ${i === currentPage ? 'active' : ''}`;
                        const link = document.createElement('a');
                        link.className = 'page-link';
                        link.href = '#';
                        link.textContent = i;
                        link.onclick = (e) => {
                            e.preventDefault();
                            currentPage = i;
                            renderPage(currentPage);
                            renderPagination();
                        };
                        li.appendChild(link);
                        paginationList.appendChild(li);
                    }

                    // Next button
                    const nextLi = document.createElement('li');
                    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
                    const nextLink = document.createElement('a');
                    nextLink.className = 'page-link';
                    nextLink.href = '#';
                    nextLink.textContent = 'Next';
                    nextLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage < totalPages) {
                            currentPage++;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    nextLi.appendChild(nextLink);
                    paginationList.appendChild(nextLi);
                };

                // Initial render
                renderPage(currentPage);
                if (totalPages > 1) {
                    renderPagination();
                    if (paginationNav) paginationNav.style.display = '';
                } else {
                    if (paginationNav) paginationNav.style.display = 'none';
                }
            };

            // Populate maternal ANC visit history table
            const fillAncVisitHistoryTable = (tbodyId, rows) => {
                const tbody = document.getElementById(tbodyId);
                if (!tbody) return;
                tbody.innerHTML = '';
                
                const paginationNav = document.getElementById('anc_pagination_nav');
                
                if (!Array.isArray(rows) || rows.length === 0) {
                    const tr = document.createElement('tr');
                    const td = document.createElement('td');
                    td.setAttribute('colspan', '9');
                    td.className = 'text-center small text-muted';
                    td.textContent = 'No ANC visit records.';
                    tr.appendChild(td);
                    tbody.appendChild(tr);
                    if (paginationNav) paginationNav.style.display = 'none';
                    return;
                }

                // Pagination setup
                const itemsPerPage = 5;
                let currentPage = 1;
                const totalPages = Math.ceil(rows.length / itemsPerPage);

                const renderPage = (page) => {
                    tbody.innerHTML = '';
                    const start = (page - 1) * itemsPerPage;
                    const end = start + itemsPerPage;
                    const pageRows = rows.slice(start, end);

                    pageRows.forEach(function (r) {
                        const tr = document.createElement('tr');
                        const visitNo = r.visit_no || '-';
                        const visitDate = r.visit_date_str || r.visit_date || '-';
                        const trimester = r.trimester_stage_name || '-';
                        const aog = (r.aog_weeks || '-') + 'w ' + (r.aog_days || '-') + 'd';
                        const weight = r.weight_kg ? r.weight_kg + ' kg' : '-';
                        const bp = (r.bp_systolic && r.bp_diastolic) ? r.bp_systolic + '/' + r.bp_diastolic : '-';
                        const leopolds = r.leopolds_findings || '-';
                        const notes = r.notes || '-';
                        const statusId = typeof r.visit_status_id !== 'undefined' && r.visit_status_id !== null ? Number(r.visit_status_id) : null;
                        
                        let statusName = '-';
                        if (statusId === 1) statusName = 'Scheduled';
                        else if (statusId === 2) statusName = 'Completed';
                        else if (statusId === 3) statusName = 'Cancelled';

                        const makeTd = (txt) => { 
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.textContent = txt;
                            td.title = txt; // Show full text on hover
                            return td;
                        };

                        const makeClickableTd = (txt, title) => {
                            const td = document.createElement('td');
                            td.style.overflow = 'hidden';
                            td.style.textOverflow = 'ellipsis';
                            td.style.whiteSpace = 'nowrap';
                            td.style.cursor = 'pointer';
                            td.style.color = '#6d2932';
                            td.style.textDecoration = 'underline';
                            td.textContent = txt;
                            td.title = 'Click to view full ' + title;
                            td.onclick = () => {
                                const modal = new bootstrap.Modal(document.getElementById('ancTextDetailModal'));
                                document.getElementById('ancTextDetailModalLabel').textContent = title;
                                document.getElementById('ancTextDetailContent').textContent = txt;
                                modal.show();
                            };
                            return td;
                        };
                        
                        tr.appendChild(makeTd(visitNo));
                        tr.appendChild(makeTd(visitDate));
                        tr.appendChild(makeTd(trimester));
                        tr.appendChild(makeTd(aog));
                        tr.appendChild(makeTd(weight));
                        tr.appendChild(makeTd(bp));
                        tr.appendChild(makeClickableTd(leopolds, "Leopold's Findings"));
                        tr.appendChild(makeClickableTd(notes, "Notes"));
                        
                        // status badge
                        const tdStatus = document.createElement('td');
                        tdStatus.style.overflow = 'hidden';
                        tdStatus.style.textOverflow = 'ellipsis';
                        tdStatus.style.whiteSpace = 'nowrap';
                        const span = document.createElement('span');
                        span.className = 'badge';
                        if (statusId === 1) { span.className += ' bg-info text-dark'; }
                        else if (statusId === 2) { span.className += ' bg-success'; }
                        else if (statusId === 3) { span.className += ' bg-warning text-dark'; }
                        else { span.className += ' bg-light text-dark'; }
                        span.textContent = statusName;
                        tdStatus.appendChild(span);
                        tr.appendChild(tdStatus);
                        
                        tbody.appendChild(tr);
                    });
                };

                const renderPagination = () => {
                    if (!paginationNav) return;
                    const paginationList = paginationNav.querySelector('.pagination');
                    if (!paginationList) return;
                    
                    paginationList.innerHTML = '';

                    // Previous button
                    const prevLi = document.createElement('li');
                    prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
                    const prevLink = document.createElement('a');
                    prevLink.className = 'page-link';
                    prevLink.href = '#';
                    prevLink.textContent = 'Previous';
                    prevLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage > 1) {
                            currentPage--;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    prevLi.appendChild(prevLink);
                    paginationList.appendChild(prevLi);

                    // Page numbers
                    for (let i = 1; i <= totalPages; i++) {
                        const li = document.createElement('li');
                        li.className = `page-item ${i === currentPage ? 'active' : ''}`;
                        const link = document.createElement('a');
                        link.className = 'page-link';
                        link.href = '#';
                        link.textContent = i;
                        link.onclick = (e) => {
                            e.preventDefault();
                            currentPage = i;
                            renderPage(currentPage);
                            renderPagination();
                        };
                        li.appendChild(link);
                        paginationList.appendChild(li);
                    }

                    // Next button
                    const nextLi = document.createElement('li');
                    nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
                    const nextLink = document.createElement('a');
                    nextLink.className = 'page-link';
                    nextLink.href = '#';
                    nextLink.textContent = 'Next';
                    nextLink.onclick = (e) => {
                        e.preventDefault();
                        if (currentPage < totalPages) {
                            currentPage++;
                            renderPage(currentPage);
                            renderPagination();
                        }
                    };
                    nextLi.appendChild(nextLink);
                    paginationList.appendChild(nextLi);
                };

                // Initial render
                renderPage(currentPage);
                if (totalPages > 1) {
                    renderPagination();
                    if (paginationNav) paginationNav.style.display = '';
                } else {
                    if (paginationNav) paginationNav.style.display = 'none';
                }
            };

            // Populate history modals tables and show history buttons when present
            const fillHistoryTable = (tbodyId, rows) => {
                const tbody = document.getElementById(tbodyId);
                if (!tbody) return;
                tbody.innerHTML = '';
                if (!Array.isArray(rows) || rows.length === 0) {
                    const tr = document.createElement('tr');
                    const td = document.createElement('td');
                    td.setAttribute('colspan', '7');
                    td.className = 'text-center small text-muted';
                    td.textContent = 'No history.';
                    tr.appendChild(td);
                    tbody.appendChild(tr);
                    return;
                }

                rows.forEach(function (r) {
                    const tr = document.createElement('tr');
                        const scheduledDate = r.scheduled_date_str || r.scheduled_date || '-';
                        const scheduledTime = r.scheduled_time_hm || (r.scheduled_time ? (String(r.scheduled_time).slice(0,5)) : '-');
                        const status = r.status_name || '-';
                        const statusId = typeof r.status_id !== 'undefined' && r.status_id !== null ? Number(r.status_id) : null;
                    const purpose = r.visit_purpose || r.visit_purpose || '-';
                    const notes = r.notes || '-';
                    const fulfilled = (r.fulfilled_visit_no ? (r.fulfilled_visit_no + ' / ') : '') + (r.fulfilled_visit_date || '');
                    const markedBy = r.marked_completed_by_name || '-';

                    const makeTd = (txt) => { const td = document.createElement('td'); td.textContent = txt; return td; };
                    tr.appendChild(makeTd(scheduledDate));
                    tr.appendChild(makeTd(scheduledTime));
                    // status badge
                    const tdStatus = document.createElement('td');
                    const span = document.createElement('span');
                    span.className = 'badge';
                    // Map status_id to bootstrap color
                    if (statusId === 1) { span.className += ' bg-warning text-dark'; }
                    else if (statusId === 2) { span.className += ' bg-success'; }
                    else if (statusId === 3) { span.className += ' bg-info text-dark'; }
                    else if (statusId === 4) { span.className += ' bg-secondary'; }
                    else if (statusId === 5) { span.className += ' bg-danger'; }
                    else { span.className += ' bg-light text-dark'; }
                    span.textContent = status;
                    tdStatus.appendChild(span);
                    tr.appendChild(tdStatus);
                    tr.appendChild(makeTd(purpose));
                    tr.appendChild(makeTd(notes));
                    tr.appendChild(makeTd(fulfilled));
                    tr.appendChild(makeTd(markedBy));
                    tbody.appendChild(tr);
                });
            };

            // Fill schedule history and ANC visit history tables
            fillScheduleHistoryTable('visit_schedule_history_tbody', visit_schedules);
            fillPostpartumScheduleHistoryTable('postpartum_visit_schedule_tbody', postpartum_visit_schedules);
            fillAncVisitHistoryTable('maternal_anc_visit_history_tbody', maternal_anc_visits);

            // Show history buttons when histories are present
            const btnSchedules = document.getElementById('btn_visit_schedules');
            const btnPostpartumVisits = document.getElementById('btn_postpartum_visits');
            const btnAncVisits = document.getElementById('btn_maternal_anc_visits');
            console.log('ANC Visits button element:', btnAncVisits);
            console.log('Should show ANC button?', Array.isArray(maternal_anc_visits) && maternal_anc_visits.length);
            if (btnSchedules) btnSchedules.style.display = (Array.isArray(visit_schedules) && visit_schedules.length) ? '' : 'none';
            if (btnPostpartumVisits) btnPostpartumVisits.style.display = (Array.isArray(postpartum_visit_schedules) && postpartum_visit_schedules.length) ? '' : 'none';
            if (btnAncVisits) btnAncVisits.style.display = (Array.isArray(maternal_anc_visits) && maternal_anc_visits.length) ? '' : 'none';

        } catch (err) {
            console.error('Failed to fetch side panel data', err);
            if (globalThis.MHRToast && typeof globalThis.MHRToast.show === 'function') globalThis.MHRToast.show('Failed to load side panel data', false);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const container = document.getElementById('maternalSidePanel');
        // Prefer the latest maternal_record_id available on the page.
        // The template may render multiple `data-mhr-id` attributes (one per record
        // action button) or a top-level `data-mhr-id` which sometimes holds an
        // older value. Scan the DOM for numeric MHR ids and pick the max.
        const findLatestMhrFromDom = function () {
            const ids = [];
            // Collect values from any element that exposes data-mhr-id
            document.querySelectorAll('[data-mhr-id]').forEach(function (el) {
                const v = el.getAttribute('data-mhr-id');
                if (v != null && String(v).trim() !== '') {
                    const n = Number(String(v).trim());
                    if (!Number.isNaN(n)) ids.push(n);
                }
            });
            // Also look at the records table first column (MHR #) as a fallback
            document.querySelectorAll('table.visit-table tbody tr').forEach(function (tr) {
                const td = tr.querySelector('td');
                if (td) {
                    const t = td.textContent.trim();
                    const n = Number(t);
                    if (!Number.isNaN(n)) ids.push(n);
                }
            });
            if (!ids.length) return null;
            return String(Math.max.apply(null, ids));
        };

        let mhrId = container ? container.dataset.mhrId : null;
        const computedLatest = findLatestMhrFromDom();
        if (!mhrId || String(mhrId).trim() === '' || (computedLatest && Number(computedLatest) > Number(mhrId))) {
            if (computedLatest) mhrId = computedLatest;
        }

        if (mhrId) fetchSidePanel(mhrId);

        // listen for postpartum:created events to refresh panel when record changes
        document.addEventListener('postpartum:created', function () {
            // Recompute latest MHR id on refresh events in case the active record changed.
            const container = document.getElementById('maternalSidePanel');
            let mhrId = container ? container.dataset.mhrId : null;
            const computedLatest = (function () {
                const ids = [];
                document.querySelectorAll('[data-mhr-id]').forEach(function (el) {
                    const v = el.getAttribute('data-mhr-id');
                    if (v != null && String(v).trim() !== '') {
                        const n = Number(String(v).trim());
                        if (!Number.isNaN(n)) ids.push(n);
                    }
                });
                document.querySelectorAll('table.visit-table tbody tr').forEach(function (tr) {
                    const td = tr.querySelector('td');
                    if (td) {
                        const t = td.textContent.trim();
                        const n = Number(t);
                        if (!Number.isNaN(n)) ids.push(n);
                    }
                });
                return ids.length ? String(Math.max.apply(null, ids)) : null;
            })();
            if (!mhrId || String(mhrId).trim() === '' || (computedLatest && Number(computedLatest) > Number(mhrId))) {
                if (computedLatest) mhrId = computedLatest;
            }
            if (mhrId) fetchSidePanel(mhrId);
        });
    });

})();
