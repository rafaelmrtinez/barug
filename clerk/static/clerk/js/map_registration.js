function fill_b_address() {
  const street = document.getElementById('street').value.trim();
  const purokSitio = document.getElementById('purok_sitio').value.trim();
  const barangay = document.getElementById('barangay').value.trim();
  const city = document.getElementById('city').value.trim();

  const parts = [street, purokSitio, barangay, city].filter(Boolean);
  document.getElementById('b_address').value = parts.join(', ');
}

document.addEventListener("DOMContentLoaded", function () {
  const mapboxToken = 'pk.eyJ1IjoicmFwaGJlbGwiLCJhIjoiY21jNHN6ODhtMDRteDJpcHdocXJpaTFpaiJ9.tkV7UFKy4yBlAtkZNYOS4A';
  mapboxgl.accessToken = mapboxToken;

  const defaultCoordinates = [123.9028, 10.2951];

  // ─────────────────────────────────────────────────────────
  // Barangay Sto. Niño boundary (lng, lat)
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
    properties: { name: "Barangay Sto. Niño" }
  };

  // Build 4 clipped sub-polys strictly inside the barangay
  function buildPurokQuads(boundary) {
    if (typeof turf === 'undefined') {
      console.warn('Turf.js is required.');
      return { type: 'FeatureCollection', features: [] };
    }
    const [minX, minY, maxX, maxY] = turf.bbox(boundary);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    const rect = (x1, y1, x2, y2) => turf.polygon([[
      [x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]
    ]]);

    // NW, NE, SW, SE (top-left → bottom-right)
    const quads = [
      { code: 'S01', name: 'KANIPAAN', poly: rect(minX, midY, midX, maxY) }, // NW
      { code: 'S02', name: 'PAMPANGO', poly: rect(midX,  midY, maxX, maxY) }, // NE
      { code: 'S03', name: 'LUTAW-LUTAW', poly: rect(minX,  minY, midX,  midY) }, // SW
      { code: 'S04', name: 'MAUCO', poly: rect(midX,  minY, maxX,  midY) }, // SE
    ];

    const features = [];
    for (const q of quads) {
      const clipped = turf.intersect(q.poly, boundary);
      if (clipped) {
        features.push({
          type: 'Feature',
          properties: { code: q.code, name: q.name },
          geometry: clipped.geometry
        });
      } else {
        // Fallback: if a quadrant misses (rare), assign tiny slice at centroid side
        const c = turf.centroid(boundary).geometry.coordinates;
        const tiny = rect(c[0]-1e-6, c[1]-1e-6, c[0]+1e-6, c[1]+1e-6);
        const tinyClip = turf.intersect(tiny, boundary);
        if (tinyClip) {
          features.push({
            type: 'Feature',
            properties: { code: q.code, name: q.name },
            geometry: tinyClip.geometry
          });
        }
      }
    }
    return { type: 'FeatureCollection', features };
  }

  // For point → which purok?
  function whichPurok(fc, lng, lat) {
    if (!fc || !fc.features) return null;
    const pt = turf.point([lng, lat]);
    for (const f of fc.features) {
      if (turf.booleanPointInPolygon(pt, f)) return f.properties; // {code,name}
    }
    return null;
  }

  const map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/streets-v11',
    center: defaultCoordinates,
    zoom: 18
  });

  const marker = new mapboxgl.Marker({ color: '#800000', draggable: true })
    .setLngLat(defaultCoordinates)
    .addTo(map);

  let currentLngLat = { lng: defaultCoordinates[0], lat: defaultCoordinates[1] };
  let purokFc = null; // computed once from the boundary

  map.on('load', () => {
    // compute quads from boundary (strictly clipped)
    purokFc = buildPurokQuads(stoNinoBoundary);
    addLayers();
    getAddressFromCoordinates(currentLngLat.lng, currentLngLat.lat);
  });

  function addLayers() {
    // barangay
    if (!map.getSource('sto-nino-BG')) {
      map.addSource('sto-nino-BG', { type: 'geojson', data: stoNinoBoundary });
    }
    if (!map.getLayer('sto-nino-outline')) {
      map.addLayer({
        id: 'sto-nino-outline',
        type: 'line',
        source: 'sto-nino-BG',
        paint: { 'line-color': '#000', 'line-width': 2 }
      });
    }
    if (!map.getLayer('sto-nino-fill')) {
      map.addLayer({
        id: 'sto-nino-fill',
        type: 'fill',
        source: 'sto-nino-BG',
        paint: { 'fill-color': '#000', 'fill-opacity': 0.08 }
      });
    }

    // puroks (computed)
    if (purokFc && !map.getSource('puroks')) {
      map.addSource('puroks', { type: 'geojson', data: purokFc });
    }
    if (!map.getLayer('purok-fill')) {
      map.addLayer({
        id: 'purok-fill',
        type: 'fill',
        source: 'puroks',
        paint: { 'fill-color': '#4f46e5', 'fill-opacity': 0.10 }
      });
    }
    if (!map.getLayer('purok-outline')) {
      map.addLayer({
        id: 'purok-outline',
        type: 'line',
        source: 'puroks',
        paint: { 'line-color': '#4f46e5', 'line-width': 1.5 }
      });
    }
    if (!map.getLayer('purok-labels')) {
      map.addLayer({
        id: 'purok-labels',
        type: 'symbol',
        source: 'puroks',
        layout: {
          'text-field': ['get', 'name'],
          'text-size': 12,
          'text-offset': [0, 0.6],
          'text-anchor': 'top'
        },
        paint: { 'text-halo-color': '#fff', 'text-halo-width': 1 }
      });
    }

    if (!document.querySelector('.mapboxgl-ctrl-group')) {
      map.addControl(new mapboxgl.NavigationControl({ showCompass: false }));
    }
  }

  marker.on('dragend', () => {
    const lngLat = marker.getLngLat();
    attemptUpdate({ lng: lngLat.lng, lat: lngLat.lat });
  });

  map.on('click', (e) => {
    attemptUpdate({ lng: e.lngLat.lng, lat: e.lngLat.lat });
  });

  document.getElementById('style-selector')?.addEventListener('change', function (e) {
    const style = `mapbox://styles/${e.target.value}`;
    map.setStyle(style);
    map.on('style.load', () => {
      // re-add sources/layers after style change
      if (!map.getSource('sto-nino-BG')) map.addSource('sto-nino-BG', { type: 'geojson', data: stoNinoBoundary });
      if (!map.getSource('puroks')) map.addSource('puroks', { type: 'geojson', data: purokFc });
      addLayers();
    });
  });

  function setPurokInput(props) {
    const purokInput = document.getElementById('purok_sitio');
    if (purokInput) purokInput.value = (props && props.name) ? props.name : (purokInput.value || '');
  }

  function getAddressFromCoordinates(lng, lat) {
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${lng},${lat}.json?access_token=${mapboxgl.accessToken}`;

    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (!data.features?.length) return;

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

        // Force barangay
        barangay = 'Sto. Niño';

        // Prefer polygon-based purok assignment (guaranteed inside)
        const hit = whichPurok(purokFc, lng, lat);
        if (hit?.name) purok = hit.name;

        const streetInput = document.getElementById('street');
        const purokInput = document.getElementById('purok_sitio');
        const barangayInput = document.getElementById('barangay');
        const cityInput = document.getElementById('city');

        if (streetInput) streetInput.value = street;
        if (purokInput) purokInput.value = purok;
        if (barangayInput) barangayInput.value = barangay;
        if (cityInput) cityInput.value = city;

        if (document.getElementById('b_address')) fill_b_address();
        console.log('Filled address:', { street, purok, barangay, city });
      })
      .catch(err => console.error('Error fetching address:', err));
  }

  function attemptUpdate(coords) {
    if (typeof turf === 'undefined') {
      console.warn('Turf is required for boundary checks.');
      return;
    }
    const point = turf.point([coords.lng, coords.lat]);
    const inside = turf.booleanPointInPolygon(point, stoNinoBoundary);

    if (inside) {
      marker.setLngLat([coords.lng, coords.lat]);
      currentLngLat = coords;

      // Assign purok immediately from our clipped quads
      const hit = whichPurok(purokFc, coords.lng, coords.lat);
      setPurokInput(hit);

      // Then reverse geocode to fill other fields
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
