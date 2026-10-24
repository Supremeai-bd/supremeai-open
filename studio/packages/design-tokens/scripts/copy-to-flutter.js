const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, '../outputs/tokens.dart');
const destPath = path.join(__dirname, '../../../apps/mobile/lib/theme/tokens.dart');

try {
    if (fs.existsSync(srcPath)) {
        // Ensure destination directory exists
        const destDir = path.dirname(destPath);
        if (!fs.existsSync(destDir)) {
            fs.mkdirSync(destDir, { recursive: true });
        }

        fs.copyFileSync(srcPath, destPath);
        console.log(`✅ Successfully copied tokens.dart to apps/mobile/lib/theme/`);
    } else {
        console.error(`❌ Source file not found: ${srcPath}`);
    }
} catch (err) {
    console.error(`❌ Error copying tokens.dart:`, err);
}
