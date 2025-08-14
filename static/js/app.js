// VaultHunter Web Manager JavaScript

// Get CSRF token
function getCSRFToken() {
    return document.querySelector('meta[name=csrf-token]').getAttribute('content');
}

// Server control functions
function serverControl(action) {
    if (!confirm(`Are you sure you want to ${action} the server?`)) {
        return;
    }
    
    const formData = new FormData();
    formData.append('action', action);
    formData.append('csrf_token', getCSRFToken());
    
    // Disable buttons during request
    const buttons = document.querySelectorAll('.btn-group .btn');
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.classList.add('loading');
    });
    
    fetch('/server/control', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', data.message);
            // Refresh server status after a delay
            setTimeout(updateServerStatus, 2000);
        } else {
            showAlert('danger', data.error || 'Server control failed');
        }
    })
    .catch(error => {
        console.error('Server control error:', error);
        showAlert('danger', 'Network error occurred');
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
        }
    })
    .catch(error => {
        console.error('Status fetch error:', error);
    });
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
        if (status.memory_usage > 0) {
            html += `<p>Memory: ${status.memory_usage} MB</p>`;
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
    
    if (startBtn) startBtn.disabled = isRunning;
    if (restartBtn) restartBtn.disabled = !isRunning;
    if (stopBtn) stopBtn.disabled = !isRunning;
}

// Show alert message
function showAlert(type, message) {
    const alertContainer = document.querySelector('.container');
    const existingAlerts = document.querySelectorAll('.alert');
    
    // Remove existing alerts
    existingAlerts.forEach(alert => {
        if (!alert.classList.contains('show')) {
            alert.remove();
        }
    });
    
    const alertHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
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

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Update server status on page load
    updateServerStatus();
    
    // Set up periodic status updates (every 30 seconds)
    setInterval(updateServerStatus, 30000);
    
    console.log('VaultHunter Web Manager loaded');
});