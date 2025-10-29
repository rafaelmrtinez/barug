(function () {
    'use strict';

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
            const prenatal_history = data && data.prenatal_schedule_history ? data.prenatal_schedule_history : [];
            const postpartum_history = data && data.postpartum_schedule_history ? data.postpartum_schedule_history : [];
            const latest_union = data && data.latest_scheduled_visit ? data.latest_scheduled_visit : null;

            // latest items are the first elements of the history arrays (API returns ordered DESC)
            const latest_prenatal = Array.isArray(prenatal_history) && prenatal_history.length ? prenatal_history[0] : null;
            const latest_postpartum = Array.isArray(postpartum_history) && postpartum_history.length ? postpartum_history[0] : null;

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

            // Populate separate Prenatal/Postpartum schedule cards.
            const showSchedule = (cardId, dtId, sched, visitType) => {
                const card = document.getElementById(cardId);
                const dtEl = document.getElementById(dtId);
                if (!card || !dtEl) return;
                // Determine status_id: prefer sched.status_id if present; otherwise
                // fall back to the union latest visit (latest_union) when it matches type & id.
                let statusId = null;
                let displayDate = null;
                let displayTime = null;

                if (sched) {
                    // sched includes status_id from repository now
                    if (typeof sched.status_id !== 'undefined' && sched.status_id !== null) {
                        statusId = Number(sched.status_id);
                    }
                    // Prefer server-side formatted fields when available
                    displayDate = sched.scheduled_date_str || sched.scheduled_date || '';
                    displayTime = sched.scheduled_time_hm || sched.scheduled_time || '';
                }

                // fallback: use latest_union if it matches this visitType and schedule id
                if ((statusId === null || typeof statusId === 'undefined') && latest_union) {
                    if (latest_union.visit_type === visitType) {
                        // if sched exists, match by schedule_id; otherwise accept latest_union
                        if (sched && typeof sched.schedule_id !== 'undefined' && sched.schedule_id !== null) {
                            if (Number(latest_union.schedule_id) === Number(sched.schedule_id)) {
                                statusId = Number(latest_union.status_id);
                                displayDate = latest_union.scheduled_date_str || latest_union.scheduled_date || displayDate;
                                displayTime = latest_union.scheduled_time_hm || latest_union.scheduled_time || displayTime;
                            }
                        } else {
                            statusId = Number(latest_union.status_id);
                            displayDate = latest_union.scheduled_date_str || latest_union.scheduled_date || displayDate;
                            displayTime = latest_union.scheduled_time_hm || latest_union.scheduled_time || displayTime;
                        }
                    }
                }

                // Always show the container. If status_id === 1 show date/time,
                // otherwise show '-' to indicate no active schedule.
                const d = displayDate || '';
                const t = displayTime || '';
                if (statusId === 1) {
                    dtEl.textContent = (d ? d : '-') + (t ? (' ' + (String(t).slice(0,5))) : '');
                } else {
                    dtEl.textContent = 'TBD';
                }
                card.style.display = '';
            };

            showSchedule('prenatal_schedule_card', 'prenatal_sched_dt', latest_prenatal, 'maternal');
            showSchedule('postpartum_schedule_card', 'postpartum_sched_dt', latest_postpartum, 'postpartum');

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

            // Fill prenatal & postpartum history tables
            fillHistoryTable('prenatal_history_tbody', prenatal_history);
            fillHistoryTable('postpartum_history_tbody', postpartum_history);

            // Show history buttons when histories are present
            const btnPren = document.getElementById('btn_prenatal_history');
            const btnPost = document.getElementById('btn_postpartum_history');
            if (btnPren) btnPren.style.display = (Array.isArray(prenatal_history) && prenatal_history.length) ? '' : 'none';
            if (btnPost) btnPost.style.display = (Array.isArray(postpartum_history) && postpartum_history.length) ? '' : 'none';

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

        console.log('Maternal Side Panel: loading data for MHR ID', mhrId, '(computed latest:', computedLatest, ')');

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
