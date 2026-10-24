import * as vscode from 'vscode';

export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3,
    SILENT = 4
}

interface LogContext {
    [key: string]: any;
}

export class Logger {
    private static instance: Logger;
    private outputChannel: vscode.OutputChannel;
    private logLevel: LogLevel;
    
    // Patterns for redacting sensitive data
    private readonly redactPatterns = [
        /(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+/gi, // Bearer tokens
        /(api_key=)[A-Za-z0-9\-\._~\+\/]+/gi,  // API keys
        /([A-Za-z0-9_]*password[A-Za-z0-9_]*\s*[:=]\s*)['"]?[^'"\s]+['"]?/gi, // Passwords
        /([A-Za-z0-9_]*token[A-Za-z0-9_]*\s*[:=]\s*)['"]?[^'"\s]+['"]?/gi // Tokens
    ];

    private constructor() {
        this.outputChannel = vscode.window.createOutputChannel('SupremeAI');
        // Environment Aware: VERBOSE in dev, INFO in prod
        const isDev = process.env.NODE_ENV === 'development' || !process.env.NODE_ENV;
        this.logLevel = isDev ? LogLevel.DEBUG : LogLevel.INFO;
    }

    public static getInstance(): Logger {
        if (!Logger.instance) {
            Logger.instance = new Logger();
        }
        return Logger.instance;
    }

    public setLogLevel(level: LogLevel) {
        this.logLevel = level;
    }

    public debug(module: string, message: string, context?: LogContext) {
        if (this.logLevel <= LogLevel.DEBUG) {
            this.log(LogLevel.DEBUG, module, message, context);
        }
    }

    public info(module: string, message: string, context?: LogContext) {
        if (this.logLevel <= LogLevel.INFO) {
            this.log(LogLevel.INFO, module, message, context);
        }
    }

    public warn(module: string, message: string, context?: LogContext) {
        if (this.logLevel <= LogLevel.WARN) {
            this.log(LogLevel.WARN, module, message, context);
        }
    }

    public error(module: string, message: string, error?: any, context?: LogContext) {
        if (this.logLevel <= LogLevel.ERROR) {
            const errorContext = { ...context, error: error?.message || error };
            this.log(LogLevel.ERROR, module, message, errorContext);
            
            // Telemetry Integration placeholder
            this.sendToTelemetry(module, message, error);
        }
    }

    private log(level: LogLevel, module: string, message: string, context?: LogContext) {
        const timestamp = new Date().toISOString();
        const levelName = LogLevel[level];
        let contextStr = '';
        
        if (context) {
            try {
                // Redact context
                const safeContext = this.redactObject(context);
                contextStr = ` ${JSON.stringify(safeContext)}`;
            } catch (e) {
                contextStr = ' [Context serialization failed]';
            }
        }

        const safeMessage = this.redactString(message);
        const logEntry = `[SupremeAI] ${timestamp} [${module}] [${levelName}] ${safeMessage}${contextStr}`;
        
        // Log to Output Channel
        this.outputChannel.appendLine(logEntry);
        
        // Log to console in development
        if (this.logLevel === LogLevel.DEBUG) {
            switch (level) {
                case LogLevel.ERROR: console.error(logEntry); break;
                case LogLevel.WARN: console.warn(logEntry); break;
                default: console.log(logEntry); break;
            }
        }
    }

    private sendToTelemetry(module: string, message: string, error?: any) {
        // Send to TelemetryTracker placeholder
        // In a real implementation this would call TelemetryTracker.getInstance().trackError()
    }

    private redactString(str: string): string {
        let safeStr = str;
        for (const pattern of this.redactPatterns) {
            safeStr = safeStr.replace(pattern, '$1[REDACTED]');
        }
        return safeStr;
    }

    private redactObject(obj: any): any {
        if (typeof obj !== 'object' || obj === null) return obj;
        if (Array.isArray(obj)) return obj.map(item => this.redactObject(item));
        
        const safeObj: any = {};
        for (const [key, value] of Object.entries(obj)) {
            const lowerKey = key.toLowerCase();
            if (lowerKey.includes('password') || lowerKey.includes('token') || lowerKey.includes('key') || lowerKey.includes('secret')) {
                safeObj[key] = '[REDACTED]';
            } else if (typeof value === 'string') {
                safeObj[key] = this.redactString(value);
            } else if (typeof value === 'object') {
                safeObj[key] = this.redactObject(value);
            } else {
                safeObj[key] = value;
            }
        }
        return safeObj;
    }
}

// Module-specific logger factory
export function createLogger(moduleName: string) {
    const logger = Logger.getInstance();
    return {
        debug: (message: string, context?: LogContext) => logger.debug(moduleName, message, context),
        info: (message: string, context?: LogContext) => logger.info(moduleName, message, context),
        warn: (message: string, context?: LogContext) => logger.warn(moduleName, message, context),
        error: (message: string, error?: any, context?: LogContext) => logger.error(moduleName, message, error, context)
    };
}
