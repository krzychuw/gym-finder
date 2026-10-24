const POLAND_CENTER = [52.0, 19.2];

const map = L.map('map').setView(POLAND_CENTER, 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
}).addTo(map);

// Nationwide, the result set can run into the thousands - plotting that many
// individual markers directly on the map makes panning/zooming janky.
// markerClusterGroup groups nearby markers into one clickable cluster bubble
// that expands as you zoom in, and chunkedLoading spreads the work of adding
// a large batch of markers across animation frames instead of doing it all
// in one blocking pass, so the UI stays responsive.
const markerClusterGroup = L.markerClusterGroup({ chunkedLoading: true });
map.addLayer(markerClusterGroup);

let markers = [];
let allFacilities = [];

function clearMarkers() {
    markerClusterGroup.clearLayers();
    markers = [];
}

function renderPackageCheckboxes(packages) {
    const container = document.getElementById('package-checkboxes');
    container.innerHTML = '';
    packages.forEach((pkg) => {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = pkg.slug;
        input.checked = true;
        input.addEventListener('change', search);
        label.appendChild(input);
        label.appendChild(document.createTextNode(pkg.display_name));
        container.appendChild(label);
    });
}

function renderCategoryOptions(categories) {
    const select = document.getElementById('category-select');
    categories.forEach((cat) => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
    });
}

function getSelectedPackages() {
    return Array.from(document.querySelectorAll('#package-checkboxes input:checked')).map((el) => el.value);
}

function renderResults(facilities) {
    clearMarkers();
    const list = document.getElementById('result-list');
    const count = document.getElementById('result-count');
    list.innerHTML = '';

    if (facilities.length === 0) {
        count.textContent = 'Brak wyników.';
        list.innerHTML = '<div id="empty-state">Nie znaleziono obiektów spełniających kryteria.</div>';
        return;
    }

    count.textContent = `${facilities.length} ${facilities.length === 1 ? 'obiekt' : 'obiektów'}`;

    const bounds = [];
    const fragment = document.createDocumentFragment();
    facilities.forEach((f) => {
        const card = document.createElement('div');
        card.className = 'facility-card';

        const title = document.createElement('h3');
        title.textContent = f.name;
        card.appendChild(title);

        const address = document.createElement('div');
        address.className = 'address';
        address.textContent = f.address || '';
        card.appendChild(address);

        f.packages.forEach((p) => {
            const badge = document.createElement('span');
            badge.className = 'badge package';
            badge.textContent = p;
            card.appendChild(badge);
        });
        f.categories.forEach((c) => {
            const badge = document.createElement('span');
            badge.className = 'badge category';
            badge.textContent = c;
            card.appendChild(badge);
        });

        const marker = L.marker([f.lat, f.lon]);
        marker.bindPopup(`<strong>${f.name}</strong><br>${f.address || ''}<br>${f.packages.join(', ')}`);
        markers.push(marker);
        bounds.push([f.lat, f.lon]);

        card.addEventListener('click', () => {
            markerClusterGroup.zoomToShowLayer(marker, () => marker.openPopup());
        });

        fragment.appendChild(card);
    });
    list.appendChild(fragment);

    // addLayers (bulk) is far faster than calling addLayer per marker in a
    // loop - it batches the cluster tree rebuild instead of redoing it after
    // every single insert.
    markerClusterGroup.addLayers(markers);

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
    }
}

function search() {
    const selectedPackages = getSelectedPackages();
    const list = document.getElementById('result-list');
    const count = document.getElementById('result-count');

    if (selectedPackages.length === 0) {
        clearMarkers();
        list.innerHTML = '<div id="empty-state">Zaznacz co najmniej jeden pakiet.</div>';
        count.textContent = '';
        return;
    }

    const category = document.getElementById('category-select').value;

    const filtered = allFacilities.filter((f) => {
        const hasAllPackages = selectedPackages.every((p) => f.packages.includes(p));
        if (!hasAllPackages) return false;
        if (category && !f.categories.includes(category)) return false;
        return true;
    });

    renderResults(filtered);
}

async function init() {
    const [packages, categories, facilities] = await Promise.all([
        fetch('data/packages.json').then((r) => r.json()),
        fetch('data/categories.json').then((r) => r.json()),
        fetch('data/facilities.json').then((r) => r.json()),
    ]);
    allFacilities = facilities;
    renderPackageCheckboxes(packages);
    renderCategoryOptions(categories);
    document.getElementById('category-select').addEventListener('change', search);

    const categorySelect = document.getElementById('category-select');
    if (categories.includes('Siłownia')) {
        categorySelect.value = 'Siłownia';
    }

    search();
}

init();
