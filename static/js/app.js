// VaultHunters Web Manager JavaScript


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
            // Check if server is ready for connections
            if (status.server_ready === true) {
                statusText = 'Running';
                badgeColor = 'success';
                statusIcon = '<i class="fas fa-check-circle"></i> ';
            } else {
                statusText = 'Running';
                badgeColor = 'warning';
                statusIcon = '<i class="fas fa-exclamation-triangle"></i> ';
            }
            break;
        case 'stopped':
        default:
            statusText = 'Stopped';
            badgeColor = 'danger';
            statusIcon = '<i class="fas fa-stop-circle"></i> ';
            break;
    }
    
    // Update status badge in left column
    const statusBadge = statusElement.querySelector('.badge');
    if (statusBadge) {
        statusBadge.className = `badge bg-${badgeColor}`;
        statusBadge.innerHTML = statusIcon + statusText;
    }
    
    // Update the entire status section with new data - now using 2 columns
    const cols = statusElement.querySelectorAll('.col-md-6');
    const leftCol = cols[0];   // Uptime, PID, RCON Status
    const rightCol = cols[1];  // Players, Java CPU, Java Memory
    
    if (leftCol) {
        let html = `
            <div class="d-flex justify-content-between mt-2">
                <span>Server Status:</span>
                <span class="badge bg-${badgeColor}">${statusIcon}${statusText}</span>
            </div>
            <div class="d-flex justify-content-between mt-2">
                <span>Uptime:</span>
                <span class="text-muted">${status.uptime}</span>
            </div>
        `;
        
        if (status.running && status.pid) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>PID:</span>
                <span class="text-muted">${status.pid}</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>PID:</span>
                <span class="text-muted">N/A</span>
            </div>`;
        }
        
        // Preserve existing RCON status or show checking if it doesn't exist
        const existingRconStatus = document.getElementById('rcon-status');
        const rconStatusDisplay = existingRconStatus ? existingRconStatus.outerHTML : '<span id="rcon-status" class="badge bg-secondary">Checking...</span>';
        
        html += `
            <div class="d-flex justify-content-between mt-2">
                <span>RCON Status:</span>
                ${rconStatusDisplay}
            </div>`;
        
        // Show additional info for starting status
        if (status.status === 'starting') {
            html += `<p class="text-warning mt-2"><i class="fas fa-info-circle"></i> Server is loading, please wait...</p>`;
        }
        
        leftCol.innerHTML = html;
    }
    
    if (rightCol) {
        let html = '';
        
        if (status.status === 'running' && status.server_ready) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="text-muted">${status.players}/${status.max_players}</span>
            </div>`;
        } else if (status.status === 'starting') {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="text-muted">Waiting for server...</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Players:</span>
                <span class="text-muted">--</span>
            </div>`;
        }
        
        // Always show CPU field
        if (status.status === 'stopped') {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java CPU:</span>
                <span class="text-muted">--</span>
            </div>`;
        } else if (status.cpu_usage > 0) {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java CPU:</span>
                <span class="text-muted">${status.cpu_usage.toFixed(1)}%</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java CPU:</span>
                <span class="text-muted loading-indicator"><i class="fas fa-spinner fa-spin"></i> Loading...</span>
            </div>`;
        }
        
        // Always show Memory field
        if (status.status === 'stopped') {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java Memory:</span>
                <span class="text-muted">--</span>
            </div>`;
        } else if (status.memory_usage > 0) {
            const memoryDisplay = status.memory_usage >= 1024 
                ? `${(status.memory_usage / 1024).toFixed(1)} GB`
                : `${status.memory_usage} MB`;
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java Memory:</span>
                <span class="text-muted">${memoryDisplay}</span>
            </div>`;
        } else {
            html += `
            <div class="d-flex justify-content-between mt-2">
                <span>Java Memory:</span>
                <span class="text-muted loading-indicator"><i class="fas fa-spinner fa-spin"></i> Loading...</span>
            </div>`;
        }
        
        rightCol.innerHTML = html;
    }
    
    // Update button states - disable controls during startup
    updateButtonStates(status.running, status.status);
    
    // Check RCON status after updating server status (only if server is running)
    if (status.running && status.status === 'running') {
        setTimeout(checkRconStatus, 500); // Small delay to let DOM update
    }
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
    if (icon) {
        if (theme === 'dark') {
            icon.className = 'fas fa-sun';
        } else {
            icon.className = 'fas fa-moon';
        }
    }
}

function initTheme() {
    // Check for saved theme preference or default to dark mode (because we're not monsters)
    const savedTheme = localStorage.getItem('theme') || 'dark';
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

// Update player list from online players API (simplified)
function updatePlayerList() {
    // Get online players directly
    fetch('/api/players/online')
    .then(response => response.json())
    .then(data => {
        const playerNames = data.players || [];
        const playerCount = data.count || 0;
        
        // Update player count badge and statistics
        const countBadge = document.getElementById('player-count-badge');
        const currentPlayersEl = document.getElementById('current-players');
        
        if (countBadge) countBadge.textContent = playerCount;
        if (currentPlayersEl) currentPlayersEl.textContent = playerCount;
        
        // Update player list (online only)
        const playerListEl = document.getElementById('player-list');
        const noPlayersMessage = document.getElementById('no-players-message');
        
        // Hide offline players checkbox since we only show online players
        const showOfflineCheckbox = document.getElementById('show-offline-checkbox');
        if (showOfflineCheckbox) {
            showOfflineCheckbox.style.display = 'none';
        }
        
        if (playerNames.length > 0) {
            // Show player list, hide no players message
            if (noPlayersMessage) noPlayersMessage.style.display = 'none';
            if (playerListEl) {
                playerListEl.style.display = 'block';
                playerListEl.innerHTML = '';
                
                playerNames.forEach(playerName => {
                    const listItem = document.createElement('li');
                    listItem.className = 'list-group-item d-flex align-items-center py-2';
                    
                    listItem.innerHTML = `
                        <i class="fas fa-user-circle text-success me-2"></i>
                        <span class="fw-medium">${escapeHtml(playerName)}</span>
                        <small class="text-muted ms-auto">Online</small>
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
        // Show no players on error
        const playerListEl = document.getElementById('player-list');
        const noPlayersMessage = document.getElementById('no-players-message');
        const countBadge = document.getElementById('player-count-badge');
        
        if (countBadge) countBadge.textContent = '0';
        if (playerListEl) playerListEl.style.display = 'none';
        if (noPlayersMessage) noPlayersMessage.style.display = 'block';
    });
}

// Player details functionality removed - only showing online players now

// Player modal functions removed - simplified to only show online players

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
    
    // Only initialize dashboard features if user is authenticated
    // Check for presence of navigation elements that indicate authentication
    const isAuthenticated = document.getElementById('darkModeToggle') !== null;
    
    if (isAuthenticated) {
        // Update server status on page load - small delay to let page render first
        setTimeout(updateServerStatus, 100);
        
        // Update system info on page load
        setTimeout(updateSystemInfo, 200);
        
        // Set up periodic status updates (every 5 seconds)
        setInterval(updateServerStatus, 5000);
    }
    
    
    // Set up player list updates (every 5 seconds) if player list is present
    if (document.getElementById('player-list')) {
        updatePlayerList(); // Initial load
        setInterval(updatePlayerList, 5000);
    }
    
    // Setup console if present on page
    setupConsole();
    
    // Check RCON status if console is present
    if (document.getElementById('rcon-status')) {
        setTimeout(checkRconStatus, 1000); // Initial check after 1 second
        // Check RCON status periodically (more frequently)
        setInterval(checkRconStatus, 15000); // Every 15 seconds instead of 30
    }
    
    // Check server properties validation on startup
    checkServerPropertiesValidation();
    
});

// Server Properties Validation Functions
function checkServerPropertiesValidation() {
    // Only run this check on the dashboard page
    if (!window.location.pathname.endsWith('/') && window.location.pathname !== '/') {
        return;
    }
    
    // Add a small delay to avoid race conditions with page loading
    setTimeout(() => {
        fetch('/api/server-properties/validate')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.validation) {
                    const validation = data.validation;
                    
                    // Show alert if there are validation issues, hide if everything is fine
                    if (!validation.valid && validation.issues && validation.issues.length > 0) {
                        showServerPropertiesAlert(validation);
                    } else {
                        // Hide alert if validation passes
                        const alertElement = document.getElementById('server-properties-alert');
                        if (alertElement) {
                            alertElement.style.display = 'none';
                        }
                    }
                } else {
                    console.warn('Failed to validate server properties:', data.error);
                }
            })
            .catch(error => {
                console.warn('Failed to check server properties validation:', error);
            });
    }, 1000); // 1 second delay
}

function showServerPropertiesAlert(validation) {
    const alertElement = document.getElementById('server-properties-alert');
    const summaryElement = document.getElementById('properties-issues-summary');
    
    if (!alertElement || !summaryElement) return;
    
    // Build summary text
    const criticalCount = validation.critical_issues || 0;
    const warningCount = validation.warning_issues || 0;
    const totalCount = validation.total_issues || 0;
    
    let summaryText = '';
    if (criticalCount > 0) {
        summaryText += `<span class="badge bg-danger me-2">${criticalCount} Critical</span>`;
    }
    if (warningCount > 0) {
        summaryText += `<span class="badge bg-warning me-2">${warningCount} Warnings</span>`;
    }
    summaryText += `<span class="text-muted">${totalCount} total issues found</span>`;
    
    summaryElement.innerHTML = summaryText;
    
    // Show the alert
    alertElement.style.display = 'block';
}

function dismissPropertiesAlert() {
    const alertElement = document.getElementById('server-properties-alert');
    if (alertElement) {
        alertElement.style.display = 'none';
    }
}

function loadServerPropertiesModal() {
    const modalContent = document.getElementById('propertiesModalContent');
    const modalLoading = document.getElementById('propertiesModalLoading');
    const modalError = document.getElementById('propertiesModalError');
    const applyBtn = document.getElementById('applyPropertiesBtn');
    
    // Show loading state
    modalContent.style.display = 'none';
    modalError.style.display = 'none';
    modalLoading.style.display = 'block';
    applyBtn.disabled = true;
    
    fetch('/api/server-properties/validate')
        .then(response => response.json())
        .then(data => {
            modalLoading.style.display = 'none';
            
            if (data.success && data.validation) {
                const validation = data.validation;
                
                if (!validation.valid && validation.issues) {
                    populatePropertiesIssues(validation.issues);
                    configurePasswordOptions(validation);
                    modalContent.style.display = 'block';
                    applyBtn.disabled = false;
                } else {
                    // No issues found
                    modalError.style.display = 'block';
                    document.getElementById('propertiesModalErrorText').textContent = 
                        'All required server properties are already properly configured.';
                }
            } else {
                throw new Error(data.error || 'Failed to validate properties');
            }
        })
        .catch(error => {
            modalLoading.style.display = 'none';
            modalError.style.display = 'block';
            document.getElementById('propertiesModalErrorText').textContent = error.message;
        });
}

function populatePropertiesIssues(issues) {
    const issuesContainer = document.getElementById('propertiesIssuesList');
    if (!issuesContainer) return;
    
    let html = '';
    
    issues.forEach((issue, index) => {
        const severityBadge = issue.severity === 'critical' ? 
            '<span class="badge bg-danger">Critical</span>' : 
            '<span class="badge bg-warning">Warning</span>';
        
        html += `
            <div class="card mb-3">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">
                        <i class="fas fa-cog"></i> ${issue.name}
                        ${severityBadge}
                    </h6>
                </div>
                <div class="card-body">
                    <p class="mb-2">${issue.description}</p>
                    
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <strong>Current Value:</strong>
                            <code class="text-danger">${issue.current_value}</code>
                        </div>
                        <div class="col-md-6">
                            <strong>Required Value:</strong>
                            <code class="text-success">${issue.required_value}</code>
                        </div>
                    </div>
                    
                    <div class="alert alert-sm alert-info mb-2">
                        <i class="fas fa-info-circle"></i>
                        <strong>Why this is needed:</strong> ${issue.technical_details}
                    </div>
                    
                    ${issue.security_note ? `
                        <div class="alert alert-sm alert-warning mb-0">
                            <i class="fas fa-shield-alt"></i>
                            <strong>Security Note:</strong> ${issue.security_note}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    issuesContainer.innerHTML = html;
}

function configurePasswordOptions(validation) {
    const keepPasswordOption = document.getElementById('keepPasswordOption');
    const generatePasswordOption = document.getElementById('generatePassword');
    const customPasswordOption = document.getElementById('customPassword');
    const keepPasswordRadio = document.getElementById('keepPassword');
    
    // Check if there's an RCON password issue and if password already exists
    const hasRconPasswordIssue = validation.issues && validation.issues.some(issue => issue.setting === 'rcon.password');
    const hasExistingPassword = validation.has_rcon_password;
    
    if (hasRconPasswordIssue && hasExistingPassword) {
        // Password exists but there's still an issue - show keep password option
        // This shouldn't normally happen with our fixed logic, but just in case
        keepPasswordOption.style.display = 'block';
        keepPasswordRadio.checked = true;
        generatePasswordOption.checked = false;
    } else if (hasRconPasswordIssue && !hasExistingPassword) {
        // No password exists - hide keep password option, default to generate
        keepPasswordOption.style.display = 'none';
        generatePasswordOption.checked = true;
    } else if (hasExistingPassword) {
        // Password exists and no issue - show keep password option as default
        keepPasswordOption.style.display = 'block';
        keepPasswordRadio.checked = true;
        generatePasswordOption.checked = false;
    } else {
        // No password and no issue - hide keep password option
        keepPasswordOption.style.display = 'none';
        generatePasswordOption.checked = true;
    }
    
    // Set up event listeners for password options (needed for dynamically shown options)
    setupPasswordOptionListeners();
}

function setupPasswordOptionListeners() {
    // Remove existing listeners first to prevent duplicates
    const passwordOptions = document.querySelectorAll('input[name="passwordOption"]');
    passwordOptions.forEach(option => {
        // Clone node to remove existing event listeners
        const newOption = option.cloneNode(true);
        option.parentNode.replaceChild(newOption, option);
    });
    
    // Add fresh event listeners
    document.querySelectorAll('input[name="passwordOption"]').forEach(option => {
        option.addEventListener('change', function() {
            const customInput = document.getElementById('customPasswordInput');
            if (this.value === 'custom') {
                customInput.style.display = 'block';
            } else {
                customInput.style.display = 'none';
            }
        });
    });
}

function togglePasswordVisibility() {
    const passwordInput = document.getElementById('customRconPassword');
    const toggleIcon = document.getElementById('passwordToggleIcon');
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        toggleIcon.className = 'fas fa-eye-slash';
    } else {
        passwordInput.type = 'password';
        toggleIcon.className = 'fas fa-eye';
    }
}

function applyServerProperties() {
    const applyBtn = document.getElementById('applyPropertiesBtn');
    const originalBtnText = applyBtn.innerHTML;
    
    // Get form data
    const restartOption = document.querySelector('input[name="restartOption"]:checked')?.value || 'apply';
    const passwordOption = document.querySelector('input[name="passwordOption"]:checked')?.value || 'generate';
    const customPassword = document.getElementById('customRconPassword')?.value || '';
    
    // Validate custom password if selected
    if (passwordOption === 'custom' && customPassword.length < 8) {
        showAlert('Error', 'Custom RCON password must be at least 8 characters long.');
        return;
    }
    
    // Show loading state
    applyBtn.disabled = true;
    applyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Applying...';
    
    const requestData = {
        restart_server: restartOption === 'restart',
        custom_rcon_password: passwordOption === 'custom' ? customPassword : null,
        keep_existing_password: passwordOption === 'keep'
    };
    
    fetch('/api/server-properties/apply', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        applyBtn.disabled = false;
        applyBtn.innerHTML = originalBtnText;
        
        if (data.success) {
            // Show success message
            let message = data.message;
            if (data.changes_made && data.changes_made.length > 0) {
                message += `\n\nChanges applied:\n`;
                data.changes_made.forEach(change => {
                    message += `• ${change.display_name}: ${change.old_value} → ${change.new_value}\n`;
                });
            }
            
            if (data.backup_created) {
                message += `\nBackup created: ${data.backup_path}`;
            }
            
            if (data.restart_performed) {
                message += '\n\nServer has been restarted with the new configuration.';
            } else if (data.restart_required) {
                message += '\n\nPlease restart the server for changes to take effect.';
            }
            
            // Close modal first
            const modalElement = document.getElementById('serverPropertiesModal');
            const modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement);
            modal.hide();
            
            // Hide properties alert if visible
            dismissPropertiesAlert();
            
            // Show success message in a simpler way
            if (data.restart_performed) {
                alert('Configuration applied successfully! Server has been restarted with the new configuration.');
            } else if (data.restart_required) {
                alert('Configuration applied successfully! Please restart the server for changes to take effect.');
            } else {
                alert('Configuration applied successfully!');
            }
            
            // Refresh page immediately to show updated status
            window.location.reload();
            
        } else {
            // Show detailed error message
            let errorMessage = data.error || 'Failed to apply server properties configuration.';
            
            // Add specific context for restart failures
            if (data.restart_required && !data.restart_performed) {
                errorMessage += '\n\nNote: Configuration changes were applied successfully, but server restart failed. Please manually restart the server for changes to take effect.';
            }
            
            alert('Configuration Failed: ' + errorMessage);
        }
    })
    .catch(error => {
        applyBtn.disabled = false;
        applyBtn.innerHTML = originalBtnText;
        console.error('Server properties apply error:', error);
        alert('Network Error: Failed to apply server properties. Please check your connection and try again.\n\nError details: ' + error.message);
    });
}

// Event listeners for the modal
document.addEventListener('DOMContentLoaded', function() {
    // Password option change listener
    const passwordOptions = document.querySelectorAll('input[name="passwordOption"]');
    passwordOptions.forEach(option => {
        option.addEventListener('change', function() {
            const customInput = document.getElementById('customPasswordInput');
            if (this.value === 'custom') {
                customInput.style.display = 'block';
            } else {
                customInput.style.display = 'none';
            }
        });
    });
    
    // Load modal content when opened
    const propertiesModal = document.getElementById('serverPropertiesModal');
    if (propertiesModal) {
        propertiesModal.addEventListener('show.bs.modal', loadServerPropertiesModal);
    }
});