// tools/vscode-extension/test/__mocks__/vscode.ts
// Type-safe VS Code Mock Engine to eliminate dead-code and false positives.

export class Position {
    constructor(public readonly line: number, public readonly character: number) {}

    isBefore(other: Position): boolean {
        if (this.line < other.line) return true;
        if (this.line > other.line) return false;
        return this.character < other.character;
    }

    isAfter(other: Position): boolean {
        if (this.line > other.line) return true;
        if (this.line < other.line) return false;
        return this.character > other.character;
    }

    isEqual(other: Position): boolean {
        return this.line === other.line && this.character === other.character;
    }
}

export class Range {
    public readonly start: Position;
    public readonly end: Position;

    constructor(start: Position, end: Position);
    constructor(startLine: number, startCharacter: number, endLine: number, endCharacter: number);
    constructor(startOrLine: Position | number, endOrChar: Position | number, endLine?: number, endCharacter?: number) {
        if (typeof startOrLine === "number" && typeof endOrChar === "number" && typeof endLine === "number" && typeof endCharacter === "number") {
            this.start = new Position(startOrLine, endOrChar);
            this.end = new Position(endLine, endCharacter);
        } else if (startOrLine instanceof Position && endOrChar instanceof Position) {
            this.start = startOrLine;
            this.end = endOrChar;
        } else {
            throw new Error("Invalid Range constructor parameters");
        }
    }

    get isEmpty(): boolean {
        return this.start.isEqual(this.end);
    }
}

export class Selection extends Range {
    public readonly anchor: Position;
    public readonly active: Position;

    constructor(anchor: Position, active: Position) {
        super(anchor, active);
        this.anchor = anchor;
        this.active = active;
    }

    get isReversed(): boolean {
        return this.active.isBefore(this.anchor);
    }
}

// ⚡ Active Functional Namespaces using Jest Spies with proper type structures
export const window = {
    showInformationMessage: vi.fn().mockResolvedValue(undefined),
    showErrorMessage: vi.fn().mockResolvedValue(undefined),
    showWarningMessage: vi.fn().mockResolvedValue(undefined),
    activeTextEditor: undefined,
    visibleTextEditors: [],
    createStatusBarItem: vi.fn().mockReturnValue({
        command: undefined,
        text: "",
        show: vi.fn(),
        hide: vi.fn(),
        dispose: vi.fn()
    })
};

export const workspace = {
    getConfiguration: vi.fn().mockReturnValue({
        get: vi.fn(),
        update: vi.fn(),
        has: vi.fn()
    }),
    textDocuments: [],
    onDidChangeTextDocument: vi.fn().mockReturnValue({ dispose: vi.fn() }),
    onDidSaveTextDocument: vi.fn().mockReturnValue({ dispose: vi.fn() })
};

export const commands = {
    registerCommand: vi.fn().mockReturnValue({ dispose: vi.fn() }),
    executeCommand: vi.fn().mockResolvedValue(undefined)
};

export enum StatusBarAlignment {
    Left = 1,
    Right = 2
}

export enum OverviewRulerLane {
    Left = 1,
    Center = 2,
    Right = 4,
    Full = 7
}

export const ExtensionContext = vi.fn().mockImplementation(() => ({
    subscriptions: [],
    workspaceState: { get: vi.fn(), update: vi.fn() },
    globalState: { get: vi.fn(), update: vi.fn(), setKeysForSync: vi.fn() },
    extensionPath: "/mock/extension/path",
    storagePath: "/mock/storage/path",
    globalStoragePath: "/mock/global/storage/path",
    logPath: "/mock/log/path"
}));
