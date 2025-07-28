function fill_home_address() {
    const street = document.getElementById('street').value.trim();
    const purokSitio = document.getElementById('purok_sitio').value.trim();
    const barangay = document.getElementById('barangay').value.trim();
    const city = document.getElementById('city').value.trim();

    // Filter out empty values, then join with comma
    const parts = [street, purokSitio, barangay, city].filter(part => part !== '');
    const fullAddress = parts.join(', ');

    document.getElementById('home_address').value = fullAddress;
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
      "properties" : {
        "name" : "Barangay Sto. Niño"
      }
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
      getAddressFromCoordinates(currentLngLat.lng, currentLngLat.lat);
    });

    function boundary_layers() {
      if(!map.getSource('sto-nino-BG')) {
        map.addSource('sto-nino-BG', {
            type: 'geojson',
            data: stoNinoBoundary
        });
      }
      if(!map.getLayer('sto-nino-outline')) {
        map.addLayer({
          id: 'sto-nino-outline',
          type: 'line',
          source: 'sto-nino-BG',
          paint: { 'line-color': '#000000', 'line-width': 2 }
        });
      }
      if(!map.getLayer('sto-nino-fill')) {
        map.addLayer({
          id: 'sto-nino-fill',
          type: 'fill',
          source: 'sto-nino-BG',
          paint: { 'fill-color': '#000000', 'fill-opacity': 0.1 }
        });
      }
      if (!document.querySelector('.mapboxgl-ctrl-group')) {
        map.addControl(new mapboxgl.NavigationControl(
          {showCompass: false}
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
                    if (purokInput) purokInput.value = purok;
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