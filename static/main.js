function getPassengersFromForm(expectedCount) {
    const list = [];
    const rows = document.querySelectorAll('#passengersList .p-row');
    rows.forEach((row, idx) => {
        const name = row.querySelector('.p-name')?.value?.trim() || '';
        const phone = row.querySelector('.p-phone')?.value?.trim() || '';
        const email = row.querySelector('.p-email')?.value?.trim() || '';
        const ageStr = row.querySelector('.p-age')?.value || '';
        const gender = row.querySelector('.p-gender')?.value || '';
        const age = ageStr ? parseInt(ageStr, 10) : null;
        list.push({ name, phone, email, age, gender });
    });
    // trim or pad to expectedCount
    if (expectedCount && Number.isFinite(expectedCount)) {
        return list.slice(0, expectedCount);
    }
    return list;
}
let selectedBus = null;
let selectedSeats = [];
let currentSeatFare = 0;
let appliedCoupon = null;
let debounceTimer = null;
let hasSearched = false;
let lastResults = [];

async function searchBuses() {
    const from = document.getElementById('fromCity').value.trim();
    const to = document.getElementById('toCity').value.trim();
    const date = document.getElementById('travelDate').value;
    const operator = document.getElementById('operator')?.value.trim();
    const type = document.getElementById('busType')?.value;
    const fareMin = document.getElementById('fareMin')?.value.trim();
    const fareMax = document.getElementById('fareMax')?.value.trim();
    showSkeletons(6);

    const params = new URLSearchParams();
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    if (date) params.set('date', date);
    if (operator) params.set('operator', operator);
    if (type) params.set('type', type);
    if (fareMin) params.set('fare_min', fareMin);
    if (fareMax) params.set('fare_max', fareMax);

    try {
        const res = await fetch(`/api/buses?${params.toString()}`);
        const data = await res.json();
        lastResults = Array.isArray(data) ? data : [];
        applySortAndRender();
        updateTripSummary();
    } catch (e) {
        hideSkeletons();
        showToast('Network error while searching', 'error');
    }
}
function renderPassengerForms() {
    const wrap = document.getElementById('passengersList');
    if (!wrap) return;
    const n = selectedSeats.length;
    // Preserve entered values
    const prev = Array.from(wrap.querySelectorAll('.p-row')).map(row => ({
        name: row.querySelector('.p-name')?.value || '',
        email: row.querySelector('.p-email')?.value || '',
        age: row.querySelector('.p-age')?.value || '',
        gender: row.querySelector('.p-gender')?.value || '',
    }));
    wrap.innerHTML = '';
    for (let i = 0; i < n; i++) {
        const row = document.createElement('div');
        row.className = 'p-row';
        const seatLabel = 'Name';
        const vals = prev[i] || {};
        row.innerHTML = `
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;align-items:end">
            <label>${seatLabel}<input class="p-name" placeholder="Name" value="${vals.name||''}"></label>
            <label>Phone<input class="p-phone" type="tel" placeholder="Phone" value="${vals.phone||''}"></label>
            <label>Email<input class="p-email" type="email" placeholder="Email" value="${vals.email||''}"></label>
            <label>Age<input class="p-age" type="number" min="1" max="120" placeholder="Age" value="${vals.age||''}"></label>
            <label>Gender<select class="p-gender"><option value="">--</option><option value="Male" ${vals.gender==='Male'?'selected':''}>Male</option><option value="Female" ${vals.gender==='Female'?'selected':''}>Female</option><option value="Other" ${vals.gender==='Other'?'selected':''}>Other</option></select></label>
          </div>
        `;
        wrap.appendChild(row);
    }
}

function updateFareTotal() {
    const seatCount = selectedSeats.length;
    const base = (seatCount * (currentSeatFare || 0));
    const discount = appliedCoupon === 'TRIP100' ? 100 : 0;
    const total = Math.max(0, base - discount);
    const el = document.getElementById('fareTotal');
    if (el) el.textContent = String(total);
}

function renderSeatMap(data) {
    const seatMap = document.getElementById('seatMap');
    if (!seatMap) return;
    const booked = new Set(data.booked || []);
    const seats = data.seats || [];
    // Render as 2x2 columns with aisle
    seatMap.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'seat-grid';
    seats.forEach((label, idx) => {
        const seat = document.createElement('div');
        seat.className = 'seat available';
        seat.textContent = label;
        if (booked.has(label)) {
            seat.classList.remove('available');
            seat.classList.add('booked');
        }
        seat.dataset.label = label;
        seat.addEventListener('click', () => {
            if (seat.classList.contains('booked')) return;
            const i = selectedSeats.indexOf(label);
            if (i >= 0) {
                selectedSeats.splice(i, 1);
                seat.classList.remove('selected');
            } else {
                if (selectedSeats.length >= 6) { showToast('Max 6 seats per booking', 'warning'); return; }
                selectedSeats.push(label);
                seat.classList.add('selected');
            }
            updateFareTotal();
            renderPassengerForms();
            // seat count is derived from selectedSeats now
        });
        container.appendChild(seat);
        // insert aisle after two seats
        const col = (idx % 4);
        if (col === 1) {
            const aisle = document.createElement('div');
            aisle.className = 'aisle';
            container.appendChild(aisle);
        }
    });
    seatMap.appendChild(container);
}

function renderResults(buses) {
    const list = document.getElementById('bus-list');
    const empty = document.getElementById('no-results');
    list.innerHTML = '';
    if (!buses || buses.length === 0) {
        empty.style.display = hasSearched ? 'block' : 'none';
        return;
    }
    empty.style.display = 'none';
    buses.forEach(bus => {
        // Mock rating computation (stable per bus)
        if (bus._rating == null) {
            bus._rating = getMockRating(bus);
            bus._ratingCount = getMockRatingCount(bus);
        }
        // Lightweight heuristics for badges/amenities (front-end only)
        const isBestseller = Number(bus.fare || 0) <= 600 || /Orange|Kaveri|APSRTC/i.test(bus.name || '');
        const amenities = [];
        amenities.push('AC');
        if (/(Express|Luxury|Garuda|Rajadhani|Orange|Kaveri|Morning)/i.test(bus.name || '')) amenities.push('Charging');
        if (/(APSRTC|TSRTC|Morning|Orange|Komitla|SVKDT)/i.test(bus.name || '')) amenities.push('Water');
        const trusted = /(APSRTC|TSRTC|Orange|Kaveri|VRL|Morning|Garuda|Rajadhani|SRS)/i.test(bus.name || '');
        const ontime = /(Express|Super|Luxury|Rajadhani|Garuda)/i.test(bus.name || '') || Number(bus.fare||0) >= 600;
        const card = document.createElement('div');
        card.className = 'bus-card';
        card.setAttribute('data-id', String(bus.id));
        card.innerHTML = `
            <div class="bus-card-header">
              <div class="bus-operator">${bus.name}</div>
              <div class="bus-fare">₹${bus.fare}</div>
            </div>
            <div class="badges">
              ${isBestseller ? '<span class="badge badge-gold">Bestseller</span>' : ''}
              ${trusted ? '<span class="badge badge-green">Trusted</span>' : ''}
              ${ontime ? '<span class="badge badge-blue">On-time</span>' : ''}
            </div>
            <div class="bus-meta">
              <div class="rating"><span class="star">★</span> ${bus._rating.toFixed(1)} <span class="count">(${bus._ratingCount} reviews)</span></div>
              <div class="route">${bus.from_city} → ${bus.to_city}</div>
              <div class="times"><span>${bus.depart_time}</span> • <span>${bus.arrive_time}</span></div>
            </div>
            <div class="amenities">${amenities.map(a => `<span class="chip">${a}</span>`).join('')}</div>
            <div class="bus-card-footer">
              <button type="button" data-id="${bus.id}" class="select-btn">Select</button>
            </div>
        `;
        list.appendChild(card);
    });
    list.querySelectorAll('.select-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openBookingModal(parseInt(btn.getAttribute('data-id'), 10), buses);
        });
    });
}

async function openBookingModal(busId, buses) {
    selectedBus = buses.find(b => b.id === busId) || null;
    const modal = document.getElementById('bookingModal');
    const trip = document.getElementById('selectedTrip');
    if (selectedBus) {
        trip.textContent = `${selectedBus.name} • ${selectedBus.from_city} → ${selectedBus.to_city} • ${selectedBus.depart_time}`;
    } else {
        trip.textContent = '';
    }
    // reset seat state
    selectedSeats = [];
    currentSeatFare = Number(selectedBus?.fare || 0);
    document.getElementById('fareTotal').textContent = '0';
    const seatMap = document.getElementById('seatMap');
    seatMap.innerHTML = '';
    // fetch seats for date
    const date = document.getElementById('travelDate')?.value || '';
    try {
        const res = await fetch(`/api/buses/${busId}/seats?date=${encodeURIComponent(date)}`);
        const data = await res.json();
        currentSeatFare = Number(data.fare || selectedBus?.fare || 0);
        renderSeatMap(data);
        updateFareTotal();
        renderPassengerForms();
    } catch (e) {
        renderSeatMap({ layout: '2x2', booked: [], seats_total: 40, seats: Array.from({length:40}, (_,i)=>String(i+1)) });
        updateFareTotal();
        renderPassengerForms();
    }
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    // Force visible in case CSS class is missing
    modal.style.display = 'block';
    // Focus first passenger name field for better UX
    setTimeout(() => {
        const nameEl = document.querySelector('#passengersList .p-name');
        if (nameEl) nameEl.focus();
    }, 50);
}

function closeBookingModal() {
    const modal = document.getElementById('bookingModal');
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    modal.style.display = 'none';
}

async function confirmBooking() {
    if (!selectedBus) { alert('Please select a trip'); return; }
    const btn = document.getElementById('confirmBooking');
    const seats = selectedSeats.length;
    if (!(seats > 0)) { showToast('Please select seats', 'warning'); return; }
    const passengers = getPassengersFromForm(seats);
    // basic passenger validation: require name for each
    const allNamesOk = passengers.length >= seats && passengers.every(p => (p.name||'').length >= 2);
    if (!allNamesOk) {
        showToast('Please fill all details correctly', 'warning');
        return;
    }
    const contactName = passengers[0]?.name || 'Guest';
    const contactPhone = passengers[0]?.phone || '';
    try {
        btn.disabled = true;
        btn.textContent = 'Processing...';
        const res = await fetch('/api/bookings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bus_id: selectedBus.id,
                name: contactName,
                phone: contactPhone,
                seats,
                seat_numbers: selectedSeats,
                date: document.getElementById('travelDate')?.value || '',
                coupon_code: appliedCoupon || '',
                passengers
            })
        });
        if (!res.ok) {
            const txt = await res.text();
            throw new Error(`HTTP ${res.status}: ${txt}`);
        }
        const data = await res.json();
        if (data && data.status === 'success') {
            showToast('Booking successful!', 'success');
            // Close the modal before navigating away
            closeBookingModal();
            window.location.href = '/bookings';
        } else {
            throw new Error('Unexpected response');
        }
    } catch (err) {
        console.error('Booking error:', err);
        showToast('Something went wrong', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Confirm Booking';
    }
}

async function fetchSuggestions(query) {
    if (!query) return [];
    const res = await fetch(`/api/locations?q=${encodeURIComponent(query)}`);
    return await res.json();
}

function renderSuggestions(container, items) {
    container.innerHTML = '';
    if (!items || items.length === 0) {
        container.style.display = 'none';
        return;
    }
    items.slice(0, 8).forEach(text => {
        const div = document.createElement('div');
        div.className = 'suggestion-item';
        div.textContent = text;
        container.appendChild(div);
    });
    container.style.display = 'block';
}

function attachAutosuggest(inputEl, suggestEl) {
    function scheduleSuggest() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => {
            const q = inputEl.value.trim();
            if (!q) { suggestEl.style.display = 'none'; return; }
            const items = await fetchSuggestions(q);
            renderSuggestions(suggestEl, items);
        }, 200);
    }
    inputEl.addEventListener('input', scheduleSuggest);
    inputEl.addEventListener('focus', scheduleSuggest);
    inputEl.addEventListener('blur', () => setTimeout(() => { suggestEl.style.display = 'none'; }, 150));
    suggestEl.addEventListener('click', (e) => {
        const t = e.target;
        if (t && t.classList.contains('suggestion-item')) {
            inputEl.value = t.textContent;
            suggestEl.style.display = 'none';
            hasSearched = true;
            searchBuses();
        }
    });
}

window.addEventListener('DOMContentLoaded', () => {
    const searchBtn = document.getElementById('searchBtn');
    const closeBtn = document.getElementById('closeModal');
    const confirmBtn = document.getElementById('confirmBooking');
    const seatSelectBtn = document.getElementById('seatSelectDone');
    const applyCouponBtn = document.getElementById('applyCoupon');
    const modal = document.getElementById('bookingModal');
    const fromInp = document.getElementById('fromCity');
    const toInp = document.getElementById('toCity');
    const dateInp = document.getElementById('travelDate');
    const operatorInp = document.getElementById('operator');
    const typeSel = document.getElementById('busType');
    const fareMinInp = document.getElementById('fareMin');
    const fareMaxInp = document.getElementById('fareMax');
    if (searchBtn) searchBtn.addEventListener('click', () => { hasSearched = true; searchBuses(); });
    if (closeBtn) closeBtn.addEventListener('click', closeBookingModal);
    // Close when clicking outside the modal content (overlay click)
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeBookingModal();
        });
    }
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const m = document.getElementById('bookingModal');
            if (m && m.classList.contains('open')) closeBookingModal();
        }
    });
    if (confirmBtn) confirmBtn.addEventListener('click', confirmBooking);
    if (applyCouponBtn) applyCouponBtn.addEventListener('click', () => {
        const code = (document.getElementById('couponCode')?.value || '').trim().toUpperCase();
        const note = document.getElementById('discountNote');
        if (code === 'TRIP100') {
            appliedCoupon = 'TRIP100';
            updateFareTotal();
            if (note) { note.style.display = 'block'; note.textContent = 'Coupon TRIP100 applied: ₹100 off on total.'; }
            showToast('Coupon applied', 'success');
        } else {
            appliedCoupon = null;
            updateFareTotal();
            if (note) { note.style.display = 'block'; note.textContent = 'Invalid coupon'; }
            showToast('Invalid coupon', 'warning');
        }
    });
    // Recalculate total if user edits Seats input directly
    // seat count input removed; count follows selected seats
    if (seatSelectBtn) seatSelectBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const cnt = selectedSeats.length;
        if (cnt === 0) { showToast('Please select seats first', 'warning'); return; }
        showToast(`${cnt} seat(s) selected`, 'success');
        renderPassengerForms();
        // No auto-confirm; user completes passenger details and confirms
    });
    // Trigger search on Enter in any input
    [fromInp, toInp, dateInp, operatorInp, fareMinInp, fareMaxInp].forEach(inp => {
        if (!inp) return;
        inp.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { hasSearched = true; searchBuses(); }
        });
    });
    // Trigger search on change for dropdowns and price inputs
    if (typeSel) typeSel.addEventListener('change', () => { hasSearched = true; searchBuses(); });
    [operatorInp, fareMinInp, fareMaxInp].forEach(inp => {
        if (!inp) return;
        inp.addEventListener('change', () => { hasSearched = true; searchBuses(); });
        inp.addEventListener('blur', () => { if (hasSearched) searchBuses(); });
    });
    // Attach autosuggest to From/To
    const fromSuggest = document.getElementById('fromSuggest');
    const toSuggest = document.getElementById('toSuggest');
    if (fromInp && fromSuggest) attachAutosuggest(fromInp, fromSuggest);
    if (toInp && toSuggest) attachAutosuggest(toInp, toSuggest);
    // Do not auto-load results; wait until user searches
    const sortSel = document.getElementById('sortBy');
    if (sortSel) sortSel.addEventListener('change', () => { applySortAndRender(); updateTripSummary(); });



    // Delegated handler for Select buttons (more robust)
    const busList = document.getElementById('bus-list');
    if (busList) {
        busList.addEventListener('click', (e) => {
            const btn = e.target.closest && e.target.closest('.select-btn');
            let idAttr = null;
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                idAttr = btn.getAttribute('data-id');
            } else {
                const cardEl = e.target.closest && e.target.closest('.bus-card');
                if (!cardEl) return;
                idAttr = cardEl.getAttribute('data-id');
            }
            const id = idAttr ? parseInt(idAttr, 10) : NaN;
            if (!id || !Number.isFinite(id)) { console.error('Invalid bus id on Select'); return; }
            try {
                openBookingModal(id, lastResults);
            } catch (err) {
                console.error('Open modal error:', err);
                showToast('Cannot open booking right now', 'error');
            }
        });
    }
});

function applySortAndRender() {
    const sortSel = document.getElementById('sortBy');
    const v = sortSel ? sortSel.value : 'recommended';
    let arr = [...lastResults];
    const parseFare = x => Number(x?.fare ?? 0);
    const parseTime = t => new Date(t).getTime() || 0;
    switch (v) {
        case 'fare_asc': arr.sort((a,b)=>parseFare(a)-parseFare(b)); break;
        case 'fare_desc': arr.sort((a,b)=>parseFare(b)-parseFare(a)); break;
        case 'depart_asc': arr.sort((a,b)=>parseTime(a.depart_time)-parseTime(b.depart_time)); break;
        case 'depart_desc': arr.sort((a,b)=>parseTime(b.depart_time)-parseTime(a.depart_time)); break;
        case 'rating_desc':
            arr.forEach(b => { if (b._rating == null) b._rating = getMockRating(b); });
            arr.sort((a,b)=> (b._rating||0) - (a._rating||0));
            break;
        default: break;
    }
    hideSkeletons();
    renderResults(arr);
}

function getSortLabel(v) {
    switch (v) {
        case 'fare_asc': return 'Fare: Low to High';
        case 'fare_desc': return 'Fare: High to Low';
        case 'depart_asc': return 'Departure: Early to Late';
        case 'depart_desc': return 'Departure: Late to Early';
        case 'rating_desc': return 'Ratings: High to Low';
        default: return 'Recommended';
    }
}

function updateTripSummary() {
    const from = document.getElementById('fromCity')?.value?.trim() || '';
    const to = document.getElementById('toCity')?.value?.trim() || '';
    const date = document.getElementById('travelDate')?.value || '';
    const sortSel = document.getElementById('sortBy');
    const sortLabel = getSortLabel(sortSel ? sortSel.value : 'recommended');
    const bar = document.getElementById('tripSummary');
    if (!bar) return;
    const rEl = bar.querySelector('.ts-route');
    const dEl = bar.querySelector('.ts-date');
    const sEl = bar.querySelector('.ts-sort');
    if (rEl) rEl.textContent = (from && to) ? `${from} → ${to}` : '—';
    if (dEl) dEl.textContent = date ? `• ${date}` : '';
    if (sEl) sEl.textContent = `Sort: ${sortLabel}`;
}

// -------- Mock rating helpers (stable) --------
function hashStr(s) {
    let h = 0; for (let i=0;i<s.length;i++){ h = ((h<<5)-h) + s.charCodeAt(i); h |= 0; }
    return Math.abs(h);
}
function getMockRating(bus) {
    const key = `${bus.id}-${bus.name}-${bus.from_city}-${bus.to_city}`;
    const h = hashStr(key);
    let base = 4.1 + ((h % 8) / 20); // 4.1 - 4.5
    const fare = Number(bus.fare || 0);
    if (fare <= 600) base += 0.1;
    if (/APSRTC|TSRTC|Orange|Kaveri|Morning|Garuda|Rajadhani/i.test(bus.name||'')) base += 0.1;
    return Math.max(3.6, Math.min(4.9, base));
}
function getMockRatingCount(bus) {
    const h = hashStr(String(bus.id||0));
    const n = 200 + (h % 1800); // 200 - 1999
    return n.toLocaleString('en-IN');
}

function showSkeletons(n=6) {
    const list = document.getElementById('bus-list');
    const empty = document.getElementById('no-results');
    if (!list) return;
    empty.style.display = 'none';
    list.innerHTML = '';
    for (let i=0;i<n;i++) {
        const sk = document.createElement('div');
        sk.className = 'bus-card skeleton';
        sk.innerHTML = `
          <div class="sk-line w-60"></div>
          <div class="sk-line w-40"></div>
          <div class="sk-line w-80"></div>
        `;
        list.appendChild(sk);
    }
}

function hideSkeletons() {
    // no-op: renderResults will overwrite the list
}

function showToast(message, type='info') {
    const cont = document.getElementById('toasts');
    if (!cont) { alert(message); return; }
    const item = document.createElement('div');
    item.className = `toast ${type}`;
    item.textContent = message;
    cont.appendChild(item);
    setTimeout(()=>{ item.classList.add('show'); }, 10);
    setTimeout(()=>{
        item.classList.remove('show');
        setTimeout(()=> item.remove(), 200);
    }, 3000);
}
