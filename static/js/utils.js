/**
 * utils.js - Utility Functions for WayfindR Dashboard
 */

const DashboardUtils = {
    escapeHtml: function(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    formatTimestamp: function(timestamp) {
        try {
            return new Date(timestamp).toLocaleString();
        } catch (e) {
            return timestamp;
        }
    },

    generateId: function(prefix = 'id') {
        return `${prefix}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    },

    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    throttle: function(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    log: function(category, message, data = null) {
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${category}] ${message}`;

        if (data) {
            console.log(logMessage, data);
        } else {
            console.log(logMessage);
        }
    },

    error: function(category, message, error = null) {
        const timestamp = new Date().toISOString();
        const errorMessage = `[${timestamp}] [${category}] ERROR: ${message}`;

        if (error) {
            console.error(errorMessage, error);
        } else {
            console.error(errorMessage);
        }
    }
};

window.DashboardUtils = DashboardUtils;
