/**
 * @supremeai/shared-services/vscode — VS Code platform adapter entry point.
 *
 * শুধুমাত্র VS Code extension এই এন্ট্রি ব্যবহার করবে। এটি `vscode` মডিউল
 * import করে, তাই browser/Electron renderer কোড থেকে এই এন্ট্রি import করা যাবে না।
 */

export * from '../index';
export * from '../platform/vscode';