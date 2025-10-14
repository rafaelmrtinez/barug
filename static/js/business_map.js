(function () {
  const MAPBOX_TOKEN = 'pk.eyJ1IjoicmFwaGJlbGwiLCJhIjoiY21jNHN6ODhtMDRteDJpcHdocXJpaTFpaiJ9.tkV7UFKy4yBlAtkZNYOS4A';
  mapboxgl.accessToken = MAPBOX_TOKEN;

  // ── Barangay Sto. Niño boundary (lng, lat)
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

  function buildPurokQuads(boundary) {
    const [minX, minY, maxX, maxY] = turf.bbox(boundary);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    const rect = (x1, y1, x2, y2) => turf.polygon([[
      [x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]
    ]]);
    const quads = [
      { code: 'S01', name: 'KANIPAAN',     poly: rect(minX, midY, midX, maxY) },
      { code: 'S02', name: 'PAMPANGO',     poly: rect(midX,  midY, maxX, maxY) },
      { code: 'S03', name: 'LUTAW-LUTAW',  poly: rect(minX,  minY, midX,  midY) },
      { code: 'S04', name: 'MAUCO',        poly: rect(midX,  minY, maxX,  midY) },
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
      }
    }
    return { type: 'FeatureCollection', features };
  }

  const purokFc = buildPurokQuads(stoNinoBoundary);

  const map = new mapboxgl.Map({
    container: 'purokMap',
    style: 'mapbox://styles/mapbox/streets-v11',
    center: [123.9028, 10.2951],
    zoom: 16,
    attributionControl: true
  });

  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }));

  let focusMarker = null;

  map.on('load', () => {
    // Fit to barangay bounds
    const bounds = turf.bbox(stoNinoBoundary);
    map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 30, duration: 0 });

    // Sources
    map.addSource('sto-nino-BG', { type: 'geojson', data: stoNinoBoundary });
    map.addSource('puroks',      { type: 'geojson', data: purokFc });

    // Layers
    map.addLayer({
      id: 'sto-nino-fill',
      type: 'fill',
      source: 'sto-nino-BG',
      paint: { 'fill-color': '#000', 'fill-opacity': 0.06 }
    });
    map.addLayer({
      id: 'sto-nino-outline',
      type: 'line',
      source: 'sto-nino-BG',
      paint: { 'line-color': '#111', 'line-width': 2 }
    });
    map.addLayer({
      id: 'purok-fill',
      type: 'fill',
      source: 'puroks',
      paint: {
        'fill-color': [
          'match',
          ['get', 'name'],
          'KANIPAAN',    '#7B1E22',
          'PAMPANGO',    '#D4AF37',
          'LUTAW-LUTAW', '#4f46e5',
          'MAUCO',       '#16a34a',
          '#999'
        ],
        'fill-opacity': 0.28
      }
    });
    map.addLayer({
      id: 'purok-outline',
      type: 'line',
      source: 'puroks',
      paint: { 'line-color': '#333', 'line-width': 1.2 }
    });
    map.addLayer({
      id: 'purok-labels',
      type: 'symbol',
      source: 'puroks',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 12,
        'text-offset': [0, 0.6],
        'text-anchor': 'top',
        'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold']
      },
      paint: { 'text-halo-color': '#fff', 'text-halo-width': 1 }
    });

    // Hook up "Locate on map" buttons
    wireLocateButtons();
  });

  function wireLocateButtons() {
    const buttons = document.querySelectorAll('.js-locate');
    buttons.forEach(btn => {
      btn.addEventListener('click', e => {
        const lat = parseFloat(btn.getAttribute('data-lat'));
        const lng = parseFloat(btn.getAttribute('data-lng'));
        if (isFinite(lat) && isFinite(lng)) {
          map.flyTo({ center: [lng, lat], zoom: 18, speed: 1.2, curve: 1.4 });

          // draw/replace focus marker
          if (focusMarker) focusMarker.remove();
          focusMarker = new mapboxgl.Marker({ color: '#6d2932' })
            .setLngLat([lng, lat])
            .addTo(map);
        }
      });
    });
  }
})();
