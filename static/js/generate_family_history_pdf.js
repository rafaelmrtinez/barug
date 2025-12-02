// JS to generate and open/download PDF for family history list
// Attaches to elements with class `btn-generate-family-history-pdf`

(function () {
    'use strict';

    async function handleGenerateClick(event) {
        const btn = event.currentTarget;
        if (!btn) return;

        // Get current search and filter parameters from URL
        const urlParams = new URLSearchParams(window.location.search);
        const quarter = urlParams.get('quarter') || '';
        const year = urlParams.get('year') || '';
        const searchValue = urlParams.get('search') || '';
        const householdTypeValue = urlParams.get('household_type') || '';
        const nhtsStatusValue = urlParams.get('nhts_status') || '';
        const indigentStatusValue = urlParams.get('indigent_status') || '';

        // Build URL with current filters
        const params = new URLSearchParams();
        if (quarter) params.set('quarter', quarter);
        if (year) params.set('year', year);
        if (searchValue) params.set('search', searchValue);
        if (householdTypeValue) params.set('household_type', householdTypeValue);
        if (nhtsStatusValue) params.set('nhts_status', nhtsStatusValue);
        if (indigentStatusValue) params.set('indigent_status', indigentStatusValue);

        // Detect role from current URL path
        const currentPath = window.location.pathname;
        let rolePrefix = '/bhw';
        if (currentPath.startsWith('/secretary/')) rolePrefix = '/secretary';
        if (currentPath.startsWith('/captain/')) rolePrefix = '/captain';
        
        const url = `${rolePrefix}/api/family/history/pdf/?${params.toString()}`;

        // Open the PDF endpoint in a new tab for preview
        const newTab = globalThis.open ? globalThis.open(url, '_blank') : null;
        if (newTab) {
            return; // PDF will open in new tab
        }
        
        // If popup was blocked, show message
        alert('Please allow popups for this site to preview the PDF.');
    }

    function init() {
        // Attach to existing buttons
        const buttons = document.querySelectorAll('.btn-generate-family-history-pdf');
        buttons.forEach((b) => {
            b.addEventListener('click', handleGenerateClick);
        });

        // Also use event delegation to catch dynamically-added buttons (if any)
        document.addEventListener('click', function (e) {
            const target = e.target.closest && e.target.closest('.btn-generate-family-history-pdf');
            if (target && !target._generatePdfAttached) {
                target.addEventListener('click', handleGenerateClick);
                target._generatePdfAttached = true;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
