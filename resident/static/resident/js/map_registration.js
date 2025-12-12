(() => {
  function fill_home_address() {
    // Support multiple possible DOM ids (Django form ids vary). Prefer house number first.
    const houseNumEl = document.getElementById('house_num') || document.getElementById('id_house_num') || document.getElementById('houseNumber') || document.getElementById('id_houseNumber');
    const streetEl = document.getElementById('street') || document.getElementById('id_street');
    const purokEl = document.getElementById('purok_sitio') || document.getElementById('id_purok_sitio');
    const barangayEl = document.getElementById('barangay') || document.getElementById('id_barangay');
    const cityEl = document.getElementById('city') || document.getElementById('id_city');

    const houseNum = houseNumEl ? houseNumEl.value.trim() : '';
    const street = streetEl ? streetEl.value.trim() : '';
    const purokSitio = purokEl ? purokEl.value.trim() : '';
    const barangay = barangayEl ? barangayEl.value.trim() : '';
    const city = cityEl ? cityEl.value.trim() : '';

    // Build address with house number before street
    const parts = [houseNum, street, purokSitio, barangay, city].filter(part => part !== '');
    const fullAddress = parts.join(', ');

    const homeAddrEl = document.getElementById('home_address') || document.getElementById('id_home_address');
    if (homeAddrEl) homeAddrEl.value = fullAddress;
    // Persist current marker coordinates into hidden form inputs if present
    try {
      const latEl = document.getElementById('latitude') || document.getElementById('id_latitude');
      const lngEl = document.getElementById('longitude') || document.getElementById('id_longitude');
      if (typeof currentLngLat !== 'undefined') {
        if (latEl) latEl.value = String(currentLngLat.lat);
        if (lngEl) lngEl.value = String(currentLngLat.lng);
      }
    } catch (err) {
      console.warn('Could not set hidden lat/lng inputs', err);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const mapboxToken = 'pk.eyJ1IjoicmFwaGJlbGwiLCJhIjoiY21jNHN6ODhtMDRteDJpcHdocXJpaTFpaiJ9.tkV7UFKy4yBlAtkZNYOS4A';
    mapboxgl.accessToken = mapboxToken;

    const defaultCoordinates = [123.9028, 10.2951];

    const stoNinoBoundary = {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [[
          [123.90212, 10.29731],
          [123.90201, 10.29786],
          [123.90058, 10.29764],
          [123.89806, 10.29617],
          [123.89771, 10.29501],
          [123.89805, 10.29378],
          [123.89904, 10.29427],
          [123.89994, 10.29420],
          [123.89934, 10.29213],
          [123.89938, 10.29193],
          [123.90009, 10.29210],
          [123.90065, 10.28980],
          [123.90212, 10.29069],
          [123.90181, 10.29169],
          [123.90195, 10.29180],
          [123.90196, 10.29194],
          [123.90334, 10.29488],
          [123.90359, 10.29580],
          [123.90382, 10.29723],
          [123.90379, 10.29753],
          [123.90213, 10.29724],
          [123.90212, 10.29731]
        ]]
      },
      "properties": {
        "name": "Barangay Sto. Niño"
      }
    };

    // === Estimated PUROK polygons from annotated map ===
    // Coordinates provided as [lat, lng]. We'll convert to [lng, lat] for GeoJSON.
    const PUROKS = [
      {
        code: "S01", name: "KANIPAAN", coords: [
          [10.29760, 123.89850],
          [10.29785, 123.90005],
          [10.29695, 123.90150],
          [10.29610, 123.90135],
          [10.29555, 123.90005],
          [10.29605, 123.89900],
          [10.29700, 123.89870],
          [10.29760, 123.89850]
        ]
      },
      {
        code: "S02", name: "PAMPANGO", coords: [
          [10.29460, 123.90160],
          [10.29475, 123.90360],
          [10.29330, 123.90350],
          [10.29260, 123.90250],
          [10.29285, 123.90120],
          [10.29380, 123.90100],
          [10.29460, 123.90160]
        ]
      },
      {
        code: "S03", name: "LUTAW-LUTAW", coords: [
          [10.29485, 123.89990],
          [10.29455, 123.90140],
          [10.29355, 123.90120],
          [10.29280, 123.90000],
          [10.29355, 123.89905],
          [10.29430, 123.89900],
          [10.29485, 123.89990]
        ]
      },
      {
        code: "S04", name: "MAUCO", coords: [
          [10.29650, 123.90200],
          [10.29605, 123.90345],
          [10.29495, 123.90370],
          [10.29460, 123.90225],
          [10.29525, 123.90155],
          [10.29650, 123.90200]
        ]
      }
    ];

    // Convert PUROKS to a GeoJSON FeatureCollection (mapbox/turf expect [lng, lat])
    const purokGeojson = {
      type: 'FeatureCollection',
      features: PUROKS.map(p => ({
        type: 'Feature',
        properties: { code: p.code, name: p.name },
        geometry: {
          type: 'Polygon',
          coordinates: [p.coords.map(([lat, lng]) => [lng, lat])]
        }
      }))
    };

    const map = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/streets-v11',
      center: defaultCoordinates,
      zoom: 18,
      pitch: 0,
      bearing: 0,
    });

    const marker = new mapboxgl.Marker({ color: '#800000', draggable: true })
      .setLngLat(defaultCoordinates)
      .addTo(map);

    let currentLngLat = { lng: defaultCoordinates[0], lat: defaultCoordinates[1] };

    map.on('load', () => {
      boundary_layers();
      // keep purokGeojson for detection, but do not add visible purok layers
      getAddressFromCoordinates(currentLngLat.lng, currentLngLat.lat);
    });

    function boundary_layers() {
      if (!map.getSource('sto-nino-BG')) {
        map.addSource('sto-nino-BG', {
          type: 'geojson',
          data: stoNinoBoundary
        });
      }
      if (!map.getLayer('sto-nino-outline')) {
        map.addLayer({
          id: 'sto-nino-outline',
          type: 'line',
          source: 'sto-nino-BG',
          paint: { 'line-color': '#000000', 'line-width': 2 }
        });
      }
      if (!map.getLayer('sto-nino-fill')) {
        map.addLayer({
          id: 'sto-nino-fill',
          type: 'fill',
          source: 'sto-nino-BG',
          paint: { 'fill-color': '#000000', 'fill-opacity': 0.1 }
        });
      }
      if (!document.querySelector('.mapboxgl-ctrl-group')) {
        map.addControl(new mapboxgl.NavigationControl(
          { showCompass: false }
        ));
      }
    }

    marker.on('dragend', () => {
      const lngLat = marker.getLngLat();
      attemptUpdate({ lng: lngLat.lng, lat: lngLat.lat });
    });

    map.on('click', (e) => {
      attemptUpdate({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    });

    document.getElementById('style-selector').addEventListener('change', function (e) {
      const style = `mapbox://styles/${e.target.value}`;
      map.setStyle(style);
      map.on('style.load', () => {
        boundary_layers();
      });
    });

    function getAddressFromCoordinates(lng, lat) {
      const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${lng},${lat}.json?access_token=${mapboxgl.accessToken}`;

      fetch(url)
        .then(response => response.json())
        .then(data => {
          if (data.features.length > 0) {
            const place = data.features[0];
            const context = place.context || [];

            let street = place.text || '';
            let purok = '';
            let barangay = '';
            let city = '';

            context.forEach(item => {
              if (item.id.includes('neighborhood')) purok = item.text;
              if (item.id.includes('place')) city = item.text;
              if (item.id.includes('locality')) barangay = item.text;
              if (item.id.includes('address')) street = item.text;
            });

            barangay = 'Sto. Niño';

            const streetInput = document.getElementById('street');
            const purokInput = document.getElementById('purok_sitio');
            const barangayInput = document.getElementById('barangay');
            const cityInput = document.getElementById('city');

            if (streetInput) streetInput.value = street;
            // Only set purok from geocoding if not already set by polygon detection
            if (purokInput && !purokInput.value) purokInput.value = purok;
            if (barangayInput) barangayInput.value = barangay;
            if (cityInput) cityInput.value = city;

            console.log('Filled address:', { street, purok, barangay, city });
          }
        })
        .catch(error => {
          console.error('Error fetching address:', error);
        });
    }

    function attemptUpdate(coords) {
      const point = turf.point([coords.lng, coords.lat]);
      const inside = turf.booleanPointInPolygon(point, stoNinoBoundary);

      if (inside) {
        marker.setLngLat([coords.lng, coords.lat]);
        currentLngLat = coords;
        // Persist coordinates immediately so form payloads pick them up without requiring modal Save
        try {
          const latEl = document.getElementById('latitude') || document.getElementById('id_latitude');
          const lngEl = document.getElementById('longitude') || document.getElementById('id_longitude');
          if (latEl) latEl.value = String(coords.lat);
          if (lngEl) lngEl.value = String(coords.lng);
        } catch (err) {
          console.warn('Could not persist lat/lng inputs from attemptUpdate', err);
        }
        // detect Purok by checking polygon features first
        try {
          const hit = purokGeojson.features.find(f => turf.booleanPointInPolygon(point, f));
          const purokInput = document.getElementById('purok_sitio');
          if (hit && purokInput) {
            purokInput.value = hit.properties.name || hit.properties.code || '';
          }
        } catch (err) {
          console.warn('Purok detection error', err);
        }

        // then call reverse geocode to fill street/city etc.
        getAddressFromCoordinates(coords.lng, coords.lat);
      } else {
        new mapboxgl.Popup()
          .setLngLat([coords.lng, coords.lat])
          .setHTML(`<strong>Invalid:</strong><br>Select only within Sto. Niño boundary.`)
          .addTo(map);
        console.warn('Clicked outside Sto. Niño:', coords);
      }
    }

  });

  window.fill_home_address = fill_home_address;
})();