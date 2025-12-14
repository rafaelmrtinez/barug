(() => {
    document.addEventListener('DOMContentLoaded', function () {
        const searchInput = document.getElementById('person_search');
        const resultsContainer = document.getElementById('person_search_results');
        const hiddenIdInput = document.getElementById('family_head_id');

        let debounceTimeout = null;

        searchInput.addEventListener('input', function () {
            const query = searchInput.value.trim();
            resultsContainer.innerHTML = '';
            hiddenIdInput.value = '';
            if (debounceTimeout) clearTimeout(debounceTimeout);
            if (query.length < 2) return;
            debounceTimeout = setTimeout(() => {
                fetch(`/resident/api/search/?q=${encodeURIComponent(query)}&limit=10`)
                    .then(response => response.json())
                    .then(data => {
                        resultsContainer.innerHTML = '';
                        if (Array.isArray(data) && data.length > 0) {
                            data.forEach(person => {
                                const item = document.createElement('button');
                                item.type = 'button';
                                item.className = 'list-group-item list-group-item-action';
                                // Compose display string with name, address, and code
                                const name = `${person.first_name} ${person.last_name}`;
                                const code = person.person_code ? ` [${person.person_code}]` : '';
                                const address = person.full_address ? `${person.full_address}` : '';
                                item.innerHTML = `<strong>${name}</strong>${code}<br><small>${address}</small>`;
                                item.addEventListener('click', function () {
                                    searchInput.value = name;
                                    hiddenIdInput.value = person.person_id;
                                    resultsContainer.innerHTML = '';
                                });
                                resultsContainer.appendChild(item);
                            });
                        } else {
                            const noResult = document.createElement('div');
                            noResult.className = 'list-group-item';
                            noResult.textContent = 'No results found.';
                            resultsContainer.appendChild(noResult);
                        }
                    })
                    .catch(() => {
                        resultsContainer.innerHTML = '<div class="list-group-item">Error searching.</div>';
                    });
            }, 300);
        });

        // Hide results when clicking outside
        document.addEventListener('click', function (e) {
            if (!resultsContainer.contains(e.target) && e.target !== searchInput) {
                resultsContainer.innerHTML = '';
            }
        });
    });

})();