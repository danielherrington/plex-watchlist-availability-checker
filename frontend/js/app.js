let continueWatching = [];
let missingItems = [];
let unwatchedItems = [];
let sagasProgress = [];
let ignoredBackend = [];

let activeTab = 'continue';
let currentFilter = 'all';
let currentSort = 'title-asc';

async function loadDashboard() {
    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();
        
        continueWatching = data.continue_watching || [];
        missingItems = data.missing_items || [];
        unwatchedItems = data.unwatched_local_gaps || [];
        sagasProgress = data.sagas_progress || [];
        ignoredBackend = data.ignored_shows || [];
        
        document.getElementById('server-name-label').textContent = data.server_name || 'Connected';
        
        updateCounts();
        filterAndRender();
    } catch (error) {
        console.error('Error loading dashboard:', error);
        document.getElementById('server-name-label').textContent = 'Connection Error';
    }
}

function isItemInQueue(item) {
    return item.watch_next;
}

function isShowIgnored(item) {
    if (item.type !== 'show') return false;
    const title = item.title.toLowerCase();
    return ignoredBackend.includes(title) || ignoredBackend.includes(item.ratingKey);
}

async function ignoreShow(ratingKey, title) {
    const key = ratingKey || title.toLowerCase();
    if (!ignoredBackend.includes(key)) {
        ignoredBackend.push(key);
    }
    
    updateCounts();
    filterAndRender();
    
    try {
        await fetch('/api/ignore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ratingKey: ratingKey, title: title })
        });
    } catch (e) {
        console.error('Failed to sync ignore with backend:', e);
    }
}

async function clearIgnored() {
    ignoredBackend = [];
    updateCounts();
    filterAndRender();
    
    try {
        await fetch('/api/unignore_all', { method: 'POST' });
        loadDashboard();
    } catch (e) {
        console.error('Failed to clear ignores on backend:', e);
    }
}

async function toggleQueue(ratingKey, title) {
    let target = null;
    const findAndToggle = (list) => {
        const item = list.find(i => i.ratingKey === ratingKey || i.title === title);
        if (item) {
            item.watch_next = !item.watch_next;
            target = item;
        }
    };
    findAndToggle(unwatchedItems);
    findAndToggle(missingItems);
    findAndToggle(continueWatching);
    
    updateCounts();
    filterAndRender();
    
    if (target) {
        const endpoint = target.watch_next ? '/api/queue' : '/api/unqueue';
        try {
            await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ratingKey: ratingKey, title: title })
            });
        } catch (e) {
            console.error('Failed to sync queue with backend:', e);
        }
    }
}

function updateCounts() {
    const visibleContinue = continueWatching.filter(item => !isShowIgnored(item));
    document.getElementById('badge-continue').textContent = visibleContinue.length;

    const allUnwatched = [...unwatchedItems, ...missingItems].filter(item => !isShowIgnored(item));
    const watchNextItems = allUnwatched.filter(item => isItemInQueue(item));
    document.getElementById('badge-watchnext').textContent = watchNextItems.length;

    const visibleUnwatched = unwatchedItems.filter(item => !isShowIgnored(item));
    document.getElementById('badge-unwatched').textContent = visibleUnwatched.length;

    const visibleMissing = missingItems.filter(item => !isShowIgnored(item));
    document.getElementById('badge-missing').textContent = visibleMissing.length;

    document.getElementById('badge-sagas').textContent = sagasProgress.length;
}

function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    
    const sortSelect = document.getElementById('sort-select');
    const mediaFilterGroup = document.getElementById('media-filter-group');
    
    if (activeTab === 'sagas') {
        mediaFilterGroup.style.display = 'none';
        document.getElementById('opt-added-desc').style.display = 'none';
        document.getElementById('opt-added-asc').style.display = 'none';
        document.getElementById('opt-progress-desc').style.display = 'block';
        document.getElementById('opt-progress-asc').style.display = 'block';
        
        if (currentSort.startsWith('added')) {
            currentSort = 'progress-desc';
            sortSelect.value = 'progress-desc';
        }
    } else if (activeTab === 'continue') {
        mediaFilterGroup.style.display = 'flex';
        document.getElementById('opt-added-desc').style.display = 'none';
        document.getElementById('opt-added-asc').style.display = 'none';
        document.getElementById('opt-progress-desc').style.display = 'block';
        document.getElementById('opt-progress-asc').style.display = 'block';
        
        if (currentSort.startsWith('added')) {
            currentSort = 'title-asc';
            sortSelect.value = 'title-asc';
        }
    } else if (activeTab === 'unwatched' || activeTab === 'watchnext') {
        mediaFilterGroup.style.display = 'flex';
        document.getElementById('opt-added-desc').style.display = 'none';
        document.getElementById('opt-added-asc').style.display = 'none';
        document.getElementById('opt-progress-desc').style.display = 'none';
        document.getElementById('opt-progress-asc').style.display = 'none';
        
        if (currentSort.startsWith('added') || currentSort.startsWith('progress')) {
            currentSort = 'title-asc';
            sortSelect.value = 'title-asc';
        }
    } else {
        mediaFilterGroup.style.display = 'flex';
        document.getElementById('opt-added-desc').style.display = 'block';
        document.getElementById('opt-added-asc').style.display = 'block';
        document.getElementById('opt-progress-desc').style.display = 'none';
        document.getElementById('opt-progress-asc').style.display = 'none';
        
        if (currentSort.startsWith('progress')) {
            currentSort = 'added-desc';
            sortSelect.value = 'added-desc';
        }
    }
    
    filterAndRender();
}

function setFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById('filter-' + filter).classList.add('active');
    filterAndRender();
}

function setSort(sortVal) {
    currentSort = sortVal;
    filterAndRender();
}

function filterAndRender() {
    const searchVal = document.getElementById('search-input').value.toLowerCase().trim();
    const grid = document.getElementById('items-grid');
    const emptyState = document.getElementById('empty-state');

    let sourceList = [];
    if (activeTab === 'continue') sourceList = continueWatching;
    else if (activeTab === 'missing') sourceList = missingItems;
    else if (activeTab === 'unwatched') sourceList = unwatchedItems;
    else if (activeTab === 'sagas') sourceList = sagasProgress;
    else if (activeTab === 'watchnext') {
        const allUnwatched = [...unwatchedItems, ...missingItems];
        sourceList = allUnwatched.filter(item => isItemInQueue(item));
    }

    let filtered = sourceList.filter(item => {
        if (isShowIgnored(item)) return false;

        if (activeTab !== 'sagas' && currentFilter !== 'all') {
            if (currentFilter === 'movie' && item.type === 'show') return false;
            if (currentFilter === 'show' && (item.type === 'movie' || item.type === 'saga')) return false;
        }
        
        if (searchVal) {
            const titleMatch = item.title.toLowerCase().includes(searchVal);
            const yearMatch = item.year && item.year.toString().includes(searchVal);
            return titleMatch || yearMatch;
        }
        return true;
    });

    filtered.sort((a, b) => {
        if (currentSort === 'title-asc') {
            return a.title.localeCompare(b.title);
        } else if (currentSort === 'title-desc') {
            return b.title.localeCompare(a.title);
        } else if (currentSort === 'year-desc') {
            const yrA = a.year || (a.next_movie ? a.next_movie.year : 0);
            const yrB = b.year || (b.next_movie ? b.next_movie.year : 0);
            return yrB - yrA;
        } else if (currentSort === 'year-asc') {
            const yrA = a.year || (a.next_movie ? a.next_movie.year : 0);
            const yrB = b.year || (b.next_movie ? b.next_movie.year : 0);
            return yrA - yrB;
        } else if (currentSort === 'added-desc') {
            return (b.added_at || '').localeCompare(a.added_at || '');
        } else if (currentSort === 'added-asc') {
            return (a.added_at || '').localeCompare(b.added_at || '');
        } else if (currentSort === 'progress-desc') {
            const progA = a.total_episodes || a.total_movies ? ((a.viewed_episodes || a.watched_movies || 0) / (a.total_episodes || a.total_movies || 1)) : 0;
            const progB = b.total_episodes || b.total_movies ? ((b.viewed_episodes || b.watched_movies || 0) / (b.total_episodes || b.total_movies || 1)) : 0;
            return progB - progA;
        } else if (currentSort === 'progress-asc') {
            const progA = a.total_episodes || a.total_movies ? ((a.viewed_episodes || a.watched_movies || 0) / (a.total_episodes || a.total_movies || 1)) : 0;
            const progB = b.total_episodes || b.total_movies ? ((b.viewed_episodes || b.watched_movies || 0) / (b.total_episodes || b.total_movies || 1)) : 0;
            return progA - progB;
        }
        return 0;
    });

    grid.innerHTML = '';
    
    if (filtered.length === 0) {
        emptyState.style.display = 'flex';
        if (searchVal) {
            emptyState.querySelector('h3').textContent = 'No Matches Found';
            emptyState.querySelector('p').textContent = 'Try adjusting your search query.';
        } else {
            emptyState.querySelector('h3').textContent = 'No Items';
            if (activeTab === 'continue') emptyState.querySelector('p').textContent = 'You have no TV shows or Sagas in progress right now.';
            else if (activeTab === 'missing') emptyState.querySelector('p').textContent = 'Everything in your watchlist is present on the server!';
            else if (activeTab === 'unwatched') emptyState.querySelector('p').textContent = 'No unwatched gaps found.';
            else if (activeTab === 'sagas') emptyState.querySelector('p').textContent = 'No Sagas loaded.';
            else if (activeTab === 'watchnext') emptyState.querySelector('p').textContent = 'Your Watch Next queue is empty. Pin items in the Unwatched or Gaps tabs!';
        }
    } else {
        emptyState.style.display = 'none';
        filtered.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card';

            let typeLabel = '';
            if (item.type === 'movie') typeLabel = 'Movie';
            else if (item.type === 'show') typeLabel = 'TV Show';
            else if (item.type === 'saga') typeLabel = 'Movie Saga';
            else typeLabel = 'Saga';

            let primaryLink = '#';
            let primaryBtnText = 'View';
            let metaInfoHTML = '';
            let badgeClass = item.type;
            let showQueueBtn = false;
            let showIgnoreBtn = false;
            
            if (activeTab === 'continue') {
                const isSaga = item.type === 'saga';
                badgeClass = item.status;
                
                if (isSaga) {
                    const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                    primaryLink = item.plex_link;
                    primaryBtnText = item.status === 'available' ? 'Watch Now' : 'Plex Info';

                    metaInfoHTML = `
                        <div class="card-meta">
                            <span class="year">Next Film</span>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${percentage}%;"></div>
                            </div>
                            <span class="progress-text">Saga Progress: ${item.viewed_episodes} of ${item.total_episodes} films watched (${percentage}%)</span>
                        </div>
                        <div class="status-badge ${item.status}">${item.status_label}</div>
                    `;
                } else {
                    showIgnoreBtn = true;
                    const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                    primaryLink = item.plex_link || `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=${item.next_episode ? item.next_episode.ratingKey || item.next_episode.title : ''}`;
                    primaryBtnText = item.status === 'available' ? 'Play S' + item.next_episode.season + 'E' + item.next_episode.episode : 'Info';

                    const epTitle = item.next_episode ? `"${item.next_episode.title}"` : 'TBA';
                    metaInfoHTML = `
                        <div class="card-meta">
                            <span class="year">${epTitle}</span>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${percentage}%;"></div>
                            </div>
                            <span class="progress-text">${item.viewed_episodes} of ${item.total_episodes} episodes watched (${percentage}%)</span>
                        </div>
                        <div class="status-badge ${item.status}">${item.status_label}</div>
                    `;
                }
            } else if (activeTab === 'missing' || activeTab === 'watchnext' || activeTab === 'unwatched') {
                showQueueBtn = true;
                if (item.type === 'show') showIgnoreBtn = true;

                if (activeTab === 'missing') {
                    primaryLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${item.ratingKey}`;
                    primaryBtnText = 'Plex Info';
                    
                    metaInfoHTML = `
                        <div class="card-meta">
                            <span class="year">${item.year || 'N/A'}</span>
                            <span class="dot">•</span>
                            <span class="added-date">Added ${item.added_at}</span>
                        </div>
                        <div class="status-badge missing">Missing from server</div>
                    `;
                } else {
                    primaryLink = item.plex_link || `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${item.ratingKey}`;
                    primaryBtnText = item.plex_link ? 'Watch Now' : 'Plex Info';

                    if (item.type === 'movie') {
                        metaInfoHTML = `
                            <div class="card-meta">
                                <span class="year">${item.year || 'N/A'}</span>
                            </div>
                            <div class="status-badge available">Unwatched Movie</div>
                        `;
                    } else {
                        const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                        metaInfoHTML = `
                            <div class="card-meta">
                                <span class="year">${item.year || 'N/A'}</span>
                            </div>
                            <div class="progress-container">
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${percentage}%;"></div>
                                </div>
                                <span class="progress-text">${item.viewed_episodes} of ${item.total_episodes} episodes watched (${percentage}%)</span>
                            </div>
                        `;
                    }
                }
            } else if (activeTab === 'sagas') {
                const isComp = item.next_movie_status === 'completed';
                badgeClass = item.next_movie_status;
                
                primaryLink = '#';
                primaryBtnText = 'Progress';

                metaInfoHTML = `
                    <div class="card-meta">
                        <span class="year">Chronological order</span>
                    </div>
                    <div class="progress-container">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${item.percentage}%;"></div>
                        </div>
                        <span class="progress-text">${item.watched_movies} of ${item.total_movies} movies watched (${item.percentage}%)</span>
                    </div>
                    <div class="status-badge ${item.next_movie_status}">
                        ${isComp ? 'Collection Completed' : `Next: ${item.next_movie} (${item.next_movie_status})`}
                    </div>
                `;
            }

            const gradients = [
                'linear-gradient(135deg, #2b3a4a 0%, #0f171e 100%)',
                'linear-gradient(135deg, #3a2b4a 0%, #170f1e 100%)',
                'linear-gradient(135deg, #2b4a3a 0%, #0f1e17 100%)',
                'linear-gradient(135deg, #4a3e2b 0%, #1e170f 100%)'
            ];
            const grad = gradients[Math.abs(item.title.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % gradients.length];
            const inQueue = isItemInQueue(item);

            let secondaryActionHTML = '';
            if (showIgnoreBtn) {
                secondaryActionHTML = `<button class="btn btn-ignore" onclick="ignoreShow('${item.ratingKey}', '${item.title.replace(/'/g, "\\'")}')">Ignore</button>`;
            } else {
                const discLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${item.guid ? item.guid.split('/').pop() : ''}`;
                secondaryActionHTML = `<a href="${discLink}" target="_blank" class="btn btn-secondary">Discover</a>`;
            }

            card.innerHTML = `
                <div class="poster-container">
                    ${item.poster_url ? `
                        <img class="poster" src="${item.poster_url}" alt="${item.title}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                    ` : ''}
                    <div class="poster-fallback" style="${item.poster_url ? 'display: none;' : 'display: flex;'} background: ${grad};">
                        <div class="fallback-icon">${item.type === 'movie' ? '🎬' : (item.type === 'show' ? '📺' : '🏅')}</div>
                        <div class="fallback-text">${item.title}</div>
                    </div>
                    <div class="type-badge ${badgeClass}">${typeLabel}</div>
                </div>
                <div class="card-body">
                    <h3 class="card-title" title="${item.title}">${item.title}</h3>
                    ${metaInfoHTML}
                    <div class="actions">
                        ${activeTab !== 'sagas' ? `<a href="${primaryLink}" target="_blank" class="btn btn-primary">${primaryBtnText}</a>` : ''}
                        ${showQueueBtn ? `
                            <button class="btn btn-queue ${inQueue ? 'active' : ''}" onclick="toggleQueue('${item.ratingKey}', '${item.title.replace(/'/g, "\\'")}')" title="${inQueue ? 'Remove from Queue' : 'Add to Watch Next'}">
                                ${inQueue ? '★' : '☆'}
                            </button>
                        ` : ''}
                        ${secondaryActionHTML}
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    }
}

// Initial dashboard load
document.addEventListener('DOMContentLoaded', loadDashboard);
