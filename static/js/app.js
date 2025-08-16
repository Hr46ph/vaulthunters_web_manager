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
    console.log('Executing server control:', action);
    console.log('CSRF token:', csrfToken ? csrfToken.substring(0, 20) + '...' : 'NULL');
    
    const formData = new FormData();
    formData.append('action', action);
    formData.append('csrf_token', csrfToken);
    
    console.log('FormData contents:', Array.from(formData.entries()));
    
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
        console.log('Server control response status:', response.status);
        console.log('Server control response headers:', response.headers);
        
        // Always try to parse JSON first to get detailed error info
        return response.json().then(data => {
            console.log('Server control response data:', data);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${data.error || response.statusText}`);
            }
            
            return data;
        });
    })
    .then(data => {
        console.log('Server control response:', data);
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


// Show status loading error
function showStatusError(message) {
    const statusElement = document.getElementById('server-status');
    if (!statusElement) return;
    
    const leftCol = statusElement.querySelector('.col-md-6:first-child');
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
    
    const badge = statusElement.querySelector('.badge');
    if (badge) {
        badge.className = `badge bg-${status.running ? 'success' : 'danger'}`;
        badge.textContent = status.running ? 'Running' : 'Stopped';
    }
    
    // Update the entire status section with new data
    const leftCol = statusElement.querySelector('.col-md-6:first-child');
    const rightCol = statusElement.querySelector('.col-md-6:last-child');
    
    if (leftCol) {
        let html = `
            <h6>Status: 
                <span class="badge bg-${status.running ? 'success' : 'danger'}">
                    ${status.running ? 'Running' : 'Stopped'}
                </span>
            </h6>
            <p>Uptime: ${status.uptime}</p>
        `;
        if (status.running && status.pid) {
            html += `<p>PID: ${status.pid}</p>`;
        }
        if (status.memory_usage > 0) {
            const memoryDisplay = status.memory_usage >= 1024 
                ? `${(status.memory_usage / 1024).toFixed(1)} GB`
                : `${status.memory_usage} MB`;
            html += `<p>Memory: ${memoryDisplay}</p>`;
        }
        leftCol.innerHTML = html;
    }
    
    if (rightCol) {
        let html = `<p>Players: ${status.players}/${status.max_players}</p>`;
        if (status.cpu_usage > 0) {
            html += `<p>CPU: ${status.cpu_usage.toFixed(1)}%</p>`;
        }
        rightCol.innerHTML = html;
    }
    
    // Update button states
    updateButtonStates(status.running);
}

// Update button states based on server status
function updateButtonStates(isRunning) {
    const startBtn = document.querySelector('button[onclick="serverControl(\'start\')"]');
    const restartBtn = document.querySelector('button[onclick="serverControl(\'restart\')"]');
    const stopBtn = document.querySelector('button[onclick="serverControl(\'stop\')"]');
    const saveBtn = document.querySelector('button[onclick="serverControl(\'save\')"]');
    const killBtn = document.querySelector('button[onclick="serverControl(\'kill\')"]');
    
    if (startBtn) startBtn.disabled = isRunning;
    if (restartBtn) restartBtn.disabled = !isRunning;
    if (stopBtn) stopBtn.disabled = !isRunning;
    if (saveBtn) saveBtn.disabled = !isRunning;
    if (killBtn) killBtn.disabled = !isRunning;
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

// Execute command
function executeCommand(command) {
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

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme
    initTheme();
    
    // Update server status on page load - small delay to let page render first
    setTimeout(updateServerStatus, 100);
    
    // Set up periodic status updates (every 10 seconds)
    setInterval(updateServerStatus, 10000);
    
    // Setup console if present on page
    setupConsole();
    
    // Check RCON status if console is present
    if (document.getElementById('rcon-status')) {
        checkRconStatus();
        // Check RCON status periodically
        setInterval(checkRconStatus, 30000);
    }
    
    console.log('VaultHunters Web Manager loaded');
});