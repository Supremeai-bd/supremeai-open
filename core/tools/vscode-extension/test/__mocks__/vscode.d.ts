export declare const window: {
    showInformationMessage: any;
    showErrorMessage: any;
    showWarningMessage: any;
    createWebviewPanel: any;
    activeTextEditor: undefined;
    visibleTextEditors: never[];
};
export declare const workspace: {
    getConfiguration: any;
    onDidChangeTextDocument: any;
    onDidSaveTextDocument: any;
};
export declare const commands: {
    executeCommand: any;
    registerCommand: any;
};
export declare const authentication: {
    getSession: any;
};
export declare class Range {
    start: any;
    end: any;
    constructor(start: any, end: any);
}
export declare class Position {
    line: number;
    character: number;
    constructor(line: number, character: number);
}
export declare class Selection {
    anchor: any;
    active: any;
    constructor(anchor: any, active: any);
}
export declare const ExtensionContext: any;
