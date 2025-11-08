const API_BASE = '';

const state = {
  token: null,
};

const authSection = document.getElementById('auth-section');
const dashboardSection = document.getElementById('dashboard');
const loginForm = document.getElementById('login-form');
const listingList = document.getElementById('listing-list');
const message = document.getElementById('message');
const refreshBtn = document.getElementById('refresh-btn');

function persistToken(token) {
  state.token = token;
  if (token) {
    localStorage.setItem('dauda_token', token);
  } else {
    localStorage.removeItem('dauda_token');
  }
}

function setAuthenticated(isAuthed) {
  if (isAuthed) {
    authSection.classList.add('hidden');
    dashboardSection.classList.remove('hidden');
  } else {
    authSection.classList.remove('hidden');
    dashboardSection.classList.add('hidden');
  }
}

async function fetchJSON(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Request failed');
  }
  return response.json();
}

function renderListings(listings) {
  listingList.innerHTML = '';
  if (!listings.length) {
    message.textContent = 'No listings yet. Create one from the API or admin tools.';
    return;
  }
  message.textContent = '';
  listings.forEach((listing) => {
    const li = document.createElement('li');
    li.className = 'listing-card';
    li.innerHTML = `
      <div class="listing-meta">
        <span class="badge">${listing.active ? 'Active' : 'Disabled'}</span>
        <span>${listing.timezone}</span>
      </div>
      <h3>${listing.name}</h3>
    `;
    listingList.appendChild(li);
  });
}

async function loadListings() {
  try {
    const listings = await fetchJSON('/listings');
    renderListings(listings);
  } catch (error) {
    console.error(error);
    message.textContent = 'Failed to load listings. Check your connection or permissions.';
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  try {
    const result = await fetchJSON('/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });
    persistToken(result.access_token);
    setAuthenticated(true);
    await loadListings();
  } catch (error) {
    console.error(error);
    alert('Login failed: ' + error.message);
  }
});

refreshBtn.addEventListener('click', () => {
  loadListings();
});

(function bootstrap() {
  const stored = localStorage.getItem('dauda_token');
  if (stored) {
    persistToken(stored);
    setAuthenticated(true);
    loadListings();
  }
})();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .catch((err) => console.error('Service worker registration failed', err));
  });
}
