/* ── State ── */
let projChart, ttChart, probChart, megaChart;
let routeMap, layer401, layer407;
let currentData = null; // latest /api/current response
let surveyLocation = { lat: null, lng: null, name: null };

/* ── Helpers ── */
function fmt(v, decimals = 0) {
    if (v == null || v === undefined) return '--';
    return Number(v).toFixed(decimals);
}

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function setColor(el, market, thesis) {
    if (market == null) { el.className = 'big-number'; return; }
    const ratio = market / thesis;
    if (ratio <= 1.0) el.className = 'big-number good';
    else if (ratio <= 1.5) el.className = 'big-number moderate';
    else el.className = 'big-number bad';
}

/* ── Polyline decoder (Google encoded polyline → [lat, lng] array) ── */
function decodePolyline(encoded) {
    const points = [];
    let index = 0, lat = 0, lng = 0;
    while (index < encoded.length) {
        let b, shift = 0, result = 0;
        do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
        lat += (result & 1) ? ~(result >> 1) : (result >> 1);
        shift = 0; result = 0;
        do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
        lng += (result & 1) ? ~(result >> 1) : (result >> 1);
        points.push([lat / 1e5, lng / 1e5]);
    }
    return points;
}

/* ── Map ── */
function initMap() {
    routeMap = L.map('routeMap', {
        center: [43.72, -79.45],
        zoom: 9,
        zoomControl: true,
        attributionControl: true,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        maxZoom: 16,
    }).addTo(routeMap);

    // Default corridors (approximate) — replaced by live polylines when available
    const default401 = [
        [43.51, -79.89], [43.55, -79.72], [43.60, -79.55], [43.64, -79.40],
        [43.66, -79.33], [43.70, -79.25], [43.74, -79.15], [43.80, -79.05],
        [43.85, -78.95], [43.87, -78.94]
    ];
    const default407 = [
        [43.51, -79.89], [43.58, -79.78], [43.65, -79.62], [43.72, -79.52],
        [43.78, -79.42], [43.82, -79.32], [43.84, -79.20], [43.86, -79.08],
        [43.87, -78.98], [43.87, -78.94]
    ];

    layer401 = L.polyline(default401, {
        color: '#3b82f6', weight: 4, opacity: 0.8,
        dashArray: null,
    }).addTo(routeMap).bindPopup('Hwy 401 — Through Toronto (Free)');

    layer407 = L.polyline(default407, {
        color: '#8b5cf6', weight: 4, opacity: 0.8,
        dashArray: '8 6',
    }).addTo(routeMap).bindPopup('Hwy 407 ETR — Bypass (Toll)');

    // Markers for origin/destination
    const truckIcon = L.divIcon({
        html: '<div style="font-size:20px">📍</div>',
        iconSize: [24, 24], iconAnchor: [12, 24], className: '',
    });

    L.marker([43.51, -79.89], { icon: truckIcon })
        .addTo(routeMap).bindPopup('<strong>Milton</strong><br>Hwy 401 @ Hwy 403<br><em>Decision point (west)</em>');
    L.marker([43.87, -78.94], { icon: truckIcon })
        .addTo(routeMap).bindPopup('<strong>Whitby</strong><br>Hwy 401 @ Hwy 412<br><em>Decision point (east)</em>');

    // Fit bounds
    const group = L.featureGroup([layer401, layer407]);
    routeMap.fitBounds(group.getBounds().pad(0.1));
}

function updateMapPolylines(r401, r407) {
    if (r401.polyline) {
        const coords = decodePolyline(r401.polyline);
        layer401.setLatLngs(coords);
    }
    if (r407.polyline) {
        const coords = decodePolyline(r407.polyline);
        layer407.setLatLngs(coords);
    }
    // Refit
    const group = L.featureGroup([layer401, layer407]);
    routeMap.fitBounds(group.getBounds().pad(0.08));
}

/* ── Current conditions ── */
async function updateCurrent() {
    try {
        const d = await fetchJSON('/api/current');
        const r401 = d.route_401;
        const r407 = d.route_407;
        const toll = d.toll;
        const vot = d.vot;

        // Route cards
        document.getElementById('tt401').innerHTML = `${fmt(r401.tt_minutes)}<span class="unit">min</span>`;
        document.getElementById('delay401').textContent = fmt(r401.delay_minutes);
        document.getElementById('dist401').textContent = fmt(r401.distance_km);

        document.getElementById('tt407').innerHTML = `${fmt(r407.tt_minutes)}<span class="unit">min</span>`;
        document.getElementById('delay407').textContent = fmt(r407.delay_minutes);
        document.getElementById('dist407').textContent = fmt(r407.distance_km);
        document.getElementById('tollCostSmall').textContent = `$${fmt(toll.total, 2)}`;

        const badge = document.getElementById('timePeriodBadge');
        badge.textContent = toll.time_period.replace('_', '-');
        badge.className = `time-period-badge ${toll.time_period}`;

        // VOT verdict
        const mvEl = document.getElementById('marketVot');
        mvEl.innerHTML = `${vot.market_vot != null ? fmt(vot.market_vot) : '&infin;'}<span class="unit">$/hr</span>`;
        setColor(mvEl, vot.market_vot, vot.thesis_vot_mean);

        document.getElementById('timeSaved').textContent = `${fmt(vot.time_saved_minutes)}m`;
        document.getElementById('tollCost').textContent = `$${fmt(vot.toll_cost, 2)}`;
        document.getElementById('choiceProb').textContent = `${fmt(vot.choice_probability_toll_simulated, 1)}%`;
        document.getElementById('fairToll').textContent = `$${fmt(vot.fair_toll_at_mean_vot, 2)}`;
        document.getElementById('verdictText').textContent = vot.verdict;

        // Verdict bar
        const bar = document.getElementById('verdictBar');
        if (vot.market_vot != null) {
            const pct = Math.min(100, (vot.thesis_vot_mean / vot.market_vot) * 100);
            bar.style.width = pct + '%';
            const ratio = vot.market_vot / vot.thesis_vot_mean;
            if (ratio <= 1.0) bar.style.background = 'var(--green)';
            else if (ratio <= 1.5) bar.style.background = 'var(--amber)';
            else bar.style.background = 'var(--red)';
        }

        // Toll breakdown
        const segDiv = document.getElementById('tollSegments');
        segDiv.innerHTML = toll.segments.map(s =>
            `<div class="toll-segment">
                <span class="seg-name">${s.from} → ${s.to} (${s.distance_km}km)</span>
                <span class="seg-cost">$${s.cost.toFixed(2)}</span>
            </div>`
        ).join('') + `<div class="toll-segment">
            <span class="seg-name">Trip charge (${toll.has_transponder ? 'transponder' : 'video'})</span>
            <span class="seg-cost">$${toll.trip_charge.toFixed(2)}</span>
        </div>`;
        document.getElementById('tollTotal').textContent = `$${toll.total.toFixed(2)}`;

        // Status
        const dot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        dot.className = d.source === 'google_maps' ? 'status-dot' : 'status-dot estimated';
        statusText.textContent = d.source === 'google_maps' ? 'Live traffic data' : 'Estimated (no API key)';

        // Timestamps
        const ts = new Date(d.timestamp);
        const timeStr = ts.toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = `Updated ${timeStr}`;
        document.getElementById('footerUpdate').textContent = `Updated ${timeStr}`;

        // Update map polylines
        updateMapPolylines(r401, r407);

        // Update popups with live data
        layer401.setPopupContent(
            `<strong>Hwy 401 — Through Toronto</strong><br>` +
            `Travel time: ${fmt(r401.tt_minutes)} min<br>` +
            `Delay: ${fmt(r401.delay_minutes)} min<br>` +
            `Distance: ${fmt(r401.distance_km)} km<br>` +
            `<em>Free route</em>`
        );
        layer407.setPopupContent(
            `<strong>Hwy 407 ETR — Bypass</strong><br>` +
            `Travel time: ${fmt(r407.tt_minutes)} min<br>` +
            `Delay: ${fmt(r407.delay_minutes)} min<br>` +
            `Distance: ${fmt(r407.distance_km)} km<br>` +
            `Toll: $${fmt(toll.total, 2)} (${toll.time_period.replace('_','-')})`
        );

        // Store for survey use
        currentData = d;
        updateSurveyConditions();

    } catch (e) {
        console.error('Failed to fetch current data:', e);
        document.getElementById('statusDot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'Connection error';
    }
}

/* ── "Now" annotation for charts ── */
function nowAnnotation(labels) {
    const now = new Date();
    const nowMinutes = now.getHours() * 60 + now.getMinutes();
    // Find the nearest label index
    let bestIdx = 0, bestDiff = Infinity;
    labels.forEach((lbl, i) => {
        const [h, m] = lbl.split(':').map(Number);
        const diff = Math.abs(h * 60 + m - nowMinutes);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
    });
    return {
        type: 'line',
        xMin: bestIdx,
        xMax: bestIdx,
        borderColor: 'rgba(255,255,255,0.4)',
        borderWidth: 2,
        borderDash: [4, 3],
        label: {
            display: true,
            content: 'Now',
            position: 'start',
            color: 'rgba(255,255,255,0.7)',
            font: { size: 10, weight: 'bold' },
            backgroundColor: 'rgba(26,29,39,0.8)',
            padding: 3,
        },
    };
}

/* ── 24h Projection ── */
async function updateProjection() {
    try {
        const d = await fetchJSON('/api/projection');
        document.getElementById('projDay').textContent = `${d.day_name} (${d.date})`;
        const data = d.data;
        const labels = data.map(p => p.time_label);
        const thesisLine = data.map(() => d.thesis_vot_mean);

        const nowLine = nowAnnotation(labels);

        // Projection chart: market VOT vs thesis VOT
        const ctx1 = document.getElementById('projChart').getContext('2d');
        if (projChart) projChart.destroy();
        projChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Market VOT (407 charges)',
                        data: data.map(p => p.market_vot),
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239,68,68,0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                    {
                        label: 'Thesis VOT ($81/hr)',
                        data: thesisLine,
                        borderColor: '#22c55e',
                        borderDash: [6, 4],
                        pointRadius: 0,
                        borderWidth: 2,
                        fill: false,
                    },
                ],
            },
            options: {
                ...chartOpts('$/hr', 0, 600),
                plugins: {
                    ...chartOpts('$/hr', 0, 600).plugins,
                    annotation: { annotations: { nowLine } },
                },
            },
        });

        // Travel time chart
        const ctx2 = document.getElementById('ttChart').getContext('2d');
        if (ttChart) ttChart.destroy();
        ttChart = new Chart(ctx2, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 Travel Time',
                        data: data.map(p => p.tt_401),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                    {
                        label: '407 Travel Time',
                        data: data.map(p => p.tt_407),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139,92,246,0.08)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                ...chartOpts('minutes', 30, 140),
                plugins: {
                    ...chartOpts('minutes', 30, 140).plugins,
                    annotation: { annotations: { nowLine: nowAnnotation(labels) } },
                },
            },
        });

        // Choice probability chart
        const ctx3 = document.getElementById('probChart').getContext('2d');
        if (probChart) probChart.destroy();
        probChart = new Chart(ctx3, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'P(choose 407)',
                        data: data.map(p => p.choice_prob_toll),
                        backgroundColor: data.map(p => {
                            if (p.choice_prob_toll >= 50) return 'rgba(34,197,94,0.7)';
                            if (p.choice_prob_toll >= 30) return 'rgba(245,158,11,0.7)';
                            return 'rgba(239,68,68,0.5)';
                        }),
                        borderRadius: 2,
                    },
                ],
            },
            options: {
                ...chartOpts('%', 0, 100),
                plugins: {
                    ...chartOpts('%', 0, 100).plugins,
                    annotation: { annotations: { nowLine: nowAnnotation(labels) } },
                },
            },
        });
    } catch (e) {
        console.error('Failed to fetch projection:', e);
    }
}

function chartOpts(yLabel, sugMin, sugMax) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                labels: { color: '#8b8d97', font: { size: 11 } },
            },
            tooltip: {
                backgroundColor: '#1a1d27',
                borderColor: '#2a2d3a',
                borderWidth: 1,
                titleColor: '#e4e4e7',
                bodyColor: '#e4e4e7',
                callbacks: {
                    label: function(ctx) {
                        const val = ctx.parsed.y;
                        if (val == null) return ctx.dataset.label + ': N/A';
                        if (yLabel === '$/hr') return `${ctx.dataset.label}: $${val.toFixed(0)}/hr`;
                        if (yLabel === '%') return `${ctx.dataset.label}: ${val.toFixed(1)}%`;
                        return `${ctx.dataset.label}: ${val.toFixed(0)} ${yLabel}`;
                    },
                },
            },
        },
        scales: {
            x: {
                ticks: { color: '#8b8d97', maxTicksLimit: 12, font: { size: 10 } },
                grid: { color: 'rgba(42,45,58,0.5)' },
            },
            y: {
                title: { display: true, text: yLabel, color: '#8b8d97' },
                ticks: { color: '#8b8d97' },
                grid: { color: 'rgba(42,45,58,0.5)' },
                suggestedMin: sugMin,
                suggestedMax: sugMax,
            },
        },
    };
}

/* ── Methodology toggle ── */
function initMethodology() {
    const toggle = document.getElementById('methodologyToggle');
    const content = document.getElementById('methodologyContent');
    toggle.addEventListener('click', () => {
        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', !isOpen);
        content.classList.toggle('open');
    });
}

/* ── Mega chart (unified historical) ── */
async function updateMegaChart(range = '24h') {
    try {
        const d = await fetchJSON(`/api/history/range?range=${range}`);
        if (!d.data || d.data.length === 0) return;

        const data = d.data;
        const labels = data.map(p => {
            const lbl = p.time_label || '';
            if (range === '24h') {
                // Trim ISO timestamp to HH:MM
                return lbl.length > 16 ? lbl.substring(11, 16) : lbl;
            }
            if (range === '7d') return lbl.substring(5, 13); // MM-DD HH
            if (range === '30d') return lbl.substring(5, 10); // MM-DD
            return lbl.substring(5, 10); // 365d: MM-DD
        });

        const ctx = document.getElementById('megaChart').getContext('2d');
        if (megaChart) megaChart.destroy();

        megaChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 Travel Time (min)',
                        data: data.map(p => p.tt_401),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.06)',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        yAxisID: 'y',
                    },
                    {
                        label: '407 Travel Time (min)',
                        data: data.map(p => p.tt_407),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139,92,246,0.06)',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Market VOT ($/hr)',
                        data: data.map(p => p.market_vot != null ? Math.min(p.market_vot, 500) : null),
                        borderColor: '#ef4444',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        borderDash: [4, 2],
                        yAxisID: 'y2',
                    },
                    {
                        label: 'Toll Cost ($)',
                        data: data.map(p => p.toll_cost),
                        borderColor: '#22c55e',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                        yAxisID: 'y2',
                    },
                    {
                        label: 'Choice Prob (%)',
                        data: data.map(p => p.choice_prob_toll),
                        borderColor: '#f59e0b',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                        borderDash: [6, 3],
                        yAxisID: 'y3',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false }, // using custom legend
                    tooltip: {
                        backgroundColor: '#1a1d27', borderColor: '#2a2d3a', borderWidth: 1,
                        titleColor: '#e4e4e7', bodyColor: '#e4e4e7',
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#8b8d97', maxTicksLimit: 16, font: { size: 10 } },
                        grid: { color: 'rgba(42,45,58,0.5)' },
                    },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Travel Time (min)', color: '#8b8d97' },
                        ticks: { color: '#8b8d97' },
                        grid: { color: 'rgba(42,45,58,0.3)' },
                    },
                    y2: {
                        position: 'right',
                        title: { display: true, text: '$/hr or $', color: '#8b8d97' },
                        ticks: { color: '#8b8d97' },
                        grid: { display: false },
                    },
                    y3: {
                        position: 'right',
                        title: { display: false },
                        ticks: { display: false },
                        grid: { display: false },
                        min: 0, max: 100,
                    },
                },
            },
        });
    } catch (e) {
        console.error('Mega chart error:', e);
    }
}

function initMegaChart() {
    // Range selector buttons
    document.querySelectorAll('.range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            updateMegaChart(btn.dataset.range);
        });
    });

    // Custom legend toggle
    document.querySelectorAll('.mega-legend-item').forEach(item => {
        item.addEventListener('click', () => {
            if (!megaChart) return;
            const idx = parseInt(item.dataset.ds);
            const meta = megaChart.getDatasetMeta(idx);
            meta.hidden = !meta.hidden;
            item.classList.toggle('hidden');
            megaChart.update();
        });
    });

    updateMegaChart('24h');
}

/* ── Survey ── */
function initSurvey() {
    // Location button
    document.getElementById('locateBtn').addEventListener('click', () => {
        if (!navigator.geolocation) {
            document.getElementById('locationStatus').textContent = 'Geolocation not supported';
            return;
        }
        document.getElementById('locationStatus').textContent = 'Detecting...';
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                surveyLocation.lat = pos.coords.latitude;
                surveyLocation.lng = pos.coords.longitude;
                const btn = document.getElementById('locateBtn');
                btn.classList.add('located');
                btn.innerHTML = `<span class="locate-icon">✅</span> Location detected`;
                // Reverse geocode for display
                document.getElementById('locationStatus').textContent =
                    `${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)}`;
            },
            (err) => {
                document.getElementById('locationStatus').textContent = 'Location denied — no problem, survey still works!';
            },
            { timeout: 10000, enableHighAccuracy: false }
        );
    });

    // Option buttons (single select per group)
    document.querySelectorAll('.survey-options').forEach(group => {
        group.querySelectorAll('.survey-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                group.querySelectorAll('.survey-opt').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                checkSurveyComplete();
            });
        });
    });

    // Submit
    document.getElementById('submitSurvey').addEventListener('click', submitSurvey);
    document.getElementById('resetSurvey').addEventListener('click', resetSurvey);

    // Load initial stats
    loadSurveyStats();
}

function checkSurveyComplete() {
    const vehicle = document.querySelector('#vehicleType .selected');
    const trip = document.querySelector('#tripType .selected');
    const company = document.querySelector('#companyPays .selected');
    const self = document.querySelector('#selfPays .selected');
    document.getElementById('submitSurvey').disabled = !(vehicle && trip && company && self);
}

async function submitSurvey() {
    const vehicle = document.querySelector('#vehicleType .selected')?.dataset.value;
    const trip = document.querySelector('#tripType .selected')?.dataset.value;
    const freq = document.querySelector('#frequency .selected')?.dataset.value;
    const company = document.querySelector('#companyPays .selected')?.dataset.value;
    const self = document.querySelector('#selfPays .selected')?.dataset.value;

    const payload = {
        lat: surveyLocation.lat,
        lng: surveyLocation.lng,
        location_name: surveyLocation.name,
        tt_401: currentData?.route_401?.tt_minutes,
        tt_407: currentData?.route_407?.tt_minutes,
        toll_cost: currentData?.toll?.total,
        time_saved: currentData?.vot?.time_saved_minutes,
        market_vot: currentData?.vot?.market_vot,
        time_period: currentData?.toll?.time_period,
        vehicle_type: vehicle,
        trip_type: trip,
        frequency: freq,
        choice_if_company_pays: company,
        choice_if_self_pays: self,
        user_agent: navigator.userAgent,
    };

    try {
        await fetch('/api/survey', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        // Show thanks + insights
        document.getElementById('surveyStep1').style.display = 'none';
        document.getElementById('surveyStep2').style.display = 'block';
        await loadSurveyStats(true);
    } catch (e) {
        console.error('Survey submit error:', e);
    }
}

function resetSurvey() {
    document.getElementById('surveyStep1').style.display = 'block';
    document.getElementById('surveyStep2').style.display = 'none';
    document.querySelectorAll('.survey-opt').forEach(b => b.classList.remove('selected'));
    document.getElementById('submitSurvey').disabled = true;
}

async function loadSurveyStats(showInsights = false) {
    try {
        const stats = await fetchJSON('/api/survey/stats');
        document.getElementById('insightBadge').textContent =
            stats.total_responses > 0 ? `${stats.total_responses} responses` : 'Be the first!';

        if (showInsights || stats.total_responses > 0) {
            document.getElementById('insCompanyYes').textContent = `${stats.company_pays_yes_pct}%`;
            document.getElementById('insSelfYes').textContent = `${stats.self_pays_yes_pct}%`;
            document.getElementById('insTotal').textContent = stats.total_responses;
            document.getElementById('insToday').textContent = stats.responses_24h || 0;
        }
    } catch (e) {
        // Survey stats not critical
    }
}

function updateSurveyConditions() {
    if (!currentData) return;
    const r401 = currentData.route_401;
    const r407 = currentData.route_407;
    const toll = currentData.toll;
    const vot = currentData.vot;

    document.getElementById('survTT401').textContent = fmt(r401.tt_minutes);
    document.getElementById('survDelay401').textContent = fmt(r401.delay_minutes);
    document.getElementById('survTT407').textContent = fmt(r407.tt_minutes);
    document.getElementById('survToll').textContent = fmt(toll.total, 2);
    document.getElementById('survTimeSaved').textContent = fmt(vot.time_saved_minutes);

    // Update inline toll references in questions
    document.querySelectorAll('.survTollInline').forEach(el => {
        el.textContent = fmt(toll.total, 2);
    });
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initMethodology();
    initMegaChart();
    initSurvey();
    updateCurrent();
    updateProjection();

    // Auto-refresh: current every 30s, projection every 10 min, mega chart every 5 min
    setInterval(updateCurrent, 30_000);
    setInterval(updateProjection, 10 * 60_000);
    setInterval(() => {
        const active = document.querySelector('.range-btn.active');
        if (active) updateMegaChart(active.dataset.range);
    }, 5 * 60_000);
});
