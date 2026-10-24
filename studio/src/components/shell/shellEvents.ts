// SupremeAI — Shell event contracts (single-frontend migration)
// বাংলা মন্তব্য: shell-এর ভেতরের component গুলো একে অপরকে window event দিয়ে ডাকে;
// নামগুলো এক জায়গায় রাখা হলো যাতে duplicate/string-drift না হয়।

/** বাংলা: global CommandBar (App.tsx-এ একবারই মাউন্ট করা) এই event শুনে খোলে। */
export const PANEL_OPEN_EVENT = 'supremeai-open-command-palette';
