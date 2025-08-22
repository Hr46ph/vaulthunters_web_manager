// VaultHunters Web Manager JavaScript

// Performance monitoring data
const performanceData = {
    lagSpikes: [], // Array of timestamps
    maxHistoryMinutes: 10 // Keep 10 minutes of history
};

// Performance monitoring functions
function addLagSpike(msDelay, ticksDelay) {
    const now = Date.now();
    performanceData.lagSpikes.push({
        timestamp: now,
        msDelay: msDelay,
        ticksDelay: ticksDelay
    });
    
    // Clean old data (older than maxHistoryMinutes)
    const cutoff = now - (performanceData.maxHistoryMinutes * 60 * 1000);
    performanceData.lagSpikes = performanceData.lagSpikes.filter(spike => spike.timestamp > cutoff);
    
    updatePerformanceIndicators();
}

function getRecentLagSpikes(seconds = 5) {
    const now = Date.now();
    const cutoff = now - (seconds * 1000);
    return performanceData.lagSpikes.filter(spike => spike.timestamp > cutoff);
}

function getAverageSpikesPerMinute() {
    if (performanceData.lagSpikes.length === 0) return 0;
    
    const now = Date.now();
    const oneMinuteAgo = now - (60 * 1000);
    const recentSpikes = performanceData.lagSpikes.filter(spike => spike.timestamp > oneMinuteAgo);
    
    return recentSpikes.length;
}

function updatePerformanceIndicators() {
    // Recent lag spikes (5 second window)
    const recentSpikes = getRecentLagSpikes(5);
    const spikeCount = recentSpikes.length;
    
    let spikeStatus = 'success'; // green
    if (spikeCount === 3) spikeStatus = 'warning'; // yellow
    else if (spikeCount >= 4) spikeStatus = 'danger'; // red
    
    // Frequency (per minute)
    const frequency = getAverageSpikesPerMinute();
    
    // Severity based on frequency
    let severityStatus = 'success'; // green
    if (frequency >= 37 && frequency <= 48) severityStatus = 'warning'; // yellow
    else if (frequency >= 49) severityStatus = 'danger'; // red
    
    // Update UI elements
    const spikeElement = document.getElementById('lag-spikes-indicator');
    const frequencyElement = document.getElementById('frequency-indicator');
    const severityElement = document.getElementById('severity-indicator');
    
    if (spikeElement) {
        spikeElement.className = `badge bg-${spikeStatus}`;
        spikeElement.textContent = spikeCount;
        spikeElement.title = `${spikeCount} lag spikes in last 5 seconds`;
    }
    
    if (frequencyElement) {
        frequencyElement.textContent = `${frequency}/min`;
        frequencyElement.title = `${frequency} lag spikes per minute (average)`;
    }
    
    if (severityElement) {
        severityElement.className = `badge bg-${severityStatus} rounded-circle`;
        severityElement.innerHTML = '●';
        severityElement.title = `Severity: ${frequency} spikes/min`;
    }
}

// Parse lag spike from log line
function parseLagSpike(logLine) {
    // Pattern: "Can't keep up! Is the server overloaded? Running 2325ms or 46 ticks behind"
    const lagPattern = /Can't keep up.*?Running (\d+)ms or (\d+) ticks behind/i;
    const match = logLine.match(lagPattern);
    
    if (match) {
        const msDelay = parseInt(match[1]);
        const ticksDelay = parseInt(match[2]);
        addLagSpike(msDelay, ticksDelay);
        return true;
    }
    return false;
}

// Get CSRF token
function getCSRFToken() {
    return document.querySelector('meta[name=csrf-token]').getAttribute('content');
}

// Modal functions (replacing alert/confirm)
function showAlert(title, message, type = 'info') {
    document.getElementById('alertModalTitle').textContent = title;
    document.getElementById('alertModalMessage').textContent = message;
    
    const modal = new bootstrap.Modal(document.getElementById('alertModal'));
    modal.show();
}

function showConfirm(title, message, callback) {
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalMessage').textContent = message;
    
    const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
    
    // Set up the OK button to call the callback
    document.getElementById('confirmModalOK').onclick = function() {
        modal.hide();
        callback();
    };
    
    modal.show();
}

// Server control functions
function serverControl(action) {
    if (action === 'start') {
        executeServerControl(action);
    } else if (action === 'save') {
        executeServerControl(action);
    } else if (action === 'kill') {
        showConfirm(
            'Emergency Server Kill', 
            `⚠️ WARNING: This will force-kill the server process!\n\nThis should only be used when RCON is unresponsive.\nUse "Stop Server (RCON)" for normal shutdown.\n\nAre you sure you want to force-kill the server?`,
            function() {
                executeServerControl(action);
            }
        );
    } else {
        showConfirm(
            'Confirm Server Action', 
            `Are you sure you want to ${action} the server?\n\nThis will use RCON commands for graceful shutdown.`,
            function() {
                executeServerControl(action);
            }
        );
    }
}

function executeServerControl(action) {
    const csrfToken = getCSRFToken();
    
    const formData = new FormData();
    formData.append('action', action);
    formData.append('csrf_token', csrfToken);
    
    // Disable buttons during request
    const buttons = document.querySelectorAll('.btn-group .btn');
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.classList.add('loading');
    });
    
    fetch('/server/control', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'  // Include session cookies for CSRF
    })
    .then(response => {
        // Always try to parse JSON first to get detailed error info
        return response.json().then(data => {
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${data.error || response.statusText}`);
            }
            
            return data;
        });
    })
    .then(data => {
        if (data.success) {
            // Show RCON command and response in console if available
            if (data.rcon_command && window.appendToConsole) {
                const timestamp = new Date().toLocaleTimeString();
                window.appendToConsole(`<span class="console-timestamp">[${timestamp}]</span> <span class="console-command">/${data.rcon_command}</span>`);
                
                if (data.rcon_response) {
                    window.appendToConsole(`<span class="console-response">${escapeHtml(data.rcon_response)}</span>`);
                }
                
                // Show system message for server control
                window.appendToConsole(`<span class="console-response">💡 Server ${action} initiated via RCON</span>`);
            }
            
            // For all actions, just refresh status without modal
            setTimeout(updateServerStatus, 2000);
        } else {
            showAlert('Error', data.error || 'Server control failed');
        }
    })
    .catch(error => {
        console.error('Server control error:', error);
        console.error('Error details:', {
            message: error.message,
            name: error.name,
            stack: error.stack
        });
        showAlert('Error', `Network error: ${error.message}`);
    })
    .finally(() => {
        // Re-enable buttons
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.classList.remove('loading');
        });
    });
}

// Update server status
function updateServerStatus() {
    fetch('/server/status')
    .then(response => response.json())
    .then(data => {
        if (!data.error) {
            updateStatusDisplay(data);
        } else {
            console.error('Status update error:', data.error);
            showStatusError('Failed to load server status');
        }
    })
    .catch(error => {
        console.error('Status fetch error:', error);
        showStatusError('Network error loading status');
    });
}

// Update system info
function updateSystemInfo() {
    fetch('/system/info')
    .then(response => response.json())
    .then(data => {
        if (!data.error) {
            // Update version displays
            const javaElement = document.getElementById('java-version');
            const vhElement = document.getElementById('vh-version');
            const kernelElement = document.getElementById('kernel-version');
            const pythonElement = document.getElementById('python-version');
            
            if (javaElement) javaElement.textContent = data.java || 'Unknown';
            if (vhElement) vhElement.textContent = data.vaulthunters || 'Unknown';
            if (kernelElement) kernelElement.textContent = data.kernel || 'Unknown';
            if (pythonElement) pythonElement.textContent = data.python || 'Unknown';
        } else {
            console.error('System info error:', data.error);
            // Show error state for all version elements
            const elements = ['java-version', 'vh-version', 'kernel-version', 'python-version'];
            elements.forEach(id => {
                const element = document.getElementById(id);
                if (element) element.innerHTML = '<span class="text-danger">Error</span>';
            });
        }
    })
    .catch(error => {
        console.error('System info fetch error:', error);
        // Show error state for all version elements
        const elements = ['java-version', 'vh-version', 'kernel-version', 'python-version'];
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) element.innerHTML = '<span class="text-danger">Network Error</span>';
        });
    });
}

// Show status loading error
function showStatusError(message) {
    const statusElement = document.getElementById('server-status');
    if (!statusElement) return;
    
    const leftCol = statusElement.querySelector('.col-md-4:first-child');
    if (leftCol) {
        leftCol.innerHTML = `
            <h6>Status: 
                <span class="badge bg-danger">
                    <i class="fas fa-exclamation-triangle"></i> Error
                </span>
            </h6>
            <p class="text-danger">${message}</p>
            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="updateServerStatus()">
                <i class="fas fa-redo"></i> Retry
            </button>
        `;
    }
}

// Update status display
function updateStatusDisplay(status) {
    const statusElement = document.getElementById('server-status');
    if (!statusElement) return;
    
    // Determine status text and badge color based on server state
    let statusText, badgeColor, statusIcon;
    
    switch (status.status) {
        case 'starting':
            statusText = 'Starting Up';
            badgeColor = 'warning';
            statusIcon = '<i class="fas fa-spinner fa-spin"></i> ';
            break;
        case 'running':
            statusText = 'Running';
            badgeColor = 'success';
            statusIcon = '<i class="fas fa-check-circle"></i> ';
            break;
        case 'stopped':
        default:
            statusText = 'Stopped';
            badgeColor = 'danger';
            statusIcon = '<i class="fas fa-stop-circle"></i> ';
            break;
    }
    
    const badge = statusElement.querySelector('.badge');
    if (badge) {
        badge.className = `badge bg-${badgeColor}`;
        badge.innerHTML = statusIcon + statusText;
    }
    
    // Update the entire status section with new data - now using 3 columns
    const cols = statusElement.querySelectorAll('.col-md-4');
    const leftCol = cols[0];   // Status, Uptime, PID
    const middleCol = cols[1]; // Players, Java CPU, Java Memory  
    const rightCol = cols[2];  // Performance stats (handled separately)
    
    if (leftCol) {
        let html = `
            <div class="d-flex justify-content-between align-items-center">
                <span>Status:</span>
                <span class="badge bg-${badgeColor}">
                    ${statusIcon}${statusText}
                </span>
            </div>
            <div class="d-flex justify-content-between mt-2">
                <span>Uptime:</span>
                <span class="ms-3">${status.uptime}</span>
            </div>
        `;
        
        if (status.running && status.pid) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>PID:</span>
                <span class="ms-3">${status.pid}</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>PID:</span>
                <span class="text-muted ms-3">N/A</span>
            </div>`;
        }
        
        // Show additional info for starting status
        if (status.status === 'starting') {
            html += `<p class="text-warning mt-2"><i class="fas fa-info-circle"></i> Server is loading, please wait...</p>`;
        }
        
        leftCol.innerHTML = html;
    }
    
    if (middleCol) {
        let html = '';
        
        if (status.status === 'running' && status.server_ready) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="ms-3">${status.players}/${status.max_players}</span>
            </div>`;
        } else if (status.status === 'starting') {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="text-muted ms-3">Waiting for server...</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="ms-3">${status.players}/${status.max_players}</span>
            </div>`;
        }
        
        // Always show CPU field
        if (status.cpu_usage > 0) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java CPU:</span>
                <span class="ms-3">${status.cpu_usage.toFixed(1)}%</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java CPU:</span>
                <span class="text-muted loading-indicator ms-3"><i class="fas fa-spinner fa-spin"></i> Loading...</span>
            </div>`;
        }
        
        // Always show Memory field
        if (status.memory_usage > 0) {
            const memoryDisplay = status.memory_usage >= 1024 
                ? `${(status.memory_usage / 1024).toFixed(1)} GB`
                : `${status.memory_usage} MB`;
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java Memory:</span>
                <span class="ms-3">${memoryDisplay}</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java Memory:</span>
                <span class="text-muted loading-indicator ms-3"><i class="fas fa-spinner fa-spin"></i> Loading...</span>
            </div>`;
        }
        
        middleCol.innerHTML = html;
    }
    
    // Update button states - disable controls during startup
    updateButtonStates(status.running, status.status);
}

// Update button states based on server status
function updateButtonStates(isRunning, serverStatus = 'stopped') {
    const startBtn = document.querySelector('button[onclick="serverControl(\'start\')"]');
    const restartBtn = document.querySelector('button[onclick="serverControl(\'restart\')"]');
    const stopBtn = document.querySelector('button[onclick="serverControl(\'stop\')"]');
    const saveBtn = document.querySelector('button[onclick="serverControl(\'save\')"]');
    const killBtn = document.querySelector('button[onclick="serverControl(\'kill\')"]');
    
    const isStarting = serverStatus === 'starting';
    const isFullyRunning = serverStatus === 'running';
    
    // Start button: disabled if running or starting
    if (startBtn) startBtn.disabled = isRunning || isStarting;
    
    // Restart/Stop/Save buttons: disabled if stopped, or limited during startup
    if (restartBtn) restartBtn.disabled = !isRunning || isStarting;
    if (stopBtn) stopBtn.disabled = !isRunning;  // Allow stop during startup
    if (saveBtn) saveBtn.disabled = !isFullyRunning;  // Only allow save when fully running
    if (killBtn) killBtn.disabled = !isRunning;  // Allow kill during startup as emergency option
}


// Dark mode functions
function toggleDarkMode() {
    const currentTheme = document.documentElement.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    
    const icon = document.getElementById('darkModeIcon');
    if (theme === 'dark') {
        icon.className = 'fas fa-sun';
    } else {
        icon.className = 'fas fa-moon';
    }
}

function initTheme() {
    // Check for saved theme preference or default to light mode
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
}

// Flash message function (for server-side flash messages)
function showFlashAlert(type, message) {
    const alertContainer = document.querySelector('.container');
    const existingAlerts = document.querySelectorAll('.alert');
    
    // Remove existing alerts
    existingAlerts.forEach(alert => {
        if (!alert.classList.contains('show')) {
            alert.remove();
        }
    });
    
    const alertHTML = `
        <div class="alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    alertContainer.insertAdjacentHTML('afterbegin', alertHTML);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        const alert = alertContainer.querySelector('.alert');
        if (alert) {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 150);
        }
    }, 5000);
}

// Console functions
let autoScroll = true;
let commandHistory = [];
let historyIndex = -1;

// Append text to console (globally available)
window.appendToConsole = function(text) {
    const output = document.getElementById('console-output');
    if (!output) return;  // Console not available on this page
    
    output.innerHTML += text + '\n';
    
    // Check for lag spikes in the console text
    const textContent = text.replace(/<[^>]*>/g, ''); // Strip HTML tags
    parseLagSpike(textContent);
    
    if (autoScroll) {
        output.scrollTop = output.scrollHeight;
    }
}

// Execute command (globally available)
window.executeCommand = function(command) {
    const output = document.getElementById('console-output');
    if (!output) return;
    
    const timestamp = new Date().toLocaleTimeString();
    
    // Add command to output
    appendToConsole(`<span class="console-timestamp">[${timestamp}]</span> <span class="console-command">/${command}</span>`);
    
    // Update last command
    const lastCommandElement = document.getElementById('last-command');
    if (lastCommandElement) {
        lastCommandElement.textContent = command;
    }
    
    // Send command to server
    fetch('/console/execute', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({command: command})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (data.response) {
                appendToConsole(`<span class="console-response">${escapeHtml(data.response)}</span>`);
            } else {
                appendToConsole(`<span class="console-response">Command executed successfully</span>`);
            }
        } else {
            appendToConsole(`<span class="console-error">Error: ${escapeHtml(data.error || 'Unknown error')}</span>`);
        }
    })
    .catch(error => {
        appendToConsole(`<span class="console-error">Connection error: ${escapeHtml(error.message)}</span>`);
    });
}

// Append text to console
function appendToConsole(text) {
    const output = document.getElementById('console-output');
    if (!output) return;
    
    output.innerHTML += text + '\n';
    
    if (autoScroll) {
        output.scrollTop = output.scrollHeight;
    }
}

// Check RCON status
function checkRconStatus() {
    const statusElement = document.getElementById('rcon-status');
    if (!statusElement) return;
    
    fetch('/console/status')
        .then(response => response.json())
        .then(data => {
            if (data.connected) {
                statusElement.className = 'badge bg-success';
                statusElement.textContent = 'Connected';
                statusElement.title = `Connected to ${data.host}:${data.port}`;
            } else {
                statusElement.className = 'badge bg-danger';
                statusElement.textContent = 'Disconnected';
                statusElement.title = data.error || 'Connection failed';
                
                // Also show error in console
                console.error('RCON Connection Failed:', data.error);
                
                // Add error message to console output
                appendToConsole(`<span class="console-error">RCON Connection Error: ${escapeHtml(data.error || 'Unknown error')}</span>`);
            }
        })
        .catch(error => {
            statusElement.className = 'badge bg-warning';
            statusElement.textContent = 'Network Error';
            statusElement.title = error.message;
            
            console.error('RCON Status Check Error:', error);
            appendToConsole(`<span class="console-error">RCON Status Check Failed: ${escapeHtml(error.message)}</span>`);
        });
}

// Helper function
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Setup console form and history
function setupConsole() {
    const consoleForm = document.getElementById('console-form');
    const commandInput = document.getElementById('command-input');
    
    if (!consoleForm || !commandInput) return;
    
    // Handle form submission
    consoleForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const command = commandInput.value.trim();
        
        if (command) {
            executeCommand(command);
            commandInput.value = '';
            
            // Add to history
            if (commandHistory[commandHistory.length - 1] !== command) {
                commandHistory.push(command);
                if (commandHistory.length > 50) {
                    commandHistory.shift();
                }
            }
            historyIndex = commandHistory.length;
        }
    });
    
    // Setup command history navigation
    commandInput.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (historyIndex > 0) {
                historyIndex--;
                commandInput.value = commandHistory[historyIndex];
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                commandInput.value = commandHistory[historyIndex];
            } else {
                historyIndex = commandHistory.length;
                commandInput.value = '';
            }
        }
    });
}

// Update player list from monitoring API
function updatePlayerList() {
    fetch('/api/monitoring/metrics')
    .then(response => response.json())
    .then(data => {
        const playerCount = data.players || 0;
        const maxPlayers = data.max_players || 20;
        const playerNames = data.player_names || [];
        const playerStatus = data.player_status || { online_players: [], offline_players: [], unique_players: [] };
        
        // Update player count badge and statistics
        const countBadge = document.getElementById('player-count-badge');
        const currentPlayersEl = document.getElementById('current-players');
        const maxPlayersEl = document.getElementById('max-players');
        
        if (countBadge) countBadge.textContent = playerCount;
        if (currentPlayersEl) currentPlayersEl.textContent = playerCount;
        if (maxPlayersEl) maxPlayersEl.textContent = maxPlayers;
        
        // Update player list with online/offline status
        const playerListEl = document.getElementById('player-list');
        const noPlayersMessage = document.getElementById('no-players-message');
        
        // Check if we should show offline players
        const showOfflineCheckbox = document.getElementById('show-offline-checkbox');
        let showOffline = false;
        
        if (showOfflineCheckbox) {
            showOffline = showOfflineCheckbox.checked;
        }
        
        // Get all unique players (latest session for each)
        const allPlayers = playerStatus.unique_players || [];
        const onlinePlayers = allPlayers.filter(p => p.is_online);
        const offlinePlayers = allPlayers.filter(p => !p.is_online);
        
        // Build player list
        let playersToShow = onlinePlayers;
        if (showOffline) {
            playersToShow = [...onlinePlayers, ...offlinePlayers];
        }
        
        if (playersToShow.length > 0) {
            // Show player list, hide no players message
            if (noPlayersMessage) noPlayersMessage.style.display = 'none';
            if (playerListEl) {
                playerListEl.style.display = 'block';
                playerListEl.innerHTML = '';
                
                playersToShow.forEach(player => {
                    const listItem = document.createElement('li');
                    const isOnline = player.is_online;
                    const opacity = isOnline ? '1' : '0.5';
                    const iconClass = isOnline ? 'text-success' : 'text-muted';
                    const statusText = isOnline ? 'Online' : 'Offline';
                    
                    listItem.className = 'list-group-item d-flex align-items-center py-2';
                    listItem.style.opacity = opacity;
                    
                    // Format login time for tooltip
                    let loginTime = '';
                    if (player.login_time) {
                        try {
                            const date = new Date(player.login_time);
                            loginTime = date.toLocaleString();
                        } catch (e) {
                            loginTime = player.login_time;
                        }
                    }
                    
                    // Format logout time for tooltip
                    let logoutTime = '';
                    if (player.logout_time && !isOnline) {
                        try {
                            const date = new Date(player.logout_time);
                            logoutTime = date.toLocaleString();
                        } catch (e) {
                            logoutTime = player.logout_time;
                        }
                    }
                    
                    const tooltipText = isOnline 
                        ? `Last login: ${loginTime}` 
                        : `Last seen: ${logoutTime}`;
                    
                    listItem.innerHTML = `
                        <i class="fas fa-user-circle ${iconClass} me-2"></i>
                        <span class="fw-medium player-name-clickable" title="${tooltipText}" 
                              style="cursor: pointer; text-decoration: underline;" 
                              onclick="showPlayerDetails('${escapeHtml(player.username)}')">${escapeHtml(player.username)}</span>
                        <small class="text-muted ms-auto">${statusText}</small>
                    `;
                    playerListEl.appendChild(listItem);
                });
            }
        } else {
            // Show no players message, hide player list
            if (playerListEl) playerListEl.style.display = 'none';
            if (noPlayersMessage) noPlayersMessage.style.display = 'block';
        }
    })
    .catch(error => {
        console.error('Error updating player list:', error);
    });
}

// Player details modal functions
function showPlayerDetails(username) {
    const modal = new bootstrap.Modal(document.getElementById('playerDetailsModal'));
    
    // Set username in modal title
    document.getElementById('playerModalUsername').textContent = username;
    
    // Show loading state
    document.getElementById('playerModalLoading').style.display = 'block';
    document.getElementById('playerModalContent').style.display = 'none';
    document.getElementById('playerModalError').style.display = 'none';
    
    // Reset modal state - show session history by default
    document.getElementById('sessionHistoryBtn').classList.add('active');
    document.getElementById('deathHistoryBtn').classList.remove('active');
    document.getElementById('sessionHistoryCard').style.display = 'block';
    document.getElementById('deathHistoryCard').style.display = 'none';
    
    // Clear death data cache
    const deathsList = document.getElementById('playerDeathsList');
    if (deathsList) {
        deathsList.removeAttribute('data-loaded');
        deathsList.innerHTML = '';
    }
    
    // Show modal
    modal.show();
    
    // Fetch player data
    fetch(`/api/player/${encodeURIComponent(username)}/history`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Hide loading, show content
            document.getElementById('playerModalLoading').style.display = 'none';
            document.getElementById('playerModalContent').style.display = 'block';
            
            // Update statistics
            document.getElementById('playerTotalPlaytime').textContent = data.total_playtime || '0s';
            document.getElementById('playerTotalSessions').textContent = data.total_sessions || 0;
            
            // Update status
            const isCurrentlyOnline = data.sessions.length > 0 && data.sessions[0].is_online;
            const statusElement = document.getElementById('playerCurrentStatus');
            const statusTextElement = document.getElementById('playerStatusText');
            
            if (isCurrentlyOnline) {
                statusElement.className = 'text-success';
                statusElement.querySelector('i').className = 'fas fa-circle text-success';
                statusTextElement.textContent = 'Online';
            } else {
                statusElement.className = 'text-muted';
                statusElement.querySelector('i').className = 'fas fa-circle text-muted';
                statusTextElement.textContent = 'Offline';
            }
            
            // Update sessions list
            const sessionsList = document.getElementById('playerSessionsList');
            sessionsList.innerHTML = '';
            
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(session => {
                    const row = document.createElement('tr');
                    
                    // Add styling for current session
                    if (session.is_online) {
                        row.className = 'table-success';
                    }
                    
                    row.innerHTML = `
                        <td class="text-nowrap">${escapeHtml(session.login_time)}</td>
                        <td class="text-nowrap">${escapeHtml(session.logout_time)}</td>
                        <td class="text-nowrap">${escapeHtml(session.duration)}</td>
                        <td>
                            ${session.is_online 
                                ? '<span class="badge bg-success"><i class="fas fa-circle"></i> Online</span>'
                                : '<span class="badge bg-secondary"><i class="fas fa-circle"></i> Offline</span>'
                            }
                        </td>
                    `;
                    
                    sessionsList.appendChild(row);
                });
            } else {
                // No sessions found
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td colspan="4" class="text-center text-muted py-3">
                        <i class="fas fa-info-circle"></i> No session history found
                    </td>
                `;
                sessionsList.appendChild(row);
            }
        })
        .catch(error => {
            console.error('Error fetching player details:', error);
            
            // Hide loading, show error
            document.getElementById('playerModalLoading').style.display = 'none';
            document.getElementById('playerModalContent').style.display = 'none';
            document.getElementById('playerModalError').style.display = 'block';
            document.getElementById('playerModalErrorText').textContent = error.message || 'Failed to load player data';
        });
}

// Functions to switch between views in player modal
function showSessionHistory() {
    // Update button states
    document.getElementById('sessionHistoryBtn').classList.add('active');
    document.getElementById('deathHistoryBtn').classList.remove('active');
    
    // Show/hide cards
    document.getElementById('sessionHistoryCard').style.display = 'block';
    document.getElementById('deathHistoryCard').style.display = 'none';
}

function showDeathHistory() {
    // Update button states
    document.getElementById('sessionHistoryBtn').classList.remove('active');
    document.getElementById('deathHistoryBtn').classList.add('active');
    
    // Show/hide cards
    document.getElementById('sessionHistoryCard').style.display = 'none';
    document.getElementById('deathHistoryCard').style.display = 'block';
    
    // Load death data if not already loaded
    const username = document.getElementById('playerModalUsername').textContent;
    loadPlayerDeaths(username);
}

function loadPlayerDeaths(username) {
    // Check if deaths are already loaded
    const deathsList = document.getElementById('playerDeathsList');
    if (deathsList.getAttribute('data-loaded') === 'true') {
        return; // Already loaded
    }
    
    // Show loading in deaths list
    deathsList.innerHTML = '<tr><td colspan="2" class="text-center"><i class="fas fa-spinner fa-spin"></i> Loading deaths...</td></tr>';
    
    // Fetch death data
    fetch(`/api/player/${encodeURIComponent(username)}/deaths`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Update death statistics
            document.getElementById('playerTotalDeaths').textContent = data.total_deaths || 0;
            document.getElementById('playerMostCommonDeath').textContent = data.most_common_method || 'None';
            
            // Clear loading and populate deaths list
            deathsList.innerHTML = '';
            
            if (data.deaths && data.deaths.length > 0) {
                data.deaths.forEach(death => {
                    const row = document.createElement('tr');
                    
                    // Choose badge color based on death method
                    let badgeColor = 'bg-danger';
                    let icon = 'fas fa-skull';
                    
                    switch (death.death_method) {
                        case 'Vault Defeat':
                            badgeColor = 'bg-purple';
                            icon = 'fas fa-dungeon';
                            break;
                        case 'Fall Damage':
                            badgeColor = 'bg-warning';
                            icon = 'fas fa-arrow-down';
                            break;
                        case 'Slain':
                            badgeColor = 'bg-danger';
                            icon = 'fas fa-sword';
                            break;
                        case 'Explosion':
                            badgeColor = 'bg-orange';
                            icon = 'fas fa-bomb';
                            break;
                        case 'Burned':
                            badgeColor = 'bg-danger';
                            icon = 'fas fa-fire';
                            break;
                        case 'Suffocation':
                            badgeColor = 'bg-secondary';
                            icon = 'fas fa-cube';
                            break;
                        case 'Projectile':
                            badgeColor = 'bg-info';
                            icon = 'fas fa-bow-arrow';
                            break;
                        default:
                            badgeColor = 'bg-dark';
                            icon = 'fas fa-question';
                    }
                    
                    row.innerHTML = `
                        <td class="text-nowrap">${escapeHtml(death.death_time)}</td>
                        <td>
                            <span class="badge ${badgeColor}">
                                <i class="${icon}"></i> ${escapeHtml(death.death_method)}
                            </span>
                        </td>
                        <td class="text-muted">${escapeHtml(death.death_cause)}</td>
                    `;
                    deathsList.appendChild(row);
                });
            } else {
                // No deaths found
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td colspan="3" class="text-center text-muted py-3">
                        <i class="fas fa-heart text-success"></i> No deaths found - this player is doing great!
                    </td>
                `;
                deathsList.appendChild(row);
            }
            
            // Mark as loaded
            deathsList.setAttribute('data-loaded', 'true');
        })
        .catch(error => {
            console.error('Error fetching player deaths:', error);
            deathsList.innerHTML = `
                <tr>
                    <td colspan="3" class="text-center text-danger py-3">
                        <i class="fas fa-exclamation-triangle"></i> Failed to load death data: ${escapeHtml(error.message)}
                    </td>
                </tr>
            `;
        });
}

// Make functions globally available
window.showPlayerDetails = showPlayerDetails;
window.showSessionHistory = showSessionHistory;
window.showDeathHistory = showDeathHistory;

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme
    initTheme();
    
    // Update server status on page load - small delay to let page render first
    setTimeout(updateServerStatus, 100);
    
    // Update system info on page load
    setTimeout(updateSystemInfo, 200);
    
    // Set up periodic status updates (every 10 seconds)
    setInterval(updateServerStatus, 10000);
    
    // Set up periodic performance indicator updates (every 2 seconds)
    setInterval(updatePerformanceIndicators, 2000);
    
    // Set up player list updates (every 10 seconds) if player list is present
    if (document.getElementById('player-list')) {
        updatePlayerList(); // Initial load
        setInterval(updatePlayerList, 10000);
    }
    
    // Setup console if present on page
    setupConsole();
    
    // Check RCON status if console is present
    if (document.getElementById('rcon-status')) {
        checkRconStatus();
        // Check RCON status periodically
        setInterval(checkRconStatus, 30000);
    }
    
});