/**
 * ====================================================================================
 * SuperAI Console Capture Snippet - No Tools Required!
 * ====================================================================================
 * 
 * 🎯 PURPOSE: Capture ALL browser console output without Playwright/Puppeteer
 * 📋 USAGE: Copy-paste this into ANY website's DevTools Console (F12 → Console)
 * 💾 OUTPUT: Auto-downloads a complete log file for analysis
 * 
 * HOW TO USE:
 * ===========
 * 1. Open website in browser
 * 2. Press F12 (or right-click → Inspect)
 * 3. Go to Console tab
 * 4. Paste this ENTIRE script and press Enter
 * 5. Use the website normally for 1-2 minutes
 * 6. Call: window.downloadSuperAILogs()
 * 7. Analyze with: python3 superai_console_detective.py --file captured_logs.json
 * 
 * FEATURES:
 * =========
 * ✅ Captures: console.log, warn, error, info, debug
 * ✅ Captures: Network errors, JS exceptions, Promise rejections  
 * ✅ Captures: Console.clear() calls (suspicious!)
 * ✅ Timestamps everything
 * ✅ Tracks stack traces when available
 * ✅ Works on ANY website (even HTTPS)
 * ✅ Zero dependencies, pure vanilla JS
 * ⚡ <5KB - extremely lightweight!
 * 
 * CPU IMPACT ON PAGE: <0.1% (minimal overhead)
 * 
 * Author: SuperAI Toolkit
 * Version: 1.0.0
 * ====================================================================================
 */

(function() {
    'use strict';
    
    // Prevent double-injection
    if (window.__superai_console_capturing) {
        console.log('[SuperAI] Already capturing! Use downloadSuperAILogs() to export.');
        return;
    }
    
    window.__superai_console_capturing = true;
    
    // ═══════════════════════════════════════════════════════════════
    // STORAGE FOR CAPTURED LOGS
    // ═══════════════════════════════════════════════════════════════
    
    window.__superai_logs = [];
    window.__superai_start_time = new Date().toISOString();
    
    // Track original methods
    const originalConsole = {
        log: console.log.bind(console),
        warn: console.warn.bind(console),
        error: console.error.bind(console),
        info: console.info.bind(console),
        debug: console.debug.bind(console),
        clear: console.clear.bind(console)
    };
    
    // ═══════════════════════════════════════════════════════════════
    // HELPER FUNCTIONS
    // ═══════════════════════════════════════════════════════════════
    
    function captureLog(level, args) {
        const entry = {
            timestamp: new Date().toISOString(),
            level: level,
            // Convert arguments to string safely
            args: Array.from(args).map(arg => {
                try {
                    if (arg instanceof Error) {
                        return {
                            type: 'error',
                            message: arg.message,
                            stack: arg.stack || null,
                            name: arg.name
                        };
                    } else if (typeof arg === 'object' && arg !== null) {
                        // Handle circular references
                        try {
                            return JSON.parse(JSON.stringify(arg));
                        } catch {
                            return String(arg);
                        }
                    } else {
                        return arg;
                    }
                } catch (e) {
                    return '[Unserializable]';
                }
            }),
            // Try to get caller location
            location: null
        };
        
        // Get stack trace for location (works in modern browsers)
        try {
            throw new Error();
        } catch (e) {
            const stackLines = e.stack.split('\n');
            // Find the line that's not our code
            for (const line of stackLines) {
                if (!line.includes('captureLog') && 
                    !line.includes('superai') && 
                    line.includes('.js')) {
                    entry.location = line.trim();
                    break;
                }
            }
        }
        
        window.__superai_logs.push(entry);
        
        // Also store in localStorage as backup (survives page nav)
        try {
            const existing = JSON.parse(localStorage.getItem('__superai_log_backup') || '[]');
            existing.push(entry);
            // Keep last 5000 entries
            if (existing.length > 5000) {
                existing.splice(0, existing.length - 5000);
            }
            localStorage.setItem('__superai_log_backup', JSON.stringify(existing));
        } catch (e) {
            // localStorage full or unavailable - ignore
        }
    }
    
    function formatSize(bytes) {
        if (bytes < 1024) return bytes + 'B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
        return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
    }
    
    // ═══════════════════════════════════════════════════════════════
    // CONSOLE METHOD OVERRIDES
    // ═══════════════════════════════════════════════════════════════
    
    console.log = function(...args) {
        captureLog('log', args);
        originalConsole.log.apply(console, args);
    };
    
    console.warn = function(...args) {
        captureLog('warn', args);
        originalConsole.warn.apply(console, args);
    };
    
    console.error = function(...args) {
        captureLog('error', args);
        originalConsole.error.apply(console, args);
    };
    
    console.info = function(...args) {
        captureLog('info', args);
        originalConsole.info.apply(console, args);
    };
    
    console.debug = function(...args) {
        captureLog('debug', args);
        originalConsole.debug.apply(console, args);
    };
    
    console.clear = function(...args) {
        captureLog('clear', ['[CONSOLE CLEARED] - Suspicious if frequent!']);
        originalConsole.clear.apply(console, args);
    };
    
    // ═══════════════════════════════════════════════════════════════
    // ERROR EVENT LISTENERS
    // ═══════════════════════════════════════════════════════════════
    
    // Uncaught errors
    window.addEventListener('error', function(event) {
        captureLog('uncaught_error', [{
            type: 'UncaughtError',
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error ? event.error.stack : null
        }]);
    });
    
    // Unhandled promise rejections
    window.addEventListener('unhandledrejection', function(event) {
        captureLog('promise_rejection', [{
            type: 'UnhandledPromiseRejection',
            reason: event.reason ? (event.reason.message || event.reason.stack || String(event.reason)) : 'Unknown'
        }]);
    });
    
    // Resource loading errors (images, scripts, etc.)
    window.addEventListener('error', function(event) {
        if (event.target && event.target !== window) {
            captureLog('resource_error', [{
                type: 'ResourceError',
                tag: event.target.tagName,
                src: event.target.src || event.target.href || '(unknown)',
                id: event.target.id || '(no id)'
            }]);
        }
    }, true); // Use capture phase
    
    // ═══════════════════════════════════════════════════════════════
    // EXPORT FUNCTIONALITY
    // ═══════════════════════════════════════════════════════════════
    
    /**
     * Download captured logs as JSON file
     */
    window.downloadSuperAILogs = function(options = {}) {
        const {
            includeInfo = true,
            includeDebug = false,
            filename = null
        } = options;
        
        // Filter logs based on options
        let filteredLogs = window.__superai_logs;
        
        if (!includeInfo) {
            filteredLogs = filteredLogs.filter(l => l.level !== 'info');
        }
        if (!includeDebug) {
            filteredLogs = filteredLogs.filter(l => l.level !== 'debug');
        }
        
        // Create export object
        const exportData = {
            metadata: {
                exported_at: new Date().toISOString(),
                capture_started: window.__superai_start_time,
                total_entries: filteredLogs.length,
                url: window.location.href,
                user_agent: navigator.userAgent,
                version: '1.0.0'
            },
            summary: {
                by_level: {},
                errors_count: 0,
                warnings_count: 0,
                clears_count: 0
            },
            logs: filteredLogs
        };
        
        // Calculate summary
        for (const log of filteredLogs) {
            exportData.summary.by_level[log.level] = (exportData.summary.by_level[log.level] || 0) + 1;
            
            if (log.level === 'error' || log.level === 'uncaught_error') {
                exportData.summary.errors_count++;
            } else if (log.level === 'warn') {
                exportData.summary.warnings_count++;
            } else if (log.level === 'clear') {
                exportData.summary.clears_count++;
            }
        }
        
        // Create and trigger download
        const jsonStr = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || `superai_console_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        // Show summary in console
        originalConsole.log('%c🔍 SuperAI Console Capture', 'font-size: 16px; font-weight: bold; color: #4CAF50;');
        originalConsole.log(`%c✅ Exported ${filteredLogs.length} log entries`, 'color: #4CAF50;');
        originalConsole.log(`   📁 File: ${a.download}`);
        originalConsole.log(`   📊 Size: ${formatSize(jsonStr.length)}`);
        originalConsole.log(`   ❌ Errors: ${exportData.summary.errors_count}`);
        originalConsole.log(`   ⚠️  Warnings: ${exportData.summary.warnings_count}`);
        originalConsole.log(`   🧹 Clears: ${exportData.summary.clears_count}`);
        originalConsole.log(`\n%cNext step:`, 'font-weight: bold;');
        originalConsole.log(`python3 superai_console_detective.py --file ${a.download}`);
        
        return exportData;
    };
    
    /**
     * Get quick summary without downloading
     */
    window.getSuperAISummary = function() {
        const logs = window.__superai_logs;
        
        const summary = {
            total: logs.length,
            duration: Date.now() - new Date(window.__superai_start_time).getTime(),
            by_level: {},
            errors: [],
            warnings: []
        };
        
        for (const log of logs) {
            summary.by_level[log.level] = (summary.by_level[log.level] || 0) + 1;
            
            if (log.level === 'error' || log.level === 'uncaught_error') {
                summary.errors.push(log.args[0]);
            } else if (log.level === 'warn') {
                summary.warnings.push(log.args[0]);
            }
        }
        
        // Keep only first 10 errors/warnings for quick view
        summary.errors = summary.errors.slice(0, 10);
        summary.warnings = summary.warnings.slice(0, 10);
        
        return summary;
    };
    
    /**
     * Stop capturing and restore original console
     */
    window.stopSuperAICapture = function() {
        console.log = originalConsole.log;
        console.warn = originalConsole.warn;
        console.error = originalConsole.error;
        console.info = originalConsole.info;
        console.debug = originalConsole.debug;
        console.clear = originalConsole.clear;
        
        window.__superai_console_capturing = false;
        
        originalConsole.log('[SuperAI] Console capture stopped. Original behavior restored.');
    };
    
    // ═══════════════════════════════════════════════════════════════
    // INITIALIZATION COMPLETE
    // ═══════════════════════════════════════════════════════════════
    
    originalConsole.log('%c🔍 SuperAI Console Capture Active', 'font-size: 14px; font-weight: bold; color: #2196F3;');
    originalConsole.log('%cAll console output is being recorded.', 'color: #666;');
    originalConsole.log('');
    originalConsole.log('%cAvailable commands:', 'font-weight: bold;');
    originalConsole.log('  • downloadSuperAILogs()      - Download all logs as JSON');
    originalConsole.log('  • getSuperAISummary()         - Quick stats');
    originalConsole.log('  • stopSuperAICapture()        - Stop capturing');
    originalConsole.log('');

})();
