// Auto-disable Save buttons for child-health sections when fields are already filled
document.addEventListener('DOMContentLoaded', function(){
    'use strict';

    function isValuePresent(el) {
        if (!el) return false;
        if (el.type === 'hidden') return false;
        if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
        if (el.tagName === 'SELECT') return (el.value || '').toString().trim() !== '';
        if (el.type === 'file') return false; // file inputs not considered here
        return (el.value || '').toString().trim() !== '';
    }

    function allFieldsFilled(form, predicates) {
        if (!form) return false;
        const els = Array.from(form.elements).filter(e => e.name && e.name !== 'csrfmiddlewaretoken' && e.name !== 'form_type');
        if (predicates && typeof predicates === 'function') return predicates(els);
        for (const el of els) {
            if (el.type === 'file') continue;
            if (!isValuePresent(el)) return false;
        }
        return els.length > 0;
    }

    function disableButtonForForm(form, condition) {
        if (!form) return;
        const btn = form.querySelector('button[type="submit"]');
        if (!btn) return;
        try { btn.disabled = !!condition; } catch (_err) { /* ignore */ }
    }

    function processSimpleSection(containerSelector) {
        const container = document.querySelector(containerSelector);
        if (!container) return;
        const form = container.querySelector('form');
        if (!form) return;
        disableButtonForForm(form, allFieldsFilled(form));
    }

    try {
        // New Born Screening (section #nbs) - disable only when BOTH non-checkbox fields are filled
        const nbsContainer = document.querySelector('#nbs');
        if (nbsContainer) {
            const nbsForm = nbsContainer.querySelector('form');
            if (nbsForm) {
                const nbsPredicate = function(elements) {
                    const els = elements.filter(e => e.name && e.name !== 'csrfmiddlewaretoken' && e.name !== 'form_type' && e.type !== 'hidden' && e.type !== 'file' && e.type !== 'checkbox' && e.type !== 'radio');
                    // Expecting two main fields: if exactly two, require both to be present
                    if (els.length === 2) {
                        return els.every(isValuePresent);
                    }
                    // Fallback: require all non-file non-hidden fields to be present
                    for (const el of els) {
                        if (!isValuePresent(el)) return false;
                    }
                    return els.length > 0;
                };
                disableButtonForForm(nbsForm, allFieldsFilled(nbsForm, nbsPredicate));
            }
        }

        // Breastfeeding Check - form has id breastFeedingForm
        const bfForm = document.getElementById('breastFeedingForm');
        if (bfForm) disableButtonForForm(bfForm, allFieldsFilled(bfForm));

        // Birth & Supplementation - disable when all NON-CHECKBOX fields are filled
        const birthContainer = document.querySelector('#birth-and-supplementation');
        if (birthContainer) {
            const birthForm = birthContainer.querySelector('form');
            if (birthForm) {
                const allNonCheckboxFilled = function(elements) {
                    const els = elements.filter(e => e.name && e.name !== 'csrfmiddlewaretoken' && e.name !== 'form_type');
                    // require all non-checkbox, non-file, non-hidden fields to have value
                    for (const el of els) {
                        if (el.type === 'hidden' || el.type === 'file' || el.type === 'checkbox' || el.type === 'radio') continue;
                        if (!isValuePresent(el)) return false;
                    }
                    return els.length > 0;
                };
                disableButtonForForm(birthForm, allFieldsFilled(birthForm, allNonCheckboxFilled));
            }
        }

        // Iron Intake
        processSimpleSection('#iron-intake');

        // Vitamin
        processSimpleSection('#vitamin-intake');

        
            // Immunization - iterate rows to handle cases where form tags are moved
            const immContainer = document.querySelector('#immunization');
            if (immContainer) {
                const rows = immContainer.querySelectorAll('tbody > tr');

                // evaluate a single row and disable/enable its submit button
                const evaluateImmunizationRow = (tr) => {
                    if (!tr) return;
                    const tds = Array.from(tr.querySelectorAll('td'));
                    const nameCell = tds[0];
                    const label = nameCell ? (nameCell.textContent || '').toLowerCase().trim() : '';

                    const tdHasValue = (td) => {
                        if (!td) return false;
                        const ctrl = td.querySelector('input, select, textarea');
                        if (ctrl) return isValuePresent(ctrl);
                        const txt = (td.textContent || '').trim();
                        return txt !== '' && txt !== '—' && txt !== '-';
                    };

                    let shouldDisable = false;

                    if (label.includes('bcg') || label.includes('hepbv') || label.includes('hep. bv') || label.includes('hep')) {
                        // check 24-hr column (td index 1)
                        shouldDisable = tdHasValue(tds[1]);
                    } else if (label.includes('pcv') || label.includes('opv') || label.includes('amv') || label.includes('pentavalent')) {
                        // require 1st, 2nd, 3rd -> td indexes 2,3,4
                        shouldDisable = tdHasValue(tds[2]) && tdHasValue(tds[3]) && tdHasValue(tds[4]);
                    } else {
                        // fallback: if row has inputs, check them; else check any non-empty td beyond first
                        const inputs = tr.querySelectorAll('input, select, textarea');
                        if (inputs.length > 0) {
                            const arr = Array.from(inputs).filter(el => el.name && el.type !== 'hidden' && el.type !== 'file');
                            shouldDisable = arr.length > 0 && arr.every(isValuePresent);
                        } else {
                            // check any of the data cells for text
                            shouldDisable = tds.slice(1).some(td => tdHasValue(td));
                        }
                    }

                    // find submit button in this row and disable it
                    let btn = tr.querySelector('button[type="submit"]');
                    if (!btn) {
                        const formInRow = tr.querySelector('form');
                        if (formInRow) btn = formInRow.querySelector('button[type="submit"]');
                    }
                    if (btn) {
                        try { btn.disabled = !!shouldDisable; } catch (_e) { /* ignore */ }
                    }
                };

                // initial pass
                rows.forEach(evaluateImmunizationRow);
                // Toggle after successful save: listen for custom event dispatched by immunizationRequest
                document.addEventListener('immunization:submitted', function(ev) {
                    try {
                        const prefix = ev && ev.detail && ev.detail.prefix;
                        if (prefix) {
                            const el = document.getElementById(`id_${prefix}_24hr`) || document.getElementById(`id_${prefix}_1st`) || document.getElementById(`id_${prefix}_2nd`);
                            const row = el ? el.closest('tr') : null;
                            if (row) return evaluateImmunizationRow(row);
                        }
                    } catch (_e) { /* ignore */ }
                    // fallback: re-evaluate all rows
                    rows.forEach(evaluateImmunizationRow);
                });
            }

        // Exclude Add Visit Entry (#visit-entry) as requested
    } catch (err) {
        console.error('auto_disable_sections init error', err);
    }
});
